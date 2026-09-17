"""
Barcha tugmalar (klaviaturalar).

Turlari:
- ReplyKeyboard (pastdagi tugmalar)
- InlineKeyboard (xabar ichidagi tugmalar)
"""

from __future__ import annotations

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot import texts as T


# ─────────────────────────────────────────────────────────────────────────
# LOGIN / RO'YXATDAN O'TISH
# ─────────────────────────────────────────────────────────────────────────
def kb_login() -> ReplyKeyboardMarkup:
    """Faqat Login tugmasi."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton(T.BTN_LOGIN)]],
        resize_keyboard=True,
    )


def kb_pending() -> ReplyKeyboardMarkup:
    """Tasdiq kutish tugmasi."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton(T.BTN_PENDING)]],
        resize_keyboard=True,
    )


def kb_blocked() -> ReplyKeyboardMarkup:
    """Bloklangan tugmasi."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton(T.BTN_BLOCKED)]],
        resize_keyboard=True,
    )


# ─────────────────────────────────────────────────────────────────────────
# ASOSIY MENYU
# ─────────────────────────────────────────────────────────────────────────
def kb_main(running: bool = False, super_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Asosiy menyu (foydalanuvchi uchun).

    running — posting ishlayaptimi
    super_admin — super admin uchun qo'shimcha tugma
    """
    status_text = f"{T.BTN_STATUS} ({'🟢 ON' if running else '🔴 OFF'})"

    rows = [
        [KeyboardButton(T.BTN_START), KeyboardButton(T.BTN_STOP)],
        [KeyboardButton(status_text), KeyboardButton(T.BTN_GROUPS)],
        [KeyboardButton(T.BTN_ADD_GROUP), KeyboardButton(T.BTN_DEL_GROUP)],
        [KeyboardButton(T.BTN_ADD_POST), KeyboardButton(T.BTN_DEL_POST)],
        [KeyboardButton(T.BTN_TIMER), KeyboardButton(T.BTN_REFERRAL)],
    ]
    if super_admin:
        rows.append([KeyboardButton(T.BTN_ADMIN)])

    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


# ─────────────────────────────────────────────────────────────────────────
# SMS KOD — NUMPAD
# ─────────────────────────────────────────────────────────────────────────
CODE_LENGTH = 5


def kb_numpad() -> InlineKeyboardMarkup:
    """SMS kod kiritish uchun raqamli tugmalar."""
    rows = [
        [InlineKeyboardButton("1", callback_data="np:1"),
         InlineKeyboardButton("2", callback_data="np:2"),
         InlineKeyboardButton("3", callback_data="np:3")],
        [InlineKeyboardButton("4", callback_data="np:4"),
         InlineKeyboardButton("5", callback_data="np:5"),
         InlineKeyboardButton("6", callback_data="np:6")],
        [InlineKeyboardButton("7", callback_data="np:7"),
         InlineKeyboardButton("8", callback_data="np:8"),
         InlineKeyboardButton("9", callback_data="np:9")],
        [InlineKeyboardButton("⬅️", callback_data="np:back"),
         InlineKeyboardButton("0", callback_data="np:0"),
         InlineKeyboardButton("✅", callback_data="np:ok")],
        [InlineKeyboardButton(T.ACTION_CANCEL, callback_data="np:cancel")],
    ]
    return InlineKeyboardMarkup(rows)
  

# ─────────────────────────────────────────────────────────────────────────
# TASDIQLASH / BEKOR QILISH
# ─────────────────────────────────────────────────────────────────────────
def kb_yes_no(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    """
    Universal 'Ha / Yo'q' tugmalari.

    Misol:
        kb_yes_no("go:yes", "go:no")
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(T.ACTION_YES, callback_data=yes_data),
            InlineKeyboardButton(T.ACTION_NO, callback_data=no_data),
        ]
    ])


def kb_confirm(cancel_data: str = "cancel") -> InlineKeyboardMarkup:
    """Faqat 'Bekor qilish' tugmasi."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(T.ACTION_CANCEL, callback_data=cancel_data)]
    ])


# ─────────────────────────────────────────────────────────────────────────
# STATUS / START / STOP
# ─────────────────────────────────────────────────────────────────────────
def kb_start_confirm() -> InlineKeyboardMarkup:
    return kb_yes_no("go:yes", "go:no")


