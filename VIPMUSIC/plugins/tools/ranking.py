# ranking.py — Full optimized ranking with /myrank, daily auto-post, weekly/monthly
import asyncio
import datetime
from typing import Dict, List, Tuple

from zoneinfo import ZoneInfo

from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from motor.motor_asyncio import AsyncIOMotorClient

from VIPMUSIC import app
from config import MONGO_DB_URI, RANKING_PIC, AUTOPOST_TIME_HOUR, AUTOPOST_TIME_MINUTE

# --------------------------
# Config fallbacks (if not present)
# --------------------------
# The design asked for 21:00 Asia/Kolkata — if user didn't provide AUTOPOST_TIME_*, fall back to 21:00.
try:
    POST_HOUR = int(AUTOPOST_TIME_HOUR)
    POST_MINUTE = int(AUTOPOST_TIME_MINUTE)
except Exception:
    POST_HOUR = 21
    POST_MINUTE = 0

TZ = ZoneInfo("Asia/Kolkata")

# --------------------------
# Motor / DB
# --------------------------
mongo = AsyncIOMotorClient(MONGO_DB_URI)
db = mongo["ghosttlead"]
ranking_db = db["ranking"]  # documents: { _id: user_id, total_messages, weekly_messages, monthly_messages }

# --------------------------
# In-memory counters
# --------------------------
# today_counts[chat_id][user_id] = count
today_counts: Dict[int, Dict[int, int]] = {}
last_reset_date = None  # date object in IST

# --------------------------
# Helpers: DB queries
# --------------------------
async def db_inc_user_messages(user_id: int) -> None:
    """Increment global, weekly and monthly counters in DB (async)."""
    await ranking_db.update_one(
        {"_id": user_id},
        {"$inc": {"total_messages": 1, "weekly_messages": 1, "monthly_messages": 1}},
        upsert=True,
    )


async def db_get_top(field: str = "total_messages", limit: int = 10) -> List[dict]:
    """Return top documents sorted by provided field."""
    cursor = ranking_db.find().sort(field, -1).limit(limit)
    return await cursor.to_list(length=limit)


async def db_reset_field(field: str) -> None:
    """Reset a numeric field to 0 for all users."""
    await ranking_db.update_many({}, {"$set": {field: 0}})


async def db_get_user_counts(user_id: int) -> Tuple[int, int, int]:
    """Return (total, weekly, monthly) counts for a user (0 if not present)."""
    doc = await ranking_db.find_one({"_id": user_id})
    if not doc:
        return 0, 0, 0
    return (
        int(doc.get("total_messages", 0)),
        int(doc.get("weekly_messages", 0)),
        int(doc.get("monthly_messages", 0)),
    )


async def db_get_rank_for_field(user_id: int, field: str) -> int:
    """Return 1-based rank of user for given field. If user not present, rank = count_greater + 1"""
    user_doc = await ranking_db.find_one({"_id": user_id})
    user_val = int(user_doc.get(field, 0)) if user_doc else 0
    # count how many have strictly greater value
    greater = await ranking_db.count_documents({field: {"$gt": user_val}})
    return greater + 1


# --------------------------
# Time / reset helpers
# --------------------------
def ist_now() -> datetime.datetime:
    return datetime.datetime.now(TZ)


def reset_today_if_needed():
    """Reset today_counts once per IST day (midnight IST). Call from watchers and scheduled tasks."""
    global today_counts, last_reset_date
    now_date = ist_now().date()
    if last_reset_date != now_date:
        today_counts = {}
        last_reset_date = now_date


# --------------------------
# WATCHERS
# --------------------------
@app.on_message(filters.group, group=6)
async def today_watcher(client, message: Message):
    """Counts per-chat 'today' counters (in-memory)."""
    if not message.from_user:
        return
    reset_today_if_needed()
    chat_id = message.chat.id
    user_id = message.from_user.id

    if chat_id not in today_counts:
        today_counts[chat_id] = {}
    today_counts[chat_id][user_id] = today_counts[chat_id].get(user_id, 0) + 1


