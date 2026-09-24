"""SQLite ma'lumotlar bazasi.

Jadvallar: users, groups, posts, referrals. Barcha userga tegishli amallar
Telegram UID bilan scope qilinadi; StringSession qiymatlari DB ichida
shifrlanadi.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import aiosqlite

from config.config import DB_PATH, SUPER_ADMIN
from core.logger import log
from core.session_crypto import decrypt_session, encrypt_session, ensure_session_cipher
from core.utils import iso_now

_db: aiosqlite.Connection | None = None
_write_lock = asyncio.Lock()

_USER_COLUMNS = {
    "name",
    "username",
    "phone",
    "session",
    "pending_session",
    "is_admin",
    "is_blocked",
    "awaiting_approval",
    "tariff_expires_at",
    "warned_at",
    "interval_min",
    "running",
    "referrer_uid",
    "referral_counted",
}


def _decode_user(row: aiosqlite.Row | dict | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    data["session"] = decrypt_session(data.get("session"))
    data["pending_session"] = decrypt_session(data.get("pending_session"))
    return data


async def _migrate_schema() -> None:
    """Eski DB'larni ma'lumot yo'qotmasdan joriy xavfsiz formatga o'tkazadi."""
    conn = _conn()

    # Eski bazada bir telefon bir nechta UID'da bo'lsa, eng ishonchli yozuvni
    # saqlab, qolganlar telefonini bo'shatamiz. Sessiyalar o'chirilmaydi.
    async with conn.execute(
        "SELECT phone FROM users WHERE phone != '' GROUP BY phone HAVING COUNT(*) > 1"
    ) as cur:
        duplicate_phones = [row["phone"] for row in await cur.fetchall()]

    for phone in duplicate_phones:
        async with conn.execute(
            "SELECT uid FROM users WHERE phone = ? "
            "ORDER BY (session != '') DESC, is_admin DESC, created_at ASC, uid ASC",
            (phone,),
        ) as cur:
            rows = await cur.fetchall()
        keep_uid = int(rows[0]["uid"])
        await conn.execute(
            "UPDATE users SET phone = '' WHERE phone = ? AND uid != ?",
            (phone, keep_uid),
        )
        log(
            f"⚠️ Duplicate telefon migratsiyasi: {len(rows) - 1} ta yozuv "
            f"tozalandi, egasi uid={keep_uid}",
            "warning",
        )

    await conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_unique "
        "ON users(phone) WHERE phone != ''"
    )

    # Oldingi plaintext StringSession'larni bir marta shifrlaymiz.
    async with conn.execute(
        "SELECT uid, session, pending_session FROM users "
        "WHERE session != '' OR pending_session != ''"
    ) as cur:
        rows = await cur.fetchall()

    migrated = 0
    for row in rows:
        session = row["session"] or ""
        pending = row["pending_session"] or ""
        encrypted_session = encrypt_session(session)
        encrypted_pending = encrypt_session(pending)
        if encrypted_session != session or encrypted_pending != pending:
            await conn.execute(
                "UPDATE users SET session = ?, pending_session = ? WHERE uid = ?",
                (encrypted_session, encrypted_pending, row["uid"]),
            )
            migrated += 1

    await conn.commit()
    if migrated:
        # Eski plaintext qiymatlar freelist/WAL sahifalarida qolib ketmasin.
        await conn.execute("VACUUM")
        await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        log(f"🔐 {migrated} ta user sessiyasi DB ichida shifrlandi")


async def init_db() -> None:
    global _db
    ensure_session_cipher()
    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA synchronous=NORMAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            uid INTEGER PRIMARY KEY,
            name TEXT DEFAULT '',
            username TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            session TEXT DEFAULT '',
            pending_session TEXT DEFAULT '',
            is_admin INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0,
            awaiting_approval INTEGER DEFAULT 0,
            tariff_expires_at TEXT,
            warned_at TEXT,
            interval_min INTEGER DEFAULT 60,
            running INTEGER DEFAULT 0,
            referrer_uid INTEGER,
            referral_counted INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT,
            UNIQUE(uid, value),
            FOREIGN KEY (uid) REFERENCES users(uid) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_groups_uid ON groups(uid);
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            text TEXT DEFAULT '',
            entities TEXT DEFAULT '[]',
            photo TEXT DEFAULT '',
            created_at TEXT,
            FOREIGN KEY (uid) REFERENCES users(uid) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_posts_uid ON posts(uid);
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_uid INTEGER NOT NULL,
            referred_uid INTEGER NOT NULL,
            counted INTEGER DEFAULT 0,
            created_at TEXT,
            UNIQUE(referred_uid),
            FOREIGN KEY (referrer_uid) REFERENCES users(uid) ON DELETE CASCADE,
            FOREIGN KEY (referred_uid) REFERENCES users(uid) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_uid);
    """)
    await _db.commit()
    await _migrate_schema()
    log("Baza tayyor")


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None
        log("Baza yopildi")


