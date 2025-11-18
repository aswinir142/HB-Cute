# VIPMUSIC/plugins/admins/reaction.py
"""
Reaction manager:
- /addreact, /delreact, /reactlist, /clearreact
- Reacts to mentions / keywords (does NOT run on commands)
"""

import asyncio
import random
from typing import Set, Dict, Optional, Tuple

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus, ChatType
from VIPMUSIC import app
from config import BANNED_USERS, MENTION_USERNAMES, START_REACTIONS, OWNER_ID
from VIPMUSIC.utils.database import mongodb, get_sudoers

print("[reaction] addreact, delreact, reactlist, clearreact")

# ---------------- DATABASE ----------------
COLLECTION = mongodb["reaction_mentions"]

# ---------------- CACHE ----------------
# normalize mention list from config
custom_mentions: Set[str] = set(x.lower().lstrip("@") for x in (MENTION_USERNAMES or []))

# ---------------- VALID TELEGRAM REACTIONS ONLY ----------------
VALID_REACTIONS = {
    "👍", "👎", "❤️", "🔥", "👏",
    "😁", "🤔", "😢", "🤯", "😍",
    "🤬", "😱", "🎉", "🤩", "🙏"
}

SAFE_REACTIONS = list(VALID_REACTIONS)

# ---------------- PER-CHAT EMOJI ROTATION ----------------
chat_used_reactions: Dict[int, Set[str]] = {}


def next_emoji(chat_id: int) -> str:
    """
    Choose a per-chat rotating emoji from SAFE_REACTIONS.
    Reset when exhausted.
    """
    if chat_id not in chat_used_reactions:
        chat_used_reactions[chat_id] = set()

    used = chat_used_reactions[chat_id]
    if len(used) >= len(SAFE_REACTIONS):
        used.clear()

    remaining = [e for e in SAFE_REACTIONS if e not in used]
    emoji = random.choice(remaining)
    used.add(emoji)
    chat_used_reactions[chat_id] = used
    return emoji


# ---------------- LOAD ON STARTUP ----------------
async def load_custom_mentions():
    try:
        docs = await COLLECTION.find({}).to_list(length=None)
        loaded = 0
        for doc in docs:
            name = doc.get("name")
            if name:
                custom_mentions.add(str(name).lower().lstrip("@"))
                loaded += 1
        print(f"[Reaction Manager] Loaded {loaded} triggers from DB.")
    except Exception as e:
        print(f"[Reaction Manager] DB load error: {e}")


# schedule loader on startup
asyncio.get_event_loop().create_task(load_custom_mentions())


