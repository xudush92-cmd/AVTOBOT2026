"""Botdagi reply va inline klaviaturalar."""

from __future__ import annotations

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot import texts as T


# ─────────────────────────────────────────
# LOGIN / ASOSIY MENYULAR
# ─────────────────────────────────────────
def kb_login() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(T.BTN_LOGIN)]], resize_keyboard=True)


def kb_pending() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(T.BTN_PENDING)]], resize_keyboard=True)


def kb_blocked() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(T.BTN_BLOCKED)]], resize_keyboard=True)


def kb_super_admin() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(T.BTN_ADMIN)]], resize_keyboard=True)


def kb_main(running: bool = False, super_admin: bool = False) -> ReplyKeyboardMarkup:
    if super_admin:
        return kb_super_admin()
    action = T.BTN_STOP if running else T.BTN_START
    status = f"{T.BTN_STATUS} ({'🟢 ON' if running else '🔴 OFF'})"
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(action)],
            [KeyboardButton(status), KeyboardButton(T.BTN_GROUPS)],
            [KeyboardButton(T.BTN_POSTS), KeyboardButton(T.BTN_TIMER)],
            [KeyboardButton(T.BTN_REFERRAL), KeyboardButton(T.BTN_ACCOUNT)],
        ],
        resize_keyboard=True,
    )


def kb_groups_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(T.BTN_ADD_GROUP), KeyboardButton(T.BTN_DEL_GROUP)],
            [KeyboardButton(T.BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def kb_posts_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(T.BTN_ADD_POST), KeyboardButton(T.BTN_DEL_POST)],
            [KeyboardButton(T.BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def kb_input_cancel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(T.BTN_BACK)]],
        resize_keyboard=True,
    )


def kb_auth_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(T.ACTION_CANCEL, callback_data="auth:cancel")]]
    )


def kb_admin_auth_cancel(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❌ Sessiya ulashni bekor qilish",
                    callback_data=f"uc:authcancel:{uid}",
                )
            ]
        ]
    )


# ─────────────────────────────────────────
# TELEGRAM KODI
# ─────────────────────────────────────────
def kb_numpad(admin_add_user: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("1", callback_data="np:1"),
            InlineKeyboardButton("2", callback_data="np:2"),
            InlineKeyboardButton("3", callback_data="np:3"),
        ],
        [
            InlineKeyboardButton("4", callback_data="np:4"),
            InlineKeyboardButton("5", callback_data="np:5"),
            InlineKeyboardButton("6", callback_data="np:6"),
        ],
        [
            InlineKeyboardButton("7", callback_data="np:7"),
            InlineKeyboardButton("8", callback_data="np:8"),
            InlineKeyboardButton("9", callback_data="np:9"),
        ],
        [
            InlineKeyboardButton("⬅️", callback_data="np:back"),
            InlineKeyboardButton("0", callback_data="np:0"),
            InlineKeyboardButton("✅", callback_data="np:ok"),
        ],
    ]
    if admin_add_user:
        rows.append(
            [
                InlineKeyboardButton(
                    T.BTN_ADMIN_ADD_CANCEL,
                    callback_data="np:cancel",
                )
            ]
        )
    else:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        "📷 Kod kelmadimi? QR Login",
                        callback_data="np:qr",
                    )
                ],
                [InlineKeyboardButton(T.ACTION_CANCEL, callback_data="np:cancel")],
            ]
        )
    return InlineKeyboardMarkup(rows)


def kb_qr_login(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Telegramda tasdiqlash", url=url)],
            [InlineKeyboardButton(T.ACTION_CANCEL, callback_data="qr:cancel")],
        ]
    )


# ─────────────────────────────────────────
# UNIVERSAL TASDIQLASH
# ─────────────────────────────────────────
def kb_yes_no(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(T.ACTION_YES, callback_data=yes_data),
                InlineKeyboardButton(T.ACTION_NO, callback_data=no_data),
            ]
        ]
    )


def kb_confirm(cancel_data: str = "cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(T.ACTION_CANCEL, callback_data=cancel_data)]]
    )


