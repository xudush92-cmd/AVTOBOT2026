"""
Barcha matnlar — o'zbek tilida.

Bu fayl orqali botdagi har bir xabar matnini bir joydan boshqarish mumkin.
"""

from __future__ import annotations

from config.config import (
    ADMIN_CONTACT_PHONE,
    DEFAULT_DURATION_DAYS,
    DEFAULT_INTERVAL_MIN,
    MAX_ALBUM_FILES,
    MAX_INTERVAL_MIN,
    MIN_INTERVAL_MIN,
    PAY_BANK,
    PAY_CARD,
    PAY_HOLDER,
    PAYMENT_DAYS,
    PAYMENT_REQUEST_TTL_MIN,
    PLAN_DEFS,
    PLAN_PRICES,
    REFERRAL_BONUS_DAYS,
)
from core.utils import format_expires

# ─────────────────────────────────────────────────────────────────────────
# UMUMIY
# ─────────────────────────────────────────────────────────────────────────
WELCOME_SHORT = (
    "🤖 AVTOBOT\n\n"
    "Telegram guruhlaringizga reklama postlarini avtomatik joylashtiruvchi bot.\n\n"
    "📌 Boshlash (🔑 Login yoki /start):\n"
    "1. Ism va familiyangizni bitta xabarda kiriting\n"
    "2. Telefon raqamingizni kiriting — Telegram kodi darhol so'raladi\n"
    "3. Kodni faqat botdagi RAQAMLI TUGMALAR orqali kiriting (matn qabul "
    "qilinmaydi); kerak bo'lsa 📷 QR Login yoki 2FA ishlatiladi\n"
    "4. Login tugagach so'rov admin tasdig'iga tushadi\n"
    "5. Admin tasdiqlagach sessiya avtomatik faollashadi — kodni qayta "
    "kiritish shart emas\n\n"
    f"📱 Yordam: {ADMIN_CONTACT_PHONE}"
)

ADMIN_CONTACT_LINE = f"📱 Admin: {ADMIN_CONTACT_PHONE}"


# ─────────────────────────────────────────────────────────────────────────
# BLOK
# ─────────────────────────────────────────────────────────────────────────
BLOCKED = f"🚫 Bot to'xtatildi.\n\nAdmin bilan bog'laning: {ADMIN_CONTACT_PHONE}"


# ─────────────────────────────────────────────────────────────────────────
# LOGIN — ISM VA FAMILIYA
# ─────────────────────────────────────────────────────────────────────────
ASK_FULL_NAME = (
    "📋 RO'YXATDAN O'TISH (1/2)\n\n"
    "👤 Ism va familiyangizni bitta xabarda kiriting:\n\n"
    "Masalan: Akmal Karimov\n\n"
    "➡️ Keyingi qadam: telefon raqami va Telegram tasdiq kodi."
)

FULL_NAME_INVALID = (
    "❌ Ism va familiyani to'liq, faqat harflar bilan kiriting.\n\n"
    "Masalan: Akmal Karimov"
)

FULL_NAME_ACCEPTED = (
    "✅ {full_name}\n\n"
    "📋 RO'YXATDAN O'TISH (2/2)\n\n"
    "📱 Telegram telefon raqamingizni yuboring:\n\n"
    "Format: +998XXXXXXXXX"
)

# Telefon qabul qilingach kod darhol so'raladi; admin tasdig'i keyin keladi.
REGISTRATION_CODE_REQUEST = (
    "✅ {phone} qabul qilindi.\n\n"
    "🔑 Endi Telegram tasdiq kodi darhol so'raladi. Kodni botdagi "
    "RAQAMLI TUGMALAR orqali kiriting — matn ko'rinishidagi kod qabul "
    "qilinmaydi.\n\n"
    "⏳ Login tugagach so'rovingiz admin tasdig'iga tushadi. Tasdiqdan keyin "
    "kodni QAYTA kiritish shart emas."
)


# ─────────────────────────────────────────────────────────────────────────
# LOGIN — TELEFON
# ─────────────────────────────────────────────────────────────────────────
PHONE_INVALID = (
    "❌ Telefon raqam noto'g'ri.\n\n"
    "Format: +998XXXXXXXXX\n"
    "Faqat raqamlar, + belgisi bilan boshlanadi."
)

PHONE_ACCEPTED = (
    "📱 {phone} raqami uchun kod so'ralmoqda...\n\n"
    "ℹ️ Telethon login kodi odatda SMSga emas, Telegram ilovasidagi "
    'rasmiy "Telegram" (777000) chatiga keladi.'
)

PHONE_ALREADY_USED = (
    "❌ Bu telefon boshqa AVTOBOT foydalanuvchisiga biriktirilgan.\n\n"
    f"Xato bo'lsa admin bilan bog'laning: {ADMIN_CONTACT_PHONE}"
)


# ─────────────────────────────────────────────────────────────────────────
# LOGIN — TELEGRAM TASDIQ KODI
# ─────────────────────────────────────────────────────────────────────────
def numpad_text(buffer: str, hint: str = "", code_length: int = 5) -> str:
    """Telegram tasdiq kodini kiritish oynasi matni."""
    total = max(5, code_length, len(buffer))
    display = " ".join("●" if i < len(buffer) else "▪" for i in range(total))
    text = (
        "🔑 TASDIQ KODI\n\n"
        "📩 Telegramdan kelgan kodni quyidagi tugmalar orqali kiriting.\n\n"
        f"🔢 Kod:  {display}\n"
    )
    if hint:
        text += f"\n{hint}\n"
    text += (
        "\n💡 Kodni matn sifatida YOZMANG — Telegram xavfsizlik "
        "tizimi bunday kodni bekor qiladi. Faqat tugmalar orqali kiriting."
    )
    return text


def code_hint_sent(destination: str) -> str:
    """Telegram qaytargan haqiqiy yetkazish usulini ko'rsatadi."""
    return (
        "✅ Telegram kod so'rovini qabul qildi.\n"
        f"📍 Yetkazish usuli: {destination}\n\n"
        "Kod 1 daqiqada kelmasa, pastdagi 📷 QR Login tugmasini bosing."
    )


CODE_HINT_WRONG = "❌ Noto'g'ri kod ({count}/{max}). Qaytadan kiriting:"

CODE_HINT_RESENT = (
    "⏰ Yangi kod yuborildi!\nTelegram ilovasidan ENG SO'NGGI kodni oling."
)

CODE_TOO_SHORT = "Kamida 5 ta raqam kiriting!"

CODE_TOO_LONG = "Maksimal 6 ta raqam!"

CODE_MAX_WRONG = (
    "❌ {count} marta noto'g'ri kod kiritildi.\n\n"
    "Qaytadan 🔑 Login bosing.\n\n"
    f"📱 Yordam: {ADMIN_CONTACT_PHONE}"
)

CODE_EXPIRED = "⏰ Kod muddati tugadi.\n\nYangi kod so'ralmoqda..."

CODE_NOT_MATN = (
    "⚠️ Iltimos, kodni MATN sifatida yozmang!\n\n"
    "Telegram xavfsizlik tizimi matnli kodni darhol bekor qiladi.\n"
    "Faqat pastdagi RAQAMLI TUGMALAR orqali kiriting."
)

CODE_CANCELLED = "❌ Login bekor qilindi."

CODE_TIMEOUT = "⏰ Login vaqti tugadi.\n\nQaytadan 🔑 Login bosing."


# ─────────────────────────────────────────────────────────────────────────
# SMS QAYTA SO'RASH LIMITI
# ─────────────────────────────────────────────────────────────────────────
SMS_LIMIT_REACHED = (
    "⚠️ Tasdiq kodini {attempts} marta so'radingiz.\n\n"
    "Iltimos, {minutes} daqiqa kuting va qaytadan urinib ko'ring.\n\n"
    f"📱 Yordam: {ADMIN_CONTACT_PHONE}"
)