# ---------------- ADMIN CHECK ----------------
async def is_admin_or_sudo(client, message: Message) -> Tuple[bool, Optional[str]]:
    """
    Returns (True, None) if the sender is owner, sudoer, or chat admin.
    Otherwise (False, debug_reason).
    """
    user_id = getattr(message.from_user, "id", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    chat_type = getattr(chat, "type", None)

    try:
        sudoers = await get_sudoers()
    except Exception:
        sudoers = set()

    # Owner or sudoers bypass
    if user_id and (user_id == OWNER_ID or user_id in sudoers):
        return True, None

    # If the message came from a sender_chat (channel as sender), allow if it's the linked chat
    sender_chat = getattr(message, "sender_chat", None)
    if sender_chat:
        try:
            chat_obj = await client.get_chat(chat_id)
            if getattr(chat_obj, "linked_chat_id", None) == sender_chat.id:
                return True, None
        except Exception:
            pass

    # For private chats, only owner/sudoers allowed
    if chat_type not in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
        return False, f"chat_type={chat_type}"

    if not user_id:
        return False, "no from_user and not linked"

    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            return True, None
        else:
            return False, f"user_status={member.status}"
    except Exception as e:
        return False, f"get_chat_member_error={e}"


# ---------------- /addreact ----------------
@app.on_message(filters.command("addreact") & ~BANNED_USERS)
async def add_reaction_name(client, message: Message):
    ok, debug = await is_admin_or_sudo(client, message)
    if not ok:
        return await message.reply_text(
            f"⚠️ Only admins or sudo users can add reaction triggers.\n\nDebug: `{debug}`"
        )

    if len(message.command) < 2:
        return await message.reply_text("Usage: `/addreact <keyword_or_username>`")

    raw = message.text.split(None, 1)[1].strip()
    name = raw.lower().lstrip("@")

    # Avoid duplicates in DB and cache
    if name in custom_mentions:
        return await message.reply_text(f"ℹ️ `{name}` is already a trigger.")

    resolved_id = None
    try:
        user = await client.get_users(name)
        if getattr(user, "id", None):
            resolved_id = user.id
    except Exception:
        # ignore resolution errors: user might be a keyword not a username
        pass

    # insert keyword
    try:
        await COLLECTION.update_one({"name": name}, {"$setOnInsert": {"name": name}}, upsert=True)
        custom_mentions.add(name)
    except Exception as e:
        return await message.reply_text(f"❌ DB error while adding `{name}`: `{e}`")

    # if username resolved to id, also store id:NNN
    if resolved_id:
        id_key = f"id:{resolved_id}"
        if id_key not in custom_mentions:
            try:
                await COLLECTION.update_one({"name": id_key}, {"$setOnInsert": {"name": id_key}}, upsert=True)
                custom_mentions.add(id_key)
            except Exception as e:
                # not fatal, still inform user
                await message.reply_text(f"⚠️ Added name but failed to add id key: `{e}`")

    msg = f"✨ Added `{name}`"
    if resolved_id:
        msg += f" (id: `{resolved_id}`)"

    await message.reply_text(msg)


# ---------------- /delreact ----------------
@app.on_message(filters.command("delreact") & ~BANNED_USERS)
async def delete_reaction_name(client, message: Message):
    ok, debug = await is_admin_or_sudo(client, message)
    if not ok:
        return await message.reply_text(
            f"⚠️ Only admins or sudo users can delete reaction triggers.\n\nDebug: `{debug}`"
        )

    if len(message.command) < 2:
        return await message.reply_text("Usage: `/delreact <keyword_or_username>`")

    raw = message.text.split(None, 1)[1].strip().lower().lstrip("@")
    removed = False

    # delete keyword
    try:
        if raw in custom_mentions:
            custom_mentions.remove(raw)
            await COLLECTION.delete_one({"name": raw})
            removed = True
    except Exception as e:
        return await message.reply_text(f"❌ Error removing `{raw}`: `{e}`")

    # attempt to resolve username to id and remove id:NNN if present
    try:
        user = await client.get_users(raw)
        if getattr(user, "id", None):
            id_key = f"id:{user.id}"
            if id_key in custom_mentions:
                custom_mentions.remove(id_key)
                await COLLECTION.delete_one({"name": id_key})
                removed = True
    except Exception:
        # ignore resolution errors
        pass

    if removed:
        return await message.reply_text(f"🗑 Removed `{raw}`.")
    else:
        return await message.reply_text(f"❌ `{raw}` not found.")


# ---------------- /reactlist ----------------
@app.on_message(filters.command("reactlist") & ~BANNED_USERS)
async def list_reactions(client, message: Message):
    if not custom_mentions:
        return await message.reply_text("ℹ️ No triggers found.")

    text = "\n".join(f"• `{m}`" for m in sorted(custom_mentions))
    await message.reply_text(f"**🧠 Reaction Triggers:**\n{text}")


# ---------------- /clearreact ----------------
@app.on_message(filters.command("clearreact") & ~BANNED_USERS)
async def clear_reactions(client, message: Message):
    ok, debug = await is_admin_or_sudo(client, message)
    if not ok:
        return await message.reply_text(
            f"⚠️ Only admins or sudo users can clear reactions.\n\nDebug: `{debug}`"
        )

    try:
        await COLLECTION.delete_many({})
        custom_mentions.clear()
        await message.reply_text("🧹 Cleared all reaction triggers.")
    except Exception as e:
        await message.reply_text(f"❌ Failed to clear triggers: `{e}`")


# ---------------- REACT ON MENTIONS (STRICT MODE) ----------------
@app.on_message(
    (filters.text | filters.caption)
    & ~filters.command()    # IMPORTANT: do NOT run on commands (Option A)
    & ~BANNED_USERS
)
async def react_on_mentions(client, message: Message):
    try:
        # text_raw used for prefix checks (commands etc.)
        text_raw = message.text or message.caption or ""
        if not text_raw:
            return

        # Optional: ignore other command-like prefixes (also safe-guard)
        if text_raw.startswith(("/", "!", "$", ".", "#")):
            # definitely not reacting to command-like messages in Option A
            return

        chat_id = message.chat.id
        text = text_raw.lower()

        # Split into words (basic tokenization). Keep the '@' as separate token where present.
        words = set(text.replace("@", " @").split())

        # Collect mentions from message entities (explicit mentions)
        entities = (message.entities or []) + (message.caption_entities or [])
        mentioned_usernames = set()
        mentioned_ids = set()

        for ent in entities:
            try:
                if ent.type == "mention":
                    source = (message.text or message.caption) or ""
                    uname = source[ent.offset : ent.offset + ent.length]
                    mentioned_usernames.add(uname.lstrip("@").lower())
                elif ent.type == "text_mention" and ent.user:
                    mentioned_ids.add(ent.user.id)
                    if ent.user.username:
                        mentioned_usernames.add(ent.user.username.lower())
            except Exception:
                # ignore entity parsing errors for safety
                continue

        # Username triggers (explicit mention)
        for uname in mentioned_usernames:
            if uname in custom_mentions:
                return await message.react(next_emoji(chat_id))

        # ID triggers (explicit text_mention)
        for uid in mentioned_ids:
            if f"id:{uid}" in custom_mentions:
                return await message.react(next_emoji(chat_id))

        # Keyword triggers (words or @keyword)
        for trig in custom_mentions:
            if trig.startswith("id:"):
                continue
            if trig in words or f"@{trig}" in words:
                return await message.react(next_emoji(chat_id))

    except Exception as e:
        # keep the bot alive; print error for debugging
        print(f"[react_on_mentions] error: {e}")
