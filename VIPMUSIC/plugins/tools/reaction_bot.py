from VIPMUSIC import app
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from VIPMUSIC.misc import SUDOERS
from VIPMUSIC.utils.databases.reactiondb import is_reaction_on, reaction_on, reaction_off
import json
from config import START_REACTIONS, OWNER_ID

print("[ReactionBot] Plugin loaded!")

# ------------------------------
# Command: /reactionon
# ------------------------------
@app.on_message(filters.command("reactionon") & (filters.group) & SUDOERS)
async def reaction_on_command(client: Client, message: Message):
    chat_id = message.chat.id
    await reaction_on(chat_id)
    await message.reply_text(
        "✅ Reaction has been turned ON for this chat.",
    )
    print(f"[ReactionBot] Reaction ON triggered in chat {chat_id}")


# ------------------------------
# Command: /reactionoff
# ------------------------------
@app.on_message(filters.command("reactionoff") & (filters.group) & SUDOERS)
async def reaction_off_command(client: Client, message: Message):
    chat_id = message.chat.id
    await reaction_off(chat_id)
    await message.reply_text(
        "❌ Reaction has been turned OFF for this chat.",
    )
    print(f"[ReactionBot] Reaction OFF triggered in chat {chat_id}")


# ------------------------------
# Command: /reaction (show buttons)
# ------------------------------
@app.on_message(filters.command("reaction") & (filters.group) & SUDOERS)
async def reaction_button_command(client: Client, message: Message):
    chat_id = message.chat.id
    on_off_status = await is_reaction_on(chat_id)
    status_text = "✅ ENABLED" if on_off_status else "❌ DISABLED"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Enable ✅", callback_data=f"reaction_enable:{chat_id}"),
                InlineKeyboardButton("Disable ❌", callback_data=f"reaction_disable:{chat_id}"),
            ]
        ]
    )

    await message.reply_text(
        f"Reaction is currently: {status_text}",
        reply_markup=keyboard,
    )


# ------------------------------
# Callback handler for buttons
# ------------------------------
@app.on_callback_query(filters.regex(r"reaction_(enable|disable):"))
async def reaction_button_callback(client: Client, callback_query):
    data = callback_query.data
    action, chat_id_str = data.split(":")
    chat_id = int(chat_id_str)

    if action == "enable":
        await reaction_on(chat_id)
        await callback_query.answer("✅ Reaction enabled")
        await callback_query.message.edit(f"Reaction is currently: ✅ ENABLED")
        print(f"[ReactionBot] Reaction ENABLED via button in chat {chat_id}")
    else:
        await reaction_off(chat_id)
        await callback_query.answer("❌ Reaction disabled")
        await callback_query.message.edit(f"Reaction is currently: ❌ DISABLED")
        print(f"[ReactionBot] Reaction DISABLED via button in chat {chat_id}")


# ------------------------------
# Auto-reaction handler (example)
# ------------------------------
@app.on_message((filters.text | filters.caption) & filters.group)
async def auto_react_messages(client: Client, message: Message):
    chat_id = message.chat.id
    if await is_reaction_on(chat_id):
        from config import START_REACTIONS
        import random
        try:
            emoji = random.choice(START_REACTIONS)
            await message.reply_text(emoji)
        except Exception as e:
            print(f"[ReactionBot] Failed to react in chat {chat_id}: {e}")