def _conn() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Baza ishga tushirilmagan.")
    return _db


async def _execute_write(query: str, params: tuple | list = ()) -> aiosqlite.Cursor:
    """Bitta write+commitni boshqa transactionlar bilan aralashishdan saqlaydi."""
    async with _write_lock:
        try:
            cursor = await _conn().execute(query, params)
            await _conn().commit()
            return cursor
        except Exception:
            await _conn().rollback()
            raise


async def backup_to(
    destination: str | Path, *, sanitize_sessions: bool = False
) -> None:
    """WAL bilan ham izchil SQLite online backup yaratadi."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    existed = destination.exists()
    target = await aiosqlite.connect(str(destination))
    try:
        async with _write_lock:
            await _conn().backup(target)
        if sanitize_sessions:
            await target.execute("PRAGMA journal_mode=DELETE")
            await target.execute("UPDATE users SET session = '', pending_session = ''")
            await target.commit()
            # UPDATE'dan oldingi shifrlangan tokenlar bo'sh sahifalarda ham qolmasin.
            await target.execute("VACUUM")
    except BaseException:
        await target.close()
        if not existed:
            destination.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm", "-journal"):
                Path(f"{destination}{suffix}").unlink(missing_ok=True)
        raise
    else:
        await target.close()
    if sanitize_sessions:
        for suffix in ("-wal", "-shm", "-journal"):
            Path(f"{destination}{suffix}").unlink(missing_ok=True)


# ─────────────────────────────────────────
# USERS
# ─────────────────────────────────────────
async def get_user(uid: int) -> dict | None:
    async with _conn().execute("SELECT * FROM users WHERE uid = ?", (uid,)) as cur:
        return _decode_user(await cur.fetchone())


async def get_user_by_phone(phone: str) -> dict | None:
    if not phone:
        return None
    async with _conn().execute("SELECT * FROM users WHERE phone = ?", (phone,)) as cur:
        return _decode_user(await cur.fetchone())


async def upsert_user(uid: int, **fields: Any) -> None:
    """Atomic INSERT/UPDATE; parallel update paytida duplicate UID xatosi bo'lmaydi."""
    unknown = set(fields) - _USER_COLUMNS
    if unknown:
        raise ValueError(f"Noma'lum users ustuni: {', '.join(sorted(unknown))}")

    values = dict(fields)
    if "session" in values:
        values["session"] = encrypt_session(values["session"])
    if "pending_session" in values:
        values["pending_session"] = encrypt_session(values["pending_session"])

    now = iso_now()
    columns = ["uid", "created_at", "updated_at", *values.keys()]
    params = [uid, now, now, *values.values()]
    placeholders = ",".join("?" for _ in columns)

    if values:
        updates = [f"{name} = excluded.{name}" for name in values]
        updates.append("updated_at = excluded.updated_at")
        conflict = f"DO UPDATE SET {', '.join(updates)}"
    else:
        conflict = "DO NOTHING"

    await _execute_write(
        f"INSERT INTO users ({','.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(uid) {conflict}",
        params,
    )


async def set_user_info(uid: int, name: str, username: str = "") -> None:
    await upsert_user(uid, name=name, username=username)


async def get_user_info(uid: int) -> dict:
    user = await get_user(uid)
    if not user:
        return {"name": "", "username": ""}
    return {"name": user.get("name", ""), "username": user.get("username", "")}


