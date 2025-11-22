# chatbot.py — TEXT-ONLY chatbot (keeps media in DB but never sends it)
import os
import random
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatMemberStatus
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

if not MONGO_URL:
    raise RuntimeError("MONGO_DB_URI / MONGO_URL not set")

mongo = MongoClient(MONGO_URL)
db = mongo.get_database("VIPMUSIC")

# Collections
chatbot_coll = db.get_collection("chatbot_replies")    # structured text replies
chatai_coll = db.get_collection("chatai")              # learning store (may contain media entries)
blockwords_coll = db.get_collection("chatbot_blockwords")
status_coll = db.get_collection("chatbot_status")
lang_coll = db.get_collection("chat_langs")

translator = GoogleTranslator(source="auto")

# -------------------- In-memory caches -------------------- #
REPLY_CACHE: Dict[str, List[Dict[str, Any]]] = {}   # text-key -> list of reply docs (text-based)
REPLIES_FULL: List[Dict[str, Any]] = []             # full store (used for learning fallback)
BLOCKWORDS: List[Dict[str, Any]] = []               # each item: { pattern, type, compiled (optional) }

# runtime helpers
blocklist: Dict[int, datetime] = {}                 # spam temp-block per user_id
message_counts: Dict[int, Dict[str, Any]] = {}      # {user_id: {"count": int, "last": datetime}}

# -------------------- Utilities -------------------- #
def normalize_word(s: Optional[str]) -> str:
    return (s or "").strip().lower()

# -------------------- Loaders -------------------- #
def load_blockwords() -> List[Dict[str, Any]]:
    out = []
    for row in blockwords_coll.find({}):
        pat = row.get("pattern", "")
        typ = row.get("type", "word")
        entry = {"pattern": pat, "type": typ}
        if typ == "regex":
            try:
                entry["compiled"] = re.compile(pat, re.IGNORECASE)
            except re.error:
                # invalid regex — store as literal fallback
                entry["compiled"] = re.compile(re.escape(pat), re.IGNORECASE)
                entry["type"] = "regex"  # keep type but compiled fallback
        out.append(entry)
    return out

def load_replies_cache():
    """Load only text replies (chatbot_coll) into REPLY_CACHE for fast exact-match lookups."""
    global REPLY_CACHE
    REPLY_CACHE = {}
    for doc in chatbot_coll.find({}):
        key = normalize_word(doc.get("word", ""))
        REPLY_CACHE.setdefault(key, []).append(doc)

def load_replies_full():
    """Load full learning store (chatai_coll) — used for get_reply_sync2 fallback."""
    global REPLIES_FULL
    try:
        REPLIES_FULL = list(chatai_coll.find({}))
    except Exception:
        REPLIES_FULL = []

# initialize caches
BLOCKWORDS = load_blockwords()
load_replies_cache()
load_replies_full()

# -------------------- Block detection -------------------- #
def is_blocked_text(text: Optional[str]) -> bool:
    if not text:
        return False
    txt = text.lower()
    for bw in BLOCKWORDS:
        if bw.get("type") == "regex":
            compiled = bw.get("compiled")
            if compiled:
                try:
                    if compiled.search(txt):
                        return True
                except Exception:
                    # fallback to simple containment
                    if bw["pattern"].lower() in txt:
                        return True
        else:
            # literal substring match
            if bw["pattern"].lower() in txt:
                return True
    return False

# -------------------- Reply management (text-only storage + learning) -------------------- #
async def save_text_reply(original: Message, reply: Message):
    """Save a plain text reply (used for chatbot_coll)."""
    try:
        if not original or not original.text:
            return
        text_raw = reply.text or ""
        if not text_raw:
            return
        if is_blocked_text(text_raw):
            return
        data = {
            "word": normalize_word(original.text),
            "text": text_raw,
            "timestamp": datetime.utcnow(),
        }
        # avoid exact dupes
        exists = chatbot_coll.find_one({"word": data["word"], "text": data["text"]})
        if not exists:
            chatbot_coll.insert_one(data)
            # update cache incrementally
            REPLY_CACHE.setdefault(data["word"], []).append(data)
    except Exception as e:
        print("[chatbot.save_text_reply] error:", e)

