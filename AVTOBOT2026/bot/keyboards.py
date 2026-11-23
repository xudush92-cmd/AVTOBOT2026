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
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(T.BTN_LOGIN)],
        ],
        resize_keyboard=True,
    )


def kb_pending() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(T.BTN_PENDING)]], resize_keyboard=True)


def kb_blocked() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(T.BTN_BLOCKED)]], resize_keyboard=True)


def kb_super_admin() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(T.BTN_ADMIN)]], resize_keyboard=True)


def kb_main(
    running: bool = False,
    super_admin: bool = False,
    team_admin: bool = False,
    team_member: bool = False,
) -> ReplyKeyboardMarkup:
    """Yassi (ichki menyusiz) foydalanuvchi klaviaturasi.

    Barcha asosiy amallar bitta ekranda: guruhlar avtomatik topiladi,
    post/qo'shish-o'chirish va interval to'g'ridan-to'g'ri shu yerdan ochiladi.
    Holat (ON/OFF) alohida Status tugmasisiz — Start/Stop tugmasining o'zida.
    """
    if super_admin:
        return kb_super_admin()
    # Start va Stop — doimiy ikki tugma. Holat (ON/OFF) ularning
    # yorlig'ida emas, alohida xabarda beriladi.
    rows = [
        [KeyboardButton(T.BTN_START), KeyboardButton(T.BTN_STOP)],
        [
            KeyboardButton(T.BTN_FIND_GROUPS),
            KeyboardButton(T.BTN_GROUPS),
        ],
        [
            KeyboardButton(T.BTN_ADD_POST),
            KeyboardButton(T.BTN_DEL_POST),
        ],
        [
            KeyboardButton(T.BTN_INTERVAL),
            KeyboardButton(T.BTN_REFERRAL),
        ],
    ]
    # Jamoa adminiga — o'z jamoasini boshqarish tugmasi.
    if team_admin or team_member:
        rows.append([KeyboardButton(T.BTN_TEAM_MENU)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


async def kb_main_for(uid: int, running: bool = False) -> ReplyKeyboardMarkup:
    """Foydalanuvchi rolini aniqlab asosiy klaviaturani qaytaradi.

    Jamoa admini va jamoa a'zosi uchun ``👥 Jamoam`` tugmasi har bir
    ekranda (``💬 Guruhlar``, ``⏱ Interval``, ``▶️ Start`` va h.k.) saqlanadi.
    """
    from core import database as db

    user = await db.get_user(uid) or {}
    return kb_main(
        running=running,
        team_admin=bool(user.get("is_team_admin")),
        team_member=bool(user.get("team_id")) and not user.get("is_team_admin"),
    )


def kb_referral(link: str) -> InlineKeyboardMarkup:
    """Referal sahifasi tugmalari: havolani ochish va do'stga yuborish.

    Jamoa admini uchun bu oyna ishlatilmaydi — u
    :func:`kb_team_link_only` ni ishlatadi (faqat jamoa havolasi).
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔗 Havolani ochish", url=link),
                InlineKeyboardButton(
                    "📨 Do'stlarga yuborish", callback_data="ref:share"
                ),
            ],
        ]
    )


def kb_team_link_only(link: str) -> InlineKeyboardMarkup:
    """Jamoa admini referal oynasi — faqat umumiy jamoa havolasi.

    Jamoa adminida shaxsiy (``ref_<uid>``) referal tugmalari va
    statistikasi kerak emas: jamoa a'zolari jamoa havolasi orqali
    keladi, shuning uchun faqat bitta havola yetarli.
    """
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔗 Jamoa havolasi", url=link)]]
    )


def kb_input_cancel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(T.BTN_BACK)]],
        resize_keyboard=True,
    )


def kb_input_cancel_inline() -> InlineKeyboardMarkup:
    """Matn kiritish oynasi uchun **inline** bekor tugmasi.

    ``kb_input_cancel()`` — Reply klaviatura. Uni ``edit_message_text``
    bilan ishlatib bo'lmaydi: Telegram faqat ``InlineKeyboardMarkup``
    qabul qiladi va aks holda ``BadRequest: Inline keyboard expected``
    xatosini beradi.

    Shu sabab inline kontekstda (tugma bosilganda) shu variant ishlatiladi.
    """
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(T.BTN_BACK, callback_data="adm:back")]]
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
def _group_button_label(item: dict) -> str:
    """``🗑`` tugmasi uchun guruh nomi.

    Telegram'dagi display name (``title``) afzal — foydalanuvchi guruhni
    nomidan tanib oladi. Nomi yo'q bo'lsa — username.

    Yopiq guruh (marked ID) uchun ID **ko'rsatilmaydi**.

    Telegram tugma matni **64 belgi** bilan cheklangan — shuning uchun
    matn qisqartiriladi.
    """
    title = str(item.get("title") or "").strip()
    value = str(item.get("value") or "").strip()
    if title and title != value:
        # Nomi bor — faqat nomi ko'rsatamiz (joy tejaladi).
        return title[:48]
    if value.startswith("@"):
        return value[:48]
    # Yopiq guruh — ID ko'rsatilmaydi.
    return (title or "Yopiq guruh")[:48]


def kb_my_groups(
    groups: list[dict],
    page: int = 0,
    page_size: int = 10,
    pending_selected: int = 0,
) -> InlineKeyboardMarkup:
    """Foydalanuvchining o'z guruhlari — bitta boshqaruv oynasi.

    Pastda — har bir guruh uchun **faqat** o'chirish tugmasi
    (``🗑 N. guruh``). Interval o'zgartirish ``⏱ Interval`` oynasidan
    amalga oshadi.

    ``🔍 Guruhlarni topish`` tugmasi bu yerga **qo'yilmaydi** — u asosiy
    menyuda mavjud. Shu yerda takror bo'lsa, foydalanuvchi bir xil
    amalni ikki joyda topadi va chalkashadi.

    ``pending_selected`` — skanerda tanlangan, lekin hali qo'shilmagan
    guruhlar soni. Noldan katta bo'lsa, «✅ Tanlanganlarni qo'shish»
    tugmasi qo'shiladi — aks holda foydalanuvchi tanlagan guruhlarini
    yo'qotib qo'yadi.
    """
    max_page = max(0, (len(groups) - 1) // page_size)
    page = min(max(page, 0), max_page)
    start = page * page_size
    rows: list[list[InlineKeyboardButton]] = []
    for offset, item in enumerate(groups[start : start + page_size], start):
        group_id = int(item["id"])
        # ✅ Tugmada guruhning **nomi** ko'rinadi (Telegram display name).
        # Nomi yo'q bo'lsa — username. Limit 64 belgi.
        label = _group_button_label(item)
        rows.append(
            [
                InlineKeyboardButton(
                    f"🗑 {offset + 1}. {label}",
                    callback_data=f"mg:del:{group_id}",
                ),
            ]
        )
    if max_page:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton("⬅️", callback_data=f"mg:page:{page - 1}")
            )
        nav.append(
            InlineKeyboardButton(f"📄 {page + 1}/{max_page + 1}", callback_data="noop")
        )
        if page < max_page:
            nav.append(
                InlineKeyboardButton("➡️", callback_data=f"mg:page:{page + 1}")
            )
        rows.append(nav)
    if pending_selected > 0:
        # ⚠️ Skanerda tanlangan, lekin hali qo'shilmagan guruhlar bor.
        # Tugmasiz foydalanuvchi ularni yo'qotib qo'yadi.
        rows.append(
            [
                InlineKeyboardButton(
                    f"💾 Tanlanganlarni saqlash ({pending_selected})",
                    callback_data="mg:apply",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton("⬅️ Asosiy menyu", callback_data="mg:back")]
    )
    return InlineKeyboardMarkup(rows)


def kb_interval_choice() -> InlineKeyboardMarkup:
    """⏱ Interval oynasi — umumiy yoki bitta guruh uchun.

    Ikki xil interval mavjud:
      * ``🌐 Barcha guruhlar uchun`` — umumiy interval (barcha guruh);
      * ``⏱ Bitta guruh uchun`` — alohida interval (tanlangan guruh).
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🌐 Barcha guruhlar uchun", callback_data="int:global"
                )
            ],
            [
                InlineKeyboardButton(
                    "⏱ Bitta guruh uchun", callback_data="int:one"
                )
            ],
            [InlineKeyboardButton("⬅️ Asosiy menyu", callback_data="int:back")],
        ]
    )


