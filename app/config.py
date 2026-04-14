import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
WHISH_DESTINATION = os.getenv("WHISH_DESTINATION", "Put your Whish account here").strip()
SUBSCRIPTION_PRICE = os.getenv("SUBSCRIPTION_PRICE", "3").strip()
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
REMINDER_DAYS = int(os.getenv("REMINDER_DAYS", "3"))
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "300"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing in .env")

if not ADMIN_ID:
    raise ValueError("ADMIN_ID is missing in .env")