from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.errors import RPCError
from pyrogram.types import Message
from VIPMUSIC import app
from VIPMUSIC.utils.vip_ban import admin_filter
from config import START_REACTIONS
import random
import asyncio

# In-memory toggle storage for each chat
REACTION_STATUS = {}

# Command prefixes to match your repo style
PREFIXES = ["/", "!", "%", ",", ".", "@", "#", ""]

# Function to get reactions safely
def get_reactions():
    if isinstance(START_REACTIONS, list) and START_REACTIONS:
        return START_REACTIONS
    # Default fallback if empty or misconfigured
    return ["❤️", "🔥", "😂", "😍", "👍", "💯", "😎", "👏"]

# ---------------- REACTION ON ---------------- #
@app.on_message(filters.command("reactionon", PREFIXES) & admin_filter)
async def enable_reaction(app: app, msg: Message):
    chat_id = msg.chat.id

    if msg.chat.type != ChatType.SUPERGROUP:
        await msg.reply_text("**ʀᴇᴀᴄᴛɪᴏɴs ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴇɴᴀʙʟᴇᴅ ɪɴ sᴜᴘᴇʀɢʀᴏᴜᴘs.**")
        return

    REACTION_STATUS[chat_id] = True
    await msg.reply_text("**✅ ʀᴇᴀᴄᴛɪᴏɴs ᴀʀᴇ ɴᴏᴡ ᴇɴᴀʙʟᴇᴅ ɪɴ ᴛʜɪs ᴄʜᴀᴛ.**")


# ---------------- REACTION OFF ---------------- #
@app.on_message(filters.command("reactionoff", PREFIXES) & admin_filter)
async def disable_reaction(app: app, msg: Message):
    chat_id = msg.chat.id

    if msg.chat.type != ChatType.SUPERGROUP:
        await msg.reply_text("**ʀᴇᴀᴄᴛɪᴏɴs ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴅɪsᴀʙʟᴇᴅ ɪɴ sᴜᴘᴇʀɢʀᴏᴜᴘs.**")
        return

    REACTION_STATUS[chat_id] = False
    await msg.reply_text("**🚫 ʀᴇᴀᴄᴛɪᴏɴs ʜᴀᴠᴇ ʙᴇᴇɴ ᴅɪsᴀʙʟᴇᴅ ɪɴ ᴛʜɪs ᴄʜᴀᴛ.**")


# ---------------- MANUAL REACTION ---------------- #
@app.on_message(filters.command("reaction", PREFIXES) & admin_filter)
async def manual_reaction(app: app, msg: Message):
    if not msg.reply_to_message:
        await msg.reply_text("**ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ ʀᴇᴀᴄᴛ.**")
        return

    chat_id = msg.chat.id
    reaction_list = get_reactions()
    emoji = random.choice(reaction_list)

    try:
        await msg.reply_to_message.react(emoji)
        await msg.reply_text(f"**ʀᴇᴀᴄᴛᴇᴅ ᴡɪᴛʜ {emoji}**")
    except RPCError as e:
        await msg.reply_text(f"**❌ ᴇʀʀᴏʀ:** `{e}`")


# ---------------- AUTO REACTION ---------------- #
@app.on_message(filters.text & filters.group)
async def auto_reaction(app: app, msg: Message):
    chat_id = msg.chat.id

    # Only react if reactions are enabled
    if not REACTION_STATUS.get(chat_id, False):
        return

    # Avoid reacting to bot/system messages
    if msg.from_user is None or msg.from_user.is_bot:
        return

    reaction_list = get_reactions()
    emoji = random.choice(reaction_list)

    try:
        # Add random delay to look natural
        await asyncio.sleep(random.uniform(0.8, 2.0))
        await msg.react(emoji)
    except RPCError:
        pass  # Silently ignore any Telegram reaction errors
