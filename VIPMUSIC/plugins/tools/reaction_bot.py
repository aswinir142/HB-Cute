# VIPMUSIC/plugins/tools/reaction_bot.py
import asyncio
import random
from typing import Set, Tuple, Optional, Dict, Any
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus
from VIPMUSIC import app
from config import (
    BANNED_USERS,
    MENTION_USERNAMES,
    START_REACTIONS,
    OWNER_ID,
    REACTION_BOT,
)
from VIPMUSIC.utils.database import mongodb, get_sudoers

# ---------------- DATABASE ----------------
COLLECTION_MENTIONS = mongodb["reaction_mentions"]
COLLECTION_STATUS = mongodb["reaction_status"]

# ---------------- CACHE ----------------
custom_mentions: Set[str] = set(x.lower().lstrip("@") for x in MENTION_USERNAMES)

# ---------------- VALID REACTION EMOJIS ----------------
VALID_REACTIONS = {
    "❤️", "💖", "💘", "💞", "💓", "✨", "🔥", "💫",
    "💥", "🌸", "😍", "🥰", "💎", "🌙", "🌹", "😂",
    "😎", "🤩", "😘", "😉", "🤭", "💐", "😻", "🥳"
}

# Filter config list safely
SAFE_REACTIONS = [e for e in START_REACTIONS if e in VALID_REACTIONS]
if not SAFE_REACTIONS:
    SAFE_REACTIONS = list(VALID_REACTIONS)

# ---------------- PER-CHAT EMOJI ROTATION ----------------
chat_used_reactions: Dict[int, Set[str]] = {}

def next_emoji(chat_id: int) -> str:
    """Return a random, non-repeating emoji per chat."""
    if chat_id not in chat_used_reactions:
        chat_used_reactions[chat_id] = set()

    used = chat_used_reactions[chat_id]

    # Reset once all are used
    if len(used) >= len(SAFE_REACTIONS):
        used.clear()

    remaining = [e for e in SAFE_REACTIONS if e not in used]
    emoji = random.choice(remaining)
    used.add(emoji)
    chat_used_reactions[chat_id] = used
    return emoji

# ---------------- PER-CHAT ENABLED CACHE ----------------
# If a chat id is present, value is True/False. If absent, default is True.
chat_reaction_status: Dict[int, bool] = {}

async def load_custom_mentions():
    try:
        docs = await COLLECTION_MENTIONS.find().to_list(None)
        for doc in docs:
            name = doc.get("name")
            if name:
                custom_mentions.add(str(name).lower().lstrip("@"))
        print(f"[Reaction Manager] Loaded {len(custom_mentions)} mention triggers.")
    except Exception as e:
        print(f"[Reaction Manager] DB load error (mentions): {e}")

async def load_chat_statuses():
    try:
        docs = await COLLECTION_STATUS.find().to_list(None)
        for doc in docs:
            cid = doc.get("chat_id")
            enabled = bool(doc.get("enabled", True))
            if cid is not None:
                chat_reaction_status[int(cid)] = enabled
        print(f"[Reaction Manager] Loaded {len(chat_reaction_status)} chat statuses.")
    except Exception as e:
        print(f"[Reaction Manager] DB load error (statuses): {e}")

# Schedule startup loads
asyncio.get_event_loop().create_task(load_custom_mentions())
asyncio.get_event_loop().create_task(load_chat_statuses())

# ---------------- ADMIN / SUDO CHECK ----------------
async def is_admin_or_sudo(client, message: Message) -> Tuple[bool, Optional[str]]:
    """Return (ok, debug_message)"""
    user_id = getattr(message.from_user, "id", None)
    chat_id = message.chat.id
    chat_type = str(getattr(message.chat, "type", "")).lower()

    # Sudo or owner
    try:
        sudoers = await get_sudoers()
    except Exception:
        sudoers = set()

    if user_id and (user_id == OWNER_ID or user_id in sudoers):
        return True, None

    # Linked channel owner (owner of the linked channel)
    sender_chat_id = getattr(message.sender_chat, "id", None)
    if sender_chat_id:
        try:
            chat = await client.get_chat(chat_id)
            if getattr(chat, "linked_chat_id", None) == sender_chat_id:
                return True, None
        except Exception:
            pass

    # Only group/supergroup/channel contexts can have admins
    if chat_type not in ("chattype.group", "chattype.supergroup", "chattype.channel"):
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

