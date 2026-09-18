"""
SQLite ma'lumotlar bazasi.
Jadvallar: users, groups, posts, referrals.
"""

from __future__ import annotations

import json
from typing import Any

import aiosqlite

from config.config import DB_PATH
from core.logger import log
from core.utils import iso_now

_db: aiosqlite.Connection | None = None


async def init_db() -> None:
    global _db
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
  

async def get_user(uid: int) -> dict | None:
    async with _conn().execute(
        "SELECT * FROM users WHERE uid = ?", (uid,)
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def upsert_user(uid: int, **fields: Any) -> None:
    existing = await get_user(uid)
    now = iso_now()
    if not existing:
        cols = ["uid", "created_at", "updated_at"]
        vals = [uid, now, now]
        for k, v in fields.items():
            cols.append(k)
            vals.append(v)
        placeholders = ",".join("?" * len(cols))
        sql = f"INSERT INTO users ({','.join(cols)}) VALUES ({placeholders})"
        await _conn().execute(sql, vals)
    else:
        if not fields:
            return
        set_parts = [f"{k} = ?" for k in fields.keys()]
        set_parts.append("updated_at = ?")
        vals = list(fields.values()) + [now, uid]
        sql = f"UPDATE users SET {','.join(set_parts)} WHERE uid = ?"
        await _conn().execute(sql, vals)
    await _conn().commit()


async def set_user_info(uid: int, name: str, username: str = "") -> None:
    await upsert_user(uid, name=name, username=username)


async def get_user_info(uid: int) -> dict:
    user = await get_user(uid)
    if not user:
        return {"name": "", "username": ""}
    return {"name": user.get("name", ""), "username": user.get("username", "")}


async def set_phone(uid: int, phone: str) -> None:
    await upsert_user(uid, phone=phone)


async def get_phone(uid: int) -> str:
    user = await get_user(uid)
    return user.get("phone", "") if user else ""


async def set_session(uid: int, session: str) -> None:
    await upsert_user(uid, session=session)


async def get_session(uid: int) -> str:
    user = await get_user(uid)
    return user.get("session", "") if user else ""


async def del_session(uid: int) -> None:
    await upsert_user(uid, session="")


async def set_pending(uid: int, session: str) -> None:
    await upsert_user(uid, pending_session=session)


async def get_pending(uid: int) -> str:
    user = await get_user(uid)
    return user.get("pending_session", "") if user else ""


async def del_pending(uid: int) -> None:
    await upsert_user(uid, pending_session="")
  

async def is_admin(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("is_admin"))


async def add_admin(uid: int) -> None:
    await upsert_user(uid, is_admin=1)


async def get_admins() -> list[int]:
    async with _conn().execute(
        "SELECT uid FROM users WHERE is_admin = 1"
    ) as cur:
        rows = await cur.fetchall()
        return [r["uid"] for r in rows]


async def delete_user(uid: int) -> None:
    await _conn().execute("DELETE FROM users WHERE uid = ?", (uid,))
    await _conn().commit()


async def is_blocked(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("is_blocked"))


async def set_blocked(uid: int, blocked: bool) -> None:
    await upsert_user(uid, is_blocked=1 if blocked else 0)


async def set_awaiting_approval(uid: int, awaiting: bool) -> None:
    await upsert_user(uid, awaiting_approval=1 if awaiting else 0)


async def is_awaiting_approval(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("awaiting_approval"))


async def set_tariff_expires(uid: int, expires_iso: str | None) -> None:
    await upsert_user(uid, tariff_expires_at=expires_iso, warned_at=None)


async def get_tariff_expires(uid: int) -> str | None:
    user = await get_user(uid)
    return user.get("tariff_expires_at") if user else None


async def mark_warned(uid: int) -> None:
    await upsert_user(uid, warned_at=iso_now())


async def is_warned(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("warned_at"))


async def get_expired_users() -> list[int]:
    async with _conn().execute(
        "SELECT uid FROM users WHERE tariff_expires_at IS NOT NULL "
        "AND tariff_expires_at <= ? AND running = 1",
        (iso_now(),),
    ) as cur:
        rows = await cur.fetchall()
        return [r["uid"] for r in rows]


async def get_last_day_users() -> list[int]:
    async with _conn().execute(
        "SELECT uid FROM users WHERE tariff_expires_at IS NOT NULL "
        "AND warned_at IS NULL",
    ) as cur:
        rows = await cur.fetchall()
        return [r["uid"] for r in rows]


async def get_interval(uid: int) -> int:
    user = await get_user(uid)
    return int(user.get("interval_min", 60)) if user else 60


async def set_interval(uid: int, minutes: int) -> None:
    await upsert_user(uid, interval_min=minutes)


async def set_running(uid: int, running: bool) -> None:
    await upsert_user(uid, running=1 if running else 0)


async def get_all_running() -> list[int]:
    async with _conn().execute(
        "SELECT uid FROM users WHERE running = 1"
    ) as cur:
        rows = await cur.fetchall()
        return [r["uid"] for r in rows]
      

async def is_admin(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("is_admin"))


async def add_admin(uid: int) -> None:
    await upsert_user(uid, is_admin=1)


async def get_admins() -> list[int]:
    async with _conn().execute(
        "SELECT uid FROM users WHERE is_admin = 1"
    ) as cur:
        rows = await cur.fetchall()
        return [r["uid"] for r in rows]


async def delete_user(uid: int) -> None:
    await _conn().execute("DELETE FROM users WHERE uid = ?", (uid,))
    await _conn().commit()


async def is_blocked(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("is_blocked"))


async def set_blocked(uid: int, blocked: bool) -> None:
    await upsert_user(uid, is_blocked=1 if blocked else 0)


async def set_awaiting_approval(uid: int, awaiting: bool) -> None:
    await upsert_user(uid, awaiting_approval=1 if awaiting else 0)


async def is_awaiting_approval(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("awaiting_approval"))


async def set_tariff_expires(uid: int, expires_iso: str | None) -> None:
    await upsert_user(uid, tariff_expires_at=expires_iso, warned_at=None)


async def get_tariff_expires(uid: int) -> str | None:
    user = await get_user(uid)
    return user.get("tariff_expires_at") if user else None


async def mark_warned(uid: int) -> None:
    await upsert_user(uid, warned_at=iso_now())


async def is_warned(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("warned_at"))


async def get_expired_users() -> list[int]:
    async with _conn().execute(
        "SELECT uid FROM users WHERE tariff_expires_at IS NOT NULL "
        "AND tariff_expires_at <= ? AND running = 1",
        (iso_now(),),
    ) as cur:
        rows = await cur.fetchall()
        return [r["uid"] for r in rows]


async def get_last_day_users() -> list[int]:
    async with _conn().execute(
        "SELECT uid FROM users WHERE tariff_expires_at IS NOT NULL "
        "AND warned_at IS NULL",
    ) as cur:
        rows = await cur.fetchall()
        return [r["uid"] for r in rows]


async def get_interval(uid: int) -> int:
    user = await get_user(uid)
    return int(user.get("interval_min", 60)) if user else 60


async def set_interval(uid: int, minutes: int) -> None:
    await upsert_user(uid, interval_min=minutes)


async def set_running(uid: int, running: bool) -> None:
    await upsert_user(uid, running=1 if running else 0)


async def get_all_running() -> list[int]:
    async with _conn().execute(
        "SELECT uid FROM users WHERE running = 1"
    ) as cur:
        rows = await cur.fetchall()
        return [r["uid"] for r in rows]
      

# ─────────────────────────────────────────
# GURUHLAR
# ─────────────────────────────────────────
async def get_chats(uid: int) -> list[str]:
    async with _conn().execute(
        "SELECT value FROM groups WHERE uid = ? ORDER BY id", (uid,)
    ) as cur:
        rows = await cur.fetchall()
        return [r["value"] for r in rows]


async def add_chat(uid: int, value: str) -> tuple[bool, str]:
    try:
        await _conn().execute(
            "INSERT INTO groups (uid, value, created_at) VALUES (?, ?, ?)",
            (uid, value, iso_now()),
        )
        await _conn().commit()
        return True, "ok"
    except aiosqlite.IntegrityError:
        return False, "duplicate"
    except Exception as e:
        log(f"add_chat xatolik: {e}", "error")
        return False, "error"


async def remove_chat(uid: int, index: int) -> str | None:
    chats = await get_chats(uid)
    if not (0 <= index < len(chats)):
        return None
    value = chats[index]
    await _conn().execute(
        "DELETE FROM groups WHERE uid = ? AND value = ?", (uid, value)
    )
    await _conn().commit()
    return value


async def remove_chat_by_value(uid: int, value: str) -> bool:
    cur = await _conn().execute(
        "DELETE FROM groups WHERE uid = ? AND value = ?", (uid, value)
    )
    await _conn().commit()
    return cur.rowcount > 0


async def count_chats(uid: int) -> int:
    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM groups WHERE uid = ?", (uid,)
    ) as cur:
        row = await cur.fetchone()
        return row["n"] if row else 0


