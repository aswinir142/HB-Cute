from VIPMUSIC import app
from pyrogram import filters

@app.on_message(filters.command("zzztest") & filters.group)
async def zzz_test(_, message):
    await message.reply_text("✅ ZZZ Test works!")
