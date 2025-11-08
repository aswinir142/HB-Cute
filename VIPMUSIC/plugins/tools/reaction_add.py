import asyncio
import random
from pyrogram import filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus
from VIPMUSIC import app
from config import BANNED_USERS, MENTION_USERNAMES, START_REACTIONS, OWNER_ID
from VIPMUSIC.utils.database import mongodb, get_sudoers

# --- DB COLLECTION ---
COLLECTION = mongodb["reaction_mentions"]

# --- CACHE ---
custom_mentions = set(x.lower().lstrip("@") for x in MENTION_USERNAMES)


# =================== LOAD CUSTOM MENTIONS ===================
async def load_custom_mentions():
    docs = await COLLECTION.find().to_list(None)
    for doc in docs:
        custom_mentions.add(doc["name"].lower().lstrip("@"))
    print(f"[Reaction Manager] Loaded {len(custom_mentions)} mention triggers.")


asyncio.get_event_loop().create_task(load_custom_mentions())


# =================== ADMIN CHECK (FINAL FIXED) ===================
async def is_admin_or_sudo(client, message: Message) -> bool:
    """Reliable admin/sudo/owner check — handles linked channels & bot permissions."""

    if not message.from_user:
        return False

    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type

    # --- SUDO or OWNER bypass ---
    try:
        sudoers = await get_sudoers()
    except Exception:
        sudoers = set()
    if user_id == OWNER_ID or user_id in sudoers:
        return True

    # --- Skip for private chats ---
    if chat_type not in ("group", "supergroup"):
        return False

    # --- First try direct get_chat_member ---
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            return True
    except Exception as e:
        print(f"[AdminCheck] get_chat_member failed: {e}")

    # --- Fallback: fetch full admin list ---
    try:
        admin_ids = set()
        async for admin in client.get_chat_members(chat_id, filter="administrators"):
            if admin and admin.user:
                admin_ids.add(admin.user.id)
        if user_id in admin_ids:
            return True
    except Exception as e:
        print(f"[AdminCheck] fallback admin list fetch error: {e}")

    # --- Linked Channel Workaround ---
    # If the group is linked to a channel, get_chat_member may fail.
    # We check if the group has a linked_chat_id and if the user is an admin in that channel.
    try:
        chat = await client.get_chat(chat_id)
        if getattr(chat, "linked_chat", None):
            linked_id = chat.linked_chat.id
            try:
                linked_member = await client.get_chat_member(linked_id, user_id)
                if linked_member.status in (
                    ChatMemberStatus.ADMINISTRATOR,
                    ChatMemberStatus.OWNER,
                ):
                    return True
            except Exception as e:
                print(f"[AdminCheck] linked channel check failed: {e}")
    except Exception as e:
        print(f"[AdminCheck] get_chat linked check failed: {e}")

    return False


# =================== COMMAND: /addreact ===================
@app.on_message(filters.command("addreact") & ~BANNED_USERS)
async def add_reaction_name(client, message: Message):
    """Add a username or keyword to the reaction list."""
    if not await is_admin_or_sudo(client, message):
        return await message.reply_text("⚠️ Only admins or sudo users can add reaction names.")

    if len(message.command) < 2:
        return await message.reply_text("Usage: `/addreact <keyword_or_username>`", quote=True)

    name = message.text.split(None, 1)[1].strip().lower().lstrip("@")

    if name in custom_mentions:
        return await message.reply_text(f"✅ `{name}` is already in the mention list!")

    await COLLECTION.insert_one({"name": name})
    custom_mentions.add(name)
    await message.reply_text(f"✨ Added `{name}` to mention reaction list.")


# =================== COMMAND: /delreact ===================
@app.on_message(filters.command("delreact") & ~BANNED_USERS)
async def delete_reaction_name(client, message: Message):
    """Remove a reaction trigger."""
    if not await is_admin_or_sudo(client, message):
        return await message.reply_text("⚠️ Only admins or sudo users can delete reaction names.")

    if len(message.command) < 2:
        return await message.reply_text("Usage: `/delreact <keyword_or_username>`")

    name = message.text.split(None, 1)[1].strip().lower().lstrip("@")

    if name not in custom_mentions:
        return await message.reply_text(f"❌ `{name}` not found in mention list.")

    await COLLECTION.delete_one({"name": name})
    custom_mentions.remove(name)
    await message.reply_text(f"🗑 Removed `{name}` from mention list.")


# =================== COMMAND: /clearreact ===================
@app.on_message(filters.command("clearreact") & ~BANNED_USERS)
async def clear_reactions(client, message: Message):
    """Clear all reaction triggers."""
    if not await is_admin_or_sudo(client, message):
        return await message.reply_text("⚠️ Only admins or sudo users can clear reactions.")

    await COLLECTION.delete_many({})
    custom_mentions.clear()
    await message.reply_text("🧹 Cleared all custom reaction mentions.")


# =================== COMMAND: /reactlist ===================
@app.on_message(filters.command("reactlist") & ~BANNED_USERS)
async def list_reactions(client, message: Message):
    """Show all active reaction trigger names."""
    if not custom_mentions:
        return await message.reply_text("ℹ️ No mention triggers found.")
    msg = "**🧠 Reaction Trigger List:**\n" + "\n".join(f"• `{x}`" for x in sorted(custom_mentions))
    await message.reply_text(msg)


# =================== REACT ON MENTION ===================
@app.on_message(filters.text | filters.caption & ~BANNED_USERS)
async def react_on_mentions(client, message: Message):
    """Automatically react when a trigger name or @username appears."""

    text = (message.text or message.caption or "").lower()
    entities = (message.entities or []) + (message.caption_entities or [])

    # Collect usernames from @mentions and text_mentions
    mentioned_users = set()
    for ent in entities:
        if ent.type == "mention":
            username = (message.text or message.caption)[ent.offset : ent.offset + ent.length]
            mentioned_users.add(username.lower().lstrip("@"))
        elif ent.type == "text_mention" and getattr(ent.user, "username", None):
            mentioned_users.add(ent.user.username.lower())

    try:
        for name in custom_mentions:
            if name in text or name in mentioned_users:
                emoji = random.choice(START_REACTIONS)
                await message.react(emoji)
                return
    except Exception as e:
        print(f"[mention_react] Error: {e}")
        pass