def kb_my_group_interval(
    group_id: int,
    current_interval: int | None,
) -> InlineKeyboardMarkup:
    """Bitta guruhning alohida intervali — foydalanuvchi uchun (``mg:``)."""
    rows: list[list[InlineKeyboardButton]] = []
    values = [5, 10, 15, 30, 60, 120]
    for start in range(0, len(values), 3):
        row = []
        for minutes in values[start : start + 3]:
            mark = "✅ " if current_interval == minutes else ""
            row.append(
                InlineKeyboardButton(
                    f"{mark}{minutes} daq",
                    callback_data=f"mg:set:{group_id}:{minutes}",
                )
            )
        rows.append(row)
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    "✏️ Qo'lda kiritish",
                    callback_data=f"mg:manual:{group_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "↩️ Umumiy intervalni ishlatish",
                    callback_data=f"mg:reset:{group_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Guruhlar", callback_data="mg:page:0"
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(rows)


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


def kb_group_interval_picker(
    groups: list[dict],
    global_interval: int,
    page: int = 0,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    max_page = max(0, (len(groups) - 1) // page_size)
    page = min(max(page, 0), max_page)
    start = page * page_size
    rows: list[list[InlineKeyboardButton]] = []
    for item in groups[start : start + page_size]:
        group_id = int(item["id"])
        value = str(item["value"])
        interval = item.get("interval_min")
        label = f"{int(interval)} daq" if interval is not None else f"Umumiy {global_interval} daq"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{value[:26]} · {label}",
                    callback_data=f"gint:select:{group_id}",
                )
            ]
        )
    if max_page:
        nav = []
        if page > 0:
            nav.append(
                InlineKeyboardButton("⬅️", callback_data=f"gint:list:{page - 1}")
            )
        nav.append(
            InlineKeyboardButton(f"{page + 1}/{max_page + 1}", callback_data="noop")
        )
        if page < max_page:
            nav.append(
                InlineKeyboardButton("➡️", callback_data=f"gint:list:{page + 1}")
            )
        rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ Guruhlar", callback_data="gint:back")])
    return InlineKeyboardMarkup(rows)


