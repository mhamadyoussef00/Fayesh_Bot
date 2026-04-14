from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.config import SUBSCRIPTION_DAYS, SUBSCRIPTION_PRICE, WHISH_DESTINATION, ADMIN_ID
from app.keyboards import back_to_menu_keyboard, subscription_menu, admin_request_keyboard, main_menu
from app.storage import (
    store_user,
    get_subscription_text,
    has_active_subscription,
    pending_phone_users,
    normalize_phone_number,
    is_valid_phone_number,
    update_user_phone,
)
from app.utils import tracked_message_answer, tracked_callback_answer, tracked_bot_send

router = Router()


@router.message(Command("payment"))
async def payment_command(message: Message):
    await tracked_message_answer(
        message,
        "Payment Info\n\n"
        f"Price: ${SUBSCRIPTION_PRICE}\n"
        f"Duration: {SUBSCRIPTION_DAYS} days\n"
        f"Pay to Whish account:\n{WHISH_DESTINATION}",
        reply_markup=subscription_menu(),
    )


@router.message(Command("status"))
async def status_command(message: Message):
    await tracked_message_answer(
        message,
        get_subscription_text(message.from_user.id),
        reply_markup=back_to_menu_keyboard(),
    )


@router.callback_query(F.data == "subscription_status")
async def subscription_status_handler(callback: CallbackQuery):
    await tracked_callback_answer(
        callback,
        get_subscription_text(callback.from_user.id),
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "payment_info")
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


@router.callback_query(F.data == "payment_sent")
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


@router.message()
async def pending_phone_handler(message: Message):
    user_id = message.from_user.id

    if user_id not in pending_phone_users:
        return

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