async def set_phone(uid: int, phone: str) -> bool:
    try:
        await upsert_user(uid, phone=phone)
        return True
    except aiosqlite.IntegrityError:
        return False


async def set_phone_existing(uid: int, phone: str) -> bool:
    try:
        cur = await _execute_write(
            "UPDATE users SET phone = ?, updated_at = ? WHERE uid = ?",
            (phone, iso_now(), uid),
        )
        return cur.rowcount > 0
    except aiosqlite.IntegrityError:
        return False


async def get_phone(uid: int) -> str:
    user = await get_user(uid)
    return user.get("phone", "") if user else ""


async def set_session(uid: int, session: str) -> bool:
    cur = await _execute_write(
        "UPDATE users SET session = ?, updated_at = ? WHERE uid = ?",
        (encrypt_session(session), iso_now(), uid),
    )
    return cur.rowcount > 0


async def get_session(uid: int) -> str:
    user = await get_user(uid)
    return user.get("session", "") if user else ""


async def del_session(uid: int) -> bool:
    return await set_session(uid, "")


async def set_pending(uid: int, session: str) -> bool:
    cur = await _execute_write(
        "UPDATE users SET pending_session = ?, updated_at = ? WHERE uid = ?",
        (encrypt_session(session), iso_now(), uid),
    )
    return cur.rowcount > 0


async def get_pending(uid: int) -> str:
    user = await get_user(uid)
    return user.get("pending_session", "") if user else ""


async def del_pending(uid: int) -> bool:
    return await set_pending(uid, "")


async def is_admin(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("is_admin"))


async def add_admin(uid: int) -> None:
    await upsert_user(uid, is_admin=1)


async def approve_user(uid: int, default_expires: str | None = None) -> bool:
    """Mavjud userni bitta SQL write bilan tasdiqlaydi va default tarif beradi."""
    cur = await _execute_write(
        "UPDATE users SET is_admin = 1, awaiting_approval = 0, "
        "warned_at = CASE "
        "WHEN is_admin = 1 AND tariff_expires_at IS NOT NULL "
        "AND tariff_expires_at != '' THEN warned_at ELSE NULL END, "
        "tariff_expires_at = COALESCE(NULLIF(tariff_expires_at, ''), ?), "
        "updated_at = ? WHERE uid = ?",
        (default_expires, iso_now(), uid),
    )
    return cur.rowcount > 0


async def get_admins() -> list[int]:
    async with _conn().execute("SELECT uid FROM users WHERE is_admin = 1") as cur:
        return [row["uid"] for row in await cur.fetchall()]


async def delete_user(uid: int) -> bool:
    cur = await _execute_write("DELETE FROM users WHERE uid = ?", (uid,))
    return cur.rowcount > 0


async def is_blocked(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("is_blocked"))


async def set_blocked(uid: int, blocked: bool) -> bool:
    cur = await _execute_write(
        "UPDATE users SET is_blocked = ?, updated_at = ? WHERE uid = ?",
        (1 if blocked else 0, iso_now(), uid),
    )
    return cur.rowcount > 0


async def set_awaiting_approval(uid: int, awaiting: bool) -> bool:
    cur = await _execute_write(
        "UPDATE users SET awaiting_approval = ?, updated_at = ? WHERE uid = ?",
        (1 if awaiting else 0, iso_now(), uid),
    )
    return cur.rowcount > 0


async def is_awaiting_approval(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("awaiting_approval"))


async def set_tariff_expires(uid: int, expires_iso: str | None) -> bool:
    cur = await _execute_write(
        "UPDATE users SET tariff_expires_at = ?, warned_at = NULL, "
        "updated_at = ? WHERE uid = ?",
        (expires_iso, iso_now(), uid),
    )
    return cur.rowcount > 0


async def get_tariff_expires(uid: int) -> str | None:
    user = await get_user(uid)
    return user.get("tariff_expires_at") if user else None


async def mark_warned(uid: int) -> bool:
    cur = await _execute_write(
        "UPDATE users SET warned_at = ?, updated_at = ? WHERE uid = ?",
        (iso_now(), iso_now(), uid),
    )
    return cur.rowcount > 0


async def is_warned(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("warned_at"))


