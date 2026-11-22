"""SQLite ma'lumotlar bazasi.

Jadvallar: users, groups, posts, referrals. Barcha userga tegishli amallar
Telegram UID bilan scope qilinadi; StringSession qiymatlari DB ichida
shifrlanadi.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import aiosqlite

from config.config import (
    ACTIVE_HOURS_DEFAULT,
    DB_PATH,
    DEFAULT_INTERVAL_MIN,
    DEFAULT_PLAN,
    MAX_INTERVAL_MIN,
    MIN_INTERVAL_MIN,
    SEND_LOGS_ENABLED,
    SEND_LOG_RETENTION_DAYS,
    SUPER_ADMIN,
    USER_DAILY_LIMIT_DEFAULT,
    plan_limits,
)
from core.logger import log
from core.session_crypto import decrypt_session, encrypt_session, ensure_session_cipher
from core.utils import iso_now, normalize_media, normalize_phone

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
    "plan",
    "max_groups",
    "max_posts",
    "daily_limit",
    "active_hours",
    "referral_bonus_days",
    "referral_bonus_note",
    "last_active_at",
    "team_id",
    "owner_admin_uid",
    "is_team_admin",
    "admin_expires_at",
    "admin_max_users",
}


def _default_limits_for_plan(plan: str | None) -> dict:
    limits = plan_limits(plan)
    return {
        "plan": limits["plan"],
        "max_groups": limits["max_groups"],
        "max_posts": limits["max_posts"],
        "daily_limit": limits["daily_limit"],
    }


def _approval_plan_values() -> dict:
    """Birinchi marta tasdiqlangan userga beriladigan paket va limitlar.

    ``DEFAULT_PLAN`` bo'sh bo'lsa (standart) limitlar 0 = cheksiz bo'ladi —
    eski xatti-harakat saqlanadi.
    """
    values = _default_limits_for_plan(DEFAULT_PLAN)
    values["active_hours"] = ACTIVE_HOURS_DEFAULT or ""
    return values



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

    async def add_missing_columns(table: str, columns: tuple[tuple[str, str], ...]) -> None:
        async with conn.execute(f"PRAGMA table_info({table})") as cur:
            existing = {row["name"] for row in await cur.fetchall()}
        for name, sql_type in columns:
            if name not in existing:
                await conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")

    # Umumiy sozlama/paket, media (albom) va referal mukofoti ustunlari —
    # barchasi ixtiyoriy, eski yozuvlar DEFAULT qiymat bilan ishlaydi.
    await add_missing_columns(
        "users",
        (
            ("plan", "TEXT DEFAULT ''"),
            ("max_groups", "INTEGER DEFAULT 0"),
            ("max_posts", "INTEGER DEFAULT 0"),
            ("daily_limit", "INTEGER DEFAULT 0"),
            ("active_hours", "TEXT DEFAULT ''"),
            ("referral_bonus_days", "INTEGER DEFAULT 0"),
            ("referral_bonus_note", "TEXT DEFAULT ''"),
            ("last_active_at", "TEXT"),
            # Jamoa (team) tizimi: user qaysi jamoaga va qaysi admin ga
            # tegishli, admin bo'limi esa o'z muddati va sig'imi.
            ("team_id", "INTEGER"),
            ("owner_admin_uid", "INTEGER"),
            ("is_team_admin", "INTEGER DEFAULT 0"),
            ("admin_expires_at", "TEXT"),
            ("admin_max_users", "INTEGER DEFAULT 0"),
        ),
    )
    await add_missing_columns(
        "posts",
        (
            ("media", "TEXT DEFAULT '[]'"),
            ("link_preview", "INTEGER DEFAULT 1"),
        ),
    )
    await add_missing_columns(
        "referrals",
        (
            ("qualified_at", "TEXT"),
            ("bonus_days", "INTEGER DEFAULT 0"),
            ("revoked", "INTEGER DEFAULT 0"),
        ),
    )

    # Eski postlarda faqat ``photo`` bor edi: uni media ro'yxatiga nusxalaymiz,
    # shunda worker va UI bitta yo'l bilan ishlaydi (JSON1 kengartmasiga
    # bog'liq bo'lmaslik uchun Python'da yasaymiz).
    async with conn.execute(
        "SELECT id, photo FROM posts WHERE (media IS NULL OR media = '' OR media = '[]') "
        "AND photo != ''"
    ) as cur:
        legacy_posts = [(row["id"], row["photo"]) for row in await cur.fetchall()]
    for post_id, photo in legacy_posts:
        payload = json.dumps([{"path": photo, "kind": "photo"}], ensure_ascii=False)
        await conn.execute("UPDATE posts SET media = ? WHERE id = ?", (payload, post_id))
    if legacy_posts:
        log(f"🖼 {len(legacy_posts)} ta eski post media ro'yxatiga o'tkazildi")

    # Yangi umumiy interval sozlamasi: paketsiz eski userlarga env defaulti.
    await conn.execute(
        "UPDATE users SET daily_limit = ? WHERE daily_limit IS NULL OR daily_limit = 0",
        (USER_DAILY_LIMIT_DEFAULT,),
    )
    await conn.execute(
        "UPDATE users SET active_hours = ? WHERE active_hours IS NULL",
        (ACTIVE_HOURS_DEFAULT,),
    )

    # Har bir guruhning ixtiyoriy intervali va navbatdagi yuborish vaqtini
    # saqlaymiz. Faqat yangi ustunlar qo'shiladi: eski guruhlar uchun
    # ``interval_min = NULL`` bo'lib, foydalanuvchining umumiy intervali ishlaydi.
    async with conn.execute("PRAGMA table_info(groups)") as cur:
        group_columns = {row["name"] for row in await cur.fetchall()}
    for name, sql_type in (
        ("interval_min", "INTEGER"),
        ("last_attempt_at", "REAL"),
        ("next_send_at", "REAL"),
        ("flood_wait_until", "REAL"),
    ):
        if name not in group_columns:
            await conn.execute(f"ALTER TABLE groups ADD COLUMN {name} {sql_type}")
    await conn.commit()

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
            plan TEXT DEFAULT '',
            max_groups INTEGER DEFAULT 0,
            max_posts INTEGER DEFAULT 0,
            daily_limit INTEGER DEFAULT 0,
            active_hours TEXT DEFAULT '',
            referral_bonus_days INTEGER DEFAULT 0,
            referral_bonus_note TEXT DEFAULT '',
            last_active_at TEXT,
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
            media TEXT DEFAULT '[]',
            link_preview INTEGER DEFAULT 1,
            created_at TEXT,
            FOREIGN KEY (uid) REFERENCES users(uid) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_posts_uid ON posts(uid);
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_uid INTEGER NOT NULL,
            referred_uid INTEGER NOT NULL,
            counted INTEGER DEFAULT 0,
            qualified_at TEXT,
            bonus_days INTEGER DEFAULT 0,
            revoked INTEGER DEFAULT 0,
            created_at TEXT,
            UNIQUE(referred_uid),
            FOREIGN KEY (referrer_uid) REFERENCES users(uid) ON DELETE CASCADE,
            FOREIGN KEY (referred_uid) REFERENCES users(uid) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_uid);
        CREATE TABLE IF NOT EXISTS send_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            group_id INTEGER,
            post_id INTEGER,
            sent_at REAL NOT NULL,
            ok INTEGER NOT NULL,
            error TEXT DEFAULT '',
            FOREIGN KEY (uid) REFERENCES users(uid) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_send_logs_uid_sent
            ON send_logs(uid, sent_at);
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_admin_uid INTEGER NOT NULL,
            max_users INTEGER DEFAULT 0,
            expires_at TEXT,
            created_at TEXT,
            UNIQUE(owner_admin_uid, name)
        );
        CREATE INDEX IF NOT EXISTS idx_teams_owner ON teams(owner_admin_uid);
        CREATE TABLE IF NOT EXISTS team_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            owner_admin_uid INTEGER NOT NULL,
            team_id INTEGER,
            kind TEXT NOT NULL DEFAULT 'member',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT,
            UNIQUE(phone, kind)
        );
        CREATE INDEX IF NOT EXISTS idx_team_invites_phone
            ON team_invites(phone);
        CREATE INDEX IF NOT EXISTS idx_team_invites_owner
            ON team_invites(owner_admin_uid);
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
    """WAL bilan ham izchil SQLite online backup yaratadi.

    Ikkita muhim nuqta:

    1. Nusxa uchun **alohida** (manba) ulanish ishlatiladi. ``aiosqlite``
       har bir ulanish uchun bitta worker thread ishlatadi va ``backup()``
       aynan shu thread'da bajarilishi kerak. Agar ``backup()`` asosiy
       ulanish ustida ishlatilsa, parallel yozuvlar bilan birga ishlaganda
       **deadlock** yuzaga keladi: yozuv commit'i nusxadan keyingi navbatda
       turadi, nusxa esa yozuvni kutadi.
    2. ``_write_lock`` bu yerda ushlanmaydi. SQLite'ning online backup API'si
       o'z ichida konsistent snapshot olish uchun WAL bilan ishlaydi va
       parallel yozuvlarni to'xtamaydi. Lock ushlab turilsa, katta bazada
       nusxa ko'chirilayotgan paytda BARCHA foydalanuvchilarning yozuvlari
       (login, interval, guruh qo'shish) bloklanib qolardi.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    existed = destination.exists()
    target = await aiosqlite.connect(str(destination))
    source: aiosqlite.Connection | None = None
    try:
        source = await aiosqlite.connect(str(DB_PATH))
        await source.backup(target)
        if sanitize_sessions:
            await target.execute("PRAGMA journal_mode=DELETE")
            await target.execute("UPDATE users SET session = '', pending_session = ''")
            await target.commit()
            # UPDATE'dan oldingi shifrlangan tokenlar bo'sh sahifalarda ham qolmasin.
            await target.execute("VACUUM")
    except BaseException:
        await target.close()
        if source is not None:
            await source.close()
        if not existed:
            destination.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm", "-journal"):
                Path(f"{destination}{suffix}").unlink(missing_ok=True)
        raise
    else:
        await target.close()
        if source is not None:
            await source.close()
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


async def set_pending_approval(uid: int, session: str) -> bool:
    """Shifrlangan pending session va awaiting flag'ni bitta UPDATE'da saqlaydi.

    Login tugagach sessiya aktiv ``session``ga emas, faqat pending sifatida
    yoziladi; admin tasdig'i kelmaguncha u ishlatilmaydi.
    """
    cur = await _execute_write(
        "UPDATE users SET pending_session = ?, awaiting_approval = 1, "
        "updated_at = ? WHERE uid = ?",
        (encrypt_session(session), iso_now(), uid),
    )
    return cur.rowcount > 0


async def approve_pending_user(uid: int, default_expires: str | None = None) -> bool:
    """Pending sessiyani atomik ravishda aktiv sessiyaga ko'chiradi.

    Bitta UPDATE ichida: ``pending_session`` → ``session``, pending tozalanadi,
    approval yoqiladi, default tarif (yo'q bo'lsa) va birinchi approval uchun
    default posting oralig'i hamda paket limitlari beriladi. Pending sessiya
    Telegramda revoke qilinmaydi — u aynan shu UID uchun tekshirilgan authorization.
    """
    limits = _approval_plan_values()
    cur = await _execute_write(
        "UPDATE users SET session = pending_session, pending_session = '', "
        "is_admin = 1, awaiting_approval = 0, "
        "warned_at = CASE "
        "WHEN is_admin = 1 AND tariff_expires_at IS NOT NULL "
        "AND tariff_expires_at != '' THEN warned_at ELSE NULL END, "
        "tariff_expires_at = COALESCE(NULLIF(tariff_expires_at, ''), ?), "
        "interval_min = CASE WHEN is_admin = 0 THEN ? ELSE interval_min END, "
        "plan = CASE WHEN is_admin = 0 THEN ? ELSE plan END, "
        "max_groups = CASE WHEN is_admin = 0 THEN ? ELSE max_groups END, "
        "max_posts = CASE WHEN is_admin = 0 THEN ? ELSE max_posts END, "
        "daily_limit = CASE WHEN is_admin = 0 THEN ? ELSE daily_limit END, "
        "active_hours = CASE "
        "WHEN is_admin = 0 AND (active_hours IS NULL OR active_hours = '') "
        "THEN ? ELSE active_hours END, "
        "updated_at = ? WHERE uid = ? AND pending_session != ''",
        (
            default_expires,
            DEFAULT_INTERVAL_MIN,
            limits["plan"],
            limits["max_groups"],
            limits["max_posts"],
            limits["daily_limit"],
            limits["active_hours"],
            iso_now(),
            uid,
        ),
    )
    return cur.rowcount > 0


async def clear_pending_approval(uid: int) -> bool:
    """Pending sessiya sirri va awaiting flag'ni tozalaydi (user qoladi)."""
    cur = await _execute_write(
        "UPDATE users SET pending_session = '', awaiting_approval = 0, "
        "updated_at = ? WHERE uid = ?",
        (iso_now(), uid),
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
    """Mavjud userni bitta SQL write bilan tasdiqlaydi va default tarif beradi.

    Birinchi approvalda standart posting oralig'i va paket limitlari ham
    beriladi. Allaqachon tasdiqlangan userning qo'lda o'zgartirilgan
    intervali/paketi tegilmaydi.
    """
    limits = _approval_plan_values()
    cur = await _execute_write(
        "UPDATE users SET is_admin = 1, awaiting_approval = 0, "
        "warned_at = CASE "
        "WHEN is_admin = 1 AND tariff_expires_at IS NOT NULL "
        "AND tariff_expires_at != '' THEN warned_at ELSE NULL END, "
        "tariff_expires_at = COALESCE(NULLIF(tariff_expires_at, ''), ?), "
        "interval_min = CASE WHEN is_admin = 0 THEN ? ELSE interval_min END, "
        "plan = CASE WHEN is_admin = 0 THEN ? ELSE plan END, "
        "max_groups = CASE WHEN is_admin = 0 THEN ? ELSE max_groups END, "
        "max_posts = CASE WHEN is_admin = 0 THEN ? ELSE max_posts END, "
        "daily_limit = CASE WHEN is_admin = 0 THEN ? ELSE daily_limit END, "
        "active_hours = CASE "
        "WHEN is_admin = 0 AND (active_hours IS NULL OR active_hours = '') "
        "THEN ? ELSE active_hours END, "
        "updated_at = ? WHERE uid = ?",
        (
            default_expires,
            DEFAULT_INTERVAL_MIN,
            limits["plan"],
            limits["max_groups"],
            limits["max_posts"],
            limits["daily_limit"],
            limits["active_hours"],
            iso_now(),
            uid,
        ),
    )
    return cur.rowcount > 0


# ─────────────────────────────────────────
# PAKET VA LIMITLAR
# ─────────────────────────────────────────
async def set_plan(uid: int, plan: str | None) -> dict | None:
    """Foydalanuvchiga paket beradi va limitlarni shu paketga moslaydi.

    Bo'sh yoki noma'lum paket nomi limitlarni 0 = cheksiz qiladi.
    """
    limits = _default_limits_for_plan(plan)
    cur = await _execute_write(
        "UPDATE users SET plan = ?, max_groups = ?, max_posts = ?, daily_limit = ?, "
        "updated_at = ? WHERE uid = ?",
        (
            limits["plan"],
            limits["max_groups"],
            limits["max_posts"],
            limits["daily_limit"],
            iso_now(),
            uid,
        ),
    )
    if not cur.rowcount:
        return None
    return await get_limits(uid)


async def set_user_limits(uid: int, **fields: object) -> bool:
    """Individual limitni qo'lda o'rnatadi (max_groups/max_posts/daily_limit/active_hours)."""
    from core.utils import parse_active_hours

    allowed = {
        "max_groups",
        "max_posts",
        "daily_limit",
        "active_hours",
        "tariff_expires_at",
        "is_blocked",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Noma'lum limit ustuni: {', '.join(sorted(unknown))}")

    updates: list[str] = []
    params: list = []
    for name in ("max_groups", "max_posts", "daily_limit", "active_hours"):
        if name not in fields:
            continue
        value = fields[name]
        if name == "active_hours":
            normalized = str(value or "").strip()
            if normalized and parse_active_hours(normalized) is None:
                return False
            params.append(normalized)
        else:
            try:
                number = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return False
            params.append(max(0, number))
        updates.append(f"{name} = ?")
    # Muddat (tariff_expires_at) — ISO sana yoki NULL (cheksiz).
    if "tariff_expires_at" in fields:
        expires = fields["tariff_expires_at"]
        params.append(str(expires) if expires else None)
        updates.append("tariff_expires_at = ?")
    # Bloklash holati (jamoa admini ham foydalana oladi).
    if "is_blocked" in fields:
        try:
            blocked = int(fields["is_blocked"])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        params.append(1 if blocked else 0)
        updates.append("is_blocked = ?")
    if not updates:
        return False
    updates.append("updated_at = ?")
    params.extend([iso_now(), uid])
    cur = await _execute_write(
        f"UPDATE users SET {', '.join(updates)} WHERE uid = ?",
        params,
    )
    return cur.rowcount > 0


async def get_limits(uid: int) -> dict:
    """Paket, limitlar va ularning qancha ishlatilgani."""
    user = await get_user(uid)
    if not user:
        return {}
    plan = (user.get("plan") or "").strip().upper()
    definition = plan_limits(plan)
    limits = {
        "plan": plan,
        "label": definition["label"] if plan else "📦 Limitlarsiz",
        "max_groups": int(user.get("max_groups") or 0),
        "max_posts": int(user.get("max_posts") or 0),
        "daily_limit": int(user.get("daily_limit") or 0),
        "active_hours": (user.get("active_hours") or "").strip(),
    }
    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM groups WHERE uid = ?", (uid,)
    ) as cur:
        row = await cur.fetchone()
    limits["used_groups"] = int(row["n"]) if row else 0
    limits["used_posts"] = await count_posts(uid)
    return limits


async def touch_last_active(uid: int) -> None:
    """Foydalanuvchining oxirgi faolligini belgilaydi (hisobot uchun)."""
    await _execute_write(
        "UPDATE users SET last_active_at = ? WHERE uid = ?", (iso_now(), uid)
    )



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


async def count_pending_users() -> int:
    """Tasdiq navbatidagi arizalar soni (panel va statistika uchun)."""
    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM users WHERE awaiting_approval = 1"
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


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


def _rescheduled_group_due(
    last_attempt_at: float | None,
    interval_min: int,
    flood_wait_until: float | None,
) -> float | None:
    """Sozlama o'zgarganda guruh navbatini xavfsiz qayta hisoblaydi."""
    if last_attempt_at is None:
        return None  # Hali urinilmagan guruh navbatga darhol tayyor.
    next_at = float(last_attempt_at) + int(interval_min) * 60
    if flood_wait_until is not None:
        next_at = max(next_at, float(flood_wait_until))
    return next_at


async def set_interval(uid: int, minutes: int) -> bool:
    """Umumiy intervalni saqlab, umumiy intervalni ishlatuvchi guruhlarni sozlaydi."""
    minutes = int(minutes)
    if not MIN_INTERVAL_MIN <= minutes <= MAX_INTERVAL_MIN:
        raise ValueError("Posting intervali ruxsat etilgan oraliqdan tashqarida")

    async with _write_lock:
        try:
            cur = await _conn().execute(
                "UPDATE users SET interval_min = ?, updated_at = ? WHERE uid = ?",
                (minutes, iso_now(), uid),
            )
            if cur.rowcount:
                async with _conn().execute(
                    "SELECT id, last_attempt_at, flood_wait_until FROM groups "
                    "WHERE uid = ? AND interval_min IS NULL",
                    (uid,),
                ) as group_cur:
                    groups = await group_cur.fetchall()
                for group in groups:
                    next_at = _rescheduled_group_due(
                        group["last_attempt_at"], minutes, group["flood_wait_until"]
                    )
                    await _conn().execute(
                        "UPDATE groups SET next_send_at = ? WHERE id = ? AND uid = ?",
                        (next_at, group["id"], uid),
                    )
            await _conn().commit()
            return cur.rowcount > 0
        except Exception:
            await _conn().rollback()
            raise


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
        "SELECT id, uid, value, created_at, interval_min, last_attempt_at, "
        "next_send_at, flood_wait_until FROM groups WHERE uid = ? ORDER BY id",
        (uid,),
    ) as cur:
        return [dict(row) for row in await cur.fetchall()]


async def get_chat_record(uid: int, group_id: int) -> dict | None:
    async with _conn().execute(
        "SELECT id, uid, value, created_at, interval_min, last_attempt_at, "
        "next_send_at, flood_wait_until FROM groups WHERE uid = ? AND id = ?",
        (uid, group_id),
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_chats(uid: int) -> list[str]:
    return [row["value"] for row in await get_chat_records(uid)]


async def set_chat_interval(
    uid: int, group_id: int, minutes: int | None
) -> bool:
    """Guruh intervalini o'rnatadi; None bo'lsa userning umumiy intervali ishlaydi."""
    if minutes is not None:
        minutes = int(minutes)
        if not MIN_INTERVAL_MIN <= minutes <= MAX_INTERVAL_MIN:
            raise ValueError("Guruh intervali ruxsat etilgan oraliqdan tashqarida")

    async with _write_lock:
        try:
            async with _conn().execute(
                "SELECT interval_min FROM users WHERE uid = ?", (uid,)
            ) as cur:
                user = await cur.fetchone()
            if not user:
                await _conn().commit()
                return False

            async with _conn().execute(
                "SELECT last_attempt_at, flood_wait_until FROM groups "
                "WHERE uid = ? AND id = ?",
                (uid, group_id),
            ) as cur:
                group = await cur.fetchone()
            if not group:
                await _conn().commit()
                return False

            effective_interval = (
                minutes if minutes is not None else int(user["interval_min"] or 60)
            )
            next_at = _rescheduled_group_due(
                group["last_attempt_at"],
                effective_interval,
                group["flood_wait_until"],
            )
            cur = await _conn().execute(
                "UPDATE groups SET interval_min = ?, next_send_at = ? "
                "WHERE uid = ? AND id = ?",
                (minutes, next_at, uid, group_id),
            )
            await _conn().commit()
            return cur.rowcount > 0
        except Exception:
            await _conn().rollback()
            raise


async def record_chat_attempt(
    uid: int,
    group_id: int,
    attempted_at: float,
    jitter_s: int = 0,
    flood_wait_until: float | None = None,
) -> float | None:
    """Urinishdan keyingi navbatni joriy interval bilan atomik saqlaydi."""
    async with _write_lock:
        try:
            async with _conn().execute(
                "SELECT g.interval_min, u.interval_min AS global_interval "
                "FROM groups g JOIN users u ON u.uid = g.uid "
                "WHERE g.uid = ? AND g.id = ?",
                (uid, group_id),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                await _conn().commit()
                return None

            interval = int(row["interval_min"] or row["global_interval"] or 60)
            delay_s = max(
                MIN_INTERVAL_MIN * 60,
                interval * 60 + int(jitter_s),
            )
            next_send_at = float(attempted_at) + delay_s
            if flood_wait_until is not None:
                next_send_at = max(next_send_at, float(flood_wait_until))

            await _conn().execute(
                "UPDATE groups SET last_attempt_at = ?, next_send_at = ?, "
                "flood_wait_until = ? WHERE uid = ? AND id = ?",
                (attempted_at, next_send_at, flood_wait_until, uid, group_id),
            )
            await _conn().commit()
            return next_send_at
        except Exception:
            await _conn().rollback()
            raise


async def add_chat(uid: int, value: str) -> tuple[bool, str]:
    """Guruh qo'shadi. Paket limiti bosilsa ``(False, "limit")`` qaytadi.

    Sanash va INSERT bitta yozuv locki ichida — parallel bulk qo'shishlar
    limitdan o'tib keta olmaydi. Limit 0 bo'lsa cheksiz (paketsiz userlar).
    """
    limit = await max_groups_for(uid)
    async with _write_lock:
        try:
            if limit > 0:
                async with _conn().execute(
                    "SELECT COUNT(*) AS n FROM groups WHERE uid = ?", (uid,)
                ) as cur:
                    row = await cur.fetchone()
                if row and int(row["n"]) >= limit:
                    await _conn().commit()
                    return False, "limit"
            await _conn().execute(
                "INSERT INTO groups (uid, value, created_at) VALUES (?, ?, ?)",
                (uid, value, iso_now()),
            )
            await _conn().commit()
            return True, "ok"
        except aiosqlite.IntegrityError:
            await _conn().rollback()
            return False, "duplicate"
        except Exception as exc:
            await _conn().rollback()
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
    data["media"] = normalize_media(data)
    raw_preview = data.get("link_preview")
    data["link_preview"] = True if raw_preview is None else bool(int(raw_preview))
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


def _media_payload(media: list | None, photo: str | None) -> list[dict]:
    """Media ro'yxatini standart ko'rinishga keltiradi.

    ``photo`` ustuni eski kod (admin kartasi, worker) uchun birinchi fayl bilan
    sinxron saqlanadi — shu sabab eski postlar ham, yangi albomlar ham bitta
    yo'l bilan o'qiladi.
    """
    items: list[dict] = []
    for item in media or []:
        if isinstance(item, str):
            path, kind = item, "photo"
        elif isinstance(item, dict):
            path, kind = item.get("path"), item.get("kind") or "photo"
        else:
            continue
        if path:
            items.append({"path": str(path), "kind": str(kind)})
    if not items and photo:
        items.append({"path": str(photo), "kind": "photo"})
    return items


async def max_posts_for(uid: int) -> int:
    """Tarifdagi post limiti (0 = cheksiz)."""
    async with _conn().execute(
        "SELECT max_posts FROM users WHERE uid = ?", (uid,)
    ) as cur:
        row = await cur.fetchone()
    return int(row["max_posts"] or 0) if row and row["max_posts"] is not None else 0


async def max_groups_for(uid: int) -> int:
    """Tarifdagi guruh limiti (0 = cheksiz)."""
    async with _conn().execute(
        "SELECT max_groups FROM users WHERE uid = ?", (uid,)
    ) as cur:
        row = await cur.fetchone()
    return int(row["max_groups"] or 0) if row and row["max_groups"] is not None else 0


async def add_post(
    uid: int,
    text: str,
    entities: list[dict],
    photo: str | None,
    media: list | None = None,
    link_preview: bool = True,
) -> tuple[bool, str, int | None]:
    """Post qo'shadi. Tarif limiti bosilsa ``(False, "limit", None)``.

    Soni tekshirish va INSERT bitta yozuv locki ichida bajariladi — parallel
    qo'shishlar limitdan o'tib keta olmaydi.
    """
    items = _media_payload(media, photo)
    entities_json = json.dumps(entities or [], ensure_ascii=False)
    media_json = json.dumps(items, ensure_ascii=False)
    photo_mirror = next(
        (item["path"] for item in items if item["kind"] == "photo"),
        items[0]["path"] if items else "",
    )
    limit = await max_posts_for(uid)
    async with _write_lock:
        try:
            if limit > 0:
                async with _conn().execute(
                    "SELECT COUNT(*) AS n FROM posts WHERE uid = ?", (uid,)
                ) as cur:
                    row = await cur.fetchone()
                if row and int(row["n"]) >= limit:
                    await _conn().commit()
                    return False, "limit", None
            cur = await _conn().execute(
                "INSERT INTO posts (uid, text, entities, photo, media, link_preview, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    uid,
                    text,
                    entities_json,
                    photo_mirror,
                    media_json,
                    1 if link_preview else 0,
                    iso_now(),
                ),
            )
            await _conn().commit()
            return True, "ok", cur.lastrowid
        except Exception as exc:
            await _conn().rollback()
            log(f"add_post xatolik: {exc}", "error")
            return False, "error", None


async def update_post(
    uid: int,
    post_id: int,
    text: str,
    entities: list[dict],
    photo: str | None,
    media: list | None = None,
    link_preview: bool | None = None,
) -> bool:
    """Postni to'liq almashtiradi (matn, media, link preview).

    ``media=None`` va ``photo=None`` bo'lsa media o'zgarmaydi; ``photo=""`` esa
    rasmlarni olib tashlashni anglatadi (matnli postga aylantiradi).
    """
    entities_json = json.dumps(entities or [], ensure_ascii=False)
    fields = ["text = ?", "entities = ?"]
    params: list = [text, entities_json]
    if media is not None or photo is not None:
        items = _media_payload(media, photo)
        photo_mirror = next(
            (item["path"] for item in items if item["kind"] == "photo"),
            items[0]["path"] if items else "",
        )
        fields.extend(["media = ?", "photo = ?"])
        params.extend([json.dumps(items, ensure_ascii=False), photo_mirror])
    if link_preview is not None:
        fields.append("link_preview = ?")
        params.append(1 if link_preview else 0)
    params.extend([post_id, uid])
    try:
        cur = await _execute_write(
            f"UPDATE posts SET {', '.join(fields)} WHERE id = ? AND uid = ?",
            params,
        )
        return cur.rowcount > 0
    except Exception as exc:
        log(f"update_post xatolik: {exc}", "error")
        return False


async def set_post_link_preview(uid: int, post_id: int, enabled: bool) -> bool:
    try:
        cur = await _execute_write(
            "UPDATE posts SET link_preview = ? WHERE id = ? AND uid = ?",
            (1 if enabled else 0, post_id, uid),
        )
        return cur.rowcount > 0
    except Exception as exc:
        log(f"set_post_link_preview xatolik: {exc}", "error")
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
                "WHERE referred_uid = ? AND referrer_uid = ? AND counted = 0 "
                "AND revoked = 0",
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
        "SELECT r.referred_uid, r.counted, r.qualified_at, r.bonus_days, r.revoked, "
        "u.name AS name "
        "FROM referrals r LEFT JOIN users u ON u.uid = r.referred_uid "
        "WHERE r.referrer_uid = ? ORDER BY r.id DESC",
        (referrer_uid,),
    ) as cur:
        rows = await cur.fetchall()
    return [
        {
            "uid": row["referred_uid"],
            # Hali tasdiqlanmagan takliflar ismi ko'rsatilmaydi — chaqirilgan
            # odisning shaxsiy ma'lumori referrerga uzatilmasin.
            "name": (
                (row["name"] or f"Foydalanuvchi {row['referred_uid']}")
                if row["counted"]
                else "Yangi foydalanuvchi"
            ),
            "counted": bool(row["counted"]),
            "qualified": bool(row["qualified_at"]),
            "bonus_days": int(row["bonus_days"] or 0),
            "revoked": bool(row["revoked"]),
        }
        for row in rows
    ]


def _today_prefix() -> str:
    """``YYYY-MM-DD`` — bugun created_at yozuvlarini tanish uchun."""
    return iso_now()[:10]


async def count_referrals_today(referrer_uid: int) -> int:
    """Bugun ro'yxatga qo'shilgan (hisoblangan-hisoblanmagan) referallar soni."""
    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM referrals "
        "WHERE referrer_uid = ? AND substr(created_at, 1, 10) = ?",
        (referrer_uid, _today_prefix()),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def bonus_days_granted_since(referrer_uid: int, since_iso: str) -> int:
    """``since_iso`` dan beri berilgan referal bonus kunlari ( oylik limit uchun)."""
    async with _conn().execute(
        "SELECT COALESCE(SUM(bonus_days), 0) AS days FROM referrals "
        "WHERE referrer_uid = ? AND qualified_at IS NOT NULL AND qualified_at >= ?",
        (referrer_uid, since_iso),
    ) as cur:
        row = await cur.fetchone()
    return int(row["days"] or 0)


async def get_referral_link_info(uid: int) -> dict | None:
    """Bu userning referal bog'lanishi (qayerdan kelgani) haqida ma'lumot."""
    async with _conn().execute(
        "SELECT r.referrer_uid, r.counted, r.qualified_at, r.bonus_days, r.revoked, "
        "r.created_at FROM referrals r WHERE r.referred_uid = ?",
        (uid,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def grant_referral_bonus(
    referred_uid: int, days: int, *, monthly_cap_days: int = 0
) -> tuple[int, int] | None:
    """Faol referal uchun referrerga bonus kunlarni BIR MARTA beradi.

    Shartlar: referal hisoblangan (counted=1), rad etilmagan (revoked=0) va
    bonus avval berilmagan (qualified_at IS NULL). ``monthly_cap_days`` > 0
    bo'lsa, oxirgi 30 kundagi jami bonus bilan cheklanadi.

    Returns:
        ``(referrer_uid, berilgan_kun)`` yoki bonus berish shart bo'lmasa
        ``None``.
    """
    if days <= 0:
        return None
    from core.utils import now_utc

    now_iso = now_utc().strftime("%Y-%m-%d %H:%M:%S")
    month_ago = (now_utc() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    async with _write_lock:
        try:
            async with _conn().execute(
                "SELECT r.id, r.referrer_uid, r.counted, r.qualified_at, r.revoked "
                "FROM referrals r WHERE r.referred_uid = ?",
                (referred_uid,),
            ) as cur:
                row = await cur.fetchone()
            if not row or not row["counted"] or row["qualified_at"] or row["revoked"]:
                await _conn().commit()
                return None
            referrer = int(row["referrer_uid"])

            applied = int(days)
            # Cheksiz tarifga ega referrerga kun qo'shishning hojati yo'q —
            # bonus "0 kun" sifatida belgilanadi, shunda keyin qayta berilmaydi.
            async with _conn().execute(
                "SELECT tariff_expires_at FROM users WHERE uid = ?", (referrer,)
            ) as cur:
                owner = await cur.fetchone()
            if not owner or not owner["tariff_expires_at"]:
                applied = 0
            if applied > 0 and monthly_cap_days > 0:
                async with _conn().execute(
                    "SELECT COALESCE(SUM(bonus_days), 0) AS days FROM referrals "
                    "WHERE referrer_uid = ? AND qualified_at IS NOT NULL "
                    "AND qualified_at >= ?",
                    (referrer, month_ago),
                ) as cur:
                    used_row = await cur.fetchone()
                used = int(used_row["days"] or 0) if used_row else 0
                applied = max(0, min(applied, monthly_cap_days - used))

            marked = await _conn().execute(
                "UPDATE referrals SET qualified_at = ?, bonus_days = ? "
                "WHERE id = ? AND qualified_at IS NULL",
                (now_iso, applied, row["id"]),
            )
            if marked.rowcount != 1:
                await _conn().rollback()
                return None
            if applied > 0:
                await _conn().execute(
                    "UPDATE users SET "
                    "tariff_expires_at = CASE "
                    "WHEN tariff_expires_at IS NULL OR tariff_expires_at = '' "
                    "THEN NULL "
                    "WHEN tariff_expires_at <= ? THEN ? "
                    "ELSE strftime('%Y-%m-%d %H:%M:%S', datetime(tariff_expires_at), "
                    "'+' || ? || ' days') END, "
                    "referral_bonus_days = COALESCE(referral_bonus_days, 0) + ?, "
                    "warned_at = NULL, updated_at = ? WHERE uid = ?",
                    (
                        now_iso,
                        _expiry_from_now(applied),
                        applied,
                        applied,
                        iso_now(),
                        referrer,
                    ),
                )
            await _conn().commit()
            return referrer, applied
        except Exception:
            await _conn().rollback()
            raise


def _expiry_from_now(days: int) -> str:
    from core.utils import calc_expires

    return calc_expires(days)


async def revoke_referral(uid: int) -> dict | None:
    """Taklif qilingan user firibgar/soxta chiqsa referal hisobini BEKOR qiladi.

    Hisobdan chiqariladi (counted=0, revoked=1) va, agar bonus berilgan bo'lsa,
    uning miqdori qaytarib olinishi uchain qaytariladi.

    Returns:
        ``{"referrer_uid": int, "bonus_days": int, "was_granted": bool}`` yoki
        bekor qilinadigan hech narsa bo'lmasa ``None``.
    """
    async with _write_lock:
        try:
            async with _conn().execute(
                "SELECT id, referrer_uid, bonus_days, counted, qualified_at, revoked "
                "FROM referrals WHERE referred_uid = ?",
                (uid,),
            ) as cur:
                row = await cur.fetchone()
            if not row or not row["counted"] or row["revoked"]:
                await _conn().commit()
                return None
            cur = await _conn().execute(
                "UPDATE referrals SET counted = 0, revoked = 1 WHERE id = ? "
                "AND counted = 1",
                (row["id"],),
            )
            if cur.rowcount != 1:
                await _conn().rollback()
                return None
            await _conn().commit()
            return {
                "referrer_uid": int(row["referrer_uid"]),
                "bonus_days": int(row["bonus_days"] or 0),
                "was_granted": bool(row["qualified_at"]),
            }
        except Exception:
            await _conn().rollback()
            raise


async def pending_referrals_of(referrer_uid: int) -> list[int]:
    """Tasdiqlangan, lekin referrer bloklangani uchun hisoblanmay qolgan referallar."""
    async with _conn().execute(
        "SELECT r.referred_uid FROM referrals r JOIN users u ON u.uid = r.referred_uid "
        "WHERE r.referrer_uid = ? AND r.counted = 0 AND r.revoked = 0 "
        "AND u.is_admin = 1 AND u.is_blocked = 0 ORDER BY r.id DESC LIMIT 50",
        (referrer_uid,),
    ) as cur:
        return [int(row["referred_uid"]) for row in await cur.fetchall()]


async def reconcile_referral(uid: int) -> int | None:
    """Hisoblanmagan qolgan referalni qayta tekshiradi (masalan blokdan chiqqanda).

    ``try_count_referral`` o'zi idempotent: u faqat ``referral_counted = 0``
    bo'lgan, tasdiqlangan va referreri bloklanmagan userlarni oladi.
    """
    return await try_count_referral(uid)


async def referral_anomalies(threshold: int) -> list[dict]:
    """Bugun shunchadan ko'p referal qilgan foydalanuvchilar (anti-fraud)."""
    async with _conn().execute(
        "SELECT r.referrer_uid, COUNT(*) AS n, u.name AS name FROM referrals r "
        "LEFT JOIN users u ON u.uid = r.referrer_uid "
        "WHERE substr(r.created_at, 1, 10) = ? "
        "GROUP BY r.referrer_uid HAVING COUNT(*) >= ? ORDER BY n DESC LIMIT 20",
        (_today_prefix(), int(threshold)),
    ) as cur:
        rows = await cur.fetchall()
    return [
        {
            "referrer_uid": int(row["referrer_uid"]),
            "count": int(row["n"]),
            "name": row["name"] or str(row["referrer_uid"]),
        }
        for row in rows
    ]


# ─────────────────────────────────────────
# YUBORISH STATISTIKASI (send_logs)
# ─────────────────────────────────────────
async def log_send(
    uid: int,
    ok: bool,
    *,
    group_id: int | None = None,
    post_id: int | None = None,
    error: str = "",
    sent_at: float | None = None,
) -> None:
    """Bitta yuborish urinishini yozadi.

    Statistika maqsadli — xato yuborishning o'zi ham yoziladi. Bu funksiya
    worker siklini buzmasligi uchun istisno ko'tarmaydi, faqat log yozadi.
    """
    if not SEND_LOGS_ENABLED:
        return
    try:
        await _execute_write(
            "INSERT INTO send_logs (uid, group_id, post_id, sent_at, ok, error) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                uid,
                group_id,
                post_id,
                float(sent_at if sent_at is not None else time.time()),
                1 if ok else 0,
                (error or "")[:120],
            ),
        )
    except Exception as exc:  # statistikaga urish ishni to'xtatmasligi kerak
        log(f"log_send xatosi {uid}: {type(exc).__name__}", "warning")


async def send_stats(uid: int, since_ts: float | None = None) -> dict:
    """Foydalanuvchi bo'yicha yuborish hisobi (kunlik status uchun)."""
    query = "SELECT ok, COUNT(*) AS n, MAX(sent_at) AS last_at FROM send_logs WHERE uid = ?"
    params: list = [uid]
    if since_ts is not None:
        query += " AND sent_at >= ?"
        params.append(float(since_ts))
    query += " GROUP BY ok"

    stats = {"sent_ok": 0, "sent_failed": 0, "last_sent_at": None, "last_error": ""}
    async with _conn().execute(query, params) as cur:
        for row in await cur.fetchall():
            if row["ok"]:
                stats["sent_ok"] = int(row["n"])
            else:
                stats["sent_failed"] = int(row["n"])
            if row["last_at"] and (
                stats["last_sent_at"] is None or row["last_at"] > stats["last_sent_at"]
            ):
                stats["last_sent_at"] = float(row["last_at"])

    async with _conn().execute(
        "SELECT error, sent_at FROM send_logs WHERE uid = ? AND ok = 0 "
        "ORDER BY sent_at DESC LIMIT 1",
        (uid,),
    ) as cur:
        row = await cur.fetchone()
    if row:
        stats["last_error"] = f"{row['error'] or 'xato'} ({_ago_text(row['sent_at'])})"
    return stats


def _ago_text(timestamp: float | None) -> str:
    """Sekundlik farqni qisqa matnga aylantiradi ('3 daqiqa oldin')."""
    if not timestamp:
        return "—"
    delta = max(0, int(time.time() - float(timestamp)))
    if delta < 90:
        return f"{delta} soniya oldin"
    if delta < 5400:
        return f"{delta // 60} daqiqa oldin"
    if delta < 172800:
        return f"{delta // 3600} soat oldin"
    return f"{delta // 86400} kun oldin"


async def count_sent_ok(uid: int, since_ts: float | None = None) -> int:
    """Muvaffaqiyatli yuborishlar soni (kunlik limit va referal sharti uchun)."""
    query = "SELECT COUNT(*) AS n FROM send_logs WHERE uid = ? AND ok = 1"
    params: list = [uid]
    if since_ts is not None:
        query += " AND sent_at >= ?"
        params.append(float(since_ts))
    async with _conn().execute(query, params) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def next_send_eta(uid: int) -> float | None:
    """Eng yaqin navbatdagi yuborish vaqti (epoch) — status ekrani uchun."""
    async with _conn().execute(
        "SELECT MIN(next_send_at) AS eta FROM groups WHERE uid = ? "
        "AND next_send_at IS NOT NULL",
        (uid,),
    ) as cur:
        row = await cur.fetchone()
    if not row or row["eta"] is None:
        return None
    return float(row["eta"])


async def group_health(uid: int) -> list[dict]:
    """Har guruh bo'yicha so'nggi natija — salomatlik paneli uchun."""
    async with _conn().execute(
        "SELECT g.id, g.value, g.interval_min, g.last_attempt_at, g.next_send_at, "
        "g.flood_wait_until, "
        "(SELECT s.ok FROM send_logs s WHERE s.group_id = g.id ORDER BY s.sent_at DESC LIMIT 1) "
        "AS last_ok, "
        "(SELECT s.error FROM send_logs s WHERE s.group_id = g.id AND s.ok = 0 "
        "ORDER BY s.sent_at DESC LIMIT 1) AS last_error, "
        "(SELECT COUNT(*) FROM send_logs s WHERE s.group_id = g.id AND s.ok = 1) "
        "AS sent_ok, "
        "(SELECT COUNT(*) FROM send_logs s WHERE s.group_id = g.id AND s.ok = 0) "
        "AS sent_failed "
        "FROM groups g WHERE g.uid = ? ORDER BY g.id",
        (uid,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def prune_send_logs(retention_days: int | None = None) -> int:
    """Eski yuborish yozuvlarini tozalaydi (disk va SQLite hajmi uchun)."""
    days = SEND_LOG_RETENTION_DAYS if retention_days is None else max(1, retention_days)
    cutoff = time.time() - days * 86400
    cur = await _execute_write("DELETE FROM send_logs WHERE sent_at < ?", (cutoff,))
    return cur.rowcount or 0


async def global_send_stats(since_ts: float) -> dict:
    """Admin hisoboti: butun bot bo'yicha kunlik ko'rsatkichlar."""
    async with _conn().execute(
        "SELECT COUNT(*) AS total, SUM(ok) AS ok FROM send_logs WHERE sent_at >= ?",
        (since_ts,),
    ) as cur:
        row = await cur.fetchone()
    total = int(row["total"] or 0)
    ok = int(row["ok"] or 0)

    async with _conn().execute(
        "SELECT COUNT(DISTINCT uid) AS n FROM send_logs WHERE sent_at >= ? AND ok = 1",
        (since_ts,),
    ) as cur:
        active_row = await cur.fetchone()

    async with _conn().execute(
        "SELECT COALESCE(error, '') AS error, COUNT(*) AS n FROM send_logs "
        "WHERE sent_at >= ? AND ok = 0 GROUP BY error ORDER BY n DESC LIMIT 8",
        (since_ts,),
    ) as cur:
        errors = [(r["error"] or "noma'lum", int(r["n"])) for r in await cur.fetchall()]

    return {
        "total": total,
        "ok": ok,
        "failed": total - ok,
        "success_rate": (ok / total * 100) if total else 100.0,
        "active_users": int(active_row["n"] or 0) if active_row else 0,
        "errors": errors,
    }


async def top_senders(since_ts: float, limit: int = 10) -> list[dict]:
    """Eng ko'p yuborgan foydalanuvchilar (admin hisoboti)."""
    async with _conn().execute(
        "SELECT s.uid, u.name, SUM(s.ok) AS ok, COUNT(*) AS total "
        "FROM send_logs s LEFT JOIN users u ON u.uid = s.uid "
        "WHERE s.sent_at >= ? GROUP BY s.uid ORDER BY total DESC LIMIT ?",
        (since_ts, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [
        {
            "uid": int(row["uid"]),
            "name": row["name"] or str(row["uid"]),
            "ok": int(row["ok"] or 0),
            "total": int(row["total"] or 0),
        }
        for row in rows
    ]


# ─────────────────────────────────────────
# TARIF BONUSLARI (referal mukofoti)
# ─────────────────────────────────────────
async def add_bonus_days(
    uid: int, days: int, *, note: str = ""
) -> tuple[str | None, str | None]:
    """Tarif muddatini ``days`` kunga UZAYTIRADI yoki QISQARTIRADI (bonus/sovg'a).

    ``give_new_term()``dan farqi: u yangi muddatni hozirdan boshlaydi va
    oldingisini bekor qiladi. Bu funksiya bonus/rewards uchun — tugamagan
    muddatning OXIRIGA kun qo'shiladi, tugagan muddat bo'lsa hozirdan
    boshlanadi. Cheksiz tarifga (muddat NULL) amalga oshmaydi.

    Berilgan/puling qilingan kunlar ``referral_bonus_days`` jurnali bilan
    birga yuritiladi — shunda avto-tasdiq va hisobotlarda kimqa necha kun
    berilgani ko'rinadi.

    Returns:
        ``(yangi_muddat, xato)`` — xato bo'lmasa ikkinchi qiymat ``None``;
        user mavjud bo'lmasa ``(None, "Foydalanuvchi topilmadi.")``.
    """
    from core.utils import calc_expires, now_utc

    user = await get_user(uid)
    if not user:
        return None, "Foydalanuvchi topilmadi."
    days = int(days)
    if days == 0:
        return (user.get("tariff_expires_at") or None), None

    now_iso = now_utc().strftime("%Y-%m-%d %H:%M:%S")
    if days > 0:
        expires_clause = (
            "tariff_expires_at = CASE "
            "WHEN tariff_expires_at IS NULL OR tariff_expires_at = '' THEN NULL "
            "WHEN tariff_expires_at <= ? THEN ? "
            "ELSE strftime('%Y-%m-%d %H:%M:%S', datetime(tariff_expires_at), "
            "'+' || ? || ' days') END"
        )
        params = (now_iso, calc_expires(days), days)
    else:
        cut = abs(days)
        expires_clause = (
            "tariff_expires_at = CASE "
            "WHEN tariff_expires_at IS NULL OR tariff_expires_at = '' THEN NULL "
            "ELSE strftime('%Y-%m-%d %H:%M:%S', datetime(tariff_expires_at), "
            "'-' || ? || ' days') END"
        )
        params = (cut,)

    await _execute_write(
        f"UPDATE users SET {expires_clause}, "
        "referral_bonus_days = MAX(0, COALESCE(referral_bonus_days, 0) + ?), "
        "referral_bonus_note = CASE WHEN ? != '' THEN ? ELSE referral_bonus_note END, "
        "warned_at = NULL, updated_at = ? WHERE uid = ?",
        (*params, days, note, note, iso_now(), uid),
    )
    fresh = await get_user(uid) or {}
    return (fresh.get("tariff_expires_at") or None), None


async def remove_bonus_days(uid: int, days: int) -> bool:
    """Berilgan bonus kunlarni tariffdan ayiradi (clawback).

    Muddat allaqachon tugagan bo'lsa — tegilmaydi; cheksiz tarifga tegilmaydi.
    """
    if days <= 0:
        return False
    from core.utils import now_utc

    now_iso = (now_utc()).strftime("%Y-%m-%d %H:%M:%S")
    cur = await _execute_write(
        "UPDATE users SET tariff_expires_at = CASE "
        "WHEN tariff_expires_at IS NULL OR tariff_expires_at = '' THEN NULL "
        "WHEN tariff_expires_at <= ? THEN tariff_expires_at "
        "ELSE strftime('%Y-%m-%d %H:%M:%S', datetime(tariff_expires_at), '-' || ? || ' days') "
        "END, updated_at = ? WHERE uid = ?",
        (now_iso, int(days), iso_now(), uid),
    )
    await _execute_write(
        "UPDATE users SET referral_bonus_days = MAX(0, referral_bonus_days - ?) "
        "WHERE uid = ?",
        (int(days), uid),
    )
    return cur.rowcount > 0


# ─────────────────────────────────────────
# ADMIN LISTS / STATS
# ─────────────────────────────────────────
async def _scalar(query: str, params: tuple = ()) -> int:
    """Statistik sonni o'qiydi.

    Jadval mavjud bo'lmasa (masalan juda eski baza yoki qisman test bazasi)
    0 qaytaradi — boshqaruv paneli statistikaga urilib buzilmasligi uchun.
    """
    try:
        async with _conn().execute(query, params) as cur:
            row = await cur.fetchone()
    except Exception:
        return 0
    return int(row["n"]) if row and row["n"] is not None else 0


async def get_stats() -> dict:
    params = (SUPER_ADMIN,)

    async def count(query: str) -> int:
        async with _conn().execute(query, params) as cur:
            return int((await cur.fetchone())["n"])

    today = _today_prefix()
    return {
        "today_referrals": await _scalar(
            "SELECT COUNT(*) AS n FROM referrals WHERE substr(created_at, 1, 10) = ?",
            (today,),
        ),
        "today_sends_ok": await _scalar(
            "SELECT COUNT(*) AS n FROM send_logs WHERE ok = 1 AND sent_at >= ?",
            (time.time() - 86400,),
        ),
        "today_sends_failed": await _scalar(
            "SELECT COUNT(*) AS n FROM send_logs WHERE ok = 0 AND sent_at >= ?",
            (time.time() - 86400,),
        ),
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


async def get_auto_approvable_candidates(limit: int = 5) -> list[dict]:
    """Shifrlangan pending sessiyasi bor bo'lgan tasdiq kutayotgan arizalar.

    Avto-tasdiq navbati shu ro'yxatdan foydalanadi — pending sessiyasiz
    (legacy) arizalar admin tasdig'iga muhtoj bo'lib qoladi.

    Jamoali foydalanuvchilar avto-tasdiqdan chiqariladi — ularni jamoa
    admini tasdiqlaydi.
    """
    async with _conn().execute(
        "SELECT * FROM users WHERE awaiting_approval = 1 AND pending_session != '' "
        "AND is_admin = 0 AND is_blocked = 0 AND uid != ? "
        "AND (owner_admin_uid IS NULL OR owner_admin_uid = 0) "
        "ORDER BY created_at ASC LIMIT ?",
        (SUPER_ADMIN, max(1, int(limit))),
    ) as cur:
        return [_decode_user(row) for row in await cur.fetchall()]


async def count_phone_prefix_users(phone: str) -> int:
    """Bir xil telefon blokida (birinchi 8 ta belgi) nechta akkaunt borligi.

    Virtual raqamlar bilan ommaviy ro'yxatdan o'tishni aniqlash uchun
    eng arzon signal.
    """
    prefix = (phone or "").strip()[:8]
    if len(prefix) < 8:
        return 0
    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM users WHERE substr(phone, 1, 8) = ?", (prefix,)
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def count_users_named(name: str) -> int:
    """Bir xil ism-familiyali akkauntlar soni (klaster belgisi)."""
    cleaned = " ".join((name or "").strip().split())
    if not cleaned:
        return 0
    async with _conn().execute(
        "SELECT COUNT(*) AS n FROM users WHERE name = ?", (cleaned,)
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def get_pending_users() -> list[dict]:
    """Super admin uchun kutayotgan arizalar — faqat jamoasiz foydalanuvchilar.

    Jamoali foydalanuvchilarni jamoa admini tasdiqlaydi, shuning uchun
    ular super admin ro'yxatida chiqmaydi.
    """
    async with _conn().execute(
        "SELECT * FROM users WHERE uid != ? AND awaiting_approval = 1 "
        "AND (owner_admin_uid IS NULL OR owner_admin_uid = 0) "
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


# ─────────────────────────────────────────
# DAVRIY XIZMAT AMALLARI
# ─────────────────────────────────────────
async def get_all_uids() -> set[int]:
    """Barcha foydalanuvchi ID'lari (yetim media papkalarni tozalash uchun)."""
    async with _conn().execute("SELECT uid FROM users") as cur:
        return {int(row["uid"]) for row in await cur.fetchall()}


async def optimize_db() -> None:
    """
    Bazani vaqti-vaqti bilan optimallashtiradi.

    - PRAGMA optimize: query planner statistikasini yangilaydi
    - wal_checkpoint(TRUNCATE): WAL faylini bazaga qo'shib, disk hajmini
      ushlab turadi (uzoq ishlaganda WAL o'sib ketmasligi uchun)
    """
    try:
        async with _write_lock:
            await _conn().execute("PRAGMA optimize")
            await _conn().execute("PRAGMA wal_checkpoint(TRUNCATE)")
            await _conn().commit()
    except Exception as exc:
        log(f"optimize_db xatosi: {type(exc).__name__}", "error")


# ─────────────────────────────────────────
# JAMOALAR (TEAMS) — jamoa admini va uning foydalanuvchilari
# ─────────────────────────────────────────
async def create_team(
    name: str,
    owner_admin_uid: int,
    max_users: int = 0,
    expires_at: str | None = None,
) -> dict | None:
    """Yangi jamoa yaratadi (jamoa admini egaligi bilan)."""
    clean = " ".join((name or "").split())
    if not clean:
        return None
    cur = await _execute_write(
        "INSERT INTO teams (name, owner_admin_uid, max_users, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (clean, int(owner_admin_uid), max(0, int(max_users or 0)), expires_at, iso_now()),
    )
    if not cur.rowcount:
        return None
    return await get_team(cur.lastrowid)


async def get_team(team_id: int) -> dict | None:
    try:
        async with _conn().execute(
            "SELECT * FROM teams WHERE id = ?", (int(team_id),)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None
    except Exception:
        return None


async def get_team_by_name(owner_admin_uid: int, name: str) -> dict | None:
    clean = " ".join((name or "").split())
    try:
        async with _conn().execute(
            "SELECT * FROM teams WHERE owner_admin_uid = ? AND name = ?",
            (int(owner_admin_uid), clean),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None
    except Exception:
        return None


async def get_teams(owner_admin_uid: int | None = None) -> list[dict]:
    """Jamoalar ro'yxati. ``owner_admin_uid`` berilsa — faqat o'shiki.

    Jamoalar jadvali eski/qisman bazalarda yo'q bo'lishi mumkin — u holda
    bo'sh ro'yxat qaytariladi (bot ishlashda davom etadi).
    """
    try:
        if owner_admin_uid is None:
            async with _conn().execute(
                "SELECT * FROM teams ORDER BY id ASC"
            ) as cur:
                return [dict(row) for row in await cur.fetchall()]
        async with _conn().execute(
            "SELECT * FROM teams WHERE owner_admin_uid = ? ORDER BY id ASC",
            (int(owner_admin_uid),),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]
    except Exception:
        return []


async def get_all_teams() -> list[dict]:
    return await get_teams(None)


async def update_team(team_id: int, **fields: Any) -> bool:
    """Jamoaning sig'imi yoki muddatini o'zgartiradi (faqat super admin)."""
    allowed = {"name", "max_users", "expires_at"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Noma'lum teams ustuni: {', '.join(sorted(unknown))}")
    if not fields:
        return False
    sets = ", ".join(f"{name} = ?" for name in fields)
    cur = await _execute_write(
        f"UPDATE teams SET {sets} WHERE id = ?",
        (*fields.values(), int(team_id)),
    )
    return cur.rowcount > 0


async def update_team_owner(team_id: int, owner_admin_uid: int) -> bool:
    """Jamoaning egasini almashtiradi (topshirish)."""
    cur = await _execute_write(
        "UPDATE teams SET owner_admin_uid = ? WHERE id = ?",
        (int(owner_admin_uid), int(team_id)),
    )
    return cur.rowcount > 0


async def reassign_team_members(team_id: int, new_owner_uid: int) -> int:
    """Jamoa a'zolarini yangi admin ostiga o'tkazadi (topshirish).

    Jamoaning o'z egasi ham ``owner_admin_uid`` yangilanadi — chunki u ham
    a'zolar ro'yxatida turadi.

    Returns:
        O'tkazilgan a'zolar soni.
    """
    cur = await _execute_write(
        "UPDATE users SET owner_admin_uid = ?, updated_at = ? WHERE team_id = ?",
        (int(new_owner_uid), iso_now(), int(team_id)),
    )
    return cur.rowcount


async def clear_team_admin(uid: int) -> bool:
    """Foydalanuvchini jamoa admini roligidan olib tashlaydi.

    Jamoaning egasi emas (boshqa admin topshirdi bo'lsa) — jamoa bilan
    bog'liq admin roli tozalanadi. Oddiy a'zo sifatida qoladi.
    """
    cur = await _execute_write(
        "UPDATE users SET is_team_admin = 0, admin_expires_at = NULL, "
        "admin_max_users = 0, updated_at = ? WHERE uid = ?",
        (iso_now(), int(uid)),
    )
    return cur.rowcount > 0


async def delete_team(team_id: int) -> bool:
    cur = await _execute_write(
        "DELETE FROM teams WHERE id = ?", (int(team_id),)
    )
    return cur.rowcount > 0


async def count_team_members(team_id: int, *, include_admin: bool = True) -> int:
    """Jamoadagi foydalanuvchilar soni.

    ``include_admin=True`` (standart) — jamoa admini ham hisobga olinadi.
    Bu sig'im (capacity) hisobi uchun kerak: admin ham jamoaning bir a'zosi.

    ``include_admin=False`` — jamoa admini hisobdan chiqariladi. Bu
    panelda ko'rsatiladigan a'zolar soni uchun kerak (admin o'z
    ro'yxatida ko'rinmasligi kerak).
    """
    if include_admin:
        return await _scalar(
            "SELECT COUNT(*) AS n FROM users WHERE team_id = ?", (int(team_id),)
        )
    return await _scalar(
        "SELECT COUNT(*) AS n FROM users WHERE team_id = ? "
        "AND COALESCE(is_team_admin, 0) = 0",
        (int(team_id),),
    )


async def team_has_free_slot(team_id: int) -> bool:
    """Jamoada bo'sh joy bormi. ``max_users = 0`` → cheksiz."""
    team = await get_team(team_id)
    if not team:
        return False
    limit = int(team.get("max_users") or 0)
    if limit <= 0:
        return True
    return await count_team_members(team_id) < limit


async def get_team_members(team_id: int) -> list[dict]:
    """Jamoaning barcha a'zolari (jamoa admini birinchi bo'lib)."""
    async with _conn().execute(
        "SELECT * FROM users WHERE team_id = ? ORDER BY created_at ASC",
        (int(team_id),),
    ) as cur:
        return [_decode_user(row) for row in await cur.fetchall()]


async def get_users_by_owner(owner_admin_uid: int) -> list[dict]:
    """Faqat berilgan jamoa adminiga tegishli foydalanuvchilar."""
    async with _conn().execute(
        "SELECT * FROM users WHERE owner_admin_uid = ? AND uid != ? "
        "ORDER BY created_at DESC",
        (int(owner_admin_uid), int(owner_admin_uid)),
    ) as cur:
        return [_decode_user(row) for row in await cur.fetchall()]


async def get_pending_by_owner(owner_admin_uid: int) -> list[dict]:
    """Jamoa admini tasdiqlashni kutayotgan arizalar."""
    async with _conn().execute(
        "SELECT * FROM users WHERE owner_admin_uid = ? AND awaiting_approval = 1 "
        "AND uid != ? ORDER BY created_at ASC",
        (int(owner_admin_uid), int(owner_admin_uid)),
    ) as cur:
        return [_decode_user(row) for row in await cur.fetchall()]


async def assign_team_member(
    uid: int,
    team_id: int,
    owner_admin_uid: int,
) -> bool:
    """Foydalanuvchini jamoaga biriktiradi (admin tasdiqlashda).

    Jamoa sig'i to'lgan bo'lsa — biriktirilmaydi (``False``).
    """
    if not await team_has_free_slot(team_id):
        return False
    cur = await _execute_write(
        "UPDATE users SET team_id = ?, owner_admin_uid = ?, updated_at = ? WHERE uid = ?",
        (int(team_id), int(owner_admin_uid), iso_now(), int(uid)),
    )
    return cur.rowcount > 0


async def set_team_pending(
    uid: int,
    team_id: int,
    owner_admin_uid: int,
    name: str = "",
    username: str = "",
) -> bool:
    """Ro'yxatdan o'tuvchi foydalanuvchi jamoani tanladi (tasdiq kutilmoqda)."""
    if not await team_has_free_slot(team_id):
        return False
    fields: dict[str, Any] = {}
    if name:
        fields["name"] = name
    if username:
        fields["username"] = username
    await upsert_user(uid, **fields)
    cur = await _execute_write(
        "UPDATE users SET team_id = ?, owner_admin_uid = ?, awaiting_approval = 1, "
        "updated_at = ? WHERE uid = ?",
        (int(team_id), int(owner_admin_uid), iso_now(), int(uid)),
    )
    return cur.rowcount > 0


async def leave_team(uid: int) -> dict | None:
    """Foydalanuvchini jamoadan chiqaradi.

    Natija:
      * ``team_id`` va ``owner_admin_uid`` tozalanadi — foydalanuvchi
        endi jamoasiz (jamoa o'z muddatiga ishlaydi);
      * ``tariff_expires_at`` ham tozalanadi — jamoadagi muddat ham tugaydi,
        chunki muddat jamoa admini tomonidan berilgan edi. Agar foydalanuvchi
        super admin tomonidan tasdiqlangan bo'lsa, uning muddati saqlanadi;
      * jamoa admini o'z jamoasidan chiqayolmaydi (``owner_admin_uid`` —
        jamoa egasi).

    Returns:
        Chiqish natijasi: ``{"team_id", "owner_admin_uid", "team_name",
        "expires_cleared"}`` yoki ``None`` (foydalanuvchi jamoada emas).
    """
    user = await get_user(uid)
    if not user:
        return None

    team_id = int(user.get("team_id") or 0)
    owner_uid = int(user.get("owner_admin_uid") or 0)

    # Jamoada bo'lmagan foydalanuvchi — chiqish mumkin emas.
    if not team_id:
        return None

    # Jamoa egasi (admin) jamoasidan chiqmaydi — jamoa sizga tegishli.
    if user.get("is_team_admin") or (team_id and owner_uid == int(uid)):
        return None

    team_name = ""
    if team_id:
        team = await get_team(team_id)
        if team:
            team_name = str(team.get("name") or "")

    # Muddat: jamoa admini bergan bo'lsa — chiqish bilan tugaydi.
    # Super admin bergan muddat (jamoasiz tasdiqlash) saqlanadi.
    expires_cleared = False
    current_expires = user.get("tariff_expires_at")
    if current_expires and owner_uid and owner_uid != SUPER_ADMIN:
        expires_cleared = True

    cur = await _execute_write(
        "UPDATE users SET team_id = NULL, owner_admin_uid = NULL, "
        "awaiting_approval = 0, tariff_expires_at = ?, updated_at = ? "
        "WHERE uid = ?",
        (None if expires_cleared else current_expires, iso_now(), int(uid)),
    )
    if not cur.rowcount:
        return None

    return {
        "team_id": team_id,
        "owner_admin_uid": owner_uid,
        "team_name": team_name,
        "expires_cleared": expires_cleared,
    }


async def add_team_invite(
    phone: str,
    owner_admin_uid: int,
    team_id: int | None = None,
    kind: str = "member",
) -> bool:
    """Do'stni (telefon raqam bilan) jamoaga biriktirishga tayyorlaydi.

    ``kind``:
      * ``"member"`` — jamoaga a'zo (jamoa admini qo'shadi);
      * ``"admin"`` — yangi jamoa admini (super admin qo'shadi).

    Agar shu raqam uchun yozuv bo'lsa — yangilanadi (qayta qo'shish).
    """
    phone = normalize_phone(phone)
    if not phone:
        return False
    await _execute_write(
        "INSERT INTO team_invites (phone, owner_admin_uid, team_id, kind, status, "
        "created_at) VALUES (?, ?, ?, ?, 'pending', ?) "
        "ON CONFLICT(phone, kind) DO UPDATE SET "
        "owner_admin_uid = excluded.owner_admin_uid, "
        "team_id = excluded.team_id, "
        "status = 'pending', "
        "created_at = excluded.created_at",
        (phone, int(owner_admin_uid), team_id, kind, iso_now()),
    )
    return True


async def get_team_invite(phone: str, kind: str = "member") -> dict | None:
    """Telefon raqam bo'yicha taklif yozuvi."""
    phone = normalize_phone(phone)
    if not phone:
        return None
    async with _conn().execute(
        "SELECT * FROM team_invites WHERE phone = ? AND kind = ?",
        (phone, kind),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_team_invites_by_phone(phone: str) -> list[dict]:
    """Telefon raqam bo'yicha barcha takliflar (member + admin)."""
    phone = normalize_phone(phone)
    if not phone:
        return []
    async with _conn().execute(
        "SELECT * FROM team_invites WHERE phone = ? ORDER BY id DESC",
        (phone,),
    ) as cur:
        return [dict(row) for row in await cur.fetchall()]


async def get_team_invites(owner_admin_uid: int) -> list[dict]:
    """Admin qo'shgan do'stlar ro'yxati."""
    async with _conn().execute(
        "SELECT * FROM team_invites WHERE owner_admin_uid = ? ORDER BY id DESC",
        (int(owner_admin_uid),),
    ) as cur:
        return [dict(row) for row in await cur.fetchall()]


async def delete_team_invite(phone: str, kind: str = "member") -> bool:
    """Taklifni o'chiradi."""
    phone = normalize_phone(phone)
    if not phone:
        return False
    cur = await _execute_write(
        "DELETE FROM team_invites WHERE phone = ? AND kind = ?", (phone, kind)
    )
    return cur.rowcount > 0


async def set_team_invite_status(
    phone: str, status: str, kind: str = "member"
) -> bool:
    """Taklif holatini yangilaydi (``pending`` / ``used`` / ``revoked``)."""
    phone = normalize_phone(phone)
    if not phone:
        return False
    cur = await _execute_write(
        "UPDATE team_invites SET status = ? WHERE phone = ? AND kind = ?",
        (status, phone, kind),
    )
    return cur.rowcount > 0


async def set_team_admin(
    uid: int,
    team_id: int,
    max_users: int = 0,
    admin_expires_at: str | None = None,
) -> bool:
    """Foydalanuvchini jamoa admini qilib tayinlaydi.

    Foydalanuvchi hali bazada bo'lmasa — yaratib qo'yadi (INSERT).
    """
    await upsert_user(uid)
    cur = await _execute_write(
        "UPDATE users SET is_team_admin = 1, team_id = ?, admin_max_users = ?, "
        "admin_expires_at = ?, updated_at = ? WHERE uid = ?",
        (int(team_id), max(0, int(max_users or 0)), admin_expires_at, iso_now(), int(uid)),
    )
    return cur.rowcount > 0


async def create_team_for_admin(
    uid: int,
    team_name: str,
    max_users: int = 0,
    admin_expires_at: str | None = None,
) -> dict | None:
    """Super admin tayyorlagan jamoa admini uchun **haqiqiy** jamoa yaratadi.

    Jamoa nomi bo'sh bo'lsa — avtomatik unikal nom yaratiladi
    (``Jamoa #<uid>``), shunda har bir adminning jamoasi alohida bo'ladi.

    Admin darhol shu jamoaga bog'lanadi: ``team_id`` va ``owner_admin_uid``
    to'ldiriladi, keyingi o'rinda ``is_team_admin = 1`` qo'yiladi.

    Qaytaradi: yaratilgan jamoa (``dict``) yoki ``None`` (muvaffaqiyatsiz).
    """
    clean = " ".join((team_name or "").split())
    if not clean:
        clean = f"Jamoa #{int(uid)}"

    # Nom band bo'lsa — unikal variant qo'shiladi (har bir jamoa alohida).
    if await get_team_by_name(uid, clean):
        base = clean
        suffix = 2
        while await get_team_by_name(uid, f"{base} ({suffix})"):
            suffix += 1
        clean = f"{base} ({suffix})"

    team = await create_team(
        clean,
        uid,
        max_users=max_users,
        expires_at=admin_expires_at,
    )
    if not team:
        return None

    await set_team_admin(
        uid,
        int(team["id"]),
        max_users=max_users,
        admin_expires_at=admin_expires_at,
    )
    # Jamoa egasi sifatini ham aniq belgilaymiz — a'zolar shu maydon orqali
    # jamoani aniqlaydi.
    await _execute_write(
        "UPDATE users SET owner_admin_uid = ?, updated_at = ? WHERE uid = ?",
        (int(uid), iso_now(), int(uid)),
    )
    return team


async def set_admin_max_users(uid: int, max_users: int) -> bool:
    """Jamoa adminining sig'imini o'zgartiradi (faqat super admin)."""
    await upsert_user(uid)
    cur = await _execute_write(
        "UPDATE users SET admin_max_users = ?, updated_at = ? WHERE uid = ?",
        (max(0, int(max_users or 0)), iso_now(), int(uid)),
    )
    return cur.rowcount > 0


async def set_admin_expires(uid: int, expires_at: str | None) -> bool:
    """Jamoa adminining muddatini o'zgartiradi (faqat super admin)."""
    await upsert_user(uid)
    cur = await _execute_write(
        "UPDATE users SET admin_expires_at = ?, updated_at = ? WHERE uid = ?",
        (expires_at, iso_now(), int(uid)),
    )
    return cur.rowcount > 0


async def get_team_admins() -> list[dict]:
    """Barcha jamoa adminlari (super admin dan tashqari)."""
    async with _conn().execute(
        "SELECT * FROM users WHERE is_team_admin = 1 AND uid != ? ORDER BY uid ASC",
        (SUPER_ADMIN,),
    ) as cur:
        return [_decode_user(row) for row in await cur.fetchall()]


async def is_team_admin(uid: int) -> bool:
    user = await get_user(uid)
    return bool(user and user.get("is_team_admin"))


async def get_team_admin_of(uid: int) -> dict | None:
    """Foydalanuvchining jamoa admini (agar mavjud bo'lsa)."""
    user = await get_user(uid)
    if not user or not user.get("owner_admin_uid"):
        return None
    owner = await get_user(int(user["owner_admin_uid"]))
    if not owner or not owner.get("is_team_admin"):
        return None
    return owner


async def team_admin_expired(uid: int) -> bool:
    """Jamoa adminining muddati tugaganmi.

    Foydalanuvchi bazada yo'q bo'lsa — muddat kiritilmagan deb hisoblanadi
    (tugagan emas), chunki jamoa admini ro'yxatdan o'tish jarayonida ham
    bo'lishi mumkin.
    """
    from core.utils import is_expired

    user = await get_user(uid)
    if not user:
        return False
    expires = user.get("admin_expires_at")
    if not expires:
        return False
    return is_expired(expires)


async def get_expired_team_admins() -> list[int]:
    """Muddati tugagan jamoa adminlarining ID'lari."""
    from core.utils import is_expired

    rows = await get_team_admins()
    return [int(r["uid"]) for r in rows if is_expired(r.get("admin_expires_at"))]


async def team_owner_expired(uid: int) -> bool:
    """Foydalanuvchining jamoasi jamoa adminining muddati sabab to'xtaganmi.

    Oddiy (jamoasiz) foydalanuvchi uchun — har doim ``False``.

    Jamoa adminining o'zi uchun ham ``False`` — uning muddati alohida
    ``team_admin_expired`` orqali tekshiriladi.
    """
    user = await get_user(uid)
    if not user:
        return False
    owner_uid = int(user.get("owner_admin_uid") or 0)
    if not owner_uid or owner_uid == int(uid):
        return False
    owner = await get_user(owner_uid)
    if not owner or not owner.get("is_team_admin"):
        return False
    return await team_admin_expired(owner_uid)


async def team_owner_disabled(uid: int) -> bool:
    """Jamoa admini bloklanganmi — jamoasi ham to'xtashi kerak.

    Bloklangan jamoa admini o'z jamoasiga xabar yubora olmaydi va uning
    a'zolari ham ishlay olmasligi kerak — aks holda firibgar jamoa admini
    bloklanishidan keyin ham jamoasini boshqarishda davom etadi.
    """
    user = await get_user(uid)
    if not user:
        return False
    owner_uid = int(user.get("owner_admin_uid") or 0)
    if not owner_uid or owner_uid == int(uid):
        return False
    owner = await get_user(owner_uid)
    if not owner or not owner.get("is_team_admin"):
        return False
    return bool(owner.get("is_blocked"))


async def get_team_member_uids(team_id: int) -> list[int]:
    """Jamoa a'zolarining UID ro'yxati (jamoa admini ham)."""
    async with _conn().execute(
        "SELECT uid FROM users WHERE team_id = ?", (int(team_id),)
    ) as cur:
        return [int(row["uid"]) for row in await cur.fetchall()]