async def clear_chats(uid: int) -> list[str]:
    chats = await get_chats(uid)
    await _conn().execute("DELETE FROM groups WHERE uid = ?", (uid,))
    await _conn().commit()
    return chats
  

# ─────────────────────────────────────────
# POSTLAR
# ─────────────────────────────────────────
async def get_posts(uid: int) -> list[dict]:
    async with _conn().execute(
        "SELECT * FROM posts WHERE uid = ? ORDER BY id", (uid,)
    ) as cur:
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["entities"] = json.loads(d.get("entities") or "[]")
            except Exception:
                d["entities"] = []
            result.append(d)
        return result


async def get_post(post_id: int) -> dict | None:
    async with _conn().execute(
        "SELECT * FROM posts WHERE id = ?", (post_id,)
    ) as cur:
        row = await cur.fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["entities"] = json.loads(d.get("entities") or "[]")
        except Exception:
            d["entities"] = []
        return d


async def add_post(
    uid: int, text: str, entities: list[dict], photo: str | None
) -> tuple[bool, str, int | None]:
    try:
        entities_json = json.dumps(entities or [], ensure_ascii=False)
        cur = await _conn().execute(
            "INSERT INTO posts (uid, text, entities, photo, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uid, text, entities_json, photo or "", iso_now()),
        )
        await _conn().commit()
        return True, "ok", cur.lastrowid
    except Exception as e:
        log(f"add_post xatolik: {e}", "error")
        return False, "error", None


