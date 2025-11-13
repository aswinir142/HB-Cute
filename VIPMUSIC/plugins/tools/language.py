from pykeyboard import InlineKeyboard
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, Message, ChatMemberUpdated

from VIPMUSIC import app
from VIPMUSIC.utils.database import get_lang, set_lang
from VIPMUSIC.utils.decorators import ActualAdminCB, language, languageCB
from config import BANNED_USERS
from strings import get_string, languages_present

print("[language] setlang")


# Language selection keyboard
def languages_keyboard(_):
    keyboard = InlineKeyboard(row_width=2)
    keyboard.add(
        *[
            InlineKeyboardButton(
                text=languages_present[i],
                callback_data=f"languages:{i}",
            )
            for i in languages_present
        ]
    )
    keyboard.row(
        InlineKeyboardButton(
            text=_["BACK_BUTTON"],
            callback_data="settingsback_helper",
        ),
        InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close"),
    )
    return keyboard


# Command: /lang, /setlang, /language
@app.on_message(filters.command(["lang", "setlang", "language"]) & ~BANNED_USERS)
@language
async def langs_command(client, message: Message, _):
    keyboard = languages_keyboard(_)
    await message.reply_text(
        _["lang_1"],
        reply_markup=keyboard,
    )


# Callback for "LG" regex
@app.on_callback_query(filters.regex("LG") & ~BANNED_USERS)
@languageCB
async def languagecb(client, CallbackQuery, _):
    try:
        await CallbackQuery.answer()
    except:
        pass
    keyboard = languages_keyboard(_)
    return await CallbackQuery.edit_message_reply_markup(reply_markup=keyboard)


# Language selection callback
@app.on_callback_query(filters.regex(r"languages:(.*?)") & ~BANNED_USERS)
@ActualAdminCB
async def language_markup(client, CallbackQuery, _):
    language = (CallbackQuery.data).split(":")[1]
    old = await get_lang(CallbackQuery.message.chat.id)
    if str(old) == str(language):
        return await CallbackQuery.answer(_["lang_4"], show_alert=True)
    try:
        _ = get_string(language)
        await CallbackQuery.answer(_["lang_2"], show_alert=True)
    except:
        _ = get_string(old)
        return await CallbackQuery.answer(_["lang_3"], show_alert=True)
    await set_lang(CallbackQuery.message.chat.id, language)
    keyboard = languages_keyboard(_)
    return await CallbackQuery.edit_message_reply_markup(reply_markup=keyboard)


# Auto-send language message when bot is added to a group
@app.on_chat_member_updated(filters.group)
async def auto_set_language(client, chat_member_updated: ChatMemberUpdated):
    # Check if bot was just added
    if (
        chat_member_updated.new_chat_member
        and chat_member_updated.new_chat_member.user.id == (await client.get_me()).id
    ):
        chat = chat_member_updated.chat
        print(f"[language auto] Bot added to group: {chat.title} ({chat.id})")

        # Default to English language texts
        _ = get_string("en")

        # Create keyboard
        keyboard = InlineKeyboard(row_width=2)
        keyboard.add(
            *[
                InlineKeyboardButton(
                    text=languages_present[i],
                    callback_data=f"languages:{i}",
                )
                for i in languages_present
            ]
        )
        keyboard.row(
            InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close")
        )

        # Caption message
        caption = (
            "» ᴘʟᴇᴀsᴇ ᴄʜᴏᴏsᴇ ᴛʜᴇ ʟᴀɴɢᴜᴀɢᴇ ᴡʜɪᴄʜ ʏᴏᴜ ᴡᴀɴɴᴀ sᴇᴛ ᴀs "
            "ᴛʜɪs ɢʀᴏᴜᴘ's ᴅᴇғᴀᴜʟᴛ ʟᴀɴɢᴜᴀɢᴇ :"
        )

        try:
            await client.send_message(
                chat.id,
                caption,
                reply_markup=keyboard,
            )
        except Exception as e:
            print(f"[language auto] Failed to send in {chat.id}: {e}")