# ─────────────────────────────────────────────────────────────────────────
# LOGIN — QR (AWS/VPS UCHUN FALLBACK)
# ─────────────────────────────────────────────────────────────────────────
QR_PREPARING = "⏳ Xavfsiz QR Login tayyorlanmoqda..."

QR_CAPTION = (
    "📷 TELEGRAM QR LOGIN\n\n"
    "1. Pastdagi «Telegramda tasdiqlash» tugmasini bosing; yoki\n"
    "2. QR rasmni boshqa ekranda ochib, Telegram → Settings → Devices → "
    "Link Desktop Device orqali skaner qiling.\n\n"
    "⚠️ Tasdiqlasangiz, AVTOBOT guruhlarga sizning akkauntingiz nomidan "
    "post yuborishi uchun Telegram sessiyasi yaratiladi.\n\n"
    "⏱ QR qisqa vaqt amal qiladi."
)

QR_WAITING = (
    "📷 QR tasdiqlanishi kutilmoqda.\n\n"
    "Rasmdagi tugmani bosing yoki QR kodni Telegram Devices bo'limidan "
    "skaner qiling."
)

QR_EXPIRED = (
    "⏰ QR kod muddati tugadi.\n\nQaytadan 🔑 Login bosing va yangi QR yarating."
)

QR_WRONG_ACCOUNT = (
    "❌ Boshqa Telegram akkaunti tasdiqlandi.\n\n"
    "Bot bilan gaplashayotgan aynan shu akkaunt orqali QR Login qiling."
)

QR_ERROR = (
    "❌ QR Login yakunlanmadi.\n\n"
    "Qaytadan 🔑 Login bosing yoki birozdan keyin urinib ko'ring."
)

API_CREDENTIALS_INVALID = (
    "❌ API_ID yoki API_HASH noto'g'ri.\n\n"
    "Bu qiymatlar BotFather'dan emas, https://my.telegram.org → "
    "API development tools bo'limidan olinishi kerak."
)

CODE_UNAVAILABLE = (
    "❌ Telegram hozir tasdiq kodini bera olmadi.\n\n"
    "Ko'p urinish bo'lgan bo'lsa bir necha soat kuting. AWS/VPS IP manzili "
    "cheklangan bo'lsa, QR Login usulidan foydalaning."
)


# ─────────────────────────────────────────────────────────────────────────
# LOGIN — 2FA PAROL
# ─────────────────────────────────────────────────────────────────────────
ASK_PASSWORD = (
    "🔐 Hisobingizda 2FA (ikki bosqichli himoya) yoqilgan.\n\n"
    "Iltimos, 2FA parolingizni MATN ko'rinishida yuboring.\n\n"
    "✅ Parol DISK-ga saqlanmaydi."
)

PASSWORD_WRONG = "❌ Noto'g'ri parol. Qaytadan kiriting:"


# ─────────────────────────────────────────────────────────────────────────
# LOGIN YAKUNLANGANDA
# ─────────────────────────────────────────────────────────────────────────
REGISTRATION_PENDING = (
    "✅ Ro'yxatdan o'tish so'rovingiz qabul qilindi!\n\n"
    "⏳ Login yakunlandi va sessiya xavfsiz saqlandi. Endi admin tasdig'i "
    "kutilmoqda — kodni qayta kiritish shart emas.\n\n"
    f"📞 Tezroq tasdiqlanish uchun: {ADMIN_CONTACT_PHONE}"
)

LOGIN_SUCCESS_PENDING = (
    "✅ Login muvaffaqiyatli!\n\n"
    "🔐 Sessiya xavfsiz (shifrlangan) holatda saqlandi.\n"
    "⏳ Endi so'rovingiz admin tasdiqini kutmoqda.\n\n"
    "ℹ️ Admin tasdiqlagach sessiya avtomatik faollashadi — qayta Login "
    "bosish yoki kod kiritish shart emas.\n\n"
    f"📞 Tezroq tasdiqlanish uchun: {ADMIN_CONTACT_PHONE}"
)

# Admin tasdiqlagan sessiya boshqa akkauntga tegishli chiqsa.
PENDING_SESSION_MISMATCH = (
    "⚠️ Xavfsizlik tekshiruvi: so'ralgan sessiya boshqa Telegram akkauntiga "
    "tegishli bo'lgani uchun u bekor qilindi.\n\n"
    "🔑 Iltimos, qaytadan Login qiling va kodni botdagi raqamli tugmalar "
    "orqali kiriting.\n\n"
    f"📱 Yordam: {ADMIN_CONTACT_PHONE}"
)

LOGIN_SUCCESS_APPROVED = (
    "✅ Tizimga muvaffaqiyatli kirdingiz!\n\n"
    "Endi guruh va post qo'shib, ▶️ Start bosishingiz mumkin."
)

LOGIN_ALREADY_PENDING = (
    f"⏳ So'rovingiz admin tasdiqini kutmoqda.\n\n📱 Admin: {ADMIN_CONTACT_PHONE}"
)

LOGIN_NOT_APPROVED = (
    "⛔ Siz hali tasdiqlanmagansiz.\n\n"
    f"📱 Admin bilan bog'laning: {ADMIN_CONTACT_PHONE}"
)


# ─────────────────────────────────────────────────────────────────────────
# ADMINGA XABAR (yangi user)
# ─────────────────────────────────────────────────────────────────────────
def new_user_notification(name: str, phone: str, username: str, uid: int) -> str:
    """Adminga yangi foydalanuvchi haqida xabar.

    Login allaqachon tugagan: sessiya ``pending_session`` sifatida saqlangan,
    shuning uchun tasdiqdan keyin foydalanuvchi kodni qayta kiritmaydi.
    """
    user_line = f"@{username}" if username else "username yo'q"
    return (
        "🔔 Yangi foydalanuvchi ro'yxatdan o'tdi\n\n"
        f"👤 Ism: {name}\n"
        f"📱 Telefon: {phone}\n"
        f"📎 {user_line}\n"
        f"🆔 ID: {uid}\n\n"
        "🔐 Telegram logini yakunlangan — sessiya shifrlangan pending "
        "holatda tayyor.\n"
        f"📅 Tarif: {DEFAULT_DURATION_DAYS} kun\n"
        f"⏱ Posting oralig'i: {DEFAULT_INTERVAL_MIN} daqiqa\n"
        "✅ Tasdiqlagach kodni qayta kiritish shart emas."
    )


def approval_result_text(uid: int, *, session_activated: bool) -> str:
    """Admin tasdiqlash natijasini aniq ko'rsatadi (tarif va interval bilan)."""
    lines = [
        f"✅ {uid} tasdiqlandi.",
        "",
        f"📅 Tarif: {DEFAULT_DURATION_DAYS} kun",
        f"⏱ Posting oralig'i: {DEFAULT_INTERVAL_MIN} daqiqa",
    ]
    if session_activated:
        lines.append("🔐 Pending sessiya faollashtirildi — kod qayta so'ralmaydi.")
    else:
        lines.append(
            "🔑 Sessiya yo'q: foydalanuvchi bir marta 🔑 Login bosib kodni "
            "kiritishi kerak."
        )
    return "\n".join(lines)


# Tasdiqlashdan keyin ko'rsatiladigan qisqa yo'riqnoma — yangi odam menyuni
# o'zi izlab topmasligi uchun (to'liq matn: /help).
APPROVAL_FIRST_STEPS = (
    "\n\n👇 Keyingi 3 qadam:\n"
    "1️⃣ 💬 Guruhlar → ➕ Guruh qo'shish (har biri yangi qatorda)\n"
    "2️⃣ 📝 Postlar → ➕ Post qo'shish (bir nechta rasm = bitta albom)\n"
    "3️⃣ ▶️ Start — va 🔎 Tekshirish bilan guruhlar tayyorligini tekshiring\n\n"
    "💡 To'liq yo'riqnoma: /help"
)