@app.on_message(filters.group, group=7)
async def global_watcher(client, message: Message):
    """Increment DB counters (async motor) for global / weekly / monthly."""
    if not message.from_user:
        return
    user_id = message.from_user.id
    try:
        await db_inc_user_messages(user_id)
    except Exception as e:
        # don't raise — log and continue
        print(f"[ranking] DB increment error for {user_id}: {e}")


# --------------------------
# Formatting helpers
# --------------------------
async def resolve_name(user_id: int) -> str:
    try:
        u = await app.get_users(user_id)
        if getattr(u, "first_name", None):
            return u.first_name
        if getattr(u, "username", None):
            return u.username
        return "Unknown"
    except Exception:
        return "Unknown"


def format_leaderboard(title: str, items: List[Tuple[str, int]]) -> str:
    text = f"<blockquote>**📈 {title}**</blockquote>\n"
    for idx, (name, count) in enumerate(items, start=1):
        text += f"<blockquote>**{idx}**. {name} • {count}\n</blockquote>"
    return text


# --------------------------
# Commands: /today, /ranking
# --------------------------
@app.on_message(filters.command("today") & filters.group)
async def cmd_today(client, message: Message):
    chat_id = message.chat.id
    reset_today_if_needed()
    if chat_id not in today_counts or not today_counts[chat_id]:
        return await message.reply_text("No data available for today.")

    pairs = sorted(today_counts[chat_id].items(), key=lambda x: x[1], reverse=True)[:10]
    items = []
    for uid, cnt in pairs:
        name = await resolve_name(uid)
        items.append((name, cnt))

    text = format_leaderboard("𝐋ᴇᴀᴅᴇʀ𝐁ᴏᴀʀᴅ 𝐓ᴏᴅᴀʏ", items)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("𝐎ᴠᴇʀᴀʟʟ", callback_data="overall")]])
    try:
        await message.reply_photo(RANKING_PIC, caption=text, reply_markup=kb)
    except Exception:
        await message.reply_text(text, reply_markup=kb)


@app.on_message(filters.command("ranking") & filters.group)
async def cmd_ranking(client, message: Message):
    top = await db_get_top("total_messages", 10)
    if not top:
        return await message.reply_text("No ranking data available.")

    items = []
    for row in top:
        name = await resolve_name(row["_id"])
        items.append((name, int(row.get("total_messages", 0))))

    text = format_leaderboard("𝐋ᴇᴀᴅᴇʀ𝐁ᴏᴀʀᴅ", items)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("𝐓ᴏᴅᴀʏ", callback_data="today")]])
    try:
        await message.reply_photo(RANKING_PIC, caption=text, reply_markup=kb)
    except Exception:
        await message.reply_text(text, reply_markup=kb)


# --------------------------
# /myrank command
# --------------------------
@app.on_message(filters.command("myrank") & filters.group)
async def cmd_myrank(client, message: Message):
    user_id = message.from_user.id
    total, weekly, monthly = await db_get_user_counts(user_id)
    rank_total = await db_get_rank_for_field(user_id, "total_messages")
    rank_weekly = await db_get_rank_for_field(user_id, "weekly_messages")
    rank_monthly = await db_get_rank_for_field(user_id, "monthly_messages")

    text = (
        f"<blockquote>**📊 Your Rank**</blockquote>\n"
        f"<blockquote>• Global: #{rank_total} • {total} msgs\n</blockquote>"
        f"<blockquote>• Weekly: #{rank_weekly} • {weekly} msgs\n</blockquote>"
        f"<blockquote>• Monthly: #{rank_monthly} • {monthly} msgs\n</blockquote>"
    )
    await message.reply_text(text)


