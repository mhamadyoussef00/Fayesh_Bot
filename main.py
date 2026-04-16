import asyncio
import json
import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiohttp import web
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, BotCommand
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing")
# =========================
# Load env
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
WHISH_DESTINATION = os.getenv("WHISH_DESTINATION", "Put your Whish account here").strip()
SUBSCRIPTION_PRICE = os.getenv("SUBSCRIPTION_PRICE", "3").strip()
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
REMINDER_DAYS = int(os.getenv("REMINDER_DAYS", "3"))
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "300"))

WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").rstrip("/")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()

WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing in .env")

if not ADMIN_ID:
    raise ValueError("ADMIN_ID is missing in .env")

if not WEBHOOK_BASE_URL:
    raise ValueError("WEBHOOK_BASE_URL is missing in .env")

if not WEBHOOK_SECRET:
    raise ValueError("WEBHOOK_SECRET is missing in .env")

# =========================
# Storage
# =========================
DATA_DIR = Path("data")
USERS_FILE = DATA_DIR / "users.json"
SUBSCRIPTIONS_FILE = DATA_DIR / "subscriptions.json"
CLEAR_HISTORY_FILE = DATA_DIR / "clear_history.json"

pending_phone_users = set()
dp = Dispatcher()


def ensure_storage():
    DATA_DIR.mkdir(exist_ok=True)

    if not USERS_FILE.exists():
        USERS_FILE.write_text("{}", encoding="utf-8")

    if not SUBSCRIPTIONS_FILE.exists():
        SUBSCRIPTIONS_FILE.write_text("{}", encoding="utf-8")

    if not CLEAR_HISTORY_FILE.exists():
        CLEAR_HISTORY_FILE.write_text("{}", encoding="utf-8")


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def format_dt(iso_text: str | None) -> str:
    if not iso_text:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_text)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_text


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def normalize_phone_number(raw: str) -> str:
    raw = raw.strip()
    raw = raw.replace(" ", "").replace("-", "")
    return raw


def is_valid_phone_number(phone: str) -> bool:
    return bool(re.fullmatch(r"\+?\d{7,15}", phone))


# =========================
# Clear tracking
# =========================
def remember_bot_message(chat_id: int, message_id: int) -> None:
    history = read_json(CLEAR_HISTORY_FILE)
    key = str(chat_id)

    ids = history.get(key, [])
    ids.append(message_id)

    history[key] = ids[-200:]
    write_json(CLEAR_HISTORY_FILE, history)


def clear_saved_history(chat_id: int) -> None:
    history = read_json(CLEAR_HISTORY_FILE)
    history[str(chat_id)] = []
    write_json(CLEAR_HISTORY_FILE, history)


def get_saved_history(chat_id: int) -> list[int]:
    history = read_json(CLEAR_HISTORY_FILE)
    return history.get(str(chat_id), [])


async def tracked_message_answer(message: Message, text: str, **kwargs):
    sent = await message.answer(text, **kwargs)
    remember_bot_message(message.chat.id, sent.message_id)
    return sent


async def tracked_callback_answer(callback: CallbackQuery, text: str, **kwargs):
    sent = await callback.message.answer(text, **kwargs)
    remember_bot_message(callback.message.chat.id, sent.message_id)
    return sent


async def tracked_bot_send(bot: Bot, chat_id: int, text: str, **kwargs):
    sent = await bot.send_message(chat_id, text, **kwargs)
    remember_bot_message(chat_id, sent.message_id)
    return sent


async def clear_recent_bot_messages(bot: Bot, chat_id: int):
    message_ids = get_saved_history(chat_id)

    for message_id in reversed(message_ids):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    clear_saved_history(chat_id)


# =========================
# User and subscription storage
# =========================
def store_user(user) -> None:
    users = read_json(USERS_FILE)
    current = users.get(str(user.id), {})

    users[str(user.id)] = {
        "id": user.id,
        "full_name": user.full_name,
        "username": user.username or "",
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "phone_number": current.get("phone_number", ""),
        "updated_at": now_utc().isoformat(),
    }

    write_json(USERS_FILE, users)