def kb_start_confirm(token: str) -> InlineKeyboardMarkup:
    return kb_yes_no(f"go:yes:{token}", f"go:no:{token}")


def kb_stop_confirm(token: str) -> InlineKeyboardMarkup:
    return kb_yes_no(f"stop:yes:{token}", f"stop:no:{token}")


# ─────────────────────────────────────────
# ODDIY USER GURUH/POST O'CHIRISH
# ─────────────────────────────────────────
def kb_groups_delete(
    groups: list[dict] | list[str],
    page: int = 0,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    max_page = max(0, (len(groups) - 1) // page_size)
    page = min(max(page, 0), max_page)
    start = page * page_size
    rows: list[list[InlineKeyboardButton]] = []
    for offset, item in enumerate(groups[start : start + page_size], start):
        if isinstance(item, dict):
            group_id = int(item["id"])
            value = str(item["value"])
        else:  # eski test/chaqiruvlar bilan moslik
            group_id = offset
            value = str(item)
        rows.append(
            [
                InlineKeyboardButton(
                    f"🗑 {offset + 1}. {value[:35]}",
                    callback_data=f"delg:id:{group_id}:{page}",
                )
            ]
        )
    if max_page:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"delg:page:{page - 1}"))
        nav.append(
            InlineKeyboardButton(f"{page + 1}/{max_page + 1}", callback_data="noop")
        )
        if page < max_page:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"delg:page:{page + 1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton(T.ACTION_CANCEL, callback_data="delg:cancel")])
    return InlineKeyboardMarkup(rows)


def kb_posts_delete(
    posts: list[dict],
    page: int = 0,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    max_page = max(0, (len(posts) - 1) // page_size)
    page = min(max(page, 0), max_page)
    start = page * page_size
    rows: list[list[InlineKeyboardButton]] = []
    for offset, post in enumerate(posts[start : start + page_size], start):
        icon = "🖼" if post.get("photo") else "📝"
        text = (post.get("text") or "").strip().replace("\n", " ")
        preview = text[:25] if text else "(rasm)"
        post_id = int(post.get("id", offset))
        rows.append(
            [
                InlineKeyboardButton(
                    f"🗑 {offset + 1}. {icon} {preview}",
                    callback_data=f"delp:id:{post_id}:{page}",
                )
            ]
        )
    if max_page:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"delp:page:{page - 1}"))
        nav.append(
            InlineKeyboardButton(f"{page + 1}/{max_page + 1}", callback_data="noop")
        )
        if page < max_page:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"delp:page:{page + 1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton(T.ACTION_CANCEL, callback_data="delp:cancel")])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────
# APPROVAL / ADMIN PANEL
# ─────────────────────────────────────────
def kb_admin_approve(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"app:yes:{uid}"),
                InlineKeyboardButton(
                    "❌ Rad etish", callback_data=f"app:rejectask:{uid}"
                ),
            ]
        ]
    )


def kb_admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Foydalanuvchi qo'shish", callback_data="adm:adduser"
                )
            ],
            [
                InlineKeyboardButton(
                    "⏳ Tasdiq kutilayotganlar", callback_data="adm:pending"
                )
            ],
            [InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="adm:users")],
            [
                InlineKeyboardButton(
                    "🕓 Muddati tugaganlar", callback_data="adm:expired"
                )
            ],
            [InlineKeyboardButton("📊 Statistika", callback_data="adm:stats")],
            [InlineKeyboardButton("📢 Xabar yuborish", callback_data="adm:broadcast")],
            [InlineKeyboardButton("🚫 Bloklanganlar", callback_data="adm:blocked")],
            [InlineKeyboardButton("💾 Ma'lumotlar bazasi", callback_data="adm:db")],
            [InlineKeyboardButton("🖥 Tizim holati", callback_data="adm:system")],
        ]
    )


def kb_admin_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back")]]
    )


def kb_admin_add_user_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    T.BTN_ADMIN_ADD_CANCEL,
                    callback_data="adm:adduser:cancel",
                )
            ]
        ]
    )


