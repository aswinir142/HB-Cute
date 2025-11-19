"""
chatbot.py — Chatbot plugin (clean, Pyrogram v2 compatible)

Key points:
- General message handler ignores commands using ~filters.regex(r'^/')
  so /start /help /play etc are preserved for other plugins.
- /chatbot command + inline Enable/Disable (admin-only)
- /chatbot reset (admin) clears learned replies (global)
- /setlang <code> sets per-chat reply translation language
- Learns replies when users reply to the bot (saves text/media)
- Spam protection per-user
- MongoDB collections: chatai, chatbot_status, chat_langs
"""

import os
import random
from datetime import datetime, timedelta
from typing import Optional

from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.errors import MessageEmpty
from pyrogram.enums import ChatMemberStatus

from pymongo import MongoClient
from deep_translator import GoogleTranslator

# -------------------- App import -------------------- #
try:
    # common HB-Cute / VIPMUSIC patterns
    from VIPMUSIC import app
except Exception:
    try:
        from main import app
    except Exception:
        raise RuntimeError("Could not import Pyrogram Client as 'app'. Make sure your project exposes it.")

# -------------------- MongoDB -------------------- #
try:
    from config import MONGO_URL
except Exception:
    MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")

mongo = MongoClient(MONGO_URL)
db = mongo.get_database("vipmusic_db")
chatai_coll = db.get_collection("chatai")          # learned replies
status_coll = db.get_collection("chatbot_status")  # per-chat enabled/disabled
lang_coll = db.get_collection("chat_langs")        # per-chat language

# -------------------- Translator -------------------- #
translator = GoogleTranslator()

# -------------------- Runtime caches & rate limit -------------------- #
replies_cache = []     # in-memory cache of reply documents
blocklist = {}         # user_id -> unblock_datetime (UTC)
message_counts = {}    # user_id -> {"count": int, "last_time": datetime}


# -------------------- Helpers -------------------- #
def _photo_file_id(msg: Message) -> Optional[str]:
    """Return a photo file_id safely (PhotoSize or list)."""
    try:
        photo = getattr(msg, "photo", None)
        if not photo:
            return None
        if hasattr(photo, "file_id"):
            return photo.file_id
        if isinstance(photo, (list, tuple)) and len(photo) > 0:
            return photo[-1].file_id
    except Exception:
        pass
    return None


async def load_replies_cache():
    """Populate in-memory cache (call if desired on startup)."""
    global replies_cache
    try:
        replies_cache = list(chatai_coll.find({}))
    except Exception as e:
        print("[chatbot] load_replies_cache error:", e)
        replies_cache = []


def get_reply_sync(word: str):
    """Synchronous selector from cache or DB. Prefers exact matches."""
    global replies_cache
    if not replies_cache:
        try:
            docs = list(chatai_coll.find({}))
            replies_cache.extend(docs)
        except Exception:
            pass

    if not replies_cache:
        return None

    exact = [r for r in replies_cache if r.get("word") == (word or "")]
    candidates = exact if exact else replies_cache
    return random.choice(candidates) if candidates else None


async def is_user_admin(client, chat_id: int, user_id: int) -> bool:
    """Awaitable admin check (works for groups)."""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


async def save_reply(original_message: Message, reply_message: Message):
    """Save bot_message.text -> reply_message (file_id or text)."""
    try:
        if not original_message or not getattr(original_message, "text", None):
            return

        doc = {
            "word": original_message.text,
            "text": None,
            "kind": "text",
            "created_at": datetime.utcnow(),
        }

        if getattr(reply_message, "sticker", None):
            doc["text"] = reply_message.sticker.file_id
            doc["kind"] = "sticker"
        elif _photo_file_id(reply_message):
            doc["text"] = _photo_file_id(reply_message)
            doc["kind"] = "photo"
        elif getattr(reply_message, "video", None):
            doc["text"] = reply_message.video.file_id
            doc["kind"] = "video"
        elif getattr(reply_message, "audio", None):
            doc["text"] = reply_message.audio.file_id
            doc["kind"] = "audio"
        elif getattr(reply_message, "animation", None):
            doc["text"] = reply_message.animation.file_id
            doc["kind"] = "gif"
        elif getattr(reply_message, "voice", None):
            doc["text"] = reply_message.voice.file_id
            doc["kind"] = "voice"
        elif getattr(reply_message, "text", None):
            doc["text"] = reply_message.text
            doc["kind"] = "text"
        else:
            return

        # dedupe exact mapping
        exists = chatai_coll.find_one({"word": doc["word"], "text": doc["text"], "kind": doc["kind"]})
        if not exists:
            chatai_coll.insert_one(doc)
            replies_cache.append(doc)

    except Exception as e:
        print("[chatbot] save_reply error:", e)