def kb_group_interval_options(
    group_id: int,
    current_interval: int | None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    values = [5, 10, 15, 30, 60, 120]
    for start in range(0, len(values), 3):
        row = []
        for minutes in values[start : start + 3]:
            mark = "✅ " if current_interval == minutes else ""
            row.append(
                InlineKeyboardButton(
                    f"{mark}{minutes} daq",
                    callback_data=f"gint:set:{group_id}:{minutes}",
                )
            )
        rows.append(row)
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    "✏️ Qo'lda kiritish",
                    callback_data=f"gint:manual:{group_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "↩️ Umumiy intervalni ishlatish",
                    callback_data=f"gint:reset:{group_id}",
                )
            ],
            [InlineKeyboardButton("⬅️ Guruhlar", callback_data="gint:list:0")],
        ]
    )
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


def kb_approve_term_options(uid: int, options: list[int]) -> InlineKeyboardMarkup:
    """Tasdiqlashda muddat (kun) tanlash — super admin uchun."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for days in options:
        row.append(
            InlineKeyboardButton(
                f"{days} kun",
                callback_data=f"app:term:{uid}:{days}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ Rad etish", callback_data=f"app:rejectask:{uid}")])
    return InlineKeyboardMarkup(rows)


def kb_team_approve_term_options(uid: int, options: list[int]) -> InlineKeyboardMarkup:
    """Tasdiqlashda muddat (kun) tanlash — jamoa admini uchun."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for days in options:
        row.append(
            InlineKeyboardButton(
                f"{days} kun",
                callback_data=f"tadm:approveterm:{uid}:{days}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data=f"tadm:member:{uid}")])
    return InlineKeyboardMarkup(rows)


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
                    "👑 Jamoa adminlari", callback_data="adm:teamadmins"
                )
            ],
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


def kb_team_admins(admins: list[dict]) -> InlineKeyboardMarkup:
    """Jamoa adminlari ro'yxati (super admin uchun)."""
    rows: list[list[InlineKeyboardButton]] = []
    for admin in admins:
        uid = int(admin.get("uid") or 0)
        name = (admin.get("name") or str(uid))[:28]
        # Muddati tugagan yoki bloklangan jamoa admini — belgi bilan.
        icon = "👑"
        if admin.get("is_blocked"):
            icon = "🚫"
        elif admin.get("awaiting_approval"):
            icon = "⏳"
        elif _admin_expired(admin):
            icon = "⌛"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{icon} {name}",
                    callback_data=f"adm:teamadmin:{uid}",
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton("👑 Jamoa adminlari yo'q", callback_data="adm:noop")])
    rows.append(
        [
            InlineKeyboardButton(
                "➕ Admin qo'shish", callback_data="adm:addteamadmin"
            )
        ]
    )
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back")])
    return InlineKeyboardMarkup(rows)