def kb_stop_confirm() -> InlineKeyboardMarkup:
    return kb_yes_no("stop:yes", "stop:no")


# ─────────────────────────────────────────────────────────────────────────
# GURUHLAR — O'CHIRISH
# ─────────────────────────────────────────────────────────────────────────
def kb_groups_delete(groups: list[str]) -> InlineKeyboardMarkup:
    """Guruhlarni o'chirish uchun ro'yxat."""
    rows = []
    for i, g in enumerate(groups):
        preview = g[:40] if len(g) > 40 else g
        rows.append([
            InlineKeyboardButton(f"🗑 {i+1}. {preview}", callback_data=f"delg:{i}")
        ])
    rows.append([InlineKeyboardButton(T.ACTION_CANCEL, callback_data="delg:cancel")])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────────────────────────
# POSTLAR — O'CHIRISH
# ─────────────────────────────────────────────────────────────────────────
def kb_posts_delete(posts: list[dict]) -> InlineKeyboardMarkup:
    """Postlarni o'chirish uchun ro'yxat."""
    rows = []
    for i, p in enumerate(posts):
        icon = "🖼" if p.get("photo") else "📝"
        text = (p.get("text") or "").strip().replace("\n", " ")
        preview = text[:25] if text else "(rasm)"
        rows.append([
            InlineKeyboardButton(
                f"🗑 {i+1}. {icon} {preview}",
                callback_data=f"delp:{i}",
            )
        ])
    rows.append([InlineKeyboardButton(T.ACTION_CANCEL, callback_data="delp:cancel")])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────────────────────────
# ADMIN — YANGI FOYDALANUVCHINI TASDIQLASH
# ─────────────────────────────────────────────────────────────────────────
def kb_admin_approve(uid: int) -> InlineKeyboardMarkup:
    """Yangi foydalanuvchini tasdiqlash/rad etish."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"app:yes:{uid}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"app:no:{uid}"),
        ]
    ])


# ─────────────────────────────────────────────────────────────────────────
# ADMIN PANEL — ASOSIY MENYU
# ─────────────────────────────────────────────────────────────────────────
def kb_admin_panel() -> InlineKeyboardMarkup:
    """Super admin paneli tugmalari."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="adm:users")],
        [InlineKeyboardButton("📊 Statistika", callback_data="adm:stats")],
        [InlineKeyboardButton("📢 Xabar yuborish", callback_data="adm:broadcast")],
        [InlineKeyboardButton("🚫 Bloklanganlar", callback_data="adm:blocked")],
        [InlineKeyboardButton("💾 Ma'lumotlar bazasi", callback_data="adm:db")],
        [InlineKeyboardButton("🖥 Tizim holati", callback_data="adm:system")],
    ])


def kb_admin_back() -> InlineKeyboardMarkup:
    """Admin panelga qaytish."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back")]
    ])


# ─────────────────────────────────────────────────────────────────────────
# ADMIN — FOYDALANUVCHI KARTASI
# ─────────────────────────────────────────────────────────────────────────
def kb_user_card(uid: int, running: bool = False, blocked: bool = False) -> InlineKeyboardMarkup:
    """
    Foydalanuvchi kartasi uchun tugmalar.

    uid — foydalanuvchi ID
    running — posting ishlayaptimi
    blocked — bloklanganmi
    """
    rows = []

    # Start / Stop
    if running:
        rows.append([
            InlineKeyboardButton("⛔ Stop", callback_data=f"uc:stop:{uid}")
        ])
    else:
        rows.append([
            InlineKeyboardButton("▶️ Start", callback_data=f"uc:start:{uid}")
        ])

    # Sessiya
    rows.append([
        InlineKeyboardButton("🔑 Sessiya ochish", callback_data=f"uc:sess:{uid}"),
        InlineKeyboardButton("🚪 Sessiya o'chirish", callback_data=f"uc:logout:{uid}"),
    ])

    # Guruh / Post
    rows.append([
        InlineKeyboardButton("➕ Guruh", callback_data=f"uc:addg:{uid}"),
        InlineKeyboardButton("📝 Post", callback_data=f"uc:addp:{uid}"),
    ])

    # Muddat
    rows.append([
        InlineKeyboardButton("⏰ Muddat", callback_data=f"uc:expire:{uid}")
    ])

    # Blok / O'chirish
    block_text = "✅ Blokdan chiqarish" if blocked else "🚫 Bloklash"
    block_data = f"uc:unblock:{uid}" if blocked else f"uc:block:{uid}"
    rows.append([
        InlineKeyboardButton(block_text, callback_data=block_data),
        InlineKeyboardButton("🗑 O'chirish", callback_data=f"uc:delete:{uid}"),
    ])

    # Batafsil
    rows.append([
        InlineKeyboardButton("📊 Batafsil", callback_data=f"uc:detail:{uid}")
    ])

    # Orqaga
    rows.append([
        InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:users")
    ])

    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────────────────────────
# ADMIN — MUDDATNI UZAYTIRISH
# ─────────────────────────────────────────────────────────────────────────
def kb_expire_options(uid: int) -> InlineKeyboardMarkup:
    """Muddatni uzaytirish tez tugmalari."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("+1 kun", callback_data=f"exp:{uid}:1"),
            InlineKeyboardButton("+7 kun", callback_data=f"exp:{uid}:7"),
        ],
        [
            InlineKeyboardButton("+30 kun", callback_data=f"exp:{uid}:30"),
            InlineKeyboardButton("+90 kun", callback_data=f"exp:{uid}:90"),
        ],
        [
            InlineKeyboardButton("✏️ Qo'lda kiritish", callback_data=f"exp:{uid}:manual")
        ],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"uc:back:{uid}")],
    ])