async def get_expired_users() -> list[int]:
    async with _conn().execute(
        "SELECT uid FROM users WHERE tariff_expires_at IS NOT NULL "
        "AND tariff_expires_at <= ? AND running = 1",
        (iso_now(),),
    ) as cur:
        return [row["uid"] for row in await cur.fetchall()]


async def get_last_day_users() -> list[int]:
    async with _conn().execute(
        "SELECT uid FROM users WHERE tariff_expires_at IS NOT NULL "
        "AND warned_at IS NULL"
    ) as cur:
        return [row["uid"] for row in await cur.fetchall()]


async def get_interval(uid: int) -> int:
    user = await get_user(uid)
    return int(user.get("interval_min", 60)) if user else 60


async def set_interval(uid: int, minutes: int) -> bool:
    cur = await _execute_write(
        "UPDATE users SET interval_min = ?, updated_at = ? WHERE uid = ?",
        (minutes, iso_now(), uid),
    )
    return cur.rowcount > 0


async def set_running(uid: int, running: bool) -> bool:
    cur = await _execute_write(
        "UPDATE users SET running = ?, updated_at = ? WHERE uid = ?",
        (1 if running else 0, iso_now(), uid),
    )
    return cur.rowcount > 0


async def get_all_running() -> list[int]:
    async with _conn().execute("SELECT uid FROM users WHERE running = 1") as cur:
        return [row["uid"] for row in await cur.fetchall()]


# ─────────────────────────────────────────
# GROUPS
# ─────────────────────────────────────────
async def get_chat_records(uid: int) -> list[dict]:
    async with _conn().execute(
        "SELECT id, uid, value, created_at FROM groups WHERE uid = ? ORDER BY id",
        (uid,),
    ) as cur:
        return [dict(row) for row in await cur.fetchall()]


async def get_chats(uid: int) -> list[str]:
    return [row["value"] for row in await get_chat_records(uid)]


async def add_chat(uid: int, value: str) -> tuple[bool, str]:
    try:
        await _execute_write(
            "INSERT INTO groups (uid, value, created_at) VALUES (?, ?, ?)",
            (uid, value, iso_now()),
        )
        return True, "ok"
    except aiosqlite.IntegrityError:
        return False, "duplicate"
    except Exception as exc:
        log(f"add_chat xatolik: {exc}", "error")
        return False, "error"


async def remove_chat_by_id(uid: int, group_id: int) -> str | None:
    async with _conn().execute(
        "SELECT value FROM groups WHERE id = ? AND uid = ?", (group_id, uid)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    cur = await _execute_write(
        "DELETE FROM groups WHERE id = ? AND uid = ?", (group_id, uid)
    )
    return row["value"] if cur.rowcount else None


async def remove_chat(uid: int, index: int) -> str | None:
    records = await get_chat_records(uid)
    if not 0 <= index < len(records):
        return None
    return await remove_chat_by_id(uid, int(records[index]["id"]))


async def remove_chat_by_value(uid: int, value: str) -> bool:
    cur = await _execute_write(
        "DELETE FROM groups WHERE uid = ? AND value = ?", (uid, value)
    )
    return cur.rowcount > 0


async def count_chats(uid: int) -> int:
    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM groups WHERE uid = ?", (uid,)
    ) as cur:
        row = await cur.fetchone()
        return row["n"] if row else 0


async def clear_chats(uid: int) -> list[str]:
    chats = await get_chats(uid)
    await _execute_write("DELETE FROM groups WHERE uid = ?", (uid,))
    return chats