USER_APPROVED = (
    "✅ Hisobingiz tasdiqlandi!\n\n"
    f"📅 Tarif: {DEFAULT_DURATION_DAYS} kun\n"
    f"⏱ Posting oralig'i: {DEFAULT_INTERVAL_MIN} daqiqa\n\n"
    "🔑 Endi bir marta Login bosing va kodni botdagi raqamli tugmalar orqali "
    "kiriting." + APPROVAL_FIRST_STEPS
)

# Pending sessiya aynan o'sha UID uchun tekshirilib faollashtirilganda yuboriladi.
USER_APPROVED_ACTIVE = (
    "✅ Hisobingiz tasdiqlandi va sessiya faollashtirildi!\n\n"
    f"📅 Tarif: {DEFAULT_DURATION_DAYS} kun\n"
    f"⏱ Posting oralig'i: {DEFAULT_INTERVAL_MIN} daqiqa\n\n"
    "ℹ️ Kodni qayta kiritish shart emas — botdan foydalanishingiz mumkin."
    + APPROVAL_FIRST_STEPS
)

USER_REJECTED = (
    f"❌ So'rovingiz rad etildi.\n\n📞 Savollar uchun: {ADMIN_CONTACT_PHONE}"
)


# ─────────────────────────────────────────────────────────────────────────
# SUPER ADMIN — FOYDALANUVCHI QO'SHISH
# ─────────────────────────────────────────────────────────────────────────
ADMIN_ADD_USER_FULL_NAME = (
    "➕ FOYDALANUVCHI QO'SHISH (1/2)\n\n"
    "👤 Foydalanuvchining ism va familiyasini bitta xabarda kiriting:\n\n"
    "Masalan: Ali Valiyev"
)

ADMIN_ADD_USER_FULL_NAME_INVALID = (
    "❌ Ism va familiyani to'liq, bitta xabarda kiriting.\n\nMasalan: Ali Valiyev"
)

ADMIN_ADD_USER_PHONE = (
    "➕ FOYDALANUVCHI QO'SHISH (2/2)\n\n"
    "📱 Foydalanuvchining Telegram telefon raqamini kiriting:\n\n"
    "Format: +998XXXXXXXXX"
)

ADMIN_ADD_USER_CANCELLED = "❌ Foydalanuvchi qo'shish bekor qilindi."


# ─────────────────────────────────────────────────────────────────────────
# RATE LIMIT
# ─────────────────────────────────────────────────────────────────────────
def rate_limit_text(minutes: int) -> str:
    return (
        f"⏳ Juda ko'p so'rov yubordingiz.\n\n"
        f"{minutes} daqiqa kuting va qaytadan urinib ko'ring."
    )


# Telefon bo'yicha kod so'rovi limiti (3 ta / soat).
PHONE_CODE_LIMIT_REACHED = (
    "⏳ Bu telefon raqami uchun kod so'rovlari limiti tugadi.\n\n"
    "{minutes} daqiqadan keyin qaytadan 🔑 Login bosing."
)


# ─────────────────────────────────────────────────────────────────────────
# MENYU TUGMALARI
# ─────────────────────────────────────────────────────────────────────────
BTN_START = "▶️ Start"
BTN_STOP = "⛔ Stop"
BTN_STATUS = "📊 Status"
BTN_GROUPS = "💬 Guruhlar"
BTN_POSTS = "📝 Postlar"
BTN_ADD_GROUP = "➕ Guruh qo'shish"
BTN_DEL_GROUP = "➖ Guruh o'chirish"
BTN_GROUP_INTERVAL = "⏱ Guruh intervali"
BTN_CHECK_GROUPS = "🔎 Guruhni tekshirish"
BTN_EDIT_POST = "✏️ Postni tahrirlash"
BTN_PREVIEW_POST = "👁 Ko'rinishi"
BTN_TEST_SEND = "🧪 Sinov yuborish"
BTN_ADD_POST = "➕ Post qo'shish"
BTN_DEL_POST = "🗑 Post o'chirish"
BTN_TIMER = "⏱ Posting oralig'i"
BTN_REFERRAL = "👥 Referal"
BTN_REPORT = "📈 Hisobot"
BTN_PLAN = "💳 Obuna"
BTN_ACCOUNT = "⚙️ Hisob"
BTN_BACK = "⬅️ Orqaga"
BTN_ADMIN_ADD_CANCEL = "❌ Sessiya yaratishni to'xtatish"
BTN_ADMIN = "🖥 Super Admin"
BTN_LOGIN = "🔑 Login"
BTN_PENDING = "⏳ Tasdiq kutilmoqda..."
BTN_BLOCKED = "🚫 Bloklangan"


# ─────────────────────────────────────────────────────────────────────────
# START / STOP
# ─────────────────────────────────────────────────────────────────────────
START_CONFIRM = (
    "▶️ Postingni boshlaymizmi?\n\n"
    "💬 {groups} ta guruhga\n"
    "📝 {posts} ta postdan navbatma-navbat\n"
    "⏰ Umumiy interval: taxminan {interval} daqiqa.\n"
    "Alohida sozlangan guruhlar o'z intervalida ishlaydi.\n"
    "ℹ️ Anti-spam uchun 5 daqiqagacha tasodifiy farq bo'lishi mumkin."
)

START_NO_GROUPS = "❌ Avval ➕ Guruh qo'shing."

START_NO_POSTS = "❌ Avval 📝 Post qo'shing."

START_ALREADY = "⚠️ Allaqachon ishlamoqda."

START_DONE = (
    "✅ Posting boshlandi!\n\n"
    "💬 {groups} ta guruh\n"
    "📝 {posts} ta post\n"
    "⏰ Umumiy interval: taxminan {interval} daqiqa\n"
    "Alohida sozlangan guruhlar o'z intervalida ishlaydi.\n"
    "ℹ️ Anti-spam farqi: 5 daqiqagacha"
)

START_BUSY = "⚠️ Tizim band. Bir oz kuting va qaytadan urinib ko'ring."

START_SESSION_INVALID = (
    "🚫 Telegram sessiyasini tasdiqlab bo'lmadi (bekor qilingan yoki boshqa "
    "akkaunt). Sessiya saqlandi; Hisob bo'limidan tekshiring yoki admin bilan "
    "bog'laning."
)

START_SESSION_RETRY = (
    "⏳ Telegram vaqtincha javob bermadi yoki FloodWait berdi. Sessiya saqlandi; "
    "keyinroq Start'ni qayta bosing."
)

STOP_CONFIRM = "⛔ Postingni to'xtatasizmi?"

STOP_NOT_RUNNING = "⚠️ Hozir ishlamayapti."

STOP_DONE = "⛔ Posting to'xtatildi."

ACTION_CANCELLED = "❌ Bekor qilindi."

ACTION_YES = "✅ Ha"
ACTION_NO = "❌ Yo'q"
ACTION_OK = "✅ Tasdiqlash"
ACTION_CANCEL = "❌ Bekor qilish"


