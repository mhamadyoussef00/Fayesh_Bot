from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.config import SUBSCRIPTION_DAYS
from app.keyboards import back_to_menu_keyboard
from app.storage import (
    is_admin,
    get_active_subscribers,
    format_dt,
    set_subscription,
    remove_subscription,
    get_user,
    get_subscription_text,
)
from app.utils import tracked_callback_answer, tracked_bot_send, tracked_message_answer

router = Router()


@router.callback_query(F.data == "subscribers_list")
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


@router.callback_query(F.data.startswith("admin_accept:"))
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


@router.callback_query(F.data.startswith("admin_reject:"))
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


@router.message(Command("accept"))
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


@router.message(Command("remove"))
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


@router.message(Command("checkuser"))
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


@router.message(Command("subs"))
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