# ─────────────────────────────────────────────────────────────────────────
# ADMIN — BLOKLANGANLAR
# ─────────────────────────────────────────────────────────────────────────
def kb_blocked_list(users: list[dict]) -> InlineKeyboardMarkup:
    """Bloklangan foydalanuvchilar ro'yxati."""
    rows = []
    for u in users[:20]:  # maksimum 20 ta
        name = u.get("name") or str(u.get("uid"))
        preview = name[:25]
        rows.append([
            InlineKeyboardButton(
                f"🔓 {preview}",
                callback_data=f"unblock:{u['uid']}",
            )
        ])
    if not rows:
        rows.append([
            InlineKeyboardButton("(bo'sh)", callback_data="adm:back")
        ])
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back")])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────────────────────────
# ADMIN — FOYDALANUVCHILAR RO'YXATI
# ─────────────────────────────────────────────────────────────────────────
def kb_users_list(users: list[dict], page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    """
    Foydalanuvchilar ro'yxati (sahifalash bilan).
    """
    start = page * per_page
    end = start + per_page
    page_users = users[start:end]

    rows = []
    for u in page_users:
        name = u.get("name") or "Noma'lum"
        uid = u.get("uid")
        # Holat belgisi
        if u.get("is_blocked"):
            mark = "🚫"
        elif u.get("running"):
            mark = "🟢"
        elif u.get("session"):
            mark = "⚪"
        else:
            mark = "🔑"
        preview = name[:22]
        rows.append([
            InlineKeyboardButton(
                f"{mark} {preview}",
                callback_data=f"uc:view:{uid}",
            )
        ])

    # Sahifalash
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm:users:{page-1}"))
    if end < len(users):
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm:users:{page+1}"))
    if nav:
        rows.append(nav)

    # Umumiy statistika
    rows.append([
        InlineKeyboardButton(f"Jami: {len(users)} ta", callback_data="adm:noop")
    ])
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back")])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────────────────────────
# ADMIN — BROADCAST (XABAR YUBORISH)
# ─────────────────────────────────────────────────────────────────────────
def kb_broadcast_confirm() -> InlineKeyboardMarkup:
    """Broadcast xabarini tasdiqlash."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yuborish", callback_data="bc:send"),
            InlineKeyboardButton("❌ Bekor", callback_data="bc:cancel"),
        ]
    ])


# ─────────────────────────────────────────────────────────────────────────
# ADMIN — DB
# ─────────────────────────────────────────────────────────────────────────
def kb_db_panel() -> InlineKeyboardMarkup:
    """Ma'lumotlar bazasi paneli."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Eksport (SQLite fayl)", callback_data="db:export")],
        [InlineKeyboardButton("💾 Zaxira nusxa", callback_data="db:backup")],
        [InlineKeyboardButton("♻️ Loglarni tozalash", callback_data="db:clearlogs")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back")],
    ])