# ─────────────────────────────────────────
# POSTS
# ─────────────────────────────────────────
def _decode_post(row: aiosqlite.Row | dict | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    try:
        data["entities"] = json.loads(data.get("entities") or "[]")
    except Exception:
        data["entities"] = []
    return data


async def get_posts(uid: int) -> list[dict]:
    async with _conn().execute(
        "SELECT * FROM posts WHERE uid = ? ORDER BY id", (uid,)
    ) as cur:
        return [_decode_post(row) for row in await cur.fetchall()]


async def get_post(post_id: int, uid: int | None = None) -> dict | None:
    if uid is None:
        query, params = "SELECT * FROM posts WHERE id = ?", (post_id,)
    else:
        query, params = "SELECT * FROM posts WHERE id = ? AND uid = ?", (post_id, uid)
    async with _conn().execute(query, params) as cur:
        return _decode_post(await cur.fetchone())


async def add_post(
    uid: int, text: str, entities: list[dict], photo: str | None
) -> tuple[bool, str, int | None]:
    try:
        entities_json = json.dumps(entities or [], ensure_ascii=False)
        cur = await _execute_write(
            "INSERT INTO posts (uid, text, entities, photo, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uid, text, entities_json, photo or "", iso_now()),
        )
        return True, "ok", cur.lastrowid
    except Exception as exc:
        log(f"add_post xatolik: {exc}", "error")
        return False, "error", None


async def update_post(
    uid: int, post_id: int, text: str, entities: list[dict], photo: str | None
) -> bool:
    try:
        entities_json = json.dumps(entities or [], ensure_ascii=False)
        cur = await _execute_write(
            "UPDATE posts SET text = ?, entities = ?, photo = ? "
            "WHERE id = ? AND uid = ?",
            (text, entities_json, photo or "", post_id, uid),
        )
        return cur.rowcount > 0
    except Exception as exc:
        log(f"update_post xatolik: {exc}", "error")
        return False


async def remove_post_by_id(uid: int, post_id: int) -> dict | None:
    post = await get_post(post_id, uid)
    if not post:
        return None
    cur = await _execute_write(
        "DELETE FROM posts WHERE id = ? AND uid = ?", (post_id, uid)
    )
    return post if cur.rowcount else None


async def remove_post(uid: int, index: int) -> dict | None:
    posts = await get_posts(uid)
    if not 0 <= index < len(posts):
        return None
    return await remove_post_by_id(uid, int(posts[index]["id"]))


async def count_posts(uid: int) -> int:
    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM posts WHERE uid = ?", (uid,)
    ) as cur:
        row = await cur.fetchone()
        return row["n"] if row else 0


async def clear_posts(uid: int) -> list[dict]:
    posts = await get_posts(uid)
    await _execute_write("DELETE FROM posts WHERE uid = ?", (uid,))
    return posts


# ─────────────────────────────────────────
# REFERRALS
# ─────────────────────────────────────────
async def set_referrer(uid: int, referrer_uid: int) -> bool:
    """Mavjud, tasdiqlangan referrerni user va referral jadvaliga atomar yozadi."""
    if uid == referrer_uid:
        return False

    now = iso_now()
    async with _write_lock:
        try:
            owner_cursor = await _conn().execute(
                "SELECT is_admin, is_blocked FROM users WHERE uid = ?",
                (referrer_uid,),
            )
            owner = await owner_cursor.fetchone()
            if not owner or not owner["is_admin"] or owner["is_blocked"]:
                return False
            cur = await _conn().execute(
                "INSERT INTO users (uid, referrer_uid, created_at, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(uid) DO UPDATE SET "
                "referrer_uid = excluded.referrer_uid, "
                "updated_at = excluded.updated_at "
                "WHERE users.referrer_uid IS NULL "
                "AND users.is_admin = 0 AND users.is_blocked = 0",
                (uid, referrer_uid, now, now),
            )
            if cur.rowcount != 1:
                await _conn().commit()
                return False
            referral = await _conn().execute(
                "INSERT OR IGNORE INTO referrals "
                "(referrer_uid, referred_uid, created_at) VALUES (?, ?, ?)",
                (referrer_uid, uid, now),
            )
            if referral.rowcount != 1:
                await _conn().rollback()
                return False
            await _conn().commit()
            return True
        except Exception as exc:
            await _conn().rollback()
            log(f"set_referrer xatolik: {exc}", "error")
            return False


