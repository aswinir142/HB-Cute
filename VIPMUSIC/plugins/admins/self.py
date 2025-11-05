import random
from pyrogram import Client, filters
from pyrogram.types import Message

# ─────────────────────────────
# FLAMES Data: Relationship text, images & quotes
# ─────────────────────────────
FLAMES_DATA = {
    "F": {
        "text": "💔 Friends",
        "images": [
            "https://i.imgur.com/Y4pZ5wU.jpg",
            "https://i.imgur.com/9RtLQFc.jpg",
            "https://i.imgur.com/hfzWEr2.jpg"
        ],
        "quotes": [
            "A true friend is one soul in two bodies 💫",
            "Friendship isn’t one big thing, it’s a million little things 🤝",
            "Good friends are like stars — you don’t always see them, but you know they’re there 🌟"
        ]
    },
    "L": {
        "text": "❤️ Lovers",
        "images": [
            "https://i.imgur.com/lZ8GmE8.jpg",
            "https://i.imgur.com/nEpmrQ2.jpg",
            "https://i.imgur.com/tv4AE4L.jpg"
        ],
        "quotes": [
            "Love is not finding someone to live with, it’s finding someone you can’t live without 💞",
            "You’re my favorite place to go when my mind searches for peace ❤️",
            "Love doesn’t make the world go round, it makes the ride worthwhile 💋"
        ]
    },
    "A": {
        "text": "💞 Affection",
        "images": [
            "https://i.imgur.com/0N8Aj7A.jpg",
            "https://i.imgur.com/w9xZsnS.jpg",
            "https://i.imgur.com/sBiF6N3.jpg"
        ],
        "quotes": [
            "Affection is a language everyone understands 💕",
            "Sometimes a simple hug can heal more than words 🌸",
            "The smallest act of kindness is worth more than the grandest intention 💗"
        ]
    },
    "M": {
        "text": "💍 Marriage",
        "images": [
            "https://i.imgur.com/hQi9sL1.jpg",
            "https://i.imgur.com/ULqf2FT.jpg",
            "https://i.imgur.com/6eI3vbl.jpg"
        ],
        "quotes": [
            "A successful marriage requires falling in love many times, always with the same person 💍",
            "Together is a beautiful place to be ❤️",
            "A great marriage is not when the perfect couple comes together — it’s when an imperfect couple learns to enjoy their differences 💫"
        ]
    },
    "E": {
        "text": "💣 Enemies",
        "images": [
            "https://i.imgur.com/1N2XP8O.jpg",
            "https://i.imgur.com/fZci4G1.jpg",
            "https://i.imgur.com/vlml3qG.jpg"
        ],
        "quotes": [
            "Keep your friends close and your enemies closer 😈",
            "Every enemy was once a friend 💀",
            "Sometimes haters are your biggest fans in disguise 😎"
        ]
    },
    "S": {
        "text": "👫 Siblings",
        "images": [
            "https://i.imgur.com/ECKcJ9N.jpg",
            "https://i.imgur.com/csXYLFA.jpg",
            "https://i.imgur.com/DdA0SKL.jpg"
        ],
        "quotes": [
            "Siblings: your first best friends and forever rivals 😂",
            "Brothers and sisters are as close as hands and feet 👣",
            "You don’t need to be perfect to be a great sibling, just annoying enough 😜"
        ]
    }
}


# ─────────────────────────────
# FLAMES algorithm logic
# ─────────────────────────────
def calculate_flames(name1: str, name2: str) -> str:
    name1 = name1.replace(" ", "").lower()
    name2 = name2.replace(" ", "").lower()

    # Remove common letters
    for ch in name1[:]:
        if ch in name2:
            name1 = name1.replace(ch, "", 1)
            name2 = name2.replace(ch, "", 1)

    count = len(name1 + name2)
    flames = list("FLAMES")

    while len(flames) > 1:
        split_index = (count % len(flames)) - 1
        if split_index >= 0:
            flames = flames[split_index + 1:] + flames[:split_index]
        else:
            flames = flames[:-1]

    return flames[0]


# ─────────────────────────────
# /flames command handler
# ─────────────────────────────
@app.on_message(filters.command("self"))
def flames_command(client: Client, message: Message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            return message.reply_text(
                "⚡ Usage:\n`/flames Name1 Name2`\n\nExample:\n`/flames John Alice`"
            )

        name1, name2 = args[1], args[2]
        result = calculate_flames(name1, name2)

        data = FLAMES_DATA[result]
        result_text = data["text"]
        result_image = random.choice(data["images"])
        result_quote = random.choice(data["quotes"])

        caption = (
            f"🔥 **FLAMES RESULT** 🔥\n\n"
            f"👤 Name 1: `{name1}`\n"
            f"👤 Name 2: `{name2}`\n\n"
            f"💘 Relationship: **{result_text}**\n\n"
            f"💬 _{result_quote}_"
        )

        client.send_photo(
            chat_id=message.chat.id,
            photo=result_image,
            caption=caption
        )

    except Exception as e:
        message.reply_text(f"❌ Error: {e}")