# ---------------- HELPERS ----------------
async def set_chat_enabled(chat_id: int, enabled: bool):
    chat_reaction_status[chat_id] = enabled
    try:
        await COLLECTION_STATUS.update_one(
            {"chat_id": chat_id},
            {"$set": {"enabled": bool(enabled)}},
            upsert=True,
        )
    except Exception as e:
        print(f"[Reaction Manager] error saving status for {chat_id}: {e}")

def is_chat_enabled(chat_id: int) -> bool:
    # If global REACTION_BOT disabled, treat everything as disabled.
    if not REACTION_BOT:
        return False
    # If chat not present, default to True
    return chat_reaction_status.get(chat_id, True)

# ---------------- /reactionon ----------------
@app.on_message(filters.command("reactionon") & ~BANNED_USERS & (filters.group | filters.supergroup))
async def cmd_reaction_on(client, message: Message):
    ok, debug = await is_admin_or_sudo(client, message)
    if not ok:
        return await message.reply_text(
            f"⚠️ Only the Owner, sudo users or group admins can enable reactions.\n\nDebug: {debug or 'unknown'}"
        )
    chat_id = message.chat.id
    await set_chat_enabled(chat_id, True)
    await message.reply_text("✅ Reactions **enabled** for this chat.")

# ---------------- /reactionoff ----------------
@app.on_message(filters.command("reactionoff") & ~BANNED_USERS & (filters.group | filters.supergroup))
async def cmd_reaction_off(client, message: Message):
    ok, debug = await is_admin_or_sudo(client, message)
    if not ok:
        return await message.reply_text(
            f"⚠️ Only the Owner, sudo users or group admins can disable reactions.\n\nDebug: {debug or 'unknown'}"
        )
    chat_id = message.chat.id
    await set_chat_enabled(chat_id, False)
    await message.reply_text("⛔ Reactions **disabled** for this chat.")

# ---------------- /reaction (show inline enable/disable) ----------------
@app.on_message(filters.command("reaction") & ~BANNED_USERS & (filters.group | filters.supergroup))
async def cmd_reaction_menu(client, message: Message):
    chat_id = message.chat.id
    ok, debug = await is_admin_or_sudo(client, message)
    status = is_chat_enabled(chat_id)
    status_text = "Enabled ✅" if status else "Disabled ⛔"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Enable", callback_data=f"reaction_toggle:enable:{chat_id}"),
                InlineKeyboardButton("Disable", callback_data=f"reaction_toggle:disable:{chat_id}"),
            ],
            [InlineKeyboardButton("Close", callback_data=f"reaction_toggle:close:{chat_id}")],
        ]
    )

    text = (
        f"**Reaction Manager**\n\n"
        f"Global REACTION_BOT: {'ON' if REACTION_BOT else 'OFF'}\n"
        f"Chat ({chat_id}) status: **{status_text}**\n\n"
        f"Only owner, sudo users and chat admins can press the buttons."
    )

    await message.reply_text(text, reply_markup=keyboard)