# ─────────────────────────────────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────────────────────────────────
def status_text(
    running: bool,
    expired: bool,
    groups: int,
    posts: int,
    interval: int,
    expires: str,
    *,
    today_ok: int | None = None,
    today_failed: int | None = None,
    next_eta: str = "",
    last_error: str = "",
    max_groups: int = 0,
    max_posts: int = 0,
    daily_left: str = "",
    active_hours: str = "",
    plan_label: str = "",
) -> str:
    """📊 Status ekrani.

    Yangi qatorlar (bugungi yuborishlar, keyingi navbat, limitlar) ixtiyoriy:
    chaqiruvchi ularni bilsa ko'rsatiladi — shu sabab eski chaqiruvlar ham
    xato bermaydi.
    """
    if expired:
        state = "⏸ Kutish rejimi (muddat tugagan)"
    elif running:
        state = "🟢 Ishlamoqda"
    else:
        state = "🔴 To'xtatilgan"

    lines = [
        "📊 STATUS\n",
        f"Holat: {state}",
        "Sessiya: ✅ Faol",
        f"📅 Muddat: {expires}",
    ]
    if plan_label:
        lines.append(f"📦 Paket: {plan_label}")
    lines.append("")
    lines.append(
        f"💬 Guruhlar: {groups}" + (f"/{max_groups}" if max_groups else "")
    )
    lines.append(f"📝 Postlar: {posts}" + (f"/{max_posts}" if max_posts else ""))
    lines.append(f"⏱ Umumiy posting oralig'i: taxminan {interval} daqiqa")

    if today_ok is not None or today_failed is not None:
        lines.append("")
        lines.append(
            f"📤 Bugun yuborildi: ✅ {today_ok or 0} ta · ❌ {today_failed or 0} ta"
        )
    if next_eta:
        lines.append(f"⏭ Keyingi yuborish: {next_eta}")
    if last_error:
        lines.append(f"⚠️ Oxirgi xato: {last_error}")
    if daily_left:
        lines.append(f"🧮 Kunlik limit qoldig'i: {daily_left}")
    if active_hours:
        lines.append(f"🕒 Ish vaqti: {active_hours}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# GURUHLAR
# ─────────────────────────────────────────────────────────────────────────
GROUPS_EMPTY = "❌ Guruhlar yo'q. ➕ Guruh qo'shish orqali qo'shing."
GROUP_INTERVALS_EMPTY = "❌ Guruhlar yo'q. Avval guruh qo'shing."
GROUP_INTERVAL_PICK = (
    "⏱ Intervalini sozlash uchun guruhni tanlang.\n"
    "Umumiy intervalni o'zgartirish uchun «Posting oralig'i» menyusidan foydalaning."
)


def groups_list(groups: list[str]) -> str:
    lines = [f"💬 GURUHLAR ({len(groups)} ta):\n"]
    for i, g in enumerate(groups, 1):
        lines.append(f"{i}. {g}")
    return "\n".join(lines)


ASK_ADD_GROUP = (
    "➕ GURUH QO'SHISH\n\n"
    "Bir yoki bir nechta guruhni yuboring — har biri YANGI QATORDA.\n"
    "Qo'shishda faqat havola/ID formati tekshiriladi, Telegram'ga ulanilmaydi. "
    "Post yuborish uchun akkaunt guruhga a'zo va yozish huquqiga ega bo'lishi "
    "kerak; bot avtomatik kirmaydi.\n\n"
    "Qabul qilinadi:\n"
    "@guruh_username\n"
    "https://t.me/guruh_username\n"
    "https://t.me/guruh_username/123\n"
    "https://t.me/+private_invite\n"
    "https://t.me/c/1234567890/123\n"
    "-1001234567890"
)


def groups_added_report(
    added: list[str], duplicates: list[str], errors: list[str]
) -> str:
    lines = ["📊 NATIJA\n"]
    for g in added:
        lines.append(f"✅ {g}")
    for g in duplicates:
        lines.append(f"⚠️ {g} — allaqachon mavjud")
    for g in errors:
        lines.append(f"❌ {g}")
    lines.append("")
    lines.append(f"✅ Qo'shildi: {len(added)} ta")
    if duplicates:
        lines.append(f"⚠️ Takror: {len(duplicates)} ta")
    if errors:
        lines.append(f"❌ Xatolik: {len(errors)} ta")
    return "\n".join(lines)


ASK_DEL_GROUP = "➖ O'chirish uchun guruhni tanlang:"

GROUPS_CLEARED = "🧹 Barcha guruhlar o'chirildi."


# ─────────────────────────────────────────────────────────────────────────
# POSTLAR
# ─────────────────────────────────────────────────────────────────────────
POSTS_EMPTY = "❌ Postlar yo'q. 📝 Post qo'shish orqali qo'shing."

POSTS_LIMIT = "❌ Maksimal {max_posts} ta post (sizning tarifingiz)."

ASK_ADD_POST = (
    "✍️ REKLAMA POSTINI YUBORING\n\n"
    "1️⃣ Faqat matn (formatlash bilan — bold, italic, link saqlanadi)\n"
    "2️⃣ Bitta rasm / video / fayl (caption bilan yoki sansiz)\n"
    f"3️⃣ {MAX_ALBUM_FILES} TAGACHA RASMNI ALBOM QILIB YUBORING\n\n"
    "💡 Ko'p suratli e'lon: rasmlarni birga (album) tanlab, matnni caption\n"
    "   qilib yozing yoki rasmdan keyin alohida xabar qiling.\n"
    "   Yakunlash uchun ✅ «Tayyor» tugmasi yoki biroz kutish kifoya.\n\n"
    "🔤 Ixtiyoriy shablonlar (har yuborishda yangilanadi):\n"
    "   {sana} → 12.10.2026 · {vaqt} → 14:05 · {kun} → Shanba\n"
    "   {Yangi|Ajoyib|Darhol} → tasodifiy variant (spam-ga o'xshamasligi uchun)"
)

POST_ADDED = "✅ Saqlandi (#{n})\n{kind}\n\n{preview}"

POST_KIND_TEXT = "📝 Matn"
POST_KIND_PHOTO = "🖼 Rasm + matn"
POST_KIND_PHOTO_ONLY = "🖼 Faqat rasm"

POST_EMPTY_ERROR = "❌ Bo'sh post qabul qilinmaydi.\nMatn yoki rasm yuboring."

POST_PHOTO_ERROR = "❌ Rasmni saqlab bo'lmadi. Qaytadan urinib ko'ring."

ASK_DEL_POST = "🗑 O'chirish uchun postni tanlang:"

POST_DELETED = "🗑 O'chirildi:\n{preview}"

POST_NOT_FOUND = "❌ Post topilmadi."


# ─────────────────────────────────────────────────────────────────────────
# VAQT (INTERVAL)
# ─────────────────────────────────────────────────────────────────────────
def ask_interval(current: int) -> str:
    return (
        f"⏱ UMUMIY POSTING ORALIG'I\n\n"
        f"Hozirgi umumiy oraliq: taxminan {current} daqiqa\n"
        f"Alohida interval berilmagan guruhlarda shu qiymat ishlaydi.\n\n"
        f"Yangi qiymatni kiriting (daqiqada):\n"
        f"{MIN_INTERVAL_MIN}–{MAX_INTERVAL_MIN} daqiqa. Anti-spam uchun real vaqt "
        f"5 daqiqagacha farq qilishi mumkin."
    )


def interval_invalid_min() -> str:
    return f"❌ {MIN_INTERVAL_MIN} dan {MAX_INTERVAL_MIN} gacha daqiqa kiriting."


INTERVAL_INVALID_NUMBER = "❌ Faqat butun son kiriting. Qaytadan:"


def interval_set(minutes: int) -> str:
    return (
        f"✅ Umumiy posting oralig'i {minutes} daqiqaga o'rnatildi.\n"
        "Alohida sozlangan guruhlar o'z intervalini saqlaydi.\n"
        "ℹ️ Anti-spam uchun real vaqt 5 daqiqagacha farq qilishi mumkin."
    )


# ─────────────────────────────────────────────────────────────────────────
# REFERAL
# ─────────────────────────────────────────────────────────────────────────
def referral_text(
    link: str,
    total: int,
    refs: list[dict],
    *,
    bonus_days: int = 0,
    min_sends: int = 1,
    granted_days: int = 0,
    today: int = 0,
) -> str:
    """👥 Referal sahifasi — havola, qoidalar va ro'yxat."""
    lines = [
        "👥 SIZNING REFERALLARINGIZ\n",
        "🔗 Taklif havolangiz:",
        link,
        "",
        f"✅ Faol referallar: {total} ta",
    ]
    if bonus_days > 0:
        lines.append(
            f"🎁 Har bir faol referalga: +{bonus_days} kun tarif\n"
            f"    (hozircha jami +{granted_days} kun olgansiz)"
        )
        lines.append(
            f"    Shart: do'stingiz tasdiqlanishi, kamida 1 ta guruh va\n"
            f"    1 ta post qo'shib, {min_sends} marta muvaffaqiyatli yuborishi kerak."
        )
    if today:
        lines.append(f"📅 Bugun qo'shilganlar: {today} ta")
    if refs:
        lines.append("")
        lines.append("📋 Ro'yxat:")
        for i, r in enumerate(refs, 1):
            if r.get("revoked"):
                mark = "↩️ bekor qilindi"
            elif r.get("qualified"):
                mark = f"🎁 +{r.get('bonus_days') or 0} kun"
            elif r.get("counted"):
                mark = "⏳ faollik kutilmoqda"
            else:
                mark = "⏳ admin tasdig'i kutilmoqda"
            lines.append(f"{i}. {r['name']} — {mark}")
        if bonus_days > 0:
            lines.append("")
            lines.append(
                "⏳ = do'stingiz hali post yubora boshlamagan. U ishlay\n"
                "    boshlagach bonus sizga avtomatik keladi."
            )
    else:
        lines.append("")
        lines.append("Hozircha referal yo'q. Havolani do'stlaringizga ulashing!")
    return "\n".join(lines)


def referral_share_text(link: str) -> str:
    """Do'stlarga yuboriladigan tayyor matn."""
    return (
        "Men Telegram guruhlarga e'lonlarimni avtomatik joylash uchun "
        "AVTOBOT ishlataman 👇\n\n"
        "• bir nechta guruhga bir vaqtda\n"
        "• bir nechta rasm (albom) bilan\n"
        "• har bir guruhga o'z oralig'ini qo'yish mumkin\n"
        "• qachon va nechta e'lon chiqqanini ko'rsatib turadi\n\n"
        f"🔗 Bepul boshlash: {link}"
    )


def referral_counted_text(
    name: str, total: int, bonus_days: int, min_sends: int
) -> str:
    base = (
        "🎉 Sizning referalingiz faollashdi!\n\n"
        f"👤 {name} ro'yxatdan o'tib, tasdiqlandi.\n"
        f"👥 Jami faol referallaringiz: {total} ta"
    )
    if bonus_days > 0:
        base += (
            f"\n\n🎁 Bonus {bonus_days} kun uchun shart: u kamida 1 ta guruh va\n"
            f"1 ta post bilan {min_sends} marta e'lon yuborishi kerak.\n"
            "Shart bajarilgach kunlar avtomatik qo'shiladi."
        )
    return base


def referral_bonus_granted(name: str, days: int, total: int, expires: str) -> str:
    return (
        "🎁 REFERAL BONUSI berildi!\n\n"
        f"👤 {name} birinchi e'lonlarini yubora boshladi.\n"
        f"➕ Tarifingizga +{days} kun qo'shildi.\n"
        f"📅 Endi muddat: {expires}\n"
        f"👥 Jami faol referallaringiz: {total} ta"
    )


def referral_bonus_zero(name: str, total: int) -> str:
    return (
        "🎉 Referalingiz ishlay boshladi!\n\n"
        f"👤 {name}\n"
        f"👥 Jami faol referallaringiz: {total} ta\n\n"
        "ℹ️ Bonus kun qo'shilmadi: sizning tarifingiz cheksiz yoki\n"
        "oylik bonus chegarasiga yetgan bo'lsangiz."
    )


def referral_revoked_note(name: str, days: int, reason: str) -> str:
    text = (
        "⚠️ Referal hisobi bekor qilindi\n\n"
        f"👤 {name} hisob-faydasiz yoki qoidabuzar deb topildi.\n"
    )
    if days > 0:
        text += f"↩️ Olingan +{days} kun bonus tarifdan qaytarib olindi.\n"
    if reason:
        text += f"\nSabab: {reason}"
    return text


# ─────────────────────────────────────────────────────────────────────────
# MUDDAT
# ─────────────────────────────────────────────────────────────────────────
LAST_DAY_WARNING = (
    "⚠️ DIQQAT!\n\n"
    "Bugun tarifingizning oxirgi kuni.\n\n"
    "Ertaga posting avtomatik to'xtaydi.\n\n"
    f"📱 Davom ettirish uchun: {ADMIN_CONTACT_PHONE}"
)

EXPIRED_TEXT = (
    "⏸ KUTISH REJIMI\n\n"
    "Muddatingiz tugadi. Posting to'xtatildi.\n\n"
    f"📱 Davom ettirish uchun: {ADMIN_CONTACT_PHONE}"
)


def new_term_admin_text(days: int, new_expires: str, previous: str | None) -> str:
    """Admin yangi muddat berganda natija xabari.

    Yangi muddat hozirdan boshlab hisoblanadi va oldingi muddatni BEKOR
    qiladi (ustiga qo'shilmaydi); shuning uchun bekor qilingan muddat
    ham ko'rsatiladi.
    """
    return (
        f"✅ Yangi muddat berildi: {days} kun\n"
        f"📅 Tugash sanasi: {new_expires[:10]}\n"
        f"♻️ Oldingi muddat bekor qilindi: {format_expires(previous)}\n\n"
        "Yangi muddat hozirdan boshlab hisoblanadi — oldingi muddat "
        "ustiga qo'shilmaydi."
    )


def new_term_user_text(new_expires: str) -> str:
    """Userga yangi tarif muddati haqida xabar."""
    return f"✅ Tarifingiz yangilandi!\n\n📅 Yangi muddat: {new_expires[:10]}"


# ─────────────────────────────────────────────────────────────────────────
# XATOLAR
# ─────────────────────────────────────────────────────────────────────────
GENERIC_ERROR = "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring."

SESSION_INVALID = (
    "🚫 Sessiyangiz Telegram tomonidan bekor qilindi.\n\nQaytadan 🔑 Login qiling."
)

SESSION_EXPIRED_SEND = "🚫 Sessiyangiz bekor qilindi. Qaytadan 🔑 Login qiling."

FLOOD_WAIT = "⏳ Telegram vaqtincha chekladi. {minutes} daqiqa kutish kerak."

GROUP_AUTO_REMOVED = (
    "⚠️ Diqqat!\n\n"
    "Quyidagi guruhga {count} marta xabar yuborib bo'lmadi:\n\n"
    "📛 {group}\n\n"
    "Sabab: bot o'sha guruhdan chiqarilgan, yozish taqiqlangan "
    "yoki guruh mavjud emas.\n\n"
    "Behuda urinishlarni to'xtatish uchun u ro'yxatdan "
    "AVTOMATIK o'chirildi. Tekshirib, qayta qo'shing."
)

USE_MENU_BUTTONS = "⚠️ Iltimos, menyudagi tugmalardan foydalaning."


# ─────────────────────────────────────────────────────────────────────────
# ALBOM / KO'P MEDIA
# ─────────────────────────────────────────────────────────────────────────
POST_ALBUM_COLLECTING = (
    "🖼 Albom yig'ilmoqda: {n} ta media.\n\n"
    "• Yana rasm qo'shsangiz — shu postga kiritiladi\n"
    "• Matn yuborsangiz — albomga caption bo'ladi\n"
    "• ✅ «Tayyor» tugmasini bosing (yoki 2 soniya kuting — o'zi saqlanadi)"
)


def album_collecting(n: int) -> str:
    return POST_ALBUM_COLLECTING.format(n=n)


POST_ALBUM_CAPTION_SAVED = "✅ Caption qabul qilindi (media: {n} ta).\n\n{preview}"


def album_caption_saved(n: int, text: str) -> str:
    preview = " ".join((text or "").split())[:160]
    return POST_ALBUM_CAPTION_SAVED.format(n=n, preview=preview)


POST_ALBUM_SAVED = "✅ Albom saqlandi (#{n}) — {files} ta media"

POST_UPDATED = "✏️ Post yangilandi (#{n})\n{kind}\n\n{preview}"

def ask_edit_post(preview: str) -> str:
    """Tahrirlash oynasi matni — eski postning hozirgi holatini ko'rsatadi."""
    return (
        "✏️ POSTNI TAHRIRLASH\n\n"
        f"Hozirgi matn:\n{preview}\n\n"
        "Yangi postni yuboring — eski matn shu bilan almashtiriladi.\n"
        "Matn yuborib, media yubormasangiz — rasmlar o'zgarishsiz qoladi.\n"
        f"{MAX_ALBUM_FILES} tagacha rasm albom qilib ham yuborish mumkin."
    )


ASK_EDIT_POST = "✏️ Tahrirlash uchun postni tanlang:"

ASK_PREVIEW_POST = (
    "👁 Ko'rinishini ko'rish uchun postni tanlang.\n\n"
    "ℹ️ Post sizning shaxsiy chatingizga yuboriladi — hech qaysi guruhga "
    "chiqmaydi. Shundan keyin 🧪 «Sinov yuborish» bilan bitta guruhga "
    "ham yuborib ko'rishingiz mumkin."
)

BTN_ALBUM_DONE = "✅ Tayyor — postni saqlash"


def post_added_text(n: int, kind: str, preview: str) -> str:
    """Yangi post haqida xabar + navbatdagi qadam ko'rsatmasi."""
    hint = ""
    if n == 1:
        hint = (
            "\n\n💡 Keyingi qadam: 💬 Guruhlar bo'limidan guruh qo'shing, "
            "so'ng ▶️ Start bosing."
        )
    return f"✅ Saqlandi (#{n})\n{kind}\n\n{preview}{hint}"


def test_send_done(group: str) -> str:
    return (
        "🧪 Sinov yuborildi!\n\n"
        f"📛 {group}\n\n"
        "Guruhga kirib ko'ring — e'lon qanday chiqqanini tekshiring.\n"
        "Hammasi yaxshi bo'lsa ▶️ Start bilan barcha guruhlarga yoqing."
    )


def test_send_failed(error: str) -> str:
    return (
        f"❌ Sinov yuborilmadi ({error}).\n\n"
        "Ko'pincha sabab: akkaunt o'sha guruhga a'zo emas yoki unda yozish "
        "taqiqlangan. 💬 Guruhlar → 🔎 Tekshirish bilan aniqlang."
    )


# ─────────────────────────────────────────────────────────────────────────
# GURUHLARNI TEKSHIRISH
# ─────────────────────────────────────────────────────────────────────────
GROUP_PICKER_CHECK = (
    "🔎 Tekshirish uchun guruhni tanlang.\n\n"
    "Bot sizning Telegram akkauntingiz orqali shu guruhga yozish "
    "mumkinmi-yu yo'qmi ekanini tekshiradi (post yuborilmaydi)."
)
GROUPS_EMPTY_HINT = (
    "❌ Guruhlar yo'q.\n\n"
    "1️⃣ Akkauntingiz guruhga a'zo bo'lsin (yoki guruhga kiring)\n"
    "2️⃣ ➕ Guruh qo'shish tugmasini bosing\n"
    "3️⃣ @username yoki https://t.me/guruh nomini yuboring "
    "(bir nechta bo'lsa — har biri yangi qatorda)"
)


def group_check_result(value: str, ok: bool, reason: str) -> str:
    if ok:
        return (
            f"✅ {value}\n\n"
            "Guruh topildi, akkaunt a'zo va yozish huquqi bor.\n"
            "Bu guruhga posting bemalol ishlaydi."
        )
    from bot.groups import group_reason_text

    return (
        f"❌ {value}\n\n"
        f"Sabab: {group_reason_text(reason)}\n\n"
        "🔧 Nima qilish kerak:\n"
        "• a'zo emasligingiz bo'lsa — akkauntingizni guruhga kiritish\n"
        "• yozish taqiqlangan bo'lsa — guruh admini ruxsat berishi kerak\n"
        "• havola noto'g'ri bo'lsa — guruhni o'chirib qaytadan qo'shing"
    )


# ─────────────────────────────────────────────────────────────────────────
# LIMITLAR / PAKETLAR
# ─────────────────────────────────────────────────────────────────────────
GROUPS_LIMIT_REACHED = (
    "❌ Paket chegarasi: {max_groups} ta guruh (hozir {used} ta).\n\n"
    "Ko'proq guruh uchun paketni kengaytiring:\n"
    f"📱 {ADMIN_CONTACT_PHONE}"
)

POSTS_LIMIT_REACHED = "❌ Paket chegarasi: {max_posts} ta post (hozir {used} ta)."


def plan_price_label(plan: str | None) -> str:
    """Paket nomi bo'yicha qisqa tavsif (admin paneli uchun)."""
    from config.config import PLAN_DEFS

    definition = PLAN_DEFS.get((plan or "").strip().upper())
    if not definition:
        return "limitlarsiz"
    groups = definition["max_groups"] or "∞"
    posts = definition["max_posts"] or "∞"
    daily = definition["daily_limit"] or "∞"
    return f"{groups} guruh · {posts} post · kuniga {daily} marta"


def plan_text(limits: dict, interval: int, expires: str, daily_left: str) -> str:
    lines = [
        "💳 OBUNAM\n",
        f"Tarif: {limits.get('label') or '—'}",
        f"💬 Guruhlar: {limits.get('used_groups', 0)}",
        f"📝 Postlar: {limits.get('used_posts', 0)}",
        f"⏱ Umumiy oralig': taxminan {interval} daqiqa",
        f"📅 Muddat: {expires}",
        "",
        "📊 Cheklovlar:",
    ]
    max_groups = int(limits.get("max_groups") or 0)
    max_posts = int(limits.get("max_posts") or 0)
    daily = int(limits.get("daily_limit") or 0)
    lines.append(
        f"• Guruhlar: {limits.get('used_groups', 0)}/{max_groups or '∞'}"
        if max_groups
        else "• Guruhlar: cheksiz"
    )
    lines.append(
        f"• Postlar: {limits.get('used_posts', 0)}/{max_posts or '∞'}"
        if max_posts
        else "• Postlar: cheksiz"
    )
    lines.append(f"• Kunlik yuborish: {daily_left}" if daily else "• Kunlik yuborish: cheksiz")
    hours = (limits.get("active_hours") or "").strip()
    lines.append(f"• Ish vaqti: {hours}" if hours else "• Ish vaqti: 24/7")
    lines.append("")
    lines.append("📱 Savollar: " + ADMIN_CONTACT_PHONE)
    return "\n".join(lines)


def group_limit_message(max_groups: int, used: int) -> str:
    return GROUPS_LIMIT_REACHED.format(max_groups=max_groups, used=used)


def post_limit_message(max_posts: int, used: int) -> str:
    return POSTS_LIMIT_REACHED.format(max_posts=max_posts, used=used)


def plans_overview() -> str:
    """Yordam matnida ko'rsatiladigan paketlar ro'yxati."""
    lines = []
    for name, definition in PLAN_DEFS.items():
        groups = definition["max_groups"] or "∞"
        posts = definition["max_posts"] or "∞"
        daily = definition["daily_limit"] or "∞"
        lines.append(
            f"{definition['label']} — 💬 {groups} guruh · 📝 {posts} post · "
            f"📤 kuniga {daily}"
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# YUBORISH HISOBOTI
# ─────────────────────────────────────────────────────────────────────────
def report_text(
    today_ok: int,
    today_failed: int,
    week_ok: int,
    groups_total: int,
    groups_failed: int,
    next_eta: str,
    last_error: str,
    daily_left: str,
    active_hours: str,
    running: bool,
    expired_users: list | None = None,
    global_today: dict | None = None,
) -> str:
    lines = [
        "📈 YUBORISH HISOBOTI\n",
        f"Bugun: ✅ {today_ok} ta · ❌ {today_failed} ta",
        f"So'nggi 7 kun: ✅ {week_ok} ta",
        f"💬 Guruhlar: {groups_total} ta faol"
        + (f" · ⚠️ {groups_failed} ta guruhda oxirgi urinish xato" if groups_failed else ""),
        f"⏭ Keyingi yuborish: {next_eta}",
    ]
    if last_error:
        lines.append(f"⚠️ Oxirgi xato: {last_error}")
    if daily_left:
        lines.append(f"📤 Kunlik limit: {daily_left}")
    if active_hours:
        lines.append(f"🕒 Ish vaqti: {active_hours}")
    lines.append("")
    lines.append("🟢 Posting ishlamoqda" if running else "🔴 Posting to'xtatilgan")
    if global_today and (global_today.get("ok") or global_today.get("failed")):
        ok_today = int(global_today.get("ok") or 0)
        failed_today = int(global_today.get("failed") or 0)
        rate = global_today.get("success_rate")
        lines += [
            "",
            "🌍 Butun bot bo'yicha bugun: "
            f"✅ {ok_today} ta · ❌ {failed_today} ta"
            + (f" ({float(rate):.0f}% muvaffaqiyat)" if rate is not None else ""),
        ]
    if expired_users:
        lines += [
            "",
            f"⛔ Muddati tugagan akkauntlar: {len(expired_users)} ta. "
            "Yana 30 kun ishlatishni xohlasangiz admin bilan bog'laning: "
            f"{ADMIN_CONTACT_PHONE}",
        ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# /help — QISQA YO'RIQNOMA
# ─────────────────────────────────────────────────────────────────────────
HELP_TEXT = (
    "🤖 AVTOBOT — QISQA YO'RIQNOMA\n\n"
    "Bot sizning Telegram akkauntingiz orqali reklama e'lonlaringizni "
    "guruhlariga avtomatik joylashtiradi.\n\n"
    "4 QADAM:\n"
    "1️⃣ 💬 Guruhlar → ➕ Guruh qo'shish — @username yoki t.me havolalarini "
    "(har biri yangi qatorda) yuboring. Akkauntingiz o'sha guruhlarda bo'lishi "
    "va yozish huquqiga ega bo'lishi kerak.\n"
    f"2️⃣ 📝 Postlar → ➕ Post qo'shish — matn, rasm, video yoki {MAX_ALBUM_FILES} "
    "tagacha rasmni albom qilib yuboring.\n"
    "3️⃣ ⏱ Posting oralig'i — nechada bir yuborilsin (5 dan 7 kungacha daqiqa). "
    "Har bir guruhga alohida: 💬 Guruhlar → ⏱ Guruh intervali.\n"
    "4️⃣ ▶️ Start — va 🔎 Tekshirish bilan guruhlar tayyorligini "
    "tasdiqlang.\n\n"
    "📈 Hisobot — necha marta yuborilgani, xatolar va keyingi navbat.\n"
    "👥 Referal — do'stingizni taklif qiling: har bir faol do'st "
    f"+{REFERRAL_BONUS_DAYS} kun tarif.\n"
    "🧪 Sinov yuborish — bitta guruhga bir marta, to'liq rejimni yoqmasdan.\n\n"
    "⚠️ Muhim:\n"
    "• Bot guruhga o'zi kirmaydi — avval akkauntingiz a'zo bo'lsin.\n"
    "• Juda tez oraliq + ko'p guruh Telegram tomonidan cheklovga olib keladi; "
    "kunlik limit va tungi tanaffus sizni himoya qiladi.\n"
    "• Sessiyangiz faqat shifrlangan holda saqlanadi, hech kimga ko'rsatilmaydi.\n\n"
    f"📱 Yordam: {ADMIN_CONTACT_PHONE}"
)

WELCOME_GUIDE = (
    "👋 Xush kelibsiz! 30 soniyada tayyor bo'lasiz:\n\n"
    "1️⃣ 💬 Guruhlar → guruhlar ro'yxatini yukoring\n"
    "2️⃣ 📝 Postlar → e'loningizni yuboring (bir nechta rasm ham bo'ladi)\n"
    "3️⃣ ▶️ Start → va 🔎 bilan tekshiring\n\n"
    "Istalgan payt 📊 Status yoki /help deb yozing."
)


# ─────────────────────────────────────────────────────────────────────────
# KO'RINISH VA SINOVDAN YUBORISH
# ─────────────────────────────────────────────────────────────────────────
def preview_sent_text(kind: str) -> str:
    labels = {
        "text": "📝 matnli post",
        "media": "🖼 media + matn",
        "album": f"🖼 albom ({MAX_ALBUM_FILES} tagacha rasm)",
        "fallback": "⚠️ media yuborilmadi — faqat matn ko'rsatildi",
    }
    return (
        "👁 KO'RINISH yuborildi\n\n"
        f"Post turi: {labels.get(kind, kind)}\n\n"
        "ℹ️ Bu xabar faqat sizga keldi — hech qaysi guruhga chiqmadi.\n"
        "Guruhda barcha rasmlar va matn BITTA albom bo'lib chiqadi."
    )


def link_preview_changed(enabled: bool) -> str:
    return (
        "🔗 Link preview "
        + ("yoqildi — havoladan keyin kartochka ko'rinadi."
           if enabled
           else "o'chirildi — faqat matn ko'rinadi.")
    )


ASK_TEST_PICK = (
    "🧪 SINOVDAN YUBORISH\n\n"
    "Avval postni tanlang — keyin bitta guruhni tanlaysiz.\n"
    "ℹ️ Bu postingni ishga tushirmaydi: faqat TANLANGAN guruhga bir marta "
    "yuboriladi."
)


def ask_test_group() -> str:
    return (
        "🧪 Qaysi guruhga sinovdan yuborilsin?\n\n"
        "⚠️ E'lon o'sha guruhda HAMMA ko'rishi uchun chiqadi.\n"
        "O'z guruhingiz yoki test uchun qulay guruhni tanlang."
    )


def test_send_ask(group: str, preview: str) -> str:
    return (
        "🧪 SINOVDAN YUBORISH TASDIQI\n\n"
        f"📛 Guruh: {group}\n"
        f"📝 Post: {preview}\n\n"
        "Bu e'lon guruhda ko'rinadigan bo'ladi. Davom etamizmi?"
    )


def status_next_step(groups: int, posts: int) -> str:
    """Bo'sh status uchun yo'riqnoma — keyingi qadamni aniq ko'rsatadi."""
    if not groups and not posts:
        return (
            "👇 Boshlash uchun:\n"
            "1️⃣ 💬 Guruhlar → ➕ Guruh qo'shish\n"
            "2️⃣ 📝 Postlar → ➕ Post qo'shish\n"
            "3️⃣ ▶️ Start"
        )
    if not groups:
        return "👇 Keyingi qadam: 💬 Guruhlar → ➕ Guruh qo'shish"
    if not posts:
        return "👇 Keyingi qadam: 📝 Postlar → ➕ Post qo'shish"
    return ""


# ─────────────────────────────────────────────────────────────────────────
# TO'LOV (A REJA) MATNLARI
# ─────────────────────────────────────────────────────────────────────────
BTN_PAY_STATUS = "🧾 To'lov holatim"
BTN_PAY_CANCEL = "❌ So'rovni bekor qilish"
BTN_PAY_QUEUE = "💰 To'lovlar navbati"
PAY_DISABLED = "💳 To'lov hozircha yoqilmagan. Paketni o'zgartirish uchun adminga murojaat qiling: " + ADMIN_CONTACT_PHONE
PAY_NOT_ALLOWED = "❌ Hisob faol emas. Avval tasdiqlangan hisob bilan 🔑 Login qiling."
PAY_PLAN_UNKNOWN = "❌ Bu paket uchun narx belgilanmagan."
PAY_PROOF_NEED_PHOTO = "📸 Kvitansiya rasmini yuboring (screenshot yoki foto). Matn yoki fayl qabul qilinmaydi."
PAY_PROOF_ALREADY = "✅ Kvitansiyangiz allaqachon yuborilgan — admin tekshirmoqda. Boshqa rasm yubormoqchi bo'lsangiz, avval ❌ bekor qiling."
PAY_PROOF_RECEIVED = (
    "✅ Kvitansiya qabul qilindi (so'rov #{pid}).\n\n"
    "Admin tekshirgach muddatingiz avtomatik uzaytiriladi va sizga xabar yuboriladi.\n"
    "Holatni 🧾 To'lov holatim tugmasi orqali ko'rishingiz mumkin."
)
PAY_PROOF_EXPIRED = (
    "⌛ To'lov so'rovi muddati o'tdi ({ttl} daqiqa ichida kvitansiya yuborilmagan).\n"
    "Qaytadan 💳 Obuna → 💳 orqali so'rov yarating."
)
PAY_CANCELLED = "❌ So'rov bekor qilindi."
PAY_CANCEL_GONE = "ℹ️ Bu so'rov allaqachon yopilgan yoki topilmadi."
PAY_REMINDER = (
    "🔔 Eslatma: {label} paketingiz muddati {until} da tugaydi ({left} kun qoldi).\n"
    "💳 Obuna → 💳 orqali uzaytirishingiz mumkin."
)
PAY_QUEUE_EMPTY = "✅ To'lovlar navbati bo'sh."
PAY_APPROVED_USER = (
    "✅ TO'LOV QABUL QILINDI\n\n"
    "📦 Paket: {label}\n"
    "📅 Yangi muddat: {expires}\n\n"
    "Rahmat! Muddat avtomatik uzaytirildi."
)
PAY_RESUMED_USER = "▶️ Posting avtomatik tiklandi. Holatni ⏱ tugmalaridan tekshirishingiz mumkin."
PAY_REJECTED_USER = (
    "❌ To'lov rad etildi (so'rov #{pid}).\n\n"
    "Sabab: kvitansiya tekshiruvdan o'tmadi (summa, izoh kodi yoki karta mos emas).\n"
    "To'g'ri kvitansiya bilan 💳 Obuna → 💳 orqali qayta so'rov yarating.\n"
    "Savol bo'lsa: " + ADMIN_CONTACT_PHONE
)
PAY_QUEUE_ALERT = "⚠️ To'lovlar navbati: {count} ta kvitansiya tekshiruvni kutmoqda (eng eskisi {age} daqiqa oldin)."


def fmt_som(amount: int | float) -> str:
    """150000 -> '150 000 so'm'."""
    return f"{int(amount):,}".replace(",", " ") + " so'm"


def plan_label(plan: str) -> str:
    definition = PLAN_DEFS.get((plan or "").upper()) or {}
    return definition.get("label") or plan


def plans_price_block() -> str:
    """💳 Obuna ekranidagi narx bloki (faqat to'lov yoqilganda)."""
    lines = ["💳 OYLIK OBUNA:"]
    for plan, amount in PLAN_PRICES.items():
        lines.append(f"{fmt_som(amount)} / {PAYMENT_DAYS} kun — cheklovlar yo'q")
    lines.append("")
    lines.append("Tugmani bosing, so'ng karta rekvizitlari va to'lov izohi ko'rsatiladi.")
    return "\n".join(lines)


def pay_instruction_text(payment: dict) -> str:
    holder = f"👤 Ism: {PAY_HOLDER}\n" if PAY_HOLDER else ""
    bank = f"🏦 Bank: {PAY_BANK}\n" if PAY_BANK else ""
    return (
        f"🧾 TO'LOV SO'ROVI #{payment['id']}\n\n"
        f"📦 Paket: {plan_label(payment['plan'])}\n"
        f"💰 Summa: {fmt_som(payment['amount'])} ({payment['days']} kun)\n\n"
        f"💳 Karta: {PAY_CARD or '—'}\n"
        f"{bank}{holder}\n"
        f"📝 Izoh (o'tkazmaga aynan shu kodni yozing):\n"
        f"{payment['reference']}\n\n"
        "📸 To'lovdan so'ng kvitansiya rasmini (screenshot) shu chatga yuboring.\n"
        f"⏳ {PAYMENT_REQUEST_TTL_MIN} daqiqa ichida kvitansiya yuborilmasa so'rov bekor bo'ladi."
    )


def pay_status_text(current: dict | None, history: list[dict]) -> str:
    labels = {
        "approved": "✅ Tasdiqlangan",
        "rejected": "❌ Rad etilgan",
        "cancelled": "🚫 Bekor qilingan",
        "expired": "⌛ Muddati o'tgan",
    }
    lines = ["🧾 TO'LOV HOLATI", ""]
    if current:
        if current.get("proof_path"):
            state = "⏳ Admin tekshirmoqda"
        else:
            state = "📸 Kvitansiya kutilmoqda"
        lines += [
            f"Joriy so'rov #{current['id']}: {state}",
            f"📦 {plan_label(current['plan'])} — {fmt_som(current['amount'])}",
            f"🔖 Izoh: {current['reference']}",
            "",
        ]
    else:
        lines += ["Ochiq so'rov yo'q.", ""]
    if history:
        lines.append("🕓 Oxirgi to'lovlar:")
        for row in history:
            label = labels.get(row["status"], row["status"])
            when = (row.get("created_at") or "")[:16]
            lines.append(f"• #{row['id']} {when} · {plan_label(row['plan'])} · {label}")
    else:
        lines.append("Hali to'lovlar yo'q.")
    return "\n".join(lines)


def admin_payment_caption(
    payment: dict,
    *,
    user_name: str,
    username: str,
    expires_text: str,
    dup_count: int,
    blocked: bool,
) -> str:
    who = f"{user_name or '—'} ({payment['uid']})"
    if username:
        who += f" @{username}"
    lines = [
        f"🧾 YANGI TO'LOV #{payment['id']}",
        "",
        f"👤 {who}",
        f"📦 Paket: {plan_label(payment['plan'])} — {fmt_som(payment['amount'])} / {payment['days']} kun",
        f"🔖 Izoh kodi: {payment['reference']}",
        f"📅 Hozirgi muddat: {expires_text}",
    ]
    if dup_count:
        lines.append(f"⚠️ Bu rasm yana {dup_count} ta so'rovda ishlatilgan — tekshiring!")
    if blocked:
        lines.append("🚫 Foydalanuvchi bloklangan")
    return "\n".join(lines)

