# FINAL MERGED CHATBOT.PY WITH BLOCK + REGEX + GROUP SYSTEM

import os
import random
import re
from datetime import datetime, timedelta
from typing import Optional
from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import MessageEmpty
from pymongo import MongoClient
from deep_translator import GoogleTranslator

# -------------------- Application client -------------------- #
try:
    from VIPMUSIC import app
except Exception:
    try:
        from main import app
    except Exception:
        raise RuntimeError("Could not import Pyrogram Client as 'app'.")

# -------------------- MongoDB Setup -------------------- #
try:
    from config import MONGO_DB_URI as MONGO_URL
except Exception:
    MONGO_URL = os.environ.get("MONGO_URL")

mongo = MongoClient(MONGO_URL)
db = mongo.get_database("VIPMUSIC")

# Collections
chatbot_coll = db.get_collection("chatbot_replies")
blockwords_coll = db.get_collection("chatbot_blockwords")
status_coll = db.get_collection("chatbot_status")
lang_coll = db.get_collection("chat_langs")
chatai_coll = db.get_collection("chatai")

translator = GoogleTranslator()

# Cache
REPLY_CACHE = {}
BLOCKWORDS = []
replies_cache = []
blocklist = {}
message_counts = {}

# -------------------- Load Blockwords -------------------- #
def load_blockwords():
    lst = []
    for w in blockwords_coll.find({}):
        lst.append({
            "pattern": w["pattern"],
            "type": w.get("type", "word"),
        })
    return lst

BLOCKWORDS = load_blockwords()

# -------------------- Reply Cache Loader -------------------- #
def load_replies_cache():
    global REPLY_CACHE
    REPLY_CACHE = {}
    for item in chatbot_coll.find({}):
        key = item["word"].lower()
        REPLY_CACHE.setdefault(key, []).append(item)

load_replies_cache()

# -------------------- Blocked Text Checker -------------------- #
def is_blocked_text(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    for bw in BLOCKWORDS:
        pattern = bw["pattern"].lower()
        if bw["type"] == "regex":
            try:
                if re.search(pattern, t, flags=re.IGNORECASE):
                    return True
            except Exception:
                continue
        else:
            if pattern in t:
                return True
    return False

# -------------------- Save Basic Text Reply -------------------- #
async def save_reply(original: Message, reply: Message):
    text_raw = reply.text or ""
    if is_blocked_text(text_raw):
        return

    data = {
        "word": original.text,
        "text": text_raw,
        "media": None,
        "timestamp": datetime.now(),
    }

    chatbot_coll.insert_one(data)
    load_replies_cache()

# -------------------- Basic Reply Fetch -------------------- #
def get_reply_sync(text: str) -> Optional[dict]:
    key = text.lower()
    if key not in REPLY_CACHE:
        return None
    options = REPLY_CACHE[key]
    if not options:
        return None
    chosen = random.choice(options)
    if is_blocked_text(chosen.get("text", "")):
        return None
    return chosen

# =====================================================================
# ADVANCED SYSTEM (GROUP + MULTIMEDIA + SPAM PROTECTION + LEARNING)
# =====================================================================

# Photo extractor
def _photo_file_id(msg: Message) -> Optional[str]:
    try:
        p = getattr(msg, "photo", None)
        if not p:
            return None
        if hasattr(p, "file_id"):
            return p.file_id
        if isinstance(p, (list, tuple)):
            return p[-1].file_id
    except Exception:
        pass
    return None

# Advanced reply loader
async def load_replies_cache2():
    global replies_cache
    try:
        replies_cache = list(chatai_coll.find({}))
    except Exception:
        replies_cache = []

# Advanced reply fetch
def get_reply_sync2(word: str):
    global replies_cache
    if not replies_cache:
        try:
            replies_cache.extend(list(chatai_coll.find({})))
        except Exception:
            pass
    if not replies_cache:
        return None
    exact = [r for r in replies_cache if r.get("word") == (word or "")]
    candidates = exact if exact else replies_cache
    return random.choice(candidates) if candidates else None

# Admin checker
async def is_user_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False

# Save multimedia replies
async def save_reply2(original: Message, reply: Message):
    try:
        if not original.text:
            return

        if reply.text and is_blocked_text(reply.text):
            return

        data = {
            "word": original.text,
            "text": None,
            "kind": "text",
            "created_at": datetime.utcnow(),
        }

        if reply.sticker:
            data["text"] = reply.sticker.file_id
            data["kind"] = "sticker"
        elif _photo_file_id(reply):
            data["text"] = _photo_file_id(reply)
            data["kind"] = "photo"
        elif reply.video:
            data["text"] = reply.video.file_id
            data["kind"] = "video"
        elif reply.audio:
            data["text"] = reply.audio.file_id
            data["kind"] = "audio"
        elif reply.animation:
            data["text"] = reply.animation.file_id
            data["kind"] = "gif"
        elif reply.voice:
            data["text"] = reply.voice.file_id
            data["kind"] = "voice"
        elif reply.text:
            data["text"] = reply.text
            data["kind"] = "text"
        else:
            return

        exists = chatai_coll.find_one(
            {"word": data["word"], "text": data["text"], "kind": data["kind"]}
        )
        if not exists:
            chatai_coll.insert_one(data)
            replies_cache.append(data)

    except Exception as e:
        print("[chatbot] save_reply2:", e)

# Chat language
async def get_chat_language(chat_id: int) -> Optional[str]:
    doc = lang_coll.find_one({"chat_id": chat_id})
    return doc.get("language") if doc else None

# Keyboard builder
def chatbot_keyboard(is_enabled: bool):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            "🔴 Disable" if is_enabled else "🟢 Enable",
            callback_data="cb_disable" if is_enabled else "cb_enable",
        )]]
    )