# ---------------- CallbackQuery handler for buttons ----------------
@app.on_callback_query(filters.regex(r"^reaction_toggle:(enable|disable|close):(-?\d+)$"))
async def reaction_toggle_cb(client, callback: CallbackQuery):
    try:
        data = callback.data or ""
        parts = data.split(":")
        if len(parts) != 3:
            return await callback.answer("Invalid data.", show_alert=True)
        action = parts[1]
        target_chat_id = int(parts[2])

        # Only allow within the chat (or owner/sudo from anywhere)
        caller_user = callback.from_user
        caller_id = getattr(caller_user, "id", None)
        # If pressed inside message reply in chat, ensure callback.message.chat.id matches target
        # But allow owner/sudo to toggle from anywhere
        allowed = False

        # Quick owner/sudo check
        try:
            sudoers = await get_sudoers()
        except Exception:
            sudoers = set()

        if caller_id and (caller_id == OWNER_ID or caller_id in sudoers):
            allowed = True
        else:
            # If the callback is happening in the same chat where toggle is intended,
            # check if the caller is admin there.
            try:
                msg_chat_id = callback.message.chat.id
            except Exception:
                msg_chat_id = None

            # Only check admin rights if callback is invoked inside the same chat.
            if msg_chat_id == target_chat_id and caller_id:
                try:
                    member = await client.get_chat_member(target_chat_id, caller_id)
                    if member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
                        allowed = True
                except Exception:
                    allowed = False

        if not allowed:
            await callback.answer("Only owner, sudousers or group admins can use this.", show_alert=True)
            return

        if action == "close":
            try:
                await callback.message.delete()
            except Exception:
                pass
            finally:
                return await callback.answer()

        if action == "enable":
            await set_chat_enabled(target_chat_id, True)
            await callback.answer("Reactions enabled for this chat.")
        elif action == "disable":
            await set_chat_enabled(target_chat_id, False)
            await callback.answer("Reactions disabled for this chat.")
        else:
            await callback.answer("Unknown action.", show_alert=True)
            return

        # Edit the message to show new status (if possible)
        try:
            new_status_text = "Enabled ✅" if is_chat_enabled(target_chat_id) else "Disabled ⛔"
            new_text = (
                f"**Reaction Manager**\n\n"
                f"Global REACTION_BOT: {'ON' if REACTION_BOT else 'OFF'}\n"
                f"Chat ({target_chat_id}) status: **{new_status_text}**\n\n"
                f"Only owner, sudo users and chat admins can press the buttons."
            )
            await callback.message.edit_text(new_text, reply_markup=callback.message.reply_markup)
        except Exception:
            # ignore editing errors
            pass

    except Exception as e:
        print(f"[reaction_toggle_cb] error: {e}")
        try:
            await callback.answer("An error occurred.", show_alert=True)
        except Exception:
            pass

# ---------------- /addreact ----------------
@app.on_message(filters.command("addreact") & ~BANNED_USERS & (filters.group | filters.supergroup))
async def add_reaction_name(client, message: Message):
    ok, debug = await is_admin_or_sudo(client, message)
    if not ok:
        return await message.reply_text(
            f"⚠️ Only admins or sudo users can add reaction names.\n\nDebug info:\n{debug or 'unknown'}"
        )

    if len(message.command) < 2:
        return await message.reply_text("Usage: `/addreact <keyword_or_username>`")

    raw = message.text.split(None, 1)[1].strip()
    if not raw:
        return await message.reply_text("Usage: `/addreact <keyword_or_username>`")

    name = raw.lower().lstrip("@")
    resolved_id = None
    try:
        user = await client.get_users(name)
        if getattr(user, "id", None):
            resolved_id = user.id
    except Exception:
        pass

    try:
        await COLLECTION_MENTIONS.insert_one({"name": name})
    except Exception as e:
        print(f"[add_reaction_name] db insert error: {e}")

    custom_mentions.add(name)
    if resolved_id:
        id_key = f"id:{resolved_id}"
        try:
            await COLLECTION_MENTIONS.insert_one({"name": id_key})
        except Exception:
            pass
        custom_mentions.add(id_key)

    msg = f"✨ Added `{name}`"
    if resolved_id:
        msg += f" (id: `{resolved_id}`)"
    await message.reply_text(msg)

# ---------------- /delreact ----------------
@app.on_message(filters.command("delreact") & ~BANNED_USERS & (filters.group | filters.supergroup))
async def delete_reaction_name(client, message: Message):
    ok, debug = await is_admin_or_sudo(client, message)
    if not ok:
        return await message.reply_text(
            f"⚠️ Only admins or sudo users can delete reaction names.\n\nDebug info:\n{debug or 'unknown'}"
        )

    if len(message.command) < 2:
        return await message.reply_text("Usage: `/delreact <keyword_or_username>`")

    raw = message.text.split(None, 1)[1].strip().lower().lstrip("@")
    removed = False

    if raw in custom_mentions:
        custom_mentions.remove(raw)
        try:
            await COLLECTION_MENTIONS.delete_one({"name": raw})
        except Exception:
            pass
        removed = True

    try:
        user = await client.get_users(raw)
        if getattr(user, "id", None):
            id_key = f"id:{user.id}"
            if id_key in custom_mentions:
                custom_mentions.remove(id_key)
                try:
                    await COLLECTION_MENTIONS.delete_one({"name": id_key})
                except Exception:
                    pass
                removed = True
    except Exception:
        pass

    if removed:
        await message.reply_text(f"🗑 Removed `{raw}` from mention list.")
    else:
        await message.reply_text(f"❌ `{raw}` not found in mention list.")