async def update_post(
    post_id: int, text: str, entities: list[dict], photo: str | None
) -> bool:
    try:
        entities_json = json.dumps(entities or [], ensure_ascii=False)
        await _conn().execute(
            "UPDATE posts SET text = ?, entities = ?, photo = ? WHERE id = ?",
            (text, entities_json, photo or "", post_id),
        )
        await _conn().commit()
        return True
    except Exception as e:
        log(f"update_post xatolik: {e}", "error")
        return False


async def remove_post(uid: int, index: int) -> dict | None:
    posts = await get_posts(uid)
    if not (0 <= index < len(posts)):
        return None
    post = posts[index]
    await _conn().execute("DELETE FROM posts WHERE id = ?", (post["id"],))
    await _conn().commit()
    return post


async def count_posts(uid: int) -> int:
    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM posts WHERE uid = ?", (uid,)
    ) as cur:
        row = await cur.fetchone()
        return row["n"] if row else 0


async def clear_posts(uid: int) -> list[dict]:
    posts = await get_posts(uid)
    await _conn().execute("DELETE FROM posts WHERE uid = ?", (uid,))
    await _conn().commit()
    return posts
  

# ─────────────────────────────────────────
# REFERALLAR
# ─────────────────────────────────────────
async def set_referrer(uid: int, referrer_uid: int) -> None:
    if uid == referrer_uid:
        return
    existing = await get_user(uid)
    if not existing:
        return
    if existing.get("referrer_uid"):
        return
    await upsert_user(uid, referrer_uid=referrer_uid)
    try:
        await _conn().execute(
            "INSERT OR IGNORE INTO referrals (referrer_uid, referred_uid, created_at) "
            "VALUES (?, ?, ?)",
            (referrer_uid, uid, iso_now()),
        )
        await _conn().commit()
    except Exception as e:
        log(f"set_referrer xatolik: {e}", "error")


