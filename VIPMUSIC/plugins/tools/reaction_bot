import os
import json
import random
import asyncio
from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.errors import RPCError
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from VIPMUSIC import app
from VIPMUSIC.misc import SUDOERS
from config import START_REACTIONS
from VIPMUSIC.utils.vip_ban import admin_filter

# File to store chat reaction states
REACTION_DB_FILE = "reaction_db.json"

# ---------------- LOAD / SAVE FUNCTIONS ---------------- #

def load_reaction_db():
    if os.path.exists(REACTION_DB_FILE):
        with open(REACTION_DB_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_reaction_db(data):
    with open(REACTION_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# Initialize database
REACTION_DB = load_reaction_db()


# ---------------- UTILS ---------------- #

def get_reactions():
    """Return list of available emojis from config."""
    if isinstance(START_REACTIONS, list) and START_REACTIONS:
        return START_REACTIONS
    return ["❤️", "🔥", "😂", "😍", "👍", "💯", "😎", "👏"]


def is_authorized(user_id):
    """Check if user is sudo or admin via decorator."""
    return user_id in SUDOERS


# ---------------- /REACTIONON COMMAND ---------------- #

@app.on_message(filters.command("reactionon", ["/", "!", "%", ".", ",", "@", "#", ""]) & admin_filter)
async def reaction_on(app: app, msg: Message):
    chat_id = str(msg.chat.id)

    if msg.chat.type not in [ChatType.SUPERGROUP, ChatType.GROUP]:
        await msg.reply_text("**ʀᴇᴀᴄᴛɪᴏɴs ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴇɴᴀʙʟᴇᴅ ɪɴ ɢʀᴏᴜᴘs.**")
        return

    REACTION_DB[chat_id] = True
    save_reaction_db(REACTION_DB)
    await msg.reply_text("**✅ ʀᴇᴀᴄᴛɪᴏɴs ᴇɴᴀʙʟᴇᴅ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ.**")


# ---------------- /REACTIONOFF COMMAND ---------------- #

@app.on_message(filters.command("reactionoff", ["/", "!", "%", ".", ",", "@", "#", ""]) & admin_filter)
async def reaction_off(app: app, msg: Message):
    chat_id = str(msg.chat.id)

    if msg.chat.type not in [ChatType.SUPERGROUP, ChatType.GROUP]:
        await msg.reply_text("**ʀᴇᴀᴄᴛɪᴏɴs ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴅɪsᴀʙʟᴇᴅ ɪɴ ɢʀᴏᴜᴘs.**")
        return

    REACTION_DB[chat_id] = False
    save_reaction_db(REACTION_DB)
    await msg.reply_text("**🚫 ʀᴇᴀᴄᴛɪᴏɴs ᴅɪsᴀʙʟᴇᴅ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ.**")


# ---------------- /REACTION (BUTTON CONTROL) ---------------- #

@app.on_message(filters.command("reaction", ["/", "!", "%", ".", ",", "@", "#", ""]) & admin_filter)
async def reaction_settings(app: app, msg: Message):
    chat_id = str(msg.chat.id)
    status = REACTION_DB.get(chat_id, False)

    text = (
        f"**📢 ʀᴇᴀᴄᴛɪᴏɴ sᴇᴛᴛɪɴɢs ғᴏʀ ᴛʜɪs ɢʀᴏᴜᴘ**\n\n"
        f"**🆔 ɢʀᴏᴜᴘ ɪᴅ:** `{chat_id}`\n"
        f"**⚙️ sᴛᴀᴛᴜs:** {'✅ ᴇɴᴀʙʟᴇᴅ' if status else '🚫 ᴅɪsᴀʙʟᴇᴅ'}"
    )

    buttons = [
        [
            InlineKeyboardButton("✅ Enable", callback_data=f"reaction_enable:{chat_id}"),
            InlineKeyboardButton("🚫 Disable", callback_data=f"reaction_disable:{chat_id}")
        ]
    ]

    await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ---------------- CALLBACK HANDLER ---------------- #

@app.on_callback_query(filters.regex(r"^reaction_(enable|disable):"))
async def reaction_callback(app, query):
    user_id = query.from_user.id
    if not (await admin_filter(app, query.message) or user_id in SUDOERS):
        await query.answer("🚫 You are not authorized to change this setting.", show_alert=True)
        return

    action, chat_id = query.data.split(":")
    chat_id = str(chat_id)

    if action == "enable":
        REACTION_DB[chat_id] = True
        text = "**✅ ʀᴇᴀᴄᴛɪᴏɴs ᴀʀᴇ ɴᴏᴡ ᴇɴᴀʙʟᴇᴅ.**"
    else:
        REACTION_DB[chat_id] = False
        text = "**🚫 ʀᴇᴀᴄᴛɪᴏɴs ᴀʀᴇ ɴᴏᴡ ᴅɪsᴀʙʟᴇᴅ.**"

    save_reaction_db(REACTION_DB)
    await query.message.edit_text(text)
    await query.answer("Updated successfully ✅")


# ---------------- AUTO REACTION ---------------- #

@app.on_message(filters.text & filters.group)
async def auto_reaction_handler(app: app, msg: Message):
    chat_id = str(msg.chat.id)
    if not REACTION_DB.get(chat_id, False):
        return

    if not msg.from_user or msg.from_user.is_bot:
        return

    reaction_list = get_reactions()
    emoji = random.choice(reaction_list)

    try:
        await asyncio.sleep(random.uniform(0.6, 1.8))
        await msg.react(emoji)
    except RPCError:
        pass  # Ignore if Telegram restricts reaction