def update_user_phone(user_id: int, phone_number: str) -> None:
    users = read_json(USERS_FILE)
    key = str(user_id)

    current = users.get(key, {"id": user_id})
    current["phone_number"] = phone_number
    current["updated_at"] = now_utc().isoformat()

    users[key] = current
    write_json(USERS_FILE, users)


def get_user(user_id: int) -> dict | None:
    users = read_json(USERS_FILE)
    return users.get(str(user_id))


def get_all_subscriptions() -> dict:
    return read_json(SUBSCRIPTIONS_FILE)


def save_all_subscriptions(data: dict):
    write_json(SUBSCRIPTIONS_FILE, data)


def get_subscription(user_id: int) -> dict | None:
    subs = get_all_subscriptions()
    return subs.get(str(user_id))


def set_subscription(user_id: int, days: int = SUBSCRIPTION_DAYS) -> dict:
    subs = get_all_subscriptions()

    start_at = now_utc()
    expires_at = start_at + timedelta(days=days)

    record = {
        "user_id": user_id,
        "status": "active",
        "start_at": start_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "approved_by": ADMIN_ID,
        "payment_method": "Whish manual approval",
        "price": SUBSCRIPTION_PRICE,
        "last_reminder_day_sent": None,
        "expired_notice_sent": False,
        "updated_at": now_utc().isoformat(),
    }

    subs[str(user_id)] = record
    save_all_subscriptions(subs)
    return record


def remove_subscription(user_id: int) -> bool:
    subs = get_all_subscriptions()
    key = str(user_id)

    if key in subs:
        del subs[key]
        save_all_subscriptions(subs)
        return True

    return False


def get_expiry_datetime(sub: dict) -> datetime | None:
    expires_at_raw = sub.get("expires_at")
    if not expires_at_raw:
        return None

    try:
        return datetime.fromisoformat(expires_at_raw)
    except Exception:
        return None


def has_active_subscription(user_id: int) -> bool:
    if is_admin(user_id):
        return True

    sub = get_subscription(user_id)
    if not sub:
        return False

    if sub.get("status") != "active":
        return False

    expires_at = get_expiry_datetime(sub)
    if not expires_at:
        return False

    return expires_at > now_utc()


def days_left_for_subscription(sub: dict) -> int | None:
    expires_at = get_expiry_datetime(sub)
    if not expires_at:
        return None

    seconds_left = (expires_at - now_utc()).total_seconds()
    if seconds_left <= 0:
        return 0

    return math.ceil(seconds_left / 86400)


def get_subscription_text(user_id: int) -> str:
    if is_admin(user_id):
        return "Admin account: full access enabled."

    sub = get_subscription(user_id)
    user = get_user(user_id)

    if not sub:
        return (
            "Subscription Status: Inactive ❌\n"
            f"Price: ${SUBSCRIPTION_PRICE}\n"
            f"Duration: {SUBSCRIPTION_DAYS} days\n"
            f"Phone Number: {user.get('phone_number', 'N/A') if user else 'N/A'}"
        )

    active = has_active_subscription(user_id)
    days_left = days_left_for_subscription(sub)
    phone_number = user.get("phone_number", "N/A") if user else "N/A"

    return (
        f"Subscription Status: {'Active ✅' if active else 'Inactive ❌'}\n"
        f"Start Date: {format_dt(sub.get('start_at'))}\n"
        f"Expire Date: {format_dt(sub.get('expires_at'))}\n"
        f"Days Left: {days_left if days_left is not None else 'N/A'}\n"
        f"Price: ${sub.get('price', SUBSCRIPTION_PRICE)}\n"
        f"Payment Method: {sub.get('payment_method', 'N/A')}\n"
        f"Phone Number: {phone_number}"
    )