async def try_count_referral(uid: int) -> int | None:
    user = await get_user(uid)
    if not user:
        return None
    if user.get("referral_counted"):
        return None
    referrer = user.get("referrer_uid")
    if not referrer:
        return None
    await upsert_user(uid, referral_counted=1)
    await _conn().execute(
        "UPDATE referrals SET counted = 1 WHERE referred_uid = ?", (uid,)
    )
    await _conn().commit()
    return referrer


async def count_referrals(referrer_uid: int) -> int:
    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM referrals "
        "WHERE referrer_uid = ? AND counted = 1",
        (referrer_uid,),
    ) as cur:
        row = await cur.fetchone()
        return row["n"] if row else 0


async def get_referrals(referrer_uid: int) -> list[dict]:
    async with _conn().execute(
        "SELECT r.referred_uid, r.counted, u.name AS name "
        "FROM referrals r "
        "LEFT JOIN users u ON u.uid = r.referred_uid "
        "WHERE r.referrer_uid = ? "
        "ORDER BY r.id DESC",
        (referrer_uid,),
    ) as cur:
        rows = await cur.fetchall()
        return [
            {
                "uid": r["referred_uid"],
                "name": r["name"] or str(r["referred_uid"]),
                "counted": bool(r["counted"]),
            }
            for r in rows
        ]


# ─────────────────────────────────────────
# STATISTIKA (admin uchun)
# ─────────────────────────────────────────
async def get_stats() -> dict:
    async with _conn().execute("SELECT COUNT(*) AS n FROM users") as cur:
        total = (await cur.fetchone())["n"]

    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM users WHERE is_admin = 1"
    ) as cur:
        admins = (await cur.fetchone())["n"]

    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM users WHERE is_blocked = 1"
    ) as cur:
        blocked = (await cur.fetchone())["n"]

    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM users WHERE awaiting_approval = 1"
    ) as cur:
        waiting = (await cur.fetchone())["n"]

    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM users WHERE running = 1"
    ) as cur:
        running = (await cur.fetchone())["n"]

    async with _conn().execute("SELECT COUNT(*) AS n FROM groups") as cur:
        groups = (await cur.fetchone())["n"]

    async with _conn().execute("SELECT COUNT(*) AS n FROM posts") as cur:
        posts = (await cur.fetchone())["n"]

    return {
        "total_users": total,
        "admins": admins,
        "blocked": blocked,
        "waiting": waiting,
        "running": running,
        "total_groups": groups,
        "total_posts": posts,
    }


async def get_all_users() -> list[dict]:
    async with _conn().execute(
        "SELECT * FROM users ORDER BY created_at DESC"
    ) as cur:
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
        

# ─────────────────────────────────────────────────────────────────────────
# MUDDAT TEKSHIRUVI
# ─────────────────────────────────────────────────────────────────────────
async def is_tariff_expired(uid: int) -> bool:
    """
    Foydalanuvchi muddati tugaganmi?

    Returns:
        True  — muddat tugagan
        False — muddat bor yoki cheksiz
    """
    user = await get_user(uid)
    if not user:
        return False

    expires = user.get("tariff_expires_at")
    if not expires:
        return False  # muddatsiz = cheksiz

    from core.utils import is_expired
    return is_expired(expires)