# --------------------------
# Callbacks for buttons
# --------------------------
@app.on_callback_query(filters.regex("^today$"))
async def cb_today(client, query: CallbackQuery):
    if not query.message or not query.message.chat:
        return await query.answer("No chat info.", show_alert=True)
    chat_id = query.message.chat.id
    reset_today_if_needed()
    if chat_id not in today_counts or not today_counts[chat_id]:
        return await query.answer("No data for today.", show_alert=True)

    pairs = sorted(today_counts[chat_id].items(), key=lambda x: x[1], reverse=True)[:10]
    items = []
    for uid, cnt in pairs:
        name = await resolve_name(uid)
        items.append((name, cnt))

    text = format_leaderboard("𝐋ᴇᴀᴅᴇʀ𝐁ᴏᴀʀᴅ", items)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("𝐎ᴠᴇʀᴀʟʟ", callback_data="overall")]])

    try:
        await query.message.edit_text(text, reply_markup=kb)
    except Exception:
        await query.answer("Unable to edit message.", show_alert=True)


@app.on_callback_query(filters.regex("^overall$"))
async def cb_overall(client, query: CallbackQuery):
    top = await db_get_top("total_messages", 10)
    if not top:
        return await query.answer("No ranking data.", show_alert=True)

    items = []
    for row in top:
        name = await resolve_name(row["_id"])
        items.append((name, int(row.get("total_messages", 0))))

    text = format_leaderboard("𝐋ᴇᴀᴅᴇʀ𝐁ᴏᴀʀᴅ", items)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("𝐓ᴏᴅᴀʏ", callback_data="today")]])

    try:
        await query.message.edit_text(text, reply_markup=kb)
    except Exception:
        await query.answer("Unable to edit message.", show_alert=True)


# --------------------------
# Auto-post scheduler (Option A: all groups)
# --------------------------
async def collect_group_chats() -> List[int]:
    """
    Collect group & supergroup chat ids where the bot is a member.
    Uses iter_dialogs to find group/supergroup dialogs.
    """
    chats = []
    try:
        async for dialog in app.iter_dialogs():
            c = dialog.chat
            if getattr(c, "type", None) in ("group", "supergroup"):
                chats.append(c.id)
    except Exception as e:
        print(f"[ranking] Failed to iterate dialogs: {e}")
    return list(set(chats))


async def build_post_text() -> Tuple[str, str, str]:
    """Return (daily_text, weekly_text, monthly_text) pre-built strings."""
    # DAILY: per-chat will be built later — here build global top 10 just once
    top_daily = []  # daily is per-chat, so global daily text not used
    # GLOBAL
    top_global = await db_get_top("total_messages", 10)
    items_global = []
    for row in top_global:
        name = await resolve_name(row["_id"])
        items_global.append((name, int(row.get("total_messages", 0))))
    text_global = format_leaderboard("𝐋ᴇᴀᴅᴇʀ𝐁ᴏᴀʀᴅ (Global)", items_global)

    # WEEKLY
    top_weekly = await db_get_top("weekly_messages", 10)
    items_weekly = []
    for row in top_weekly:
        name = await resolve_name(row["_1"] if "_1" in row else row["_id"])
        # (defensive) use _id
        name = await resolve_name(row["_id"])
        items_weekly.append((name, int(row.get("weekly_messages", 0))))
    text_weekly = format_leaderboard("𝐋ᴇᴀᴅᴇʀ𝐁ᴏᴀʀᴅ (Weekly)", items_weekly)

    # MONTHLY
    top_monthly = await db_get_top("monthly_messages", 10)
    items_monthly = []
    for row in top_monthly:
        name = await resolve_name(row["_id"])
        items_monthly.append((name, int(row.get("monthly_messages", 0))))
    text_monthly = format_leaderboard("𝐋ᴇᴀᴅᴇʀ𝐁ᴏᴀʀᴅ (Monthly)", items_monthly)

    return text_global, text_weekly, text_monthly


