import asyncio
import random
import time
from typing import Optional, Set

from pyrogram import filters
from pyrogram.types import Message, MessageEntity
from pyrogram.enums import ChatMemberStatus
from VIPMUSIC import app
from config import BANNED_USERS, MENTION_USERNAMES, START_REACTIONS, OWNER_ID
from VIPMUSIC.utils.database import mongodb, get_sudoers

# =================== DATABASE COLLECTION ===================
COLLECTION = mongodb["reaction_mentions"]

# =================== CACHE ===================
custom_mentions: Set[str] = set(x.lower().lstrip("@") for x in MENTION_USERNAMES)
admin_cache = {}  # chat_id -> {"admins": set(user_ids), "time": float}
ADMIN_CACHE_TTL = 600  # seconds


# =================== LOAD CUSTOM MENTIONS ===================
async def load_custom_mentions():
    try:
        docs = await COLLECTION.find().to_list(None)
        for doc in docs:
            custom_mentions.add(doc["name"].lower().lstrip("@"))
        print(f"[Reaction Manager] Loaded {len(custom_mentions)} mention triggers.")
    except Exception as e:
        print(f"[Reaction Manager] Error loading mentions from DB: {e}")


# schedule loading on startup
asyncio.get_event_loop().create_task(load_custom_mentions())


# =================== ADMIN CACHE HELPERS ===================
async def fetch_admins(client, chat_id: int) -> Set[int]:
    """Fetch admin IDs from Telegram and cache them."""
    admins = set()
    try:
        async for memb in client.get_chat_members(chat_id, filter="administrators"):
            # member.user may be present
            if memb and getattr(memb, "user", None):
                admins.add(memb.user.id)
    except Exception as e:
        print(f"[fetch_admins] failed to fetch admins for {chat_id}: {e}")
    admin_cache[chat_id] = {"admins": admins, "time": time.time()}
    return admins


async def get_cached_admins(client, chat_id: int) -> Set[int]:
    """Return cached admins if fresh, else fetch new."""
    now = time.time()
    info = admin_cache.get(chat_id)
    if info and (now - info.get("time", 0)) < ADMIN_CACHE_TTL:
        return info.get("admins", set())
    return await fetch_admins(client, chat_id)


# =================== PERMISSION CHECK ===================
async def is_admin_or_sudo(client, message: Message) -> bool:
    """
    Robust admin check:
    1. Owner or sudo
    2. Direct get_chat_member() check (best)
    3. Check cached admin list
    4. Fetch admin list fallback
    """
    # protect against messages without from_user (rare)
    if not message.from_user:
        return False

    user_id = message.from_user.id
    chat = message.chat
    chat_id = chat.id

    # 1) Owner or sudoers bypass
    try:
        sudoers = await get_sudoers()
    except Exception as e:
        print(f"[is_admin_or_sudo] get_sudoers error: {e}")
        sudoers = set()

    if user_id == OWNER_ID or user_id in sudoers:
        return True

    # Only valid in groups/supergroups
    if chat.type not in ("group", "supergroup"):
        return False

    # 2) Direct get_chat_member() — preferred
    try:
        member = await client.get_chat_member(chat_id, user_id)
        status = getattr(member, "status", None)
        if status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            # update cache
            admins = await get_cached_admins(client, chat_id)
            admins.add(user_id)
            admin_cache[chat_id] = {"admins": admins, "time": time.time()}
            return True
    except Exception as e:
        # Often fails if bot lacks rights; keep going to fallback
        print(f"[is_admin_or_sudo] get_chat_member error for {user_id} in {chat_id}: {e}")

    # 3) Check cached admin list
    try:
        cached = await get_cached_admins(client, chat_id)
        if user_id in cached:
            return True
    except Exception as e:
        print(f"[is_admin_or_sudo] cached admin check error: {e}")

    # 4) Fetch admin list as final fallback
    try:
        fetched = await fetch_admins(client, chat_id)
        if user_id in fetched:
            return True
    except Exception as e:
        print(f"[is_admin_or_sudo] fetch_admins final fallback error: {e}")

    # Not admin / not sudo / not owner
    return False


# =================== COMMAND: /addreact ===================
@app.on_message(filters.command("addreact") & ~BANNED_USERS)
async def add_reaction_name(client, message: Message):
    """Add a username or keyword to the reaction list."""
    if not await is_admin_or_sudo(client, message):
        return await message.reply_text("⚠️ Only admins or sudo users can add reaction names.", quote=True)

    if len(message.command) < 2:
        return await message.reply_text("Usage: `/addreact <keyword_or_username>`", quote=True)

    name_to_add = message.text.split(None, 1)[1].strip().lower().lstrip("@")
    if not name_to_add:
        return await message.reply_text("Usage: `/addreact <keyword_or_username>`", quote=True)

    if name_to_add in custom_mentions:
        return await message.reply_text(f"✅ `{name_to_add}` is already in the mention list!", quote=True)

    try:
        await COLLECTION.insert_one({"name": name_to_add})
    except Exception as e:
        print(f"[add_reaction_name] DB insert error: {e}")
        # still add to local cache for immediate effect
    custom_mentions.add(name_to_add)
    await message.reply_text(f"✨ Added `{name_to_add}` to the mention reaction list.", quote=True)


