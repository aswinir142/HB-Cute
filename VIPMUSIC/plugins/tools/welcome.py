from VIPMUSIC import app
from pyrogram import filters, enums
from pyrogram.types import ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from VIPMUSIC.utils.database import get_lang, set_lang
from VIPMUSIC.utils.decorators import languageCB, ActualAdminCB
from strings import get_string, languages_present
from pykeyboard import InlineKeyboard
from logging import getLogger
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageChops
import os, random

LOGGER = getLogger(__name__)

# Random welcome backgrounds
random_photo = [
    "https://telegra.ph/file/1949480f01355b4e87d26.jpg",
    "https://telegra.ph/file/3ef2cc0ad2bc548bafb30.jpg",
    "https://telegra.ph/file/a7d663cd2de689b811729.jpg",
    "https://telegra.ph/file/6f19dc23847f5b005e922.jpg",
    "https://telegra.ph/file/2973150dd62fd27a3a6ba.jpg",
]


# ---------------------------- DATABASE SIMULATION ----------------------------
class WelDatabase:
    def __init__(self):
        self.data = {}

    async def find_one(self, chat_id):
        return chat_id in self.data

    async def add_wlcm(self, chat_id):
        if chat_id not in self.data:
            self.data[chat_id] = {"state": "off"}  # Default disabled

    async def rm_wlcm(self, chat_id):
        if chat_id in self.data:
            del self.data[chat_id]


wlcm = WelDatabase()


# ---------------------------- IMAGE CREATION ----------------------------
def circle(pfp, size=(500, 500), brightness_factor=1.2):
    pfp = pfp.resize(size).convert("RGBA")
    pfp = ImageEnhance.Brightness(pfp).enhance(brightness_factor)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size[0], size[1]), fill=255)
    pfp.putalpha(mask)
    return pfp


def welcomepic(pic, user, chatname, uid, uname):
    background = Image.open("VIPMUSIC/assets/wel2.png")
    pfp = Image.open(pic).convert("RGBA")
    pfp = circle(pfp, (892, 880))
    draw = ImageDraw.Draw(background)
    font = ImageFont.truetype("VIPMUSIC/assets/font.ttf", size=95)

    # Draw text
    draw.text((1820, 1080), f": {user}", fill=(200, 0, 0), font=font)
    draw.text((1620, 1280), f": {uid}", fill=(255, 255, 255), font=font)
    draw.text((2000, 1510), f": {uname}", fill=(255, 255, 255), font=font)

    # Paste pfp
    background.paste(pfp, (265, 360), pfp)
    out_path = f"downloads/welcome_{uid}.png"
    background.save(out_path)
    return out_path


# ---------------------------- WELCOME TOGGLE ----------------------------
@app.on_message(filters.command("welcome") & ~filters.private)
async def toggle_welcome(_, message):
    usage = "**Usage:** `/welcome [on|off]`"
    if len(message.command) == 1:
        return await message.reply_text(usage)

    chat_id = message.chat.id
    user = await app.get_chat_member(chat_id, message.from_user.id)
    if user.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
        return await message.reply_text("**Only admins can toggle welcome messages.**")

    state = message.text.split(None, 1)[1].strip().lower()
    current = await wlcm.find_one(chat_id)

    if state == "off":
        if current:
            await wlcm.rm_wlcm(chat_id)
            await message.reply_text(f"✅ Welcome message disabled in {message.chat.title}")
        else:
            await message.reply_text("⚠️ Welcome messages are already off.")
    elif state == "on":
        if not current:
            await wlcm.add_wlcm(chat_id)
            await message.reply_text(f"✅ Welcome message enabled in {message.chat.title}")
        else:
            await message.reply_text("⚠️ Welcome messages are already on.")
    else:
        await message.reply_text(usage)


# ---------------------------- AUTO WELCOME + LANGUAGE SET ----------------------------
@app.on_chat_member_updated(filters.group)
async def greet_new_member(client, member: ChatMemberUpdated):
    chat_id = member.chat.id
    user = member.new_chat_member.user if member.new_chat_member else member.from_user
    bot_user = await client.get_me()

    # ✅ Case 1: Bot added to group → send language setup
    if user and user.is_bot and user.id == bot_user.id:
        print(f"[language auto] Bot added to group: {member.chat.title} ({chat_id})")

        _ = get_string("en")  # default English
        keyboard = InlineKeyboard(row_width=2)
        keyboard.add(
            *[
                InlineKeyboardButton(text=languages_present[i], callback_data=f"languages:{i}")
                for i in languages_present
            ]
        )
        keyboard.row(
            InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close")
        )

        caption = (
            "» ᴘʟᴇᴀsᴇ ᴄʜᴏᴏsᴇ ᴛʜᴇ ʟᴀɴɢᴜᴀɢᴇ ᴡʜɪᴄʜ ʏᴏᴜ ᴡᴀɴɴᴀ sᴇᴛ ᴀs "
            "ᴛʜɪs ɢʀᴏᴜᴘ's ᴅᴇғᴀᴜʟᴛ ʟᴀɴɢᴜᴀɢᴇ :"
        )
        try:
            await client.send_message(chat_id, caption, reply_markup=keyboard)
        except Exception as e:
            print(f"[language auto] Failed to send in {chat_id}: {e}")
        return

    # ✅ Case 2: Normal user joined
    if member.new_chat_member and not user.is_bot:
        # Check welcome state
        wlcm_enabled = await wlcm.find_one(chat_id)
        if not wlcm_enabled:
            return  # Disabled

        try:
            count = await app.get_chat_members_count(chat_id)
        except Exception:
            count = 0

        try:
            pic_path = "VIPMUSIC/assets/upic.png"
            if user.photo:
                pic_path = await app.download_media(user.photo.big_file_id)
        except Exception:
            pic_path = "VIPMUSIC/assets/upic.png"

        try:
            welcome_img = welcomepic(pic_path, user.first_name, member.chat.title, user.id, user.username)
            deep_link = f"tg://openmessage?user_id={user.id}"
            add_link = f"https://t.me/{app.username}?startgroup=true"

            caption = f"""
<blockquote>**☆ . * ● ¸ . ✦ .★° :. ★ * • ○ ° ★**

**{member.chat.title}**

**⊰●⊱┈─★ 𝑊𝑒𝑙𝑐𝑜𝑚𝑒 ★─┈⊰●⊱**</blockquote>
<blockquote>**➽───────────────────❥**

**💕 𝐍꘍𖾕𖾔 🦋** {user.mention}
**💕 𝐈𖽴 🦋** {user.id}
**💕 𝐔𖾗𖾔𖽷𖽡꘍𖾕𖾔 🦋** @{user.username if user.username else "None"}
**💕 𝐌𖾔𖾕𖽜𖾔𖾖𖾗 🦋** {count}

**➽───────────────────❥**</blockquote>  
<blockquote>**☆ . * ● ¸ . ✦ .★　° :. ★ * • ○ ° ★**</blockquote>
"""

            await client.send_photo(
                chat_id,
                photo=welcome_img,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("💕 𝐍𖾔𖾟 𝐌𖾔𖾕𖽜𖾔𖾖 🦋", url=deep_link)],
                        [InlineKeyboardButton("💕 𝐊𖽹𖽴𖽡꘍𖽳 𝐌𖽞  🦋", url=add_link)],
                    ]
                ),
            )
        except Exception as e:
            LOGGER.error(f"[welcome] Error: {e}")