async def try_count_referral(uid: int) -> int | None:
    """Referralni faqat mavjud bog'lanish uchun bir marta atomar hisoblaydi."""
    async with _write_lock:
        try:
            cursor = await _conn().execute(
                "SELECT u.referrer_uid FROM users u "
                "JOIN users owner ON owner.uid = u.referrer_uid "
                "WHERE u.uid = ? AND u.is_admin = 1 "
                "AND u.referral_counted = 0 "
                "AND owner.is_admin = 1 AND owner.is_blocked = 0",
                (uid,),
            )
            user = await cursor.fetchone()
            if not user:
                return None
            referrer = int(user["referrer_uid"])

            referral = await _conn().execute(
                "UPDATE referrals SET counted = 1 "
                "WHERE referred_uid = ? AND referrer_uid = ? AND counted = 0",
                (uid, referrer),
            )
            if referral.rowcount != 1:
                await _conn().rollback()
                return None
            user_update = await _conn().execute(
                "UPDATE users SET referral_counted = 1, updated_at = ? "
                "WHERE uid = ? AND referral_counted = 0",
                (iso_now(), uid),
            )
            if user_update.rowcount != 1:
                await _conn().rollback()
                return None
            await _conn().commit()
            return referrer
        except Exception:
            await _conn().rollback()
            raise


async def count_referrals(referrer_uid: int) -> int:
    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM referrals WHERE referrer_uid = ? AND counted = 1",
        (referrer_uid,),
    ) as cur:
        row = await cur.fetchone()
        return row["n"] if row else 0


async def get_referrals(referrer_uid: int) -> list[dict]:
    async with _conn().execute(
        "SELECT r.referred_uid, r.counted, u.name AS name "
        "FROM referrals r LEFT JOIN users u ON u.uid = r.referred_uid "
        "WHERE r.referrer_uid = ? ORDER BY r.id DESC",
        (referrer_uid,),
    ) as cur:
        rows = await cur.fetchall()
    return [
        {
            "uid": row["referred_uid"],
            "name": row["name"] or str(row["referred_uid"]),
            "counted": bool(row["counted"]),
        }
        for row in rows
    ]


# ─────────────────────────────────────────
# ADMIN LISTS / STATS
# ─────────────────────────────────────────
async def get_stats() -> dict:
    params = (SUPER_ADMIN,)

    async def count(query: str) -> int:
        async with _conn().execute(query, params) as cur:
            return int((await cur.fetchone())["n"])

    return {
        "total_users": await count("SELECT COUNT(*) AS n FROM users WHERE uid != ?"),
        "admins": await count(
            "SELECT COUNT(*) AS n FROM users WHERE is_admin = 1 AND uid != ?"
        ),
        "blocked": await count(
            "SELECT COUNT(*) AS n FROM users WHERE is_blocked = 1 AND uid != ?"
        ),
        "waiting": await count(
            "SELECT COUNT(*) AS n FROM users WHERE awaiting_approval = 1 AND uid != ?"
        ),
        "running": await count(
            "SELECT COUNT(*) AS n FROM users WHERE running = 1 AND uid != ?"
        ),
        "total_groups": await count("SELECT COUNT(*) AS n FROM groups WHERE uid != ?"),
        "total_posts": await count("SELECT COUNT(*) AS n FROM posts WHERE uid != ?"),
    }


async def get_all_users() -> list[dict]:
    async with _conn().execute(
        "SELECT * FROM users WHERE uid != ? ORDER BY created_at DESC",
        (SUPER_ADMIN,),
    ) as cur:
        return [_decode_user(row) for row in await cur.fetchall()]


async def get_pending_users() -> list[dict]:
    async with _conn().execute(
        "SELECT * FROM users WHERE uid != ? AND awaiting_approval = 1 "
        "ORDER BY created_at ASC",
        (SUPER_ADMIN,),
    ) as cur:
        return [_decode_user(row) for row in await cur.fetchall()]


async def get_broadcast_users() -> list[dict]:
    """Faqat tasdiqlangan va ilova ichida bloklanmagan userlar."""
    async with _conn().execute(
        "SELECT uid FROM users WHERE uid != ? AND is_admin = 1 "
        "AND is_blocked = 0 ORDER BY created_at",
        (SUPER_ADMIN,),
    ) as cur:
        return [dict(row) for row in await cur.fetchall()]


# ─────────────────────────────────────────
# TARIFF
# ─────────────────────────────────────────
async def is_tariff_expired(uid: int) -> bool:
    user = await get_user(uid)
    if not user:
        return False
    expires = user.get("tariff_expires_at")
    if not expires:
        return False
    from core.utils import is_expired

    return is_expired(expires)
