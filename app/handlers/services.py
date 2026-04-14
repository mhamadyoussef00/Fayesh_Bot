from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.keyboards import back_to_menu_keyboard
from app.utils import premium_locked, tracked_callback_answer

router = Router()


@router.callback_query(F.data == "car_number")
async def car_number_handler(callback: CallbackQuery):
    if not await premium_locked(callback, "Car Number"):
        return

    await tracked_callback_answer(
        callback,
        "Car Number Search ✅\nPut your premium car number content here.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "phone_search")
async def phone_search_handler(callback: CallbackQuery):
    if not await premium_locked(callback, "Phone Number Search"):
        return

    await tracked_callback_answer(
        callback,
        "Phone Number Search ✅\nPut your premium phone search content here.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "market")
async def market_handler(callback: CallbackQuery):
    if not await premium_locked(callback, "Live Market"):
        return

    await tracked_callback_answer(
        callback,
        "Live Market ✅\nPut your premium market content here.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "social")
async def social_handler(callback: CallbackQuery):
    if not await premium_locked(callback, "Social Media App"):
        return

    await tracked_callback_answer(
        callback,
        "Social Media App ✅\nPut your premium social media content here.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "carfax")
async def carfax_handler(callback: CallbackQuery):
    if not await premium_locked(callback, "CarFax"):
        return

    await tracked_callback_answer(
        callback,
        "CarFax ✅\nPut your premium CarFax content here.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()