async def get_chat_language(chat_id: int) -> Optional[str]:
    doc = lang_coll.find_one({"chat_id": chat_id})
    if doc and "language" in doc:
        return doc["language"]
    return None


# -------------------- Inline keyboard -------------------- #
def chatbot_keyboard(is_enabled: bool):
    if is_enabled:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔴 Disable", callback_data="cb_disable")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("🟢 Enable", callback_data="cb_enable")]])


# -------------------- /chatbot command (group) -------------------- #
@app.on_message(filters.command("chatbot") & filters.group)
async def chatbot_cmd_group(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_user_admin(client, chat_id, user_id):
        return await message.reply_text("❌ Only group admins can configure the chatbot.")

    status_doc = status_coll.find_one({"chat_id": chat_id})
    is_enabled = not status_doc or status_doc.get("status") == "enabled"

    text = (
        "**🤖 Chatbot Settings**\n\n"
        f"Current Status: **{'🟢 Enabled' if is_enabled else '🔴 Disabled'}**\n\n"
        "Use buttons to toggle the chatbot for this chat."
    )
    await message.reply_text(text, reply_markup=chatbot_keyboard(is_enabled))


# -------------------- /chatbot command (private) -------------------- #
@app.on_message(filters.command("chatbot") & filters.private)
async def chatbot_cmd_private(client, message: Message):
    chat_id = message.chat.id
    status_doc = status_coll.find_one({"chat_id": chat_id})
    is_enabled = not status_doc or status_doc.get("status") == "enabled"
    text = f"**🤖 Chatbot (Private)**\nStatus: **{'🟢 Enabled' if is_enabled else '🔴 Disabled'}**"
    await message.reply_text(text, reply_markup=chatbot_keyboard(is_enabled))


# -------------------- callbacks for enable/disable -------------------- #
@app.on_callback_query(filters.regex("^cb_enable$") | filters.regex("^cb_disable$"))
async def chatbot_toggle_cb(client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    caller_id = cq.from_user.id

    # Admin check in groups
    if cq.message.chat.type in ("group", "supergroup"):
        if not await is_user_admin(client, chat_id, caller_id):
            return await cq.answer("Only group admins can perform this action.", show_alert=True)

    if cq.data == "cb_enable":
        status_coll.update_one({"chat_id": chat_id}, {"$set": {"status": "enabled"}}, upsert=True)
        await cq.message.edit_text("**🤖 Chatbot Enabled!**\nStatus: 🟢 Enabled", reply_markup=chatbot_keyboard(True))
        await cq.answer("Chatbot enabled.")
    else:
        status_coll.update_one({"chat_id": chat_id}, {"$set": {"status": "disabled"}}, upsert=True)
        await cq.message.edit_text("**🤖 Chatbot Disabled!**\nStatus: 🔴 Disabled", reply_markup=chatbot_keyboard(False))
        await cq.answer("Chatbot disabled.")


# -------------------- /chatbot reset (admin) -------------------- #
@app.on_message(filters.command("chatbot") & filters.regex(r"^/chatbot\s+reset$", flags=0) & filters.group)
async def chatbot_reset_group(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_user_admin(client, chat_id, user_id):
        return await message.reply_text("❌ Only group admins can reset chatbot data.")
    chatai_coll.delete_many({})
    replies_cache.clear()
    await message.reply_text("✅ All learned replies cleared (global).")


@app.on_message(filters.command("chatbot") & filters.regex(r"^/chatbot\s+reset$", flags=0) & filters.private)
async def chatbot_reset_private(client, message: Message):
    chatai_coll.delete_many({})
    replies_cache.clear()
    await message.reply_text("✅ All learned replies cleared (global).")


# -------------------- /setlang command -------------------- #
@app.on_message(filters.command("setlang") & filters.group)
async def setlang_group(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_user_admin(client, chat_id, user_id):
        return await message.reply_text("❌ Only group admins can set chatbot language for the chat.")
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("Usage: /setlang <language_code>  e.g. /setlang en")
    lang = parts[1].strip()
    lang_coll.update_one({"chat_id": chat_id}, {"$set": {"language": lang}}, upsert=True)
    await message.reply_text(f"✅ Chatbot language set to: `{lang}`")


@app.on_message(filters.command("setlang") & filters.private)
async def setlang_private(client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("Usage: /setlang <language_code>")
    lang = parts[1].strip()
    lang_coll.update_one({"chat_id": message.chat.id}, {"$set": {"language": lang}}, upsert=True)
    await message.reply_text(f"✅ Chatbot language set to: `{lang}`")


# -------------------- Learning: save replies when user replies to bot -------------------- #
@app.on_message(filters.reply & (filters.group | filters.private) & ~filters.regex(r"^/"))
async def learn_reply(client, message: Message):
    """If a user replies to a bot message, store mapping bot_message.text -> user's reply."""
    try:
        if not message.reply_to_message:
            return
        bot = await client.get_me()
        if getattr(message.reply_to_message, "from_user", None) and message.reply_to_message.from_user.id == bot.id:
            await save_reply(message.reply_to_message, message)
    except Exception:
        pass


# -------------------- Main chatbot auto-reply handler -------------------- #
# Important: use ~filters.regex(r'^/') so commands (like /start /help /play) are NOT handled by this plugin.
@app.on_message((filters.text | filters.caption) & ~filters.regex(r"^/"))
async def chatbot_handler(client, message: Message):
    # ignore edited messages
    if message.edit_date:
        return

    # basic checks
    if not message.from_user:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    now = datetime.utcnow()

    # cleanup expired blocks
    global blocklist, message_counts
    blocklist = {u: t for u, t in blocklist.items() if t > now}

    # rate limiting / spam protection
    mc = message_counts.get(user_id)
    if not mc:
        message_counts[user_id] = {"count": 1, "last_time": now}
    else:
        diff = (now - mc["last_time"]).total_seconds()
        if diff <= 3:
            mc["count"] += 1
        else:
            mc["count"] = 1
        mc["last_time"] = now

        if mc["count"] >= 6:
            blocklist[user_id] = now + timedelta(minutes=1)
            message_counts.pop(user_id, None)
            try:
                await message.reply_text("⛔ You are blocked for 1 minute due to spam.")
            except Exception:
                pass
            return

    if user_id in blocklist:
        return

    # respect per-chat enabled/disabled
    s = status_coll.find_one({"chat_id": chat_id})
    if s and s.get("status") == "disabled":
        return

    # choose whether to respond:
    # respond when message is a reply to bot OR general messages (you can change to reply-only)
    should_respond = False
    if message.reply_to_message and getattr(message.reply_to_message, "from_user", None):
        bot = await client.get_me()
        if message.reply_to_message.from_user.id == bot.id:
            should_respond = True
    else:
        # set to False here if you want bot to ONLY respond to replies addressed to it
        should_respond = True

    if not should_respond:
        return

    # pick an existing learned reply
    r = get_reply_sync(message.text or "")
    if r:
        response = r.get("text") or ""
        kind = r.get("kind", "text")
        chat_lang = await get_chat_language(chat_id)

        # translate textual replies if language set
        if kind == "text" and response and chat_lang and chat_lang != "nolang":
            try:
                response = translator.translate(response, target=chat_lang)
            except Exception:
                pass

        # try to send in correct media type
        try:
            if kind == "sticker":
                await message.reply_sticker(response)
            elif kind == "photo":
                await message.reply_photo(response)
            elif kind == "video":
                await message.reply_video(response)
            elif kind == "audio":
                await message.reply_audio(response)
            elif kind == "gif":
                await message.reply_animation(response)
            elif kind == "voice":
                await message.reply_voice(response)
            else:
                await message.reply_text(response or "I don't understand.")
        except MessageEmpty:
            pass
        except Exception as e:
            try:
                await message.reply_text(response or "I don't understand.")
            except Exception:
                print("[chatbot] send error:", e)
    else:
        # optional gentle fallback — comment out if you'd prefer silence
        try:
            await message.reply_text("I don't understand. 🤔")
        except Exception:
            pass