def get_active_subscribers() -> list[dict]:
    subs = get_all_subscriptions()
    users = read_json(USERS_FILE)

    result = []

    for user_id_str, sub in subs.items():
        try:
            user_id = int(user_id_str)
        except Exception:
            continue

        if not has_active_subscription(user_id):
            continue

        user = users.get(user_id_str, {})
        result.append(
            {
                "user_id": user_id,
                "full_name": user.get("full_name", "Unknown"),
                "username": user.get("username", ""),
                "phone_number": user.get("phone_number", ""),
                "expires_at": sub.get("expires_at"),
                "days_left": days_left_for_subscription(sub),
            }
        )

    result.sort(key=lambda x: x["expires_at"] or "")
    return result


# =========================
# Keyboards
# =========================
def main_menu(user_id: int):
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="My Account", callback_data="account")
    keyboard.button(text="Services", callback_data="services_menu")
    keyboard.button(text="Subscription", callback_data="subscription_menu")
    keyboard.button(text="Support 24/7", callback_data="support")

    if is_admin(user_id):
        keyboard.button(text="Admin Panel", callback_data="admin_panel")

    keyboard.adjust(1)
    return keyboard.as_markup()


def services_menu():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Car Number", callback_data="car_number")
    keyboard.button(text="Phone Number Search", callback_data="phone_search")
    keyboard.button(text="Live Market", callback_data="market")
    keyboard.button(text="Social Media App", callback_data="social")
    keyboard.button(text="CarFax", callback_data="carfax")
    keyboard.button(text="Back to Menu", callback_data="back_menu")
    keyboard.adjust(1)
    return keyboard.as_markup()


def subscription_menu():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Subscription Status", callback_data="subscription_status")
    keyboard.button(text="Payment Info", callback_data="payment_info")
    keyboard.button(text="I Sent Payment", callback_data="payment_sent")
    keyboard.button(text="Back to Menu", callback_data="back_menu")
    keyboard.adjust(1)
    return keyboard.as_markup()


def admin_menu():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Subscribers List", callback_data="subscribers_list")
    keyboard.button(text="Back to Menu", callback_data="back_menu")
    keyboard.adjust(1)
    return keyboard.as_markup()


def back_to_menu_keyboard():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Back to Menu", callback_data="back_menu")
    keyboard.adjust(1)
    return keyboard.as_markup()


def admin_request_keyboard(user_id: int):
    keyboard = InlineKeyboardBuilder()
    keyboard.button(
        text=f"Accept {SUBSCRIPTION_DAYS} Days",
        callback_data=f"admin_accept:{user_id}:{SUBSCRIPTION_DAYS}",
    )
    keyboard.button(
        text="Reject",
        callback_data=f"admin_reject:{user_id}",
    )
    keyboard.adjust(1)
    return keyboard.as_markup()


# =========================
# Bot Commands
# =========================
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="menu", description="Show main menu"),
        BotCommand(command="account", description="Show my account"),
        BotCommand(command="payment", description="Show payment info"),
        BotCommand(command="status", description="Show subscription status"),
        BotCommand(command="support", description="Contact support"),
        BotCommand(command="clear", description="Clear recent bot messages"),
    ]
    await bot.set_my_commands(commands)


async def premium_locked(callback: CallbackQuery, feature_name: str) -> bool:
    if has_active_subscription(callback.from_user.id):
        return True

    await callback.answer("Subscribers only", show_alert=True)
    await tracked_callback_answer(
        callback,
        f"{feature_name} is for paid users only.\n\n"
        f"Price: ${SUBSCRIPTION_PRICE}\n"
        f"Duration: {SUBSCRIPTION_DAYS} days\n"
        f"Pay via Whish to:\n{WHISH_DESTINATION}\n\n"
        "After payment, open Subscription > I Sent Payment",
        reply_markup=subscription_menu(),
    )
    return False


