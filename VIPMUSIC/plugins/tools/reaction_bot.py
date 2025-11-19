# ================================
#      FINAL REACTION BOT
# ================================
import asyncio
import random
from typing import Set, Dict, Optional, Tuple

from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatType, ChatMemberStatus

from VIPMUSIC import app
from VIPMUSIC.utils.database import mongodb, get_sudoers
from config import BANNED_USERS, OWNER_ID, START_REACTIONS

print("[reaction_bot] loaded")

# ---------------- DB ----------------
MENTION_DB = mongodb["reaction_mentions"]
SWITCH_DB = mongodb["reaction_settings"]  # ON/OFF toggle

# ---------------- STATE ----------------
REACTION_ENABLED = True

# ---------------- CACHE ----------------
custom_mentions: Set[str] = set()

VALID_REACTIONS = {
    "❤️", "💖", "💘", "💞", "💓", "✨", "🔥", "💫",
    "💥", "🌸", "😍", "🥰", "💎", "🌙", "🌹", "😂",
    "😎", "🤩", "😘", "😉", "🤭", "💐", "😻", "🥳"
}

SAFE_REACTIONS = [e for e in START_REACTIONS if e in VALID_REACTIONS]
if not SAFE_REACTIONS:
    SAFE_REACTIONS = list(VALID_REACTIONS)

chat_used_reactions: Dict[int, Set[str]] = {}


def next_emoji(chat_id: int) -> str:
    if chat_id not in chat_used_reactions:
        chat_used_reactions[chat_id] = set()

    used = chat_used_reactions[chat_id]
    if len(used) >= len(SAFE_REACTIONS):
        used.clear()

    remaining = [x for x in SAFE_REACTIONS if x not in used]
    emoji = random.choice(remaining)

    used.add(emoji)
    chat_used_reactions[chat_id] = used
    return emoji


# ---------------- LOAD TRIGGERS ----------------
async def load_custom():
    try:
        docs = await MENTION_DB.find().to_list(length=None)
        for d in docs:
            name = d.get("name")
            if name:
                custom_mentions.add(name.lower().lstrip("@"))
        print(f"[reaction_bot] triggers loaded: {len(custom_mentions)}")
    except Exception as e:
        print(f"[reaction_bot] load error: {e}")


asyncio.get_event_loop().create_task(load_custom())


# ---------------- LOAD SWITCH STATE ----------------
async def load_switch():
    global REACTION_ENABLED
    doc = await SWITCH_DB.find_one({"_id": "switch"})
    if doc:
        REACTION_ENABLED = doc.get("enabled", True)

    print(f"[reaction_bot] switch loaded => {REACTION_ENABLED}")


asyncio.get_event_loop().create_task(load_switch())


# ---------------- ADMIN CHECK ----------------
async def is_admin(client, message: Message) -> Tuple[bool, Optional[str]]:
    user = message.from_user
    chat = message.chat

    if not user or not chat:
        return False, "invalid message"

    user_id = user.id
    cid = chat.id

    try:
        sudo = await get_sudoers()
    except:
        sudo = set()

    if user_id == OWNER_ID or user_id in sudo:
        return True, None

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
        return False, f"bad_chat_type={chat.type}"

    try:
        mem = await client.get_chat_member(cid, user_id)
        if mem.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            return True, None
        return False, f"user_status={mem.status}"
    except Exception as e:
        return False, f"get_chat_member_error={e}"


# ---------------- /reaction PANEL ----------------
@app.on_message(filters.command("reaction") & ~BANNED_USERS)
async def reaction_panel(client, message: Message):
    ok, debug = await is_admin(client, message)
    if not ok:
        return await message.reply_text(f"⚠️ Admin only.\nDebug: `{debug}`")

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Enable", callback_data="react_on"),
                InlineKeyboardButton("🛑 Disable", callback_data="react_off")
            ],
            [InlineKeyboardButton("🔍 Status", callback_data="react_status")]
        ]
    )

    await message.reply_text(
        f"**Reaction System**\n\nCurrent: {'🟢 ON' if REACTION_ENABLED else '🔴 OFF'}",
        reply_markup=kb
    )


# ---------------- CALLBACK ----------------
@app.on_callback_query(filters.regex("^react_"))
async def cb_handler(client, cq: CallbackQuery):
    global REACTION_ENABLED

    ok, debug = await is_admin(client, cq.message)
    if not ok:
        return await cq.answer("Admins only.", show_alert=True)

    if cq.data == "react_on":
        REACTION_ENABLED = True
        await SWITCH_DB.update_one({"_id": "switch"}, {"$set": {"enabled": True}}, upsert=True)
        return await cq.edit_message_text("✅ **Reactions Enabled**")

    if cq.data == "react_off":
        REACTION_ENABLED = False
        await SWITCH_DB.update_one({"_id": "switch"}, {"$set": {"enabled": False}}, upsert=True)
        return await cq.edit_message_text("🛑 **Reactions Disabled**")

    if cq.data == "react_status":
        return await cq.answer(
            f"Reactions are {'ON' if REACTION_ENABLED else 'OFF'}",
            show_alert=True
        )


# ---------------- AUTO REACT LISTENER ----------------
@app.on_message(
    (filters.text | filters.caption)
    & ~filters.command(["reaction", "addreact", "delreact", "clearreact", "reactlist"])
    & ~BANNED_USERS
)
async def auto_react(client, message: Message):

    if not REACTION_ENABLED:
        return

    try:
        raw = message.text or message.caption
        if not raw:
            return

        text = raw.lower()
        chat_id = message.chat.id

        # Ignore if starts like command
        if text.startswith(("/", "!", ".", "$", "#")):
            return

        words = set(text.replace("@", " @").split())

        entities = (message.entities or []) + (message.caption_entities or [])
        mentioned_usernames = set()
        mentioned_ids = set()

        for e in entities:
            try:
                src = raw
                if e.type == "mention":
                    uname = src[e.offset:e.offset + e.length]
                    mentioned_usernames.add(uname.lstrip("@").lower())
                elif e.type == "text_mention" and e.user:
                    mentioned_ids.add(e.user.id)
                    if e.user.username:
                        mentioned_usernames.add(e.user.username.lower())
            except:
                continue

        # Match username triggers
        for u in mentioned_usernames:
            if u in custom_mentions:
                return await message.react(next_emoji(chat_id))

        # Match ID triggers
        for uid in mentioned_ids:
            if f"id:{uid}" in custom_mentions:
                return await message.react(next_emoji(chat_id))

        # Match keyword triggers
        for trig in custom_mentions:
            if trig.startswith("id:"):
                continue
            if trig in words or f"@{trig}" in words:
                return await message.react(next_emoji(chat_id))

    except Exception as e:
        print(f"[reaction_bot error] {e}")