def _admin_expired(admin: dict) -> bool:
    """Jamoa adminining muddati tugaganmi."""
    expires = admin.get("admin_expires_at")
    if not expires:
        return False
    from core.utils import is_expired

    return is_expired(expires)


def kb_team_admin_card(uid: int) -> InlineKeyboardMarkup:
    """Jamoa admini kartasi — muddat, sig'im va topshirish boshqaruvi."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📅 Muddatni uzaytirish", callback_data=f"adm:teamterm:{uid}"
                )
            ],
            [
                InlineKeyboardButton(
                    "👥 Sig'imni o'zgartirish", callback_data=f"adm:teamlimit:{uid}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Jamoani topshirish", callback_data=f"adm:teamhandover:{uid}"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Orqaga", callback_data="adm:teamadmins"
                )
            ],
        ]
    )


def kb_team_handover_options(
    uid: int, admins: list[dict]
) -> InlineKeyboardMarkup:
    """Jamoani topshirish uchun yangi adminni tanlash (super admin)."""
    rows: list[list[InlineKeyboardButton]] = []
    for admin in admins:
        new_uid = int(admin.get("uid") or 0)
        name = (admin.get("name") or str(new_uid))[:28]
        rows.append(
            [
                InlineKeyboardButton(
                    f"👑 {name}",
                    callback_data=f"adm:teamhandoverset:{uid}:{new_uid}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"adm:teamadmin:{uid}")]
    )
    return InlineKeyboardMarkup(rows)


def kb_team_admin_term(uid: int, options: list[int]) -> InlineKeyboardMarkup:
    """Jamoa adminiga yangi muddat berish."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for days in options:
        row.append(
            InlineKeyboardButton(
                f"{days} kun",
                callback_data=f"adm:teamsetterm:{uid}:{days}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"adm:teamadmin:{uid}")]
    )
    return InlineKeyboardMarkup(rows)


def kb_team_admin_limit(uid: int, options: list[int]) -> InlineKeyboardMarkup:
    """Jamoa adminining sig'imini (user soni) o'zgartirish."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for size in options:
        row.append(
            InlineKeyboardButton(
                f"{size} ta",
                callback_data=f"adm:teamsetlimit:{uid}:{size}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"adm:teamadmin:{uid}")]
    )
    return InlineKeyboardMarkup(rows)


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
                "⏱ Umumiy interval", callback_data=f"uc:interval:{uid}"
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
    rows.append(
        [
            InlineKeyboardButton(
                "👥 Jamoaga biriktirish", callback_data=f"uc:teambind:{uid}"
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


def kb_team_bind_choose(target: int, admins: list[dict]) -> InlineKeyboardMarkup:
    """Super admin uchun: jamoaga biriktirish — jamoa adminini tanlash."""
    rows: list[list[InlineKeyboardButton]] = []
    for admin in admins:
        uid = int(admin.get("uid") or 0)
        name = (admin.get("name") or str(uid))[:28]
        icon = "👑" if not admin.get("is_blocked") else "🚫"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{icon} {name}",
                    callback_data=f"uc:teambindgo:{target}:{uid}",
                )
            ]
        )
    if not rows:
        rows.append(
            [InlineKeyboardButton("👑 Jamoa admini yo'q", callback_data="adm:noop")]
        )
    rows.append(
        [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"uc:view:{target}")]
    )
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
        interval = item.get("interval_min") if isinstance(item, dict) else None
        interval_label = f"{int(interval)} daq" if interval is not None else "Umumiy"
        rows.append(
            [
                InlineKeyboardButton(
                    f"🗑 {offset + 1}. {value[:26]}",
                    callback_data=f"uc:delg:{uid}:{group_id}:{page}",
                ),
                InlineKeyboardButton(
                    f"⏱ {interval_label}",
                    callback_data=f"uc:gint:{uid}:{group_id}",
                ),
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


def kb_admin_group_interval(
    uid: int,
    group_id: int,
    current_interval: int | None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    values = [5, 10, 15, 30, 60, 120]
    for start in range(0, len(values), 3):
        row = []
        for minutes in values[start : start + 3]:
            mark = "✅ " if current_interval == minutes else ""
            row.append(
                InlineKeyboardButton(
                    f"{mark}{minutes} daq",
                    callback_data=f"uc:gint:{uid}:{group_id}:{minutes}",
                )
            )
        rows.append(row)
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    "✏️ Qo'lda kiritish",
                    callback_data=f"uc:gint:{uid}:{group_id}:manual",
                )
            ],
            [
                InlineKeyboardButton(
                    "↩️ Umumiy intervalni ishlatish",
                    callback_data=f"uc:gint:{uid}:{group_id}:general",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Guruhlar", callback_data=f"uc:groups:{uid}"
                )
            ],
        ]
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
                    f"🗑 {offset + 1}. {text[:35]}",
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


def kb_admin_plan(uid: int, plan: str = "") -> InlineKeyboardMarkup:
    """Admin paneli: foydalanuvchiga tarif paketini va limitini qo'yish."""
    from config.config import PLAN_DEFS

    names = list(PLAN_DEFS.keys())
    rows = []
    for i in range(0, len(names), 2):
        rows.append(
            [
                InlineKeyboardButton(
                    ("✅ " if (names[j] or "♾") == (plan or "♾") else "") + (
                        names[j] if names[j] else "Cheksiz"
                    ),
                    callback_data=f"uc:plan:set:{uid}:{names[j] or '_'}",
                )
                for j in range(i, min(i + 2, len(names)))
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("0️⃣ Limitlarsiz", callback_data=f"uc:plan:lim:{uid}:off"),
            InlineKeyboardButton("🔰 5 guruh / 30 kun", callback_data=f"uc:plan:lim:{uid}:5"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton("🎁 +7 kun", callback_data=f"uc:plan:bonus:{uid}:7"),
            InlineKeyboardButton("🎁 +30 kun", callback_data=f"uc:plan:bonus:{uid}:30"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton("➖1 kun", callback_data=f"uc:plan:bonus:{uid}:-1"),
            InlineKeyboardButton("⬅️ Kartaga", callback_data=f"uc:card:{uid}"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def kb_expire_options(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("1 kun", callback_data=f"exp:{uid}:1"),
                InlineKeyboardButton("7 kun", callback_data=f"exp:{uid}:7"),
            ],
            [
                InlineKeyboardButton("30 kun", callback_data=f"exp:{uid}:30"),
                InlineKeyboardButton("90 kun", callback_data=f"exp:{uid}:90"),
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


# ─────────────────────────────────────────
# ALBOM / POST AMALLARI
# ─────────────────────────────────────────
def kb_album_done() -> InlineKeyboardMarkup:
    """Yig'ilayotgan albomni saqlash tugmasi."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(T.BTN_ALBUM_DONE, callback_data="alb:done")]]
    )


def _post_picker(
    posts: list[dict],
    page: int,
    action: str,
    prefix_icon: str,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    """Post ro'yxatidan birini tanlash uchun umumiy konstruktor."""
    max_page = max(0, (len(posts) - 1) // page_size)
    page = min(max(page, 0), max_page)
    start = page * page_size
    rows: list[list[InlineKeyboardButton]] = []
    for offset, post in enumerate(posts[start : start + page_size], start):
        text = (post.get("text") or "").strip().replace("\n", " ")
        count = len(post.get("media") or [])
        icon = f"🖼×{count}" if count > 1 else ("🖼" if count else "📝")
        preview = text[:24] if text else "(media)"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{prefix_icon} {offset + 1}. {icon} {preview}",
                    callback_data=f"{action}:{int(post.get('id', offset))}:{page}",
                )
            ]
        )
    if max_page:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"{action}:page:{page - 1}"))
        nav.append(
            InlineKeyboardButton(
                f"{page + 1}/{max_page + 1}", callback_data="noop"
            )
        )
        if page < max_page:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"{action}:page:{page + 1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton(T.ACTION_CANCEL, callback_data=f"{action}:cancel")])
    return InlineKeyboardMarkup(rows)


def kb_posts_edit(posts: list[dict], page: int = 0) -> InlineKeyboardMarkup:
    return _post_picker(posts, page, "ped", "✏️")


def kb_posts_preview(posts: list[dict], page: int = 0) -> InlineKeyboardMarkup:
    return _post_picker(posts, page, "pvw", "👁")


def kb_posts_test(posts: list[dict], page: int = 0) -> InlineKeyboardMarkup:
    return _post_picker(posts, page, "tstp", "🧪")


def kb_post_options(post: dict) -> InlineKeyboardMarkup:
    """Bitta post bo'yicha amallar: preview, sinov, link preview yoqish/o'chirish."""
    post_id = int(post.get("id") or 0)
    preview_on = bool(post.get("link_preview", True))
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👁 Ko'rinishi", callback_data=f"pvw:id:{post_id}:0"),
                InlineKeyboardButton("🧪 Sinov", callback_data=f"tstp:id:{post_id}:0"),
            ],
            [
                InlineKeyboardButton(
                    "🔗 Link preview: " + ("✅ yoqilgan" if preview_on else "❌ o'chirilgan"),
                    callback_data=f"lp:toggle:{post_id}",
                )
            ],
            [InlineKeyboardButton("⬅️ Postlar", callback_data="pvw:back")],
        ]
    )


