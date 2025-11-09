import asyncio
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from VIPMUSIC import app, REACTION_BOT
from VIPMUSIC.utils.database import get_sudoers
from VIPMUSIC.utils.database.reactiondb import (
    get_reaction_status,
    set_reaction_status,
)
from VIPMUSIC.misc import SUDOERS
from VIPMUSIC.utils.decorators import AdminRightsCheck
from VIPMUSIC.utils.filters import command

BANNED_USERS = filters.user([])

# ------------------------------
# 🔘 BUTTON LAYOUT
# ------------------------------
def reaction_buttons(chat_id: int):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Enable", callback_data=f"reactionon_{chat_id}"),
                InlineKeyboardButton("🚫 Disable", callback_data=f"reactionoff_{chat_id}"),
            ]
        ]
    )

# ------------------------------
# ⚙️ REACTION COMMAND HANDLER
# ------------------------------
@app.on_message(command("reaction") & ~BANNED_USERS)
@AdminRightsCheck
async def reaction_toggle(client, message):
    if message.chat.type not in ["group", "supergroup"]:
        return await message.reply_text("❌ This command can be used only in groups.")

    sudoers = await get_sudoers()
    if message.from_user.id not in sudoers and not message.from_user.id in SUDOERS:
        return await message.reply_text("🚫 Only admins or sudo users can manage reactions.")

    chat_id = message.chat.id
    current_status = await get_reaction_status(chat_id)

    if len(message.command) == 1:
        status_text = "🟢 Enabled" if current_status else "🔴 Disabled"
        return await message.reply_text(
            f"**Reaction Bot is currently {status_text} for this chat.**\n\nUse buttons below to toggle:",
            reply_markup=reaction_buttons(chat_id),
        )

    arg = message.command[1].lower()
    if arg == "on":
        await set_reaction_status(chat_id, True)
        await message.reply_text("✅ Reaction Bot **enabled** for this chat.")
    elif arg == "off":
        await set_reaction_status(chat_id, False)
        await message.reply_text("🚫 Reaction Bot **disabled** for this chat.")
    else:
        await message.reply_text("Usage:\n`/reaction on` or `/reaction off`")

# ------------------------------
# 🔘 BUTTON CALLBACK HANDLERS
# ------------------------------
@app.on_callback_query(filters.regex(r"^reactionon_(\d+)$"))
async def cb_enable_reaction(client, query):
    chat_id = int(query.data.split("_")[1])
    await set_reaction_status(chat_id, True)
    await query.message.edit_text(
        "✅ Reaction Bot **enabled** for this chat.",
        reply_markup=reaction_buttons(chat_id),
    )

@app.on_callback_query(filters.regex(r"^reactionoff_(\d+)$"))
async def cb_disable_reaction(client, query):
    chat_id = int(query.data.split("_")[1])
    await set_reaction_status(chat_id, False)
    await query.message.edit_text(
        "🚫 Reaction Bot **disabled** for this chat.",
        reply_markup=reaction_buttons(chat_id),
    )

# ------------------------------
# 🤖 MESSAGE REACTOR
# ------------------------------
@app.on_message(filters.all & ~BANNED_USERS)
async def auto_reactor(client, message):
    if not REACTION_BOT:
        return  # disabled globally in config

    if message.chat.type not in ["group", "supergroup", "private"]:
        return

    chat_id = message.chat.id
    status = await get_reaction_status(chat_id)
    if not status:
        return  # Reaction disabled in this chat

    # Skip own messages
    if message.from_user and message.from_user.is_self:
        return

    # Rotate emoji logic (per chat rotation handled in reaction.py)
    from VIPMUSIC.plugins.tools.reaction import next_emoji
    try:
        emoji = next_emoji(chat_id)
        await message.react(emoji)
    except Exception as e:
        print(f"[ReactionBot] Failed to react in {chat_id}: {e}")