# =================== COMMAND: /reactlist (Everyone) ===================
@app.on_message(filters.command("reactlist") & ~BANNED_USERS)
async def list_reactions(client, message: Message):
    """Show all active reaction trigger names."""
    if not custom_mentions:
        return await message.reply_text("ℹ️ No mention triggers found yet.", quote=True)

    msg = "**🧠 Reaction Trigger List:**\n"
    msg += "\n".join([f"• `{x}`" for x in sorted(custom_mentions)])
    await message.reply_text(msg, quote=True)


# =================== COMMAND: /delreact ===================
@app.on_message(filters.command("delreact") & ~BANNED_USERS)
async def delete_reaction_name(client, message: Message):
    """Remove a reaction trigger."""
    if not await is_admin_or_sudo(client, message):
        return await message.reply_text("⚠️ Only admins or sudo users can delete reaction names.", quote=True)

    if len(message.command) < 2:
        return await message.reply_text("Usage: `/delreact <keyword_or_username>`", quote=True)

    name_to_del = message.text.split(None, 1)[1].strip().lower().lstrip("@")
    if not name_to_del:
        return await message.reply_text("Usage: `/delreact <keyword_or_username>`", quote=True)

    if name_to_del not in custom_mentions:
        return await message.reply_text(f"❌ `{name_to_del}` not found in mention list.", quote=True)

    try:
        await COLLECTION.delete_one({"name": name_to_del})
    except Exception as e:
        print(f"[delete_reaction_name] DB delete error: {e}")
    custom_mentions.discard(name_to_del)
    await message.reply_text(f"🗑 Removed `{name_to_del}` from mention list.", quote=True)


# =================== COMMAND: /clearreact ===================
@app.on_message(filters.command("clearreact") & ~BANNED_USERS)
async def clear_reactions(client, message: Message):
    """Clear all reaction triggers."""
    if not await is_admin_or_sudo(client, message):
        return await message.reply_text("⚠️ Only admins or sudo users can clear reactions.", quote=True)

    try:
        await COLLECTION.delete_many({})
    except Exception as e:
        print(f"[clear_reactions] DB clear error: {e}")
    custom_mentions.clear()
    await message.reply_text("🧹 Cleared all custom reaction mentions.", quote=True)


# =================== HELPERS: PARSE ENTITIES & TEXT ===================
def extract_mentioned_usernames_from_entities(message: Message) -> Set[str]:
    """
    Parse 'mention' and 'text_mention' entities from message.text or message.caption.
    Returns set of usernames without the leading '@', lowercased.
    """
    usernames = set()
    # choose the right text source (text for text messages, caption for media)
    text_source = message.text or message.caption or ""
    entities = (message.entities or []) + (message.caption_entities or [])
    for ent in entities:
        try:
            if ent.type == "mention":  # @username in text
                # safe slice
                start = ent.offset
                end = ent.offset + ent.length
                uname = text_source[start:end].lstrip("@").lower()
                if uname:
                    usernames.add(uname)
            elif ent.type == "text_mention":  # user without @, entity.user present
                if getattr(ent, "user", None) and getattr(ent.user, "username", None):
                    usernames.add(ent.user.username.lower())
        except Exception:
            # ignore entity parse errors and continue
            continue
    return usernames


def build_full_text(message: Message) -> str:
    """Return combined text+caption lowercased for keyword matching."""
    parts = []
    if message.text:
        parts.append(message.text.lower())
    if message.caption:
        parts.append(message.caption.lower())
    return " ".join(parts)


# =================== REACT ON MENTION (text, caption, entities) ===================
@app.on_message((filters.text | filters.caption) & ~BANNED_USERS)
async def react_on_mentions(client, message: Message):
    """
    Automatically react when:
      - any trigger keyword exists in text or caption
      - any @username or text_mention matches a trigger username
    """
    text_combined = build_full_text(message)
    mentioned_usernames = extract_mentioned_usernames_from_entities(message)

    try:
        # 1) check username mentions first (explicit @username)
        for uname in mentioned_usernames:
            if uname in custom_mentions:
                emoji = random.choice(START_REACTIONS)
                await message.react(emoji)
                return

        # 2) check plain keywords anywhere in text/caption
        # iterate triggers and stop on first match
        for trigger in custom_mentions:
            if trigger and trigger in text_combined:
                emoji = random.choice(START_REACTIONS)
                await message.react(emoji)
                return

    except Exception as e:
        # keep bot stable; log to console
        print(f"[react_on_mentions] Error reacting: {e}")
        return