def kb_group_picker(
    groups: list[dict],
    page: int,
    action: str,
    icon: str,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    """Guruh ro'yxatidan bitta tanlash (tekshirish / sinov yuborish uchun)."""
    max_page = max(0, (len(groups) - 1) // page_size)
    page = min(max(page, 0), max_page)
    start = page * page_size
    rows: list[list[InlineKeyboardButton]] = []
    for group in groups[start : start + page_size]:
        value = str(group.get("value", ""))
        rows.append(
            [
                InlineKeyboardButton(
                    f"{icon} {value[:40]}",
                    callback_data=f"{action}:id:{int(group['id'])}:{page}",
                )
            ]
        )
    if max_page:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"{action}:page:{page - 1}"))
        nav.append(
            InlineKeyboardButton(f"{page + 1}/{max_page + 1}", callback_data="noop")
        )
        if page < max_page:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"{action}:page:{page + 1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton(T.BTN_BACK, callback_data=f"{action}:back")])
    return InlineKeyboardMarkup(rows)


def kb_test_send_confirm(post_id: int, group_id: int, token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Ha, bitta guruhga yuborish",
                    callback_data=f"tst:go:{post_id}:{group_id}:{token}",
                )
            ],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="tst:cancel")],
        ]
    )


def kb_test_group_picker(
    groups: list[dict], post_id: int, page: int = 0, page_size: int = 10
) -> InlineKeyboardMarkup:
    """Sinov yuborish uchun bitta guruhni tanlash.

    Callback'da post_id ham saqlanadi — shu sabab oddiy guruh tanlagichdan
    alohida quriladi.
    """
    max_page = max(0, (len(groups) - 1) // page_size)
    page = min(max(page, 0), max_page)
    start = page * page_size
    rows: list[list[InlineKeyboardButton]] = []
    for group in groups[start : start + page_size]:
        rows.append(
            [
                InlineKeyboardButton(
                    f"📛 {str(group.get('value', ''))[:40]}",
                    callback_data=f"tstg:ask:{post_id}:{int(group['id'])}",
                )
            ]
        )
    if max_page:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    "⬅️", callback_data=f"tstg:page:{post_id}:{page - 1}"
                )
            )
        nav.append(
            InlineKeyboardButton(f"{page + 1}/{max_page + 1}", callback_data="noop")
        )
        if page < max_page:
            nav.append(
                InlineKeyboardButton(
                    "➡️", callback_data=f"tstg:page:{post_id}:{page + 1}"
                )
            )
        rows.append(nav)
    rows.append([InlineKeyboardButton(T.BTN_BACK, callback_data="tstg:back")])
    return InlineKeyboardMarkup(rows)


