import random
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from VIPMUSIC import app
from VIPMUSIC.utils.databases.reactiondb import is_reaction_on, reaction_on, reaction_off
from VIPMUSIC.misc import SUDOERS
from config import OWNER_ID, START_REACTIONS

print("[ReactionBot] Plugin loaded!")

# ------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------

async def is_admin_or_sudo(client, message: Message) -> bool:
    """Check if user is admin, sudo, or owner"""
    if message.from_user is None:
        return False

    user_id = message.from_user.id

    # Owner or Sudo
    if user_id == OWNER_ID or user_id in SUDOERS:
        return True

    try:
        member = await message.chat.get_member(user_id)
        if member.status in ("administrator", "creator"):
            return True
    except Exception:
        pass

    return False


def reaction_buttons(status: bool):
    """Enable/Disable buttons layout"""
    if status:
        text = "✅ Reaction is currently *Enabled*"
        buttons = [
            [InlineKeyboardButton("🛑 Disable", callback_data="reaction_disable")]
        ]
    else:
        text = "❌ Reaction is currently *Disabled*"
        buttons = [
            [InlineKeyboardButton("✅ Enable", callback_data="reaction_enable")]
        ]
    return text, InlineKeyboardMarkup(buttons)


# ------------------------------------------------------------
# Commands
# ------------------------------------------------------------

@app.on_message(filters.command(["reactionon"], prefixes=["/", "!", "."]) & filters.group)
async def cmd_reaction_on(client, message):
    if not await is_admin_or_sudo(client, message):
        return await message.reply_text("🚫 You don’t have permission to use this command.")

    await reaction_on(message.chat.id)
    await message.reply_text("✅ Reactions enabled for this group.")


@app.on_message(filters.command(["reactionoff"], prefixes=["/", "!", "."]) & filters.group)
async def cmd_reaction_off(client, message):
    if not await is_admin_or_sudo(client, message):
        return await message.reply_text("🚫 You don’t have permission to use this command.")

    await reaction_off(message.chat.id)
    await message.reply_text("🛑 Reactions disabled for this group.")


@app.on_message(filters.command(["reaction"], prefixes=["/", "!", "."]) & filters.group)
async def cmd_reaction_status(client, message):
    if not await is_admin_or_sudo(client, message):
        return await message.reply_text("🚫 You don’t have permission to use this command.")

    status = await is_reaction_on(message.chat.id)
    text, keyboard = reaction_buttons(status)
    await message.reply_text(text, reply_markup=keyboard)


# ------------------------------------------------------------
# Callback Query Handler (Buttons)
# ------------------------------------------------------------

@app.on_callback_query(filters.regex("^reaction_"))
async def callback_reaction_handler(client, callback_query):
    user = callback_query.from_user
    chat_id = callback_query.message.chat.id
    data = callback_query.data

    # Permission check
    try:
        member = await callback_query.message.chat.get_member(user.id)
        if (
            user.id != OWNER_ID
            and user.id not in SUDOERS
            and member.status not in ("administrator", "creator")
        ):
            return await callback_query.answer("🚫 Only admins or sudo users can change this.", show_alert=True)
    except Exception:
        return await callback_query.answer("❌ Failed to verify permissions.", show_alert=True)

    if data == "reaction_enable":
        await reaction_on(chat_id)
        text, keyboard = reaction_buttons(True)
        await callback_query.message.edit_text(text, reply_markup=keyboard)
        await callback_query.answer("✅ Reaction enabled!")

    elif data == "reaction_disable":
        await reaction_off(chat_id)
        text, keyboard = reaction_buttons(False)
        await callback_query.message.edit_text(text, reply_markup=keyboard)
        await callback_query.answer("🛑 Reaction disabled!")


# ------------------------------------------------------------
# Reaction Message Listener
# ------------------------------------------------------------

@app.on_message((filters.text | filters.caption) & filters.group)
async def random_reaction_listener(client, message):
    # Skip service messages or commands
    if message.text and message.text.startswith(("/", "!", ".")):
        return

    status = await is_reaction_on(message.chat.id)
    if not status:
        return

    try:
        emoji = random.choice(START_REACTIONS)
        await message.react(emoji)
    except Exception:
        pass


# ------------------------------------------------------------
# Simple Test Command (For Debug)
# ------------------------------------------------------------
@app.on_message(filters.command("reactiontest") & filters.group)
async def test_react_cmd(_, message):
    print("[ReactionBot] /reactiontest command triggered!")
    await message.reply_text("✅ Reaction test command works!")