# =========================
# Background tasks
# =========================
async def reminder_loop(bot: Bot):
    while True:
        try:
            subs = get_all_subscriptions()
            changed = False

            for user_id_str, sub in subs.items():
                try:
                    user_id = int(user_id_str)
                except Exception:
                    continue

                if sub.get("status") != "active":
                    continue

                expires_at = get_expiry_datetime(sub)
                if not expires_at:
                    continue

                seconds_left = (expires_at - now_utc()).total_seconds()
                days_left = days_left_for_subscription(sub)

                if seconds_left <= 0:
                    if not sub.get("expired_notice_sent", False):
                        try:
                            await tracked_bot_send(
                                bot,
                                user_id,
                                "❌ Your subscription has expired.\nRenew to keep access.",
                                reply_markup=subscription_menu(),
                            )
                        except Exception:
                            pass

                        sub["expired_notice_sent"] = True
                        sub["updated_at"] = now_utc().isoformat()
                        changed = True

                    continue

                if days_left is not None and 0 < days_left <= REMINDER_DAYS:
                    last_sent = sub.get("last_reminder_day_sent")

                    if last_sent != days_left:
                        try:
                            await tracked_bot_send(
                                bot,
                                user_id,
                                f"⏰ Reminder: your subscription expires in {days_left} day(s).",
                                reply_markup=subscription_menu(),
                            )
                        except Exception:
                            pass

                        sub["last_reminder_day_sent"] = days_left
                        sub["updated_at"] = now_utc().isoformat()
                        changed = True

            if changed:
                save_all_subscriptions(subs)

        except Exception as e:
            logging.exception("Reminder loop error: %s", e)

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


# =========================
# Slash Commands
# =========================
@dp.message(CommandStart())
async def start_handler(message: Message):
    store_user(message.from_user)
    user_id = message.from_user.id

    if has_active_subscription(user_id):
        text = "Welcome to Fayesh_Bot 👋\n\nYour subscription is active ✅"
    else:
        text = (
            "Welcome to Fayesh_Bot 👋\n\n"
            "Premium services available inside the bot.\n"
            f"Subscription: ${SUBSCRIPTION_PRICE} / {SUBSCRIPTION_DAYS} days"
        )

    await tracked_message_answer(message, text, reply_markup=main_menu(user_id))


@dp.message(Command("menu"))
async def menu_command(message: Message):
    store_user(message.from_user)
    await tracked_message_answer(
        message,
        "Main Menu",
        reply_markup=main_menu(message.from_user.id),
    )


@dp.message(Command("account"))
async def account_command(message: Message):
    store_user(message.from_user)
    user = message.from_user
    sub_text = get_subscription_text(user.id)

    await tracked_message_answer(
        message,
        f"User Info:\n"
        f"- Name: {user.full_name}\n"
        f"- User: @{user.username if user.username else 'No User'}\n"
        f"- ID: {user.id}\n\n"
        f"{sub_text}",
        reply_markup=back_to_menu_keyboard(),
    )


@dp.message(Command("payment"))
async def payment_command(message: Message):
    await tracked_message_answer(
        message,
        "Payment Info\n\n"
        f"Price: ${SUBSCRIPTION_PRICE}\n"
        f"Duration: {SUBSCRIPTION_DAYS} days\n"
        f"Pay to Whish account:\n{WHISH_DESTINATION}",
        reply_markup=subscription_menu(),
    )


@dp.message(Command("status"))
async def status_command(message: Message):
    await tracked_message_answer(
        message,
        get_subscription_text(message.from_user.id),
        reply_markup=back_to_menu_keyboard(),
    )


@dp.message(Command("support"))
async def support_command(message: Message):
    await tracked_message_answer(
        message,
        "Support System\nWrite your message here and we will check it.",
        reply_markup=back_to_menu_keyboard(),
    )


@dp.message(Command("clear"))
async def clear_command(message: Message):
    await clear_recent_bot_messages(message.bot, message.chat.id)

    try:
        await message.delete()
    except Exception:
        pass

    await tracked_message_answer(
        message,
        "Recent bot messages cleared ✅",
        reply_markup=main_menu(message.from_user.id),
    )