async def save_reply_full(original: Message, reply: Message):
    """
    Save the full reply to chatai_coll (may include media). We keep media in DB per Option B.
    """
    try:
        if not original or not original.text:
            return

        data = {
            "word": normalize_word(original.text),
            "text": None,
            "kind": "text",
            "created_at": datetime.utcnow(),
        }

        # prefer to capture any text caption first
        if reply.text:
            data["text"] = reply.text
            data["kind"] = "text"
        elif getattr(reply, "sticker", None):
            data["text"] = reply.sticker.file_id
            data["kind"] = "sticker"
        elif getattr(reply, "photo", None):
            # pick last photo size file_id if possible
            ph = reply.photo
            if isinstance(ph, (list, tuple)) and ph:
                data["text"] = ph[-1].file_id
            else:
                try:
                    data["text"] = ph.file_id
                except Exception:
                    data["text"] = None
            data["kind"] = "photo"
        elif getattr(reply, "video", None):
            data["text"] = reply.video.file_id
            data["kind"] = "video"
        elif getattr(reply, "audio", None):
            data["text"] = reply.audio.file_id
            data["kind"] = "audio"
        elif getattr(reply, "animation", None):
            data["text"] = reply.animation.file_id
            data["kind"] = "gif"
        elif getattr(reply, "voice", None):
            data["text"] = reply.voice.file_id
            data["kind"] = "voice"
        else:
            # nothing worth saving
            return

        # don't save if the textual content (if any) is blocked
        if data["text"] and data["kind"] == "text" and is_blocked_text(data["text"]):
            return

        exists = chatai_coll.find_one({"word": data["word"], "text": data["text"], "kind": data["kind"]})
        if not exists:
            chatai_coll.insert_one(data)
            REPLIES_FULL.append(data)
    except Exception as e:
        print("[chatbot.save_reply_full] error:", e)

# -------------------- Reply lookup -------------------- #
def get_reply_sync(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Fast exact-match lookup from chatbot_coll (text-only replies)."""
    key = normalize_word(text)
    if not key:
        return None
    options = REPLY_CACHE.get(key)
    if not options:
        return None
    # choose random option and ensure not blocked
    shuffled = options[:] 
    random.shuffle(shuffled)
    for opt in shuffled:
        if not is_blocked_text(opt.get("text", "")):
            return opt
    return None

def get_reply_sync2(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Fallback learning lookup from chatai_coll (REPLIES_FULL).
    Tries exact normalized match first, otherwise returns a random entry.
    """
    w = normalize_word(text)
    if not REPLIES_FULL:
        load_replies_full()
    # exact matches first
    exact = [r for r in REPLIES_FULL if r.get("word") == w]
    candidates = exact if exact else REPLIES_FULL
    if not candidates:
        return None
    # pick a candidate that is allowed (i.e., we will later ensure text-only sending)
    random.shuffle(candidates)
    for c in candidates:
        # if candidate has text kind and that text is blocked -> skip
        if c.get("kind") == "text" and is_blocked_text(c.get("text", "")):
            continue
        return c
    return None

# -------------------- Admin / util helpers -------------------- #
async def is_user_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False

def chatbot_keyboard(is_enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔴 Disable" if is_enabled else "🟢 Enable",
                               callback_data="cb_disable" if is_enabled else "cb_enable")]]
    )

# -------------------- Block commands (SUDO ONLY) -------------------- #
from VIPMUSIC.misc import SUDOERS