async def post_daily_leaderboards():
    """
    Post leaderboards:
    - per-chat today leaderboard (if that chat has today data)
    - global leaderboard (all chats)
    - if Monday also post weekly and reset weekly counters
    - if day == 1 also post monthly and reset monthly counters
    """
    now = ist_now()
    weekday = now.weekday()  # Monday == 0
    day_of_month = now.day

    # prepare static texts for global/weekly/monthly
    text_global, text_weekly, text_monthly = await build_post_text()

    # collect groups (Option A)
    groups = await collect_group_chats()
    if not groups:
        print("[ranking] No groups found to post to.")
        return

    for chat_id in groups:
        # build per-chat today leaderboard if any
        reset_today_if_needed()
        if chat_id in today_counts and today_counts[chat_id]:
            pairs = sorted(today_counts[chat_id].items(), key=lambda x: x[1], reverse=True)[:10]
            items = []
            for uid, cnt in pairs:
                name = await resolve_name(uid)
                items.append((name, cnt))
            text_chat = format_leaderboard("𝐋ᴇᴀᴅᴇʀ𝐁ᴏᴀʀᴅ 𝐓ᴏᴅᴀʏ", items)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("𝐎ᴠᴇʀᴀʟʟ", callback_data="overall")]])
            try:
                await app.send_photo(chat_id, RANKING_PIC, caption=text_chat, reply_markup=kb)
            except Exception:
                try:
                    await app.send_message(chat_id, text_chat, reply_markup=kb)
                except Exception as e:
                    print(f"[ranking] failed to post today to {chat_id}: {e}")

        # Also post global leaderboard for every group
        kb2 = InlineKeyboardMarkup([[InlineKeyboardButton("𝐓ᴏᴅᴀʏ", callback_data="today")]])
        try:
            await app.send_photo(chat_id, RANKING_PIC, caption=text_global, reply_markup=kb2)
        except Exception:
            try:
                await app.send_message(chat_id, text_global, reply_markup=kb2)
            except Exception as e:
                print(f"[ranking] failed to post global to {chat_id}: {e}")

        # If Monday, post weekly
        if weekday == 0:
            try:
                await app.send_photo(chat_id, RANKING_PIC, caption=text_weekly, reply_markup=kb2)
            except Exception:
                try:
                    await app.send_message(chat_id, text_weekly, reply_markup=kb2)
                except Exception as e:
                    print(f"[ranking] failed to post weekly to {chat_id}: {e}")

        # If 1st of month, post monthly
        if day_of_month == 1:
            try:
                await app.send_photo(chat_id, RANKING_PIC, caption=text_monthly, reply_markup=kb2)
            except Exception:
                try:
                    await app.send_message(chat_id, text_monthly, reply_markup=kb2)
                except Exception as e:
                    print(f"[ranking] failed to post monthly to {chat_id}: {e}")

    # Resets after posting:
    # weekly reset on Monday after posting
    if weekday == 0:
        try:
            await db_reset_field("weekly_messages")
            print("[ranking] weekly_messages reset done.")
        except Exception as e:
            print(f"[ranking] weekly reset failed: {e}")

    # monthly reset on the 1st after posting
    if day_of_month == 1:
        try:
            await db_reset_field("monthly_messages")
            print("[ranking] monthly_messages reset done.")
        except Exception as e:
            print(f"[ranking] monthly reset failed: {e}")


async def schedule_daily_poster():
    """Background task: sleeps until next POST_HOUR:POST_MINUTE IST and posts leaderboards."""
    await app.start()  # ensure client started (safe-guard if called early)
    print(f"[ranking] Auto-post scheduler started. Posting at {POST_HOUR:02d}:{POST_MINUTE:02d} IST daily.")
    while True:
        now = ist_now()
        target = now.replace(hour=POST_HOUR, minute=POST_MINUTE, second=0, microsecond=0)
        if target <= now:
            target = target + datetime.timedelta(days=1)
        # compute seconds until target in UTC
        delta = (target - now).total_seconds()
        try:
            await asyncio.sleep(delta)
            # wake up and post
            try:
                await post_daily_leaderboards()
            except Exception as e:
                print(f"[ranking] Error posting leaderboards: {e}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[ranking] scheduler error: {e}")
            # small backoff before retrying loop
            await asyncio.sleep(60)


# Start scheduler in background
# Use get_event_loop().create_task so it runs while app is running
try:
    loop = asyncio.get_event_loop()
    loop.create_task(schedule_daily_poster())
except Exception as e:
    print(f"[ranking] Failed to schedule daily poster at import time: {e}")