def kb_pending_users(
    users: list[dict],
    page: int = 0,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    max_page = max(0, (len(users) - 1) // page_size)
    page = min(max(page, 0), max_page)
    start = page * page_size
    rows = []
    for user in users[start : start + page_size]:
        name = (user.get("name") or str(user["uid"]))[:24]
        rows.append(
            [
                InlineKeyboardButton(
                    f"⏳ {name}",
                    callback_data=f"uc:view:{user['uid']}",
                )
            ]
        )
    if max_page:
        nav = []
        if page > 0:
            nav.append(
                InlineKeyboardButton("⬅️", callback_data=f"adm:pending:{page - 1}")
            )
        nav.append(
            InlineKeyboardButton(f"{page + 1}/{max_page + 1}", callback_data="adm:noop")
        )
        if page < max_page:
            nav.append(
                InlineKeyboardButton("➡️", callback_data=f"adm:pending:{page + 1}")
            )
        rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back")])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────
# SELECTED USER KARTASI
# ─────────────────────────────────────────
def kb_user_card(
    uid: int,
    running: bool = False,
    blocked: bool = False,
    has_session: bool | None = None,
    approved: bool = True,
    awaiting: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if not approved or awaiting:
        if awaiting:
            rows.append(
                [
                    InlineKeyboardButton(
                        "✅ Tasdiqlash", callback_data=f"uc:approve:{uid}"
                    ),
                    InlineKeyboardButton(
                        "❌ Rad etish", callback_data=f"uc:rejectask:{uid}"
                    ),
                ]
            )
        block_text = "✅ Blokdan chiqarish" if blocked else "🚫 Bloklash"
        block_action = "unblock" if blocked else "blockask"
        rows.append(
            [
                InlineKeyboardButton(
                    block_text, callback_data=f"uc:{block_action}:{uid}"
                ),
                InlineKeyboardButton(
                    "🗑 O'chirish", callback_data=f"uc:deleteask:{uid}"
                ),
            ]
        )
        rows.append(
            [InlineKeyboardButton("📊 Batafsil", callback_data=f"uc:detail:{uid}")]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    "⬅️ Orqaga",
                    callback_data="adm:pending" if awaiting else "adm:users",
                )
            ]
        )
        return InlineKeyboardMarkup(rows)

    if has_session and not blocked:
        if running:
            rows.append(
                [InlineKeyboardButton("⛔ Stop", callback_data=f"uc:stop:{uid}")]
            )
        else:
            rows.append(
                [InlineKeyboardButton("▶️ Start", callback_data=f"uc:start:{uid}")]
            )

    if has_session is True:
        rows.append(
            [
                InlineKeyboardButton(
                    "🚪 Sessiyani uzish",
                    callback_data=f"uc:logoutask:{uid}",
                )
            ]
        )
    elif has_session is False:
        rows.append(
            [
                InlineKeyboardButton(
                    "🔑 Sessiyani ulash",
                    callback_data=f"uc:sess:{uid}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton("💬 Guruhlar", callback_data=f"uc:groups:{uid}"),
            InlineKeyboardButton("📝 Postlar", callback_data=f"uc:posts:{uid}"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                "⏱ Posting oralig'i", callback_data=f"uc:interval:{uid}"
            ),
            InlineKeyboardButton("⏰ Tarif muddati", callback_data=f"uc:expire:{uid}"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                "✉️ Xabar yuborish", callback_data=f"uc:msg:{uid}"
            )
        ]
    )

    block_text = "✅ Blokdan chiqarish" if blocked else "🚫 Bloklash"
    block_action = "unblock" if blocked else "blockask"
    rows.append(
        [
            InlineKeyboardButton(block_text, callback_data=f"uc:{block_action}:{uid}"),
            InlineKeyboardButton("🗑 O'chirish", callback_data=f"uc:deleteask:{uid}"),
        ]
    )
    rows.append([InlineKeyboardButton("📊 Batafsil", callback_data=f"uc:detail:{uid}")])
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:users")])
    return InlineKeyboardMarkup(rows)


def kb_user_confirm(
    uid: int,
    action: str,
    confirm_text: str,
    token: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    confirm_text,
                    callback_data=f"uc:{action}:{uid}:{token}",
                ),
                InlineKeyboardButton("❌ Bekor", callback_data=f"uc:back:{uid}"),
            ]
        ]
    )