def kb_group_check_picker(
    groups: list[dict], page: int = 0, page_size: int = 10
) -> InlineKeyboardMarkup:
    return kb_group_picker(groups, page, "gchk", "🔎")


# ─────────────────────────────────────────
# JAMOALAR (TEAMS)
# ─────────────────────────────────────────
def kb_team_pick(teams: list[dict], page: int = 0, page_size: int = 10) -> InlineKeyboardMarkup:
    """Ro'yxatdan o'tuvchi uchun jamoa tanlash tugmalari."""
    rows: list[list[InlineKeyboardButton]] = []
    if teams:
        total_pages = max(1, (len(teams) + page_size - 1) // page_size)
        page = min(max(0, page), total_pages - 1)
        start = page * page_size
        window = teams[start : start + page_size]
        for team in window:
            team_id = int(team.get("id") or 0)
            name = (team.get("name") or "Noma'lum")[:30]
            rows.append(
                [
                    InlineKeyboardButton(
                        f"🎯 {name}",
                        callback_data=f"team:pick:{team_id}",
                    )
                ]
            )
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton("⬅️", callback_data=f"team:page:{page - 1}")
            )
        nav.append(
            InlineKeyboardButton(
                f"{page + 1}/{total_pages}", callback_data="team:noop"
            )
        )
        if page + 1 < total_pages:
            nav.append(
                InlineKeyboardButton("➡️", callback_data=f"team:page:{page + 1}")
            )
        if nav:
            rows.append(nav)
    rows.append(
        [InlineKeyboardButton("🙋 Jamoasiz davom etish", callback_data="team:skip")]
    )
    return InlineKeyboardMarkup(rows)