@app.on_message(filters.command("addblock") & filters.user(SUDOERS))
async def add_blockword(client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("Usage: /addblock <word_or_regex>")
    pattern = parts[1].strip()
    bw_type = "regex" if any(ch in pattern for ch in ".^$*+?{}[]|()") else "word"
    # validate regex
    if bw_type == "regex":
        try:
            re.compile(pattern)
        except re.error:
            return await message.reply_text("❌ Invalid regex pattern.")
    blockwords_coll.insert_one({"pattern": pattern, "type": bw_type})
    # refresh compiled list
    global BLOCKWORDS
    BLOCKWORDS = load_blockwords()
    # remove text replies that match the new pattern (only delete text entries from chatbot_coll)
    if bw_type == "regex":
        try:
            chatbot_coll.delete_many({"text": {"$regex": pattern, "$options": "i"}})
        except Exception:
            pass
    else:
        chatbot_coll.delete_many({"text": {"$regex": re.escape(pattern), "$options": "i"}})
    load_replies_cache()
    await message.reply_text(f"✔ Added block pattern: `{pattern}` (type: {bw_type})")

@app.on_message(filters.command("rmblock") & filters.user(SUDOERS))
async def rm_blockword(client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("Usage: /rmblock <word_or_regex>")
    pattern = parts[1].strip()
    blockwords_coll.delete_one({"pattern": pattern})
    global BLOCKWORDS
    BLOCKWORDS = load_blockwords()
    await message.reply_text(f"✔ Removed blocked entry: `{pattern}`")

@app.on_message(filters.command("listblock") & filters.user(SUDOERS))
async def list_block(client, message: Message):
    if not BLOCKWORDS:
        return await message.reply_text("Blocklist is empty.")
    txt = "**🔐 GLOBAL BLOCK PATTERNS:**\n\n"
    for b in BLOCKWORDS:
        txt += f"• `{b['pattern']}`  (type: {b['type']})\n"
    await message.reply_text(txt)

# -------------------- Main chatbot handler (TEXT-ONLY SEND) -------------------- #
@app.on_message(filters.incoming & ~filters.me, group=99)
async def chatbot_handler(client, message: Message):
    # quick guards
    if message.edit_date:
        return
    if not message.from_user:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    now = datetime.utcnow()

    # SPAM CHECK / TEMP BLOCK
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

    # chatbot enabled check
    s = status_coll.find_one({"chat_id": chat_id})
    if s and s.get("status") == "disabled":
        return

    # ignore commands
    if message.text and message.text.split()[0].startswith("/"):
        return

    # should bot reply? only when message replies to bot or not (config here: reply-to-bot OR any message)
    should_reply = False
    if message.reply_to_message:
        bot = await client.get_me()
        if message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot.id:
            should_reply = True
    else:
        should_reply = True
    if not should_reply:
        return

    # blocked incoming text?
    if message.text and is_blocked_text(message.text):
        return

    # lookup reply (text-first, fallback to learned store)
    query_text = normalize_word(message.text or "")
    r = get_reply_sync(query_text) or get_reply_sync2(query_text)
    if not r:
        try:
            await message.reply_text("I don't understand. 🤔")
        except Exception:
            pass
        return

    kind = r.get("kind", "text")
    response_text = r.get("text") if r.get("kind") == "text" else None

    # If stored reply is media-only (non-text), we will NOT send media.
    # Option B: keep media in DB but never send it. We'll send a safe textual placeholder or any available caption/text.
    if kind != "text":
        # if the DB entry also stored textual fallback (rare), use it
        if isinstance(r.get("text"), str) and r.get("text").strip():
            response_text = r.get("text")
        else:
            # generic textual placeholder for media-only replies
            response_text = "[This response contains media which is disabled. Please ask for a text reply.]"

    # translation (only for text content)
    lang = None
    try:
        lang = await (lambda cid: get_chat_language(cid))(chat_id)  # small inline call to keep structure
    except Exception:
        lang = None

    if response_text and lang and lang != "nolang":
        try:
            response_text = translator.translate(response_text, target=lang)
        except Exception:
            pass

    # final block-check on what we will send
    if is_blocked_text(response_text):
        return

    # send text-only reply
    try:
        await message.reply_text(response_text or "I don't understand.")
    except Exception:
        try:
            await message.reply_text("I don't understand.")
        except Exception:
            pass

# -------------------- Learning hooks -------------------- #
@app.on_message(filters.reply & filters.group)
async def learn_reply_group(client, message: Message):
    if not message.reply_to_message:
        return
    bot = await client.get_me()
    if message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot.id:
        # save both text-only database (chatbot_coll) if it's text,
        # and also the full chatai store (which may include media) for Option B
        await save_text_reply(message.reply_to_message, message)
        await save_reply_full(message.reply_to_message, message)

@app.on_message(filters.reply & filters.private)
async def learn_reply_private(client, message: Message):
    if not message.reply_to_message:
        return
    bot = await client.get_me()
    if message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot.id:
        await save_text_reply(message.reply_to_message, message)
        await save_reply_full(message.reply_to_message, message)

# -------------------- Chatbot UI (group/private) -------------------- #
@app.on_message(filters.command("chatbot") & filters.group)
async def chatbot_settings_group(client, message: Message):
    if not await is_user_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Only admins can manage chatbot settings.")
    doc = status_coll.find_one({"chat_id": message.chat.id})
    enabled = not doc or doc.get("status") == "enabled"
    txt = f"**🤖 Chatbot Settings**\nCurrent Status: {'🟢 Enabled' if enabled else '🔴 Disabled'}"
    await message.reply_text(txt, reply_markup=chatbot_keyboard(enabled))

@app.on_message(filters.command("chatbot") & filters.private)
async def chatbot_settings_private(client, message: Message):
    doc = status_coll.find_one({"chat_id": message.chat.id})
    enabled = not doc or doc.get("status") == "enabled"
    await message.reply_text(f"🤖 Chatbot (private)\nStatus: {'🟢 Enabled' if enabled else '🔴 Disabled'}",
                             reply_markup=chatbot_keyboard(enabled))

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

# -------------------- Language setting -------------------- #
@app.on_message(filters.command("setlang") & filters.group)
async def setlang_group(client, message: Message):
    if not await is_user_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Only admins can set language.")
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("Usage: /setlang <code>")
    lang = parts[1].strip()
    lang_coll.update_one({"chat_id": message.chat.id}, {"$set": {"language": lang}}, upsert=True)
    await message.reply_text(f"✅ Language set to `{lang}`")

@app.on_message(filters.command("setlang") & filters.private)
async def setlang_private(client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("Usage: /setlang <code>")
    lang = parts[1].strip()
    lang_coll.update_one({"chat_id": message.chat.id}, {"$set": {"language": lang}}, upsert=True)
    await message.reply_text(f"✅ Language set to `{lang}`")