def kb_admin_groups(
    uid: int,
    groups: list[dict] | list[str],
    page: int = 0,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    max_page = max(0, (len(groups) - 1) // page_size)
    page = min(max(page, 0), max_page)
    start = page * page_size
    rows = [[InlineKeyboardButton("➕ Guruh qo'shish", callback_data=f"uc:addg:{uid}")]]
    for offset, item in enumerate(groups[start : start + page_size], start):
        if isinstance(item, dict):
            group_id, value = int(item["id"]), str(item["value"])
        else:
            group_id, value = offset, str(item)
        rows.append(
            [
                InlineKeyboardButton(
                    f"🗑 {value[:35]}",
                    callback_data=f"uc:delg:{uid}:{group_id}:{page}",
                )
            ]
        )
    if max_page:
        nav = []
        if page > 0:
            nav.append(
                InlineKeyboardButton("⬅️", callback_data=f"uc:groups:{uid}:{page - 1}")
            )
        nav.append(
            InlineKeyboardButton(f"{page + 1}/{max_page + 1}", callback_data="noop")
        )
        if page < max_page:
            nav.append(
                InlineKeyboardButton("➡️", callback_data=f"uc:groups:{uid}:{page + 1}")
            )
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton("⬅️ Foydalanuvchi", callback_data=f"uc:back:{uid}")]
    )
    return InlineKeyboardMarkup(rows)


def kb_admin_posts(
    uid: int,
    posts: list[dict],
    page: int = 0,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    max_page = max(0, (len(posts) - 1) // page_size)
    page = min(max(page, 0), max_page)
    start = page * page_size
    rows = [[InlineKeyboardButton("➕ Post qo'shish", callback_data=f"uc:addp:{uid}")]]
    for offset, post in enumerate(posts[start : start + page_size], start):
        text = (post.get("text") or "(rasm)").strip().replace("\n", " ")
        post_id = int(post.get("id", offset))
        rows.append(
            [
                InlineKeyboardButton(
                    f"🗑 {text[:35]}",
                    callback_data=f"uc:delp:{uid}:{post_id}:{page}",
                )
            ]
        )
    if max_page:
        nav = []
        if page > 0:
            nav.append(
                InlineKeyboardButton("⬅️", callback_data=f"uc:posts:{uid}:{page - 1}")
            )
        nav.append(
            InlineKeyboardButton(f"{page + 1}/{max_page + 1}", callback_data="noop")
        )
        if page < max_page:
            nav.append(
                InlineKeyboardButton("➡️", callback_data=f"uc:posts:{uid}:{page + 1}")
            )
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton("⬅️ Foydalanuvchi", callback_data=f"uc:back:{uid}")]
    )
    return InlineKeyboardMarkup(rows)


def kb_admin_section_back(uid: int, section: str = "back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Bekor qilish", callback_data=f"uc:{section}:{uid}")]]
    )


def kb_admin_interval(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("5 daq", callback_data=f"aint:{uid}:5"),
                InlineKeyboardButton("10 daq", callback_data=f"aint:{uid}:10"),
                InlineKeyboardButton("15 daq", callback_data=f"aint:{uid}:15"),
            ],
            [
                InlineKeyboardButton("30 daq", callback_data=f"aint:{uid}:30"),
                InlineKeyboardButton("60 daq", callback_data=f"aint:{uid}:60"),
                InlineKeyboardButton("120 daq", callback_data=f"aint:{uid}:120"),
            ],
            [
                InlineKeyboardButton(
                    "✏️ Qo'lda kiritish", callback_data=f"aint:{uid}:manual"
                )
            ],
            [InlineKeyboardButton("⬅️ Foydalanuvchi", callback_data=f"uc:back:{uid}")],
        ]
    )


