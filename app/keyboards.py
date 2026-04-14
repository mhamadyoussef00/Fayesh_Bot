from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import SUBSCRIPTION_DAYS
from app.storage import is_admin


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