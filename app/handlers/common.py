from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery

from app.keyboards import main_menu, services_menu, subscription_menu, admin_menu, back_to_menu_keyboard
from app.storage import store_user, get_subscription_text, is_admin
from app.utils import tracked_message_answer, tracked_callback_answer, clear_recent_bot_messages
from app.config import SUBSCRIPTION_PRICE, SUBSCRIPTION_DAYS

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message):
    store_user(message.from_user)
    user_id = message.from_user.id

    text = (
        "Welcome to Fayesh_Bot 👋\n\n"
        f"Subscription: ${SUBSCRIPTION_PRICE} / {SUBSCRIPTION_DAYS} days"
    )

    await tracked_message_answer(message, text, reply_markup=main_menu(user_id))


@router.message(Command("menu"))
async def menu_command(message: Message):
    store_user(message.from_user)
    await tracked_message_answer(message, "Main Menu", reply_markup=main_menu(message.from_user.id))


@router.message(Command("account"))
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


@router.message(Command("support"))
async def support_command(message: Message):
    await tracked_message_answer(
        message,
        "Support System\nWrite your message here and we will check it.",
        reply_markup=back_to_menu_keyboard(),
    )


@router.message(Command("clear"))
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


@router.callback_query(F.data == "back_menu")
async def back_menu_handler(callback: CallbackQuery):
    await tracked_callback_answer(callback, "Main Menu", reply_markup=main_menu(callback.from_user.id))
    await callback.answer()


@router.callback_query(F.data == "services_menu")
async def services_menu_handler(callback: CallbackQuery):
    await tracked_callback_answer(callback, "Services Menu", reply_markup=services_menu())
    await callback.answer()


@router.callback_query(F.data == "subscription_menu")
async def subscription_menu_handler(callback: CallbackQuery):
    await tracked_callback_answer(callback, "Subscription Menu", reply_markup=subscription_menu())
    await callback.answer()


@router.callback_query(F.data == "support")
async def support_handler(callback: CallbackQuery):
    await tracked_callback_answer(
        callback,
        "Support System\nWrite your message here and we will check it.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "account")
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


@router.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("No permission", show_alert=True)
        return

    await tracked_callback_answer(callback, "Admin Panel", reply_markup=admin_menu())
    await callback.answer()