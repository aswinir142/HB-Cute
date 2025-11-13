from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from helper.utils import (
    is_admin,
    get_config, update_config,
    increment_warning, reset_warnings,
    is_whitelisted, add_whitelist, remove_whitelist, get_whitelist
)
from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    URL_PATTERN
)

app = Client(
    "BioLinkRobot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# =================== Memory store for /biolink toggle ===================
BIO_LINK_STATUS = {}  # True = ON, False = OFF


# =================== /biolink (Enable / Disable protection) ===================
@app.on_message(filters.group & filters.command("biolink"))
async def biolink_toggle(client: Client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(client, chat_id, user_id):
        return await message.reply_text("❌ 𝐎иƖу 𝐀ᴅмιи Ƈαи ʋƨɛ 𝐓нιƨ Ƈσммαиᴅ.")

    status = BIO_LINK_STATUS.get(chat_id, True)
    state_text = "🟢 𝐄иαвƖɛᴅ" if status else "🔴 𝐃ιƨαвƖɛᴅ"
    text = f"**🧠 𝐁ɪσ-𝐋ɪɴᴋ 𝐏ʀᴏᴛᴇᴄᴛɪᴏɴ:** {state_text}\n\n**Ƈнσσƨɛ 𝐎ρтɪσи ƁɛƖσш:**"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 𝐄иαвƖɛ", callback_data=f"biolink_enable_{chat_id}"),
            InlineKeyboardButton("🚫 𝐃ιƨαвƖɛ", callback_data=f"biolink_disable_{chat_id}")
        ]
    ])
    await message.reply_text(text, reply_markup=keyboard)


# =================== Config Command ===================
@app.on_message(filters.group & filters.command("config"))
async def configure(client: Client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_admin(client, chat_id, user_id):
        return

    mode, limit, penalty = await get_config(chat_id)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔻 𝐖αяи 🔻", callback_data="warn")],
        [
            InlineKeyboardButton("🔻 𝐌ʋтɛ ✅" if penalty == "mute" else "Mute", callback_data="mute"),
            InlineKeyboardButton("🔻 𝐁αи ✅" if penalty == "ban" else "Ban", callback_data="ban")
        ],
        [InlineKeyboardButton("🔻 𝐂Ɩσƨɛ 🔻", callback_data="close")]
    ])
    await client.send_message(
        chat_id,
        "**𝐒ɛƭ 𝐏ʋиιƨнмɛит ƒσя 𝐁ισ-𝐋ιиκ 𝐃ɛтɛᴄтɪσи:**",
        reply_markup=keyboard
    )
    await message.delete()


# =================== Whitelist Commands ===================
@app.on_message(filters.group & filters.command("free"))
async def command_free(client: Client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_admin(client, chat_id, user_id):
        return

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        target = await client.get_users(int(arg) if arg.isdigit() else arg)
    else:
        return await message.reply_text("**ʀɛρƖʏ σя ʋƨɛ /free [υѕɛя/ɪᴅ] тσ ᴀᴅᴅ ᴛσ ᴡʜɪᴛᴇʟɪꜱᴛ.**")

    await add_whitelist(chat_id, target.id)
    await reset_warnings(chat_id, target.id)

    text = f"✅ **{target.mention} 𝐀ᴅᴅɛᴅ 𝐓σ 𝐖нιтɛƖιƨт.**"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚫 𝐔и𝐖нιтɛƖιƨт", callback_data=f"unwhitelist_{target.id}"),
            InlineKeyboardButton("🗑️ 𝐂Ɩσƨɛ", callback_data="close")
        ]
    ])
    await message.reply_text(text, reply_markup=keyboard)


@app.on_message(filters.group & filters.command("unfree"))
async def command_unfree(client: Client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_admin(client, chat_id, user_id):
        return

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        target = await client.get_users(int(arg) if arg.isdigit() else arg)
    else:
        return await message.reply_text("**ʀɛρƖʏ σя ʋƨɛ /unfree [υѕɛя/ɪᴅ] тσ ʀᴇᴍᴏᴠᴇ ғʀᴏᴍ ᴡʜɪᴛᴇʟɪꜱᴛ.**")

    if await is_whitelisted(chat_id, target.id):
        await remove_whitelist(chat_id, target.id)
        text = f"🚫 **{target.mention} 𝐑ɛмσᴠɛᴅ 𝐅яσм 𝐖нιтɛƖιƨт.**"
    else:
        text = f"ℹ️ **{target.mention} 𝐈ƨ 𝐍σт 𝐖нιтɛƖιƨт.**"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 𝐖нιтɛƖιƨт", callback_data=f"whitelist_{target.id}"),
            InlineKeyboardButton("🗑️ 𝐂Ɩσƨɛ", callback_data="close")
        ]
    ])
    await message.reply_text(text, reply_markup=keyboard)


