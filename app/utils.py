import asyncio
import logging

from aiogram import Bot
from aiogram.types import Message, CallbackQuery, BotCommand

from app.config import (
    CHECK_INTERVAL_SECONDS,
    REMINDER_DAYS,
    SUBSCRIPTION_DAYS,
    SUBSCRIPTION_PRICE,
    WHISH_DESTINATION,
)
from app.keyboards import back_to_menu_keyboard, subscription_menu
from app.storage import (
    get_all_subscriptions,
    save_all_subscriptions,
    get_expiry_datetime,
    days_left_for_subscription,
    remember_bot_message,
    clear_saved_history,
    get_saved_history,
    has_active_subscription,
)


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

                seconds_left = (expires_at.timestamp() - __import__("time").time())
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
                        changed = True

            if changed:
                save_all_subscriptions(subs)

        except Exception as e:
            logging.exception("Reminder loop error: %s", e)

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)