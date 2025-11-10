import os
import random
from datetime import datetime
from telegraph import upload_file
from PIL import Image, ImageDraw
from pyrogram import *
from pyrogram.types import *
from pyrogram.enums import *

# BOT FILE NAME
from VIPMUSIC import app
from VIPMUSIC.mongo.couples_db import _get_image, get_couple, save_couple

print("[Couples] couples")

def dt():
    now = datetime.now()
    dt_string = now.strftime("%d/%m/%Y %H:%M")
    dt_list = dt_string.split(" ")
    return dt_list


def dt_tom():
    a = (
        str(int(dt()[0].split("/")[0]) + 1)
        + "/"
        + dt()[0].split("/")[1]
        + "/"
        + dt()[0].split("/")[2]
    )
    return a


tomorrow = str(dt_tom())
today = str(dt()[0])


@app.on_message(filters.command("couples"))
async def ctest(_, message):
    cid = message.chat.id
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text("This command only works in groups.")
    try:
        is_selected = await get_couple(cid, today)
        if not is_selected:
            msg = await message.reply_text("🦋")
            list_of_users = []

            async for i in app.get_chat_members(message.chat.id, limit=50):
                if not i.user.is_bot:
                    list_of_users.append(i.user.id)

            if len(list_of_users) < 2:
                return await message.reply_text("Not enough users to pick couples!")

            c1_id = random.choice(list_of_users)
            c2_id = random.choice(list_of_users)
            while c1_id == c2_id:
                c2_id = random.choice(list_of_users)

            photo1 = (await app.get_chat(c1_id)).photo
            photo2 = (await app.get_chat(c2_id)).photo

            N1 = (await app.get_users(c1_id)).mention
            N2 = (await app.get_users(c2_id)).mention

            try:
                p1 = await app.download_media(photo1.big_file_id, file_name="pfp1.png")
            except Exception:
                p1 = "ANNIEMUSIC/assets/upic.png"
            try:
                p2 = await app.download_media(photo2.big_file_id, file_name="pfp2.png")
            except Exception:
                p2 = "ANNIEMUSIC/assets/upic.png"

            img1 = Image.open(p1)
            img2 = Image.open(p2)
            img = Image.open("ANNIEMUSIC/assets/annie/ANNIECP.png")

            img1 = img1.resize((486, 486))
            img2 = img2.resize((486, 486))

            mask = Image.new("L", img1.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0) + img1.size, fill=255)

            mask1 = Image.new("L", img2.size, 0)
            draw = ImageDraw.Draw(mask1)
            draw.ellipse((0, 0) + img2.size, fill=255)

            img1.putalpha(mask)
            img2.putalpha(mask1)

            img.paste(img1, (410, 500), img1)
            img.paste(img2, (1395, 500), img2)

            output_path = f"test_{cid}.png"
            img.save(output_path)

            TXT = f"""
**<blockquote>𝐓ᴏᴅᴀʏ's 𝐒ᴇʟᴇᴄᴛᴇᴅ 𝐂ᴏᴜᴘʟᴇs 🎉</blockquote>
✧══════•❁♡︎❁•══════✧
<blockquote>{N1} + {N2} = 💗</blockquote>
✧══════•❁♡︎❁•══════✧
<blockquote>𝐍ᴇxᴛ 𝐂ᴏᴜᴘʟᴇs 𝐖ɪʟʟ 𝐁ᴇ 𝐒ᴇʟᴇᴄᴛᴇᴅ 𝐎ɴ {tomorrow} !!</blockquote>**
"""

            await message.reply_photo(output_path, caption=TXT)
            await msg.delete()

            a = upload_file(output_path)
            for x in a:
                telegraph_url = "https://graph.org/" + x
                couple = {"c1_id": c1_id, "c2_id": c2_id}
                await save_couple(cid, today, couple, telegraph_url)

        else:
            msg = await message.reply_text("𝐆ᴇᴛᴛɪɴɢ 𝐓ᴏᴅᴀʏs 𝐂ᴏᴜᴘʟᴇs 𝐈ᴍᴀɢᴇ...")
            b = await _get_image(cid)
            c1_id = int(is_selected["c1_id"])
            c2_id = int(is_selected["c2_id"])
            c1_name = (await app.get_users(c1_id)).first_name
            c2_name = (await app.get_users(c2_id)).first_name

            TXT = f"""
**<blockquote>𝐓ᴏᴅᴀʏ's 𝐒ᴇʟᴇᴄᴛᴇᴅ 𝐂ᴏᴜᴘʟᴇs 🎉</blockquote>
✧══════•❁♡︎❁•══════✧
<blockquote>[{c1_name}](tg://openmessage?user_id={c1_id}) + [{c2_name}](tg://openmessage?user_id={c2_id}) = ❣️</blockquote>
✧══════•❁♡︎❁•══════✧
<blockquote>𝐍ᴇxᴛ 𝐂ᴏᴜᴘʟᴇs 𝐖ɪʟʟ 𝐁ᴇ 𝐒ᴇʟᴇᴄᴛᴇᴅ 𝐎ɴ {tomorrow} !!</blockquote>**
"""
            await message.reply_photo(b, caption=TXT)
            await msg.delete()

    except Exception as e:
        print("Error in /couples:", e)

    try:
        os.remove("pfp1.png")
        os.remove("pfp2.png")
        os.remove(f"test_{cid}.png")
    except Exception:
        pass


__mod__ = "COUPLES"
__help__ = """
**» /couples** - Get Today's Couples Of The Group In Interactive View
"""