def kb_expire_options(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("+1 kun", callback_data=f"exp:{uid}:1"),
                InlineKeyboardButton("+7 kun", callback_data=f"exp:{uid}:7"),
            ],
            [
                InlineKeyboardButton("+30 kun", callback_data=f"exp:{uid}:30"),
                InlineKeyboardButton("+90 kun", callback_data=f"exp:{uid}:90"),
            ],
            [InlineKeyboardButton("♾ Cheksiz", callback_data=f"exp:{uid}:forever")],
            [
                InlineKeyboardButton(
                    "✏️ Qo'lda kiritish", callback_data=f"exp:{uid}:manual"
                )
            ],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"uc:back:{uid}")],
        ]
    )


# ─────────────────────────────────────────
# ADMIN RO'YXATLARI
# ─────────────────────────────────────────
def kb_blocked_list(
    users: list[dict], page: int = 0, per_page: int = 20
) -> InlineKeyboardMarkup:
    max_page = max(0, (len(users) - 1) // per_page)
    page = min(max(page, 0), max_page)
    start = page * per_page
    rows = []
    for user in users[start : start + per_page]:
        name = (user.get("name") or str(user.get("uid")))[:25]
        rows.append(
            [InlineKeyboardButton(f"🔓 {name}", callback_data=f"unblock:{user['uid']}")]
        )
    if max_page:
        nav = []
        if page > 0:
            nav.append(
                InlineKeyboardButton("⬅️", callback_data=f"adm:blocked:{page - 1}")
            )
        nav.append(
            InlineKeyboardButton(f"{page + 1}/{max_page + 1}", callback_data="noop")
        )
        if page < max_page:
            nav.append(
                InlineKeyboardButton("➡️", callback_data=f"adm:blocked:{page + 1}")
            )
        rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back")])
    return InlineKeyboardMarkup(rows)


def kb_users_list(
    users: list[dict], page: int = 0, per_page: int = 8
) -> InlineKeyboardMarkup:
    max_page = max(0, (len(users) - 1) // per_page)
    page = min(max(page, 0), max_page)
    start = page * per_page
    rows = []
    for user in users[start : start + per_page]:
        name = user.get("name") or "Noma'lum"
        if user.get("is_blocked"):
            mark = "🚫"
        elif user.get("awaiting_approval"):
            mark = "⏳"
        elif not user.get("is_admin"):
            mark = "❌"
        elif user.get("running"):
            mark = "🟢"
        elif user.get("session"):
            mark = "⚪"
        else:
            mark = "🔑"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark} {name[:22]}",
                    callback_data=f"uc:view:{user['uid']}",
                )
            ]
        )
    if max_page:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm:users:{page - 1}"))
        nav.append(
            InlineKeyboardButton(f"{page + 1}/{max_page + 1}", callback_data="noop")
        )
        if page < max_page:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"adm:users:{page + 1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton(f"Jami: {len(users)} ta", callback_data="noop")])
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back")])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────
# BROADCAST / DB / USER ACCOUNT
# ─────────────────────────────────────────
def kb_broadcast_input() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Bekor", callback_data="bc:cancel")]]
    )


def kb_broadcast_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Yuborish", callback_data="bc:send"),
                InlineKeyboardButton("❌ Bekor", callback_data="bc:cancel"),
            ]
        ]
    )


def kb_broadcast_progress() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⛔ Yuborishni to'xtatish", callback_data="bc:stop")]]
    )


def kb_db_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📥 Xavfsiz eksport (sessiyasiz)", callback_data="db:export"
                )
            ],
            [
                InlineKeyboardButton(
                    "💾 Izchil SQLite backup", callback_data="db:backup"
                )
            ],
            [
                InlineKeyboardButton(
                    "♻️ Loglarni tozalash", callback_data="db:clearlogs:ask"
                )
            ],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back")],
        ]
    )


def kb_clear_logs_confirm(token: str) -> InlineKeyboardMarkup:
    return kb_yes_no(f"db:clearlogs:confirm:{token}", "adm:db")


def kb_account() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚪 Telegram sessiyasini uzish", callback_data="self:logoutask"
                )
            ],
            [InlineKeyboardButton("❌ Yopish", callback_data="self:close")],
        ]
    )


def kb_account_logout_confirm(token: str) -> InlineKeyboardMarkup:
    return kb_yes_no(f"self:logoutconfirm:{token}", "self:close")
