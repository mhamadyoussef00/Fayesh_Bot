import asyncpg
from typing import Any, Optional

pool: Optional[asyncpg.Pool] = None


async def init_db(database_url: str) -> None:
    global pool

    pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=1,
        max_size=5,
    )

    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            full_name TEXT NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            phone_number TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id BIGINT PRIMARY KEY,
            status TEXT NOT NULL,
            start_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            approved_by BIGINT,
            payment_method TEXT,
            price TEXT,
            last_reminder_day_sent INTEGER,
            expired_notice_sent BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """)


async def close_db() -> None:
    global pool
    if pool is not None:
        await pool.close()
        pool = None


def _require_pool() -> asyncpg.Pool:
    if pool is None:
        raise RuntimeError("Database pool is not initialized.")
    return pool


async def store_user(user: Any) -> None:
    db = _require_pool()

    async with db.acquire() as conn:
        await conn.execute("""
        INSERT INTO users (
            user_id, full_name, username, first_name, last_name, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            username = EXCLUDED.username,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            updated_at = NOW();
        """,
        user.id,
        user.full_name,
        user.username or "",
        user.first_name or "",
        user.last_name or "",
        )


async def update_user_phone(user_id: int, phone_number: str) -> None:
    db = _require_pool()

    async with db.acquire() as conn:
        await conn.execute("""
        INSERT INTO users (
            user_id, full_name, username, first_name, last_name, phone_number, updated_at
        )
        VALUES ($1, '', '', '', '', $2, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            phone_number = EXCLUDED.phone_number,
            updated_at = NOW();
        """, user_id, phone_number)


async def get_user(user_id: int) -> Optional[dict]:
    db = _require_pool()

    async with db.acquire() as conn:
        row = await conn.fetchrow("""
        SELECT user_id, full_name, username, first_name, last_name, phone_number, updated_at
        FROM users
        WHERE user_id = $1
        """, user_id)

    return dict(row) if row else None


async def set_subscription(user_id: int, days: int, admin_id: int, price: str) -> None:
    db = _require_pool()

    async with db.acquire() as conn:
        await conn.execute("""
        INSERT INTO subscriptions (
            user_id,
            status,
            start_at,
            expires_at,
            approved_by,
            payment_method,
            price,
            last_reminder_day_sent,
            expired_notice_sent,
            updated_at
        )
        VALUES (
            $1,
            'active',
            NOW(),
            NOW() + ($2 || ' days')::interval,
            $3,
            'Whish manual approval',
            $4,
            NULL,
            FALSE,
            NOW()
        )
        ON CONFLICT (user_id) DO UPDATE SET
            status = 'active',
            start_at = NOW(),
            expires_at = NOW() + ($2 || ' days')::interval,
            approved_by = $3,
            payment_method = 'Whish manual approval',
            price = $4,
            last_reminder_day_sent = NULL,
            expired_notice_sent = FALSE,
            updated_at = NOW();
        """, user_id, days, admin_id, price)


async def get_subscription(user_id: int) -> Optional[dict]:
    db = _require_pool()

    async with db.acquire() as conn:
        row = await conn.fetchrow("""
        SELECT *
        FROM subscriptions
        WHERE user_id = $1
        """, user_id)

    return dict(row) if row else None


async def remove_subscription(user_id: int) -> bool:
    db = _require_pool()

    async with db.acquire() as conn:
        result = await conn.execute("""
        DELETE FROM subscriptions
        WHERE user_id = $1
        """, user_id)

    return result != "DELETE 0"


async def get_active_subscribers() -> list[dict]:
    db = _require_pool()

    async with db.acquire() as conn:
        rows = await conn.fetch("""
        SELECT
            u.user_id,
            u.full_name,
            u.username,
            u.phone_number,
            s.expires_at
        FROM subscriptions s
        LEFT JOIN users u ON u.user_id = s.user_id
        WHERE s.status = 'active'
          AND s.expires_at > NOW()
        ORDER BY s.expires_at ASC
        """)

    return [dict(row) for row in rows]


async def get_all_active_subscriptions() -> list[dict]:
    db = _require_pool()

    async with db.acquire() as conn:
        rows = await conn.fetch("""
        SELECT *
        FROM subscriptions
        WHERE status = 'active'
        ORDER BY expires_at ASC
        """)

    return [dict(row) for row in rows]


async def update_subscription_reminder(
    user_id: int,
    last_reminder_day_sent: Optional[int],
    expired_notice_sent: bool,
) -> None:
    db = _require_pool()

    async with db.acquire() as conn:
        await conn.execute("""
        UPDATE subscriptions
        SET
            last_reminder_day_sent = $2,
            expired_notice_sent = $3,
            updated_at = NOW()
        WHERE user_id = $1
        """, user_id, last_reminder_day_sent, expired_notice_sent)