# ---------------- /reactlist ----------------
@app.on_message(filters.command("reactlist") & ~BANNED_USERS & (filters.group | filters.supergroup))
async def list_reactions(client, message: Message):
    if not custom_mentions:
        return await message.reply_text("ℹ️ No mention triggers found.")

    text = "\n".join(f"• `{m}`" for m in sorted(custom_mentions))
    await message.reply_text(f"**🧠 Reaction Triggers:**\n{text}")

# ---------------- /clearreact ----------------
@app.on_message(filters.command("clearreact") & ~BANNED_USERS & (filters.group | filters.supergroup))
async def clear_reactions(client, message: Message):
    ok, debug = await is_admin_or_sudo(client, message)
    if not ok:
        return await message.reply_text(
            f"⚠️ Only admins or sudo users can clear reactions.\n\nDebug info:\n{debug or 'unknown'}"
        )

    try:
        await COLLECTION_MENTIONS.delete_many({})
    except Exception as e:
        print(f"[clear_reactions] db delete error: {e}")

    custom_mentions.clear()
    await message.reply_text("🧹 Cleared all custom reaction mentions.")

# ---------------- REACT ON MENTIONS ----------------
@app.on_message((filters.text | filters.caption) & ~BANNED_USERS & (filters.group | filters.supergroup))
async def react_on_mentions(client, message: Message):
    try:
        # If global REACTION_BOT is disabled, do nothing
        if not REACTION_BOT:
            return

        # Skip bot commands
        if message.text and message.text.startswith("/"):
            return

        chat_id = message.chat.id

        # If chat has reactions disabled, skip
        if not is_chat_enabled(chat_id):
            return

        text = (message.text or message.caption or "").lower()
        entities = (message.entities or []) + (message.caption_entities or [])
        usernames, user_ids = set(), set()

        # Parse entities
        for ent in entities:
            if ent.type == "mention":
                full_text = (message.text or message.caption) or ""
                uname = full_text[ent.offset:ent.offset + ent.length].lstrip("@").lower()
                usernames.add(uname)
            elif ent.type == "text_mention" and ent.user:
                user_ids.add(ent.user.id)
                if ent.user.username:
                    usernames.add(ent.user.username.lower())

        reacted = False

        # 1️⃣ Username mentions
        for uname in usernames:
            if uname in custom_mentions or f"@{uname}" in text:
                emoji = next_emoji(chat_id)
                try:
                    await message.react(emoji)
                    print(f"[Reaction] Chat {chat_id} → {emoji} for @{uname}")
                except Exception:
                    try:
                        await message.react("❤️")
                    except Exception:
                        pass
                reacted = True
                break

        # 2️⃣ ID-based
        if not reacted:
            for uid in user_ids:
                if f"id:{uid}" in custom_mentions:
                    emoji = next_emoji(chat_id)
                    try:
                        await message.react(emoji)
                        print(f"[Reaction] Chat {chat_id} → {emoji} for id:{uid}")
                    except Exception:
                        try:
                            await message.react("❤️")
                        except Exception:
                            pass
                    reacted = True
                    break

        # 3️⃣ Keyword trigger
        if not reacted:
            for trig in custom_mentions:
                if trig.startswith("id:"):
                    continue
                if trig in text or f"@{trig}" in text:
                    emoji = next_emoji(chat_id)
                    try:
                        await message.react(emoji)
                        print(f"[Reaction] Chat {chat_id} → {emoji} for trigger '{trig}'")
                    except Exception:
                        try:
                            await message.react("❤️")
                        except Exception:
                            pass
                    break

    except Exception as e:
        print(f"[react_on_mentions] error: {e}")