# =====================================================================
# BLOCK COMMANDS (/addblock /rmblock /listblock)
# =====================================================================
from VIPMUSIC.misc import SUDOERS

@app.on_message(filters.command("addblock") & filters.user(SUDOERS))
async def add_blockword(client, message: Message):
    msg = message.text.split(maxsplit=1)
    if len(msg) < 2:
        return await message.reply("Usage: /addblock <word or regex>")

    pattern = msg[1].strip()

    bw_type = "regex" if any(c in pattern for c in ".^$*+?{}[]|()") else "word"

    blockwords_coll.insert_one({"pattern": pattern, "type": bw_type})

    BLOCKWORDS.clear()
    BLOCKWORDS.extend(load_blockwords())

    chatbot_coll.delete_many({"text": {"$regex": pattern, "$options": "i"}})

    load_replies_cache()

    await message.reply(f"✔ Added block pattern: `{pattern}` (type: {bw_type})")

@app.on_message(filters.command("rmblock") & filters.user(SUDOERS))
async def rm_blockword(client, message: Message):
    msg = message.text.split(maxsplit=1)
    if len(msg) < 2:
        return await message.reply("Usage: /rmblock <word or regex>")

    pattern = msg[1].strip()

    blockwords_coll.delete_one({"pattern": pattern})

    BLOCKWORDS.clear()
    BLOCKWORDS.extend(load_blockwords())

    await message.reply(f"✔ Removed blocked entry: `{pattern}`")

@app.on_message(filters.command("listblock") & filters.user(SUDOERS))
async def list_block(client, message: Message):
    if not BLOCKWORDS:
        return await message.reply("Blocklist is empty.")

    txt = "**🔐 GLOBAL BLOCK PATTERNS:**

"
    for b in BLOCKWORDS:
        txt += f"• `{b['pattern']}`  (type: {b['type']})
"

    await message.reply(txt)