def kb_team_admin_panel() -> InlineKeyboardMarkup:
    """Jamoa admini panelining asosiy tugmalari."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "👥 Foydalanuvchilar", callback_data="tadm:users"
                ),
                InlineKeyboardButton("📊 Statistika", callback_data="tadm:stats"),
            ],
            [
                InlineKeyboardButton(
                    "➕ Do'st qo'shish", callback_data="tadm:addfriend"
                ),
                InlineKeyboardButton(
                    "📋 Do'stlar ro'yxati", callback_data="tadm:invites"
                ),
            ],
            [
                InlineKeyboardButton(
                    "📨 Xabar yuborish", callback_data="tadm:message"
                ),
            ],
            [
                InlineKeyboardButton(
                    "✏️ Jamoa nomi", callback_data="tadm:rename"
                ),
                InlineKeyboardButton("🔗 Havola", callback_data="tadm:link"),
            ],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="tadm:back")],
        ]
    )


def kb_team_stats_back() -> InlineKeyboardMarkup:
    """Statistika oynasidan jamoa admini paneliga qaytish."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Orqaga", callback_data="tadm:panel")]]
    )


def kb_team_invites(invites: list[dict]) -> InlineKeyboardMarkup:
    """Admin qo'shgan do'stlar ro'yxati."""
    rows: list[list[InlineKeyboardButton]] = []
    for inv in invites:
        phone = inv.get("phone") or "?"
        status = inv.get("status") or "pending"
        icon = {"pending": "⏳", "used": "✅"}.get(status, "❓")
        rows.append(
            [InlineKeyboardButton(f"{icon} {phone}", callback_data="tadm:noop")]
        )
        # Taklifni bekor qilish (o'chirish).
        if status == "pending":
            rows.append(
                [
                    InlineKeyboardButton(
                        f"🗑 {phone} — bekor qilish",
                        callback_data=f"tadm:delinvite:{phone}",
                    )
                ]
            )
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="tadm:panel")])
    return InlineKeyboardMarkup(rows)


def kb_team_members(members: list[dict], page: int = 0, page_size: int = 10) -> InlineKeyboardMarkup:
    """Jamoa a'zolari ro'yxati — tarif berish uchun tanlash."""
    rows: list[list[InlineKeyboardButton]] = []
    if members:
        total_pages = max(1, (len(members) + page_size - 1) // page_size)
        page = min(max(0, page), total_pages - 1)
        start = page * page_size
        window = members[start : start + page_size]
        for user in window:
            uid = int(user.get("uid") or 0)
            name = (user.get("name") or str(uid))[:28]
            awaiting = bool(user.get("awaiting_approval"))
            button = InlineKeyboardButton(
                f"{'⏳' if awaiting else '👤'} {name}",
                callback_data=f"tadm:member:{uid}",
            )
            if awaiting:
                # Tasdiq kutilayotgan a'zo — to'g'ridan-to'g'ri tasdiqlash.
                rows.append(
                    [
                        button,
                        InlineKeyboardButton(
                            "✅ Tasdiqlash", callback_data=f"tadm:approve:{uid}"
                        ),
                    ]
                )
            else:
                rows.append([button])
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton("⬅️", callback_data=f"tadm:users:{page - 1}")
            )
        nav.append(
            InlineKeyboardButton(
                f"{page + 1}/{total_pages}", callback_data="tadm:noop"
            )
        )
        if page + 1 < total_pages:
            nav.append(
                InlineKeyboardButton("➡️", callback_data=f"tadm:users:{page + 1}")
            )
        if nav:
            rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="tadm:panel")])
    return InlineKeyboardMarkup(rows)


