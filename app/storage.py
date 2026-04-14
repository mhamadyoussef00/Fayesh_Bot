import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import ADMIN_ID, SUBSCRIPTION_DAYS, SUBSCRIPTION_PRICE

DATA_DIR = Path("data")
USERS_FILE = DATA_DIR / "users.json"
SUBSCRIPTIONS_FILE = DATA_DIR / "subscriptions.json"
CLEAR_HISTORY_FILE = DATA_DIR / "clear_history.json"

pending_phone_users = set()


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