@app.on_message(filters.group & filters.command("freelist"))
async def command_freelist(client: Client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_admin(client, chat_id, user_id):
        return

    ids = await get_whitelist(chat_id)
    if not ids:
        return await message.reply_text("⚠️ **𝐍σ 𝐔ƨɛя 𝐈ƨ 𝐖нιтɛƖιƨтɛᴅ.**")

    text = "**📋 𝐖нιтɛƖιƨтɛᴅ 𝐔ƨɛяƨ:**\n\n"
    for i, uid in enumerate(ids, start=1):
        try:
            user = await client.get_users(uid)
            text += f"{i}. {user.first_name} [`{uid}`]\n"
        except:
            text += f"{i}. [User Not Found] [`{uid}`]\n"

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ 𝐂Ɩσƨɛ", callback_data="close")]])
    await message.reply_text(text, reply_markup=keyboard)


# =================== Callback Handler ===================
@app.on_callback_query()
async def callback_handler(client: Client, cq):
    data = cq.data
    chat_id = cq.message.chat.id
    user_id = cq.from_user.id

    if not await is_admin(client, chat_id, user_id):
        return await cq.answer("❌ 𝐘συ 𝐀яɛ 𝐍σт 𝐀и 𝐀ᴅмιи.", show_alert=True)

    # ====== BioLink Enable/Disable ======
    if data.startswith("biolink_enable_") or data.startswith("biolink_disable_"):
        gid = int(data.split("_")[-1])
        if data.startswith("biolink_enable_"):
            BIO_LINK_STATUS[gid] = True
            status = "🟢 𝐁ɪσ-𝐋ɪɴᴋ 𝐏ʀᴏᴛᴇᴄᴛɪᴏɴ 𝐄иαвƖɛᴅ"
        else:
            BIO_LINK_STATUS[gid] = False
            status = "🔴 𝐁ɪσ-𝐋ɪɴᴋ 𝐏ʀᴏᴛᴇᴄᴛɪᴏɴ 𝐃ιƨαвƖɛᴅ"

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ 𝐄иαвƖɛ", callback_data=f"biolink_enable_{gid}"),
                InlineKeyboardButton("🚫 𝐃ιƨαвƖɛ", callback_data=f"biolink_disable_{gid}")
            ]
        ])
        await cq.message.edit_text(f"**{status}**", reply_markup=kb)
        return await cq.answer()

    if data == "close":
        return await cq.message.delete()


# =================== BioLink Detection ===================
@app.on_message(filters.group)
async def check_bio(client: Client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Skip detection if disabled
    if not BIO_LINK_STATUS.get(chat_id, True):
        return

    if await is_admin(client, chat_id, user_id) or await is_whitelisted(chat_id, user_id):
        return

    user = await client.get_chat(user_id)
    bio = user.bio or ""
    full_name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
    mention = f"[{full_name}](tg://user?id={user_id})"

    if URL_PATTERN.search(bio):
        try:
            await message.delete()
        except errors.MessageDeleteForbidden:
            return await message.reply_text("❌ 𝐑ɛмσᴠɛ 𝐘σʋя 𝐁ɪσ-𝐋ɪɴᴋ.")

        mode, limit, penalty = await get_config(chat_id)
        count = await increment_warning(chat_id, user_id)

        warning_text = (
            f"🚨 **𝐖αяиɪиɢ** 🚨\n\n"
            f"👤 **𝐔ƨɛя:** {mention}\n"
            f"❌ **𝐑ɛαƨσи:** 𝐋ɪиᴋ ƒσʋиᴅ ɪи ʙɪσ\n"
            f"⚠️ **𝐖αяиɪиɢ:** {count}/{limit}\n\n"
            "**𝐑ɛмσᴠɛ 𝐋ɪиᴋ 𝐅яσм 𝐘σʋя 𝐁ɪσ!**"
        )

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("❌ 𝐂αиᴄɛƖ 𝐖αяиɪиɢ", callback_data=f"cancel_warn_{user_id}"),
                InlineKeyboardButton("✅ 𝐖нιтɛƖιƨт", callback_data=f"whitelist_{user_id}")
            ],
            [InlineKeyboardButton("🗑️ 𝐂Ɩσƨɛ", callback_data="close")]
        ])

        sent = await message.reply_text(warning_text, reply_markup=kb)

        if count >= limit:
            try:
                if penalty == "mute":
                    await client.restrict_chat_member(chat_id, user_id, ChatPermissions())
                    await sent.edit_text(f"🔇 **{mention} 𝐌ʋтɛᴅ ƒσя 𝐁ɪσ-𝐋ɪиᴋ.**")
                else:
                    await client.ban_chat_member(chat_id, user_id)
                    await sent.edit_text(f"🔨 **{mention} 𝐁αииɛᴅ ƒσя 𝐁ɪσ-𝐋ɪиᴋ.**")
            except errors.ChatAdminRequired:
                await sent.edit_text("⚠️ 𝐈 𝐃σи’т 𝐇αᴠɛ 𝐏ɛямɪƨƨɪσи 𝐓σ 𝐌ʋтɛ/𝐁αи 𝐔ƨɛяƨ.")
    else:
        await reset_warnings(chat_id, user_id)


# =================== Run Bot ===================
def biolink():
    """Start the BioLink bot instance."""
    app.run()