def kb_team_member_card(uid: int, awaiting: bool = False) -> InlineKeyboardMarkup:
    """Jamoa a'zosi kartasi — tasdiqlash / tarif berish / bloklash."""
    rows: list[list[InlineKeyboardButton]] = []
    if awaiting:
        rows.append(
            [
                InlineKeyboardButton(
                    "✅ Tasdiqlash", callback_data=f"tadm:approve:{uid}"
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "📅 Muddat berish", callback_data=f"tadm:term:{uid}"
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                "🚫 Bloklash", callback_data=f"tadm:block:{uid}"
            ),
            InlineKeyboardButton(
                "✅ Blokdan chiqarish", callback_data=f"tadm:unblock:{uid}"
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                "🚪 Jamoadan chiqarish", callback_data=f"tadm:kick:{uid}"
            )
        ]
    )
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="tadm:users")])
    return InlineKeyboardMarkup(rows)


def kb_team_term_options(uid: int, options: list[int]) -> InlineKeyboardMarkup:
    """Muddat (kun) tanlash tugmalari."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for days in options:
        row.append(
            InlineKeyboardButton(
                f"{days} kun",
                callback_data=f"tadm:setterm:{uid}:{days}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data=f"tadm:member:{uid}")])
    return InlineKeyboardMarkup(rows)


def kb_team_member_self_card() -> InlineKeyboardMarkup:
    """Oddiy jamoa a'zosi kartasi — jamoadan chiqish."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚪 Jamoadan chiqish", callback_data="team:leaveask"
                )
            ]
        ]
    )


def kb_team_leave_confirm() -> InlineKeyboardMarkup:
    """Jamoadan chiqishni tasdiqlash."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Ha, chiqaman", callback_data="team:leaveconfirm"
                ),
                InlineKeyboardButton(
                    "⬅️ Yo'q", callback_data="team:leavecancel"
                ),
            ]
        ]
    )


def kb_team_admin_register() -> InlineKeyboardMarkup:
    """Admin bo'lish oynasi uchun bekor tugmasi."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Bekor qilish", callback_data="team:back")]]
    )


# ─────────────────────────────────────────────────────────────────────────
# GURUHLARNI TOPISH — QO'LDA BELGILASH
# ─────────────────────────────────────────────────────────────────────────
def kb_discover_groups(
    groups: list,
    selected: set[str],
    page: int = 0,
    page_size: int = 15,
    total: int = 0,
    pages: int = 1,
) -> InlineKeyboardMarkup:
    """Topilgan guruhlar ro'yxati — ✅ belgilash va sahifalash.

    ``callback_data`` hajmi cheklangan (64 bayt) — shuning uchun guruh
    o'rniga **sessiya indeksi** ishlatiladi.
    """
    rows: list[list[InlineKeyboardButton]] = []
    offset = page * page_size
    for index, group in enumerate(groups):
        abs_index = offset + index
        key = getattr(group, "key", "") or ""
        is_on = key in selected
        icon = "✅" if is_on else "⬜"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{icon} {group.display()}",
                    callback_data=f"disc:toggle:{abs_index}",
                )
            ]
        )

    # Navigatsiya
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"disc:page:{page - 1}"))
    nav.append(
        InlineKeyboardButton(f"📄 {page + 1}/{pages}", callback_data="disc:noop")
    )
    if page + 1 < pages:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"disc:page:{page + 1}"))
    if nav:
        rows.append(nav)

    # Har sahifada «tanlanganlarni ko'rish» — tanlangan boshqa sahifada bo'lsa.
    count = len(selected)
    if count:
        rows.append(
            [
                InlineKeyboardButton(
                    f"💾 Tanlanganlarni saqlash ({count})",
                    callback_data="disc:apply",
                )
            ]
        )
    # ⚠️ «Bekor qilish» tanlanishni butunlay tozalaydi. Shuuning uchun
    # undan oldin «⬅️ Guruhlar» — tanlanishni saqlab, foydalanuvchining
    # «💬 Guruhlar» oynasiga qaytish imkonini beradi.
    rows.append(
        [
            InlineKeyboardButton("⬅️ Guruhlar", callback_data="disc:groups"),
            InlineKeyboardButton("🚫 Bekor qilish", callback_data="disc:cancel"),
        ]
    )
    return InlineKeyboardMarkup(rows)