# =========================
# Menus
# =========================
@dp.callback_query(F.data == "back_menu")
async def back_menu_handler(callback: CallbackQuery):
    await tracked_callback_answer(
        callback,
        "Main Menu",
        reply_markup=main_menu(callback.from_user.id),
    )
    await callback.answer()


@dp.callback_query(F.data == "services_menu")
async def services_menu_handler(callback: CallbackQuery):
    await tracked_callback_answer(
        callback,
        "Services Menu",
        reply_markup=services_menu(),
    )
    await callback.answer()


@dp.callback_query(F.data == "subscription_menu")
async def subscription_menu_handler(callback: CallbackQuery):
    await tracked_callback_answer(
        callback,
        "Subscription Menu",
        reply_markup=subscription_menu(),
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("No permission", show_alert=True)
        return

    await tracked_callback_answer(
        callback,
        "Admin Panel",
        reply_markup=admin_menu(),
    )
    await callback.answer()


# =========================
# Account / Subscription
# =========================
@dp.callback_query(F.data == "account")
async def account_handler(callback: CallbackQuery):
    store_user(callback.from_user)
    user = callback.from_user
    sub_text = get_subscription_text(user.id)

    await tracked_callback_answer(
        callback,
        f"User Info:\n"
        f"- Name: {user.full_name}\n"
        f"- User: @{user.username if user.username else 'No User'}\n"
        f"- ID: {user.id}\n\n"
        f"{sub_text}",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "subscription_status")
async def subscription_status_handler(callback: CallbackQuery):
    await tracked_callback_answer(
        callback,
        get_subscription_text(callback.from_user.id),
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "payment_info")
async def payment_info_handler(callback: CallbackQuery):
    await tracked_callback_answer(
        callback,
        "Payment Info\n\n"
        f"Price: ${SUBSCRIPTION_PRICE}\n"
        f"Duration: {SUBSCRIPTION_DAYS} days\n"
        f"Pay to Whish account:\n{WHISH_DESTINATION}\n\n"
        "After payment, click: I Sent Payment",
        reply_markup=subscription_menu(),
    )
    await callback.answer()


@dp.callback_query(F.data == "payment_sent")
async def payment_sent_handler(callback: CallbackQuery):
    store_user(callback.from_user)

    if has_active_subscription(callback.from_user.id):
        await tracked_callback_answer(
            callback,
            "Your subscription is already active ✅",
            reply_markup=subscription_menu(),
        )
        await callback.answer()
        return

    pending_phone_users.add(callback.from_user.id)

    await tracked_callback_answer(
        callback,
        "Send your phone number now.\nExample: 03XXXXXX or +9613XXXXXX",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer("Now send your phone number")


# =========================
# Premium Services
# =========================
@dp.callback_query(F.data == "car_number")
async def car_number_handler(callback: CallbackQuery):
    if not await premium_locked(callback, "Car Number"):
        return

    await tracked_callback_answer(
        callback,
        "Car Number Search ✅\nPut your premium car number content here.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "phone_search")
async def phone_search_handler(callback: CallbackQuery):
    if not await premium_locked(callback, "Phone Number Search"):
        return

    await tracked_callback_answer(
        callback,
        "Phone Number Search ✅\nPut your premium phone search content here.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "market")
async def market_handler(callback: CallbackQuery):
    if not await premium_locked(callback, "Live Market"):
        return

    await tracked_callback_answer(
        callback,
        "Live Market ✅\nPut your premium market content here.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "social")
async def social_handler(callback: CallbackQuery):
    if not await premium_locked(callback, "Social Media App"):
        return

    await tracked_callback_answer(
        callback,
        "Social Media App ✅\nPut your premium social media content here.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "carfax")
async def carfax_handler(callback: CallbackQuery):
    if not await premium_locked(callback, "CarFax"):
        return

    await tracked_callback_answer(
        callback,
        "CarFax ✅\nPut your premium CarFax content here.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


# =========================
# Support
# =========================
@dp.callback_query(F.data == "support")
async def support_handler(callback: CallbackQuery):
    await tracked_callback_answer(
        callback,
        "Support System\nWrite your message here and we will check it.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


# =========================
# Admin
# =========================
@dp.callback_query(F.data == "subscribers_list")
async def subscribers_list_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("No permission", show_alert=True)
        return

    subscribers = get_active_subscribers()

    if not subscribers:
        await tracked_callback_answer(
            callback,
            "No active subscribers حاليا.",
            reply_markup=back_to_menu_keyboard(),
        )
        await callback.answer()
        return

    lines = [f"Active Subscribers: {len(subscribers)}\n"]

    for i, sub in enumerate(subscribers[:50], start=1):
        username = f"@{sub['username']}" if sub["username"] else "No username"
        phone_number = sub["phone_number"] if sub["phone_number"] else "No phone"
        lines.append(
            f"{i}. {sub['full_name']} | {username}\n"
            f"ID: {sub['user_id']}\n"
            f"Phone: {phone_number}\n"
            f"Expires: {format_dt(sub['expires_at'])}\n"
            f"Days Left: {sub['days_left']}\n"
        )

    await tracked_callback_answer(
        callback,
        "\n".join(lines),
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_accept:"))
async def admin_accept_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("No permission", show_alert=True)
        return

    try:
        _, user_id_str, days_str = callback.data.split(":")
        user_id = int(user_id_str)
        days = int(days_str)
    except Exception:
        await callback.answer("Invalid data", show_alert=True)
        return

    set_subscription(user_id, days)

    try:
        await tracked_bot_send(
            callback.bot,
            user_id,
            f"✅ Your subscription has been accepted and activated for {days} days.",
            reply_markup=back_to_menu_keyboard(),
        )
    except Exception:
        pass

    await callback.message.edit_text(
        callback.message.text + f"\n\n✅ Accepted for {days} days."
    )
    await callback.answer("Activated")


@dp.callback_query(F.data.startswith("admin_reject:"))
async def admin_reject_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("No permission", show_alert=True)
        return

    try:
        _, user_id_str = callback.data.split(":")
        user_id = int(user_id_str)
    except Exception:
        await callback.answer("Invalid data", show_alert=True)
        return

    try:
        await tracked_bot_send(
            callback.bot,
            user_id,
            "❌ Your payment request was rejected. Contact support if you already paid.",
            reply_markup=back_to_menu_keyboard(),
        )
    except Exception:
        pass

    await callback.message.edit_text(callback.message.text + "\n\n❌ Rejected.")
    await callback.answer("Rejected")


@dp.message(Command("accept"))
async def accept_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()

    if len(parts) < 2:
        await tracked_message_answer(message, "Usage:\n/accept USER_ID 30")
        return

    try:
        user_id = int(parts[1])
        days = int(parts[2]) if len(parts) >= 3 else SUBSCRIPTION_DAYS
    except ValueError:
        await tracked_message_answer(message, "USER_ID and DAYS must be numbers.")
        return

    set_subscription(user_id, days)

    await tracked_message_answer(message, f"✅ User {user_id} activated for {days} days.")

    try:
        await tracked_bot_send(
            message.bot,
            user_id,
            f"✅ Your subscription has been activated for {days} days.",
            reply_markup=back_to_menu_keyboard(),
        )
    except Exception:
        pass


@dp.message(Command("remove"))
async def remove_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()

    if len(parts) != 2:
        await tracked_message_answer(message, "Usage:\n/remove USER_ID")
        return

    try:
        user_id = int(parts[1])
    except ValueError:
        await tracked_message_answer(message, "USER_ID must be a number.")
        return

    deleted = remove_subscription(user_id)

    if deleted:
        await tracked_message_answer(message, f"✅ Subscription removed for user {user_id}.")
    else:
        await tracked_message_answer(message, "No saved subscription for this user.")


@dp.message(Command("checkuser"))
async def checkuser_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()

    if len(parts) != 2:
        await tracked_message_answer(message, "Usage:\n/checkuser USER_ID")
        return

    try:
        user_id = int(parts[1])
    except ValueError:
        await tracked_message_answer(message, "USER_ID must be a number.")
        return

    user = get_user(user_id)
    sub_text = get_subscription_text(user_id)

    if user:
        username_text = f"@{user.get('username')}" if user.get("username") else "No username"
        phone_number = user.get("phone_number", "No phone")
        text = (
            f"Name: {user.get('full_name', 'Unknown')}\n"
            f"User: {username_text}\n"
            f"User ID: {user_id}\n"
            f"Phone Number: {phone_number}\n\n"
            f"{sub_text}"
        )
    else:
        text = f"No saved user info.\n\n{sub_text}"

    await tracked_message_answer(message, text)


@dp.message(Command("subs"))
async def subs_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    subscribers = get_active_subscribers()

    if not subscribers:
        await tracked_message_answer(message, "No active subscribers حاليا.")
        return

    lines = [f"Active Subscribers: {len(subscribers)}\n"]

    for i, sub in enumerate(subscribers[:50], start=1):
        username = f"@{sub['username']}" if sub["username"] else "No username"
        phone_number = sub["phone_number"] if sub["phone_number"] else "No phone"
        lines.append(
            f"{i}. {sub['full_name']} | {username}\n"
            f"ID: {sub['user_id']}\n"
            f"Phone: {phone_number}\n"
            f"Expires: {format_dt(sub['expires_at'])}\n"
            f"Days Left: {sub['days_left']}\n"
        )

    await tracked_message_answer(message, "\n".join(lines))


# =========================
# Catch-all messages
# =========================
@dp.message()
async def message_handler(message: Message):
    store_user(message.from_user)
    user_id = message.from_user.id

    if user_id in pending_phone_users:
        phone_number = normalize_phone_number(message.text or "")

        if not is_valid_phone_number(phone_number):
            await tracked_message_answer(
                message,
                "Invalid phone number format.\nSend it like: 03XXXXXX or +9613XXXXXX",
                reply_markup=back_to_menu_keyboard(),
            )
            return

        update_user_phone(user_id, phone_number)
        pending_phone_users.discard(user_id)

        user = message.from_user
        username_text = f"@{user.username}" if user.username else "No username"

        admin_text = (
            "New Payment Request 🔔\n\n"
            f"Name: {user.full_name}\n"
            f"User: {username_text}\n"
            f"User ID: {user.id}\n"
            f"Phone Number: {phone_number}\n"
            f"Price: ${SUBSCRIPTION_PRICE}\n"
            f"Duration: {SUBSCRIPTION_DAYS} days\n"
            f"Whish Destination: {WHISH_DESTINATION}\n\n"
            "Check the payment manually, then Accept or Reject."
        )

        await tracked_bot_send(
            message.bot,
            ADMIN_ID,
            admin_text,
            reply_markup=admin_request_keyboard(user.id),
        )

        await tracked_message_answer(
            message,
            "Your phone number and payment request were sent ✅",
            reply_markup=main_menu(user.id),
        )
        return

    if has_active_subscription(user_id):
        await tracked_message_answer(
            message,
            "Use the menu buttons to access the bot features.",
            reply_markup=main_menu(user_id),
        )
    else:
        await tracked_message_answer(
            message,
            "This bot requires a paid subscription.\nUse /start or open Subscription from the menu.",
            reply_markup=main_menu(user_id),
        )


# =========================
# Webhook setup
# =========================
async def on_startup(bot: Bot) -> None:
    await set_commands(bot)
    await bot.set_webhook(
        url=f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}",
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
    )
    asyncio.create_task(reminder_loop(bot))


async def healthcheck(request: web.Request) -> web.Response:
    return web.Response(text="OK")


def create_app() -> web.Application:
    ensure_storage()
    logging.basicConfig(level=logging.INFO)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp.startup.register(on_startup)

    app = web.Application()
    app.router.add_get("/", healthcheck)
    app.router.add_get("/health", healthcheck)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        handle_in_background=True,
        secret_token=WEBHOOK_SECRET,
    ).register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)