# =====================================================================
# MAIN CHATBOT HANDLER (ADVANCED)
# =====================================================================
@app.on_message(filters.incoming & ~filters.me, group=99)
async def chatbot_handler2(client, message: Message):
    if message.edit_date:
        return
    if not message.from_user:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    now = datetime.utcnow()

    # SPAM CHECK
    global blocklist, message_counts
    blocklist = {u: t for u, t in blocklist.items() if t > now}

    mc = message_counts.get(user_id)
    if not mc:
        message_counts[user_id] = {"count": 1, "last": now}
    else:
        diff = (now - mc["last"]).total_seconds()
        mc["count"] = mc["count"] + 1 if diff <= 3 else 1
        mc["last"] = now
        if mc["count"] >= 6:
            blocklist[user_id] = now + timedelta(minutes=1)
            message_counts.pop(user_id, None)
            try:
                await message.reply_text("⛔ Blocked 1 minute for spam.")
            except Exception:
                pass
            return

    if user_id in blocklist:
        return

    # STATUS CHECK
    s = status_coll.find_one({"chat_id": chat_id})
    if s and s.get("status") == "disabled":
        return

    # IGNORE COMMANDS
    if message.text and message.text.startswith("/"):
        return

    # SHOULD BOT REPLY?
    should_reply = False
    if message.reply_to_message:
        bot = await client.get_me()
        if message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot.id:
            should_reply = True
    else:
        should_reply = True

    if not should_reply:
        return

    # BLOCKED WORD DETECTION
    if message.text and is_blocked_text(message.text):
        return

    r = get_reply_sync2(message.text or "")
    if not r:
        try:
            await message.reply_text("I don't understand. 🤔")
        except Exception:
            pass
        return

    response = r.get("text", "")
    kind = r.get("kind", "text")

    lang = await get_chat_language(chat_id)

    if kind == "text" and response and lang and lang != "nolang":
        try:
            response = translator.translate(response, target=lang)
        except Exception:
            pass

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
    except Exception:
        try:
            await message.reply_text(response)
        except Exception:
            pass

# =====================================================================
# LEARNING MODE
# =====================================================================
@app.on_message(filters.reply & filters.group)
async def learn_reply_group(client, message):
    if not message.reply_to_message:
        return
    bot = await client.get_me()
    if message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot.id:
        await save_reply2(message.reply_to_message, message)

@app.on_message(filters.reply & filters.private)
async def learn_reply_private(client, message):
    if not message.reply_to_message:
        return
    bot = await client.get_me()
    if message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot.id:
        await save_reply2(message.reply_to_message, message)

# =====================================================================
# CHATBOT COMMAND UI / ENABLE-DISABLE
# =====================================================================
@app.on_message(filters.command("chatbot") & filters.group)
async def chatbot_settings_group(client, message):
    if not await is_user_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Only admins can manage chatbot settings.")

    doc = status_coll.find_one({"chat_id": message.chat.id})
    enabled = not doc or doc.get("status") == "enabled"

    txt = f"**🤖 Chatbot Settings**
Current Status: {'🟢 Enabled' if enabled else '🔴 Disabled'}"

    await message.reply_text(txt, reply_markup=chatbot_keyboard(enabled))

@app.on_message(filters.command("chatbot") & filters.private)
async def chatbot_settings_private(client, message):
    doc = status_coll.find_one({"chat_id": message.chat.id})
    enabled = not doc or doc.get("status") == "enabled"
    await message.reply_text(
        f"🤖 Chatbot (private)
Status: {'🟢 Enabled' if enabled else '🔴 Disabled'}",
        reply_markup=chatbot_keyboard(enabled),
    )

@app.on_callback_query(filters.regex("^cb_(enable|disable)$"))
async def chatbot_toggle_cb(client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    uid = cq.from_user.id

    if cq.message.chat.type in ("group", "supergroup"):
        if not await is_user_admin(client, chat_id, uid):
            return await cq.answer("Only admins can do this.", show_alert=True)

    if cq.data == "cb_enable":
        status_coll.update_one({"chat_id": chat_id}, {"$set": {"status": "enabled"}}, upsert=True)
        await cq.message.edit_text("🤖 Chatbot Enabled!", reply_markup=chatbot_keyboard(True))
    else:
        status_coll.update_one({"chat_id": chat_id}, {"$set": {"status": "disabled"}}, upsert=True)
        await cq.message.edit_text("🤖 Chatbot Disabled!", reply_markup=chatbot_keyboard(False))

    await cq.answer()

# =====================================================================
# LANGUAGE SETTING
# =====================================================================
@app.on_message(filters.command("setlang") & filters.group)
async def setlang_group(client, message):
    if not await is_user_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Only admins can set language.")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("Usage: /setlang <code>")

    lang = parts[1].strip()
    lang_coll.update_one({"chat_id": message.chat.id}, {"$set": {"language": lang}}, upsert=True)
    await message.reply_text(f"✅ Language set to `{lang}`")

@app.on_message(filters.command("setlang") & filters.private)
async def setlang_private(client, message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("Usage: /setlang <code>")

    lang = parts[1].strip()
    lang_coll.update_one({"chat_id": message.chat.id}, {"$set": {"language": lang}}, upsert=True)
