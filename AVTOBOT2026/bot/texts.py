"""
Barcha matnlar — o'zbek tilida.

Bu fayl orqali botdagi har bir xabar matnini bir joydan boshqarish mumkin.
"""

from __future__ import annotations

from config.config import ADMIN_CONTACT_PHONE, MIN_INTERVAL_MIN


# ─────────────────────────────────────────────────────────────────────────
# UMUMIY
# ─────────────────────────────────────────────────────────────────────────
WELCOME_SHORT = (
    "🤖 AVTOBOT\n\n"
    "Telegram guruhlaringizga reklama postlarini avtomatik joylashtiruvchi bot.\n\n"
    "📌 Boshlash:\n"
    "1. 🔑 Login bosib ism, familiya va telefonni kiriting\n"
    "2. Admin tasdiqlashini kuting\n"
    "3. Tasdiqdan keyin yana 🔑 Login bosing\n"
    "4. Telegram kodini tugmalar orqali kiriting\n\n"
    f"📱 Yordam: {ADMIN_CONTACT_PHONE}"
)

ADMIN_CONTACT_LINE = f"📱 Admin: {ADMIN_CONTACT_PHONE}"


# ─────────────────────────────────────────────────────────────────────────
# BLOK
# ─────────────────────────────────────────────────────────────────────────
BLOCKED = (
    "🚫 Bot to'xtatildi.\n\n"
    f"Admin bilan bog'laning: {ADMIN_CONTACT_PHONE}"
)


# ─────────────────────────────────────────────────────────────────────────
# LOGIN — ISM
# ─────────────────────────────────────────────────────────────────────────
ASK_NAME = (
    "📋 RO'YXATDAN O'TISH (1/4)\n\n"
    "👤 Ismingizni kiriting:\n\n"
    "Masalan: Akmal"
)

NAME_TOO_SHORT = "❌ Ism juda qisqa. Kamida 2 harf kiriting:"

NAME_ACCEPTED = (
    "✅ {name}\n\n"
    "📋 RO'YXATDAN O'TISH (2/4)\n\n"
    "👤 Familiyangizni kiriting:"
)


# ─────────────────────────────────────────────────────────────────────────
# LOGIN — FAMILIYA
# ─────────────────────────────────────────────────────────────────────────
SURNAME_TOO_SHORT = "❌ Familiya juda qisqa. Kamida 2 harf kiriting:"

SURNAME_ACCEPTED = (
    "✅ {full_name}\n\n"
    "📋 RO'YXATDAN O'TISH (3/4)\n\n"
    "📱 Telefon raqamingizni yuboring:\n\n"
    "Format: +998XXXXXXXXX"
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
    "rasmiy \"Telegram\" (777000) chatiga keladi."
)


# ─────────────────────────────────────────────────────────────────────────
# LOGIN — TELEGRAM TASDIQ KODI
# ─────────────────────────────────────────────────────────────────────────
def numpad_text(buffer: str, hint: str = "") -> str:
    """Telegram tasdiq kodini kiritish oynasi matni."""
    total = max(5, len(buffer))
    display = " ".join(
        buffer[i] if i < len(buffer) else "▪" for i in range(total)
    )
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
    "⏰ Yangi kod yuborildi!\n"
    "Telegram ilovasidan ENG SO'NGGI kodni oling."
)

CODE_TOO_SHORT = "Kamida 5 ta raqam kiriting!"

CODE_TOO_LONG = "Maksimal 6 ta raqam!"

CODE_MAX_WRONG = (
    "❌ {count} marta noto'g'ri kod kiritildi.\n\n"
    "Qaytadan 🔑 Login bosing.\n\n"
    f"📱 Yordam: {ADMIN_CONTACT_PHONE}"
)

CODE_EXPIRED = (
    "⏰ Kod muddati tugadi.\n\n"
    "Yangi kod so'ralmoqda..."
)

CODE_NOT_MATN = (
    "⚠️ Iltimos, kodni MATN sifatida yozmang!\n\n"
    "Telegram xavfsizlik tizimi matnli kodni darhol bekor qiladi.\n"
    "Faqat pastdagi RAQAMLI TUGMALAR orqali kiriting."
)

CODE_CANCELLED = "❌ Login bekor qilindi."

CODE_TIMEOUT = (
    "⏰ Login vaqti tugadi.\n\n"
    "Qaytadan 🔑 Login bosing."
)


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
    "⏰ QR kod muddati tugadi.\n\n"
    "Qaytadan 🔑 Login bosing va yangi QR yarating."
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
    "⏳ Avval admin sizni tasdiqlaydi. Shundan keyin 🔑 Login bosib "
    "Telegram kodini so'raysiz.\n\n"
    f"📞 Tezroq tasdiqlanish uchun: {ADMIN_CONTACT_PHONE}"
)

LOGIN_SUCCESS_PENDING = (
    "✅ Login muvaffaqiyatli!\n\n"
    "⏳ So'rovingiz admin tasdiqini kutmoqda.\n\n"
    f"📞 Tezroq tasdiqlanish uchun: {ADMIN_CONTACT_PHONE}"
)

LOGIN_SUCCESS_APPROVED = (
    "✅ Tizimga muvaffaqiyatli kirdingiz!\n\n"
    "Endi guruh va post qo'shib, ▶️ Start bosishingiz mumkin."
)

LOGIN_ALREADY_PENDING = (
    "⏳ So'rovingiz admin tasdiqini kutmoqda.\n\n"
    f"📱 Admin: {ADMIN_CONTACT_PHONE}"
)

LOGIN_NOT_APPROVED = (
    "⛔ Siz hali tasdiqlanmagansiz.\n\n"
    f"📱 Admin bilan bog'laning: {ADMIN_CONTACT_PHONE}"
)


# ─────────────────────────────────────────────────────────────────────────
# ADMINGA XABAR (yangi user)
# ─────────────────────────────────────────────────────────────────────────
def new_user_notification(name: str, phone: str, username: str, uid: int) -> str:
    """Adminga yangi foydalanuvchi haqida xabar."""
    user_line = f"@{username}" if username else "username yo'q"
    return (
        "🔔 Yangi foydalanuvchi ro'yxatdan o'tdi\n\n"
        f"👤 Ism: {name}\n"
        f"📱 Telefon: {phone}\n"
        f"📎 {user_line}\n"
        f"🆔 ID: {uid}"
    )


USER_APPROVED = (
    "✅ Hisobingiz tasdiqlandi!\n\n"
    "Endi botdan foydalanishingiz mumkin.\n"
    "🔑 Login bosing va kodni kiriting."
)

USER_REJECTED = (
    "❌ So'rovingiz rad etildi.\n\n"
    f"📞 Savollar uchun: {ADMIN_CONTACT_PHONE}"
)


# ─────────────────────────────────────────────────────────────────────────
# RATE LIMIT
# ─────────────────────────────────────────────────────────────────────────
def rate_limit_text(minutes: int) -> str:
    return (
        f"⏳ Juda ko'p so'rov yubordingiz.\n\n"
        f"{minutes} daqiqa kuting va qaytadan urinib ko'ring."
)
  

# ─────────────────────────────────────────────────────────────────────────
# MENYU TUGMALARI
# ─────────────────────────────────────────────────────────────────────────
BTN_START = "▶️ Start"
BTN_STOP = "⛔ Stop"
BTN_STATUS = "📊 Status"
BTN_GROUPS = "💬 Guruhlar"
BTN_ADD_GROUP = "➕ Guruh qo'shish"
BTN_DEL_GROUP = "➖ Guruh o'chirish"
BTN_ADD_POST = "📝 Post qo'shish"
BTN_DEL_POST = "🗑 Post o'chirish"
BTN_TIMER = "⏰ Vaqt"
BTN_REFERRAL = "👥 Referal"
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
    "⏰ Har {interval} daqiqada yuboriladi."
)

START_NO_GROUPS = "❌ Avval ➕ Guruh qo'shing."

START_NO_POSTS = "❌ Avval 📝 Post qo'shing."

START_ALREADY = "⚠️ Allaqachon ishlamoqda."

START_DONE = (
    "✅ Posting boshlandi!\n\n"
    "💬 {groups} ta guruh\n"
    "📝 {posts} ta post\n"
    "⏰ Har {interval} daqiqada"
)

START_BUSY = "⚠️ Tizim band. Bir oz kuting va qaytadan urinib ko'ring."

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
) -> str:
    if expired:
        state = "⏸ Kutish rejimi (muddat tugagan)"
    elif running:
        state = "🟢 Ishlamoqda"
    else:
        state = "🔴 To'xtatilgan"
    return (
        "📊 STATUS\n\n"
        f"Holat: {state}\n"
        f"Sessiya: ✅ Faol\n"
        f"📅 Muddat: {expires}\n\n"
        f"💬 Guruhlar: {groups}\n"
        f"📝 Postlar: {posts}\n"
        f"⏰ Vaqt: {interval} daqiqa"
    )


# ─────────────────────────────────────────────────────────────────────────
# GURUHLAR
# ─────────────────────────────────────────────────────────────────────────
GROUPS_EMPTY = "❌ Guruhlar yo'q. ➕ Guruh qo'shish orqali qo'shing."

def groups_list(groups: list[str]) -> str:
    lines = [f"💬 GURUHLAR ({len(groups)} ta):\n"]
    for i, g in enumerate(groups, 1):
        lines.append(f"{i}. {g}")
    return "\n".join(lines)


ASK_ADD_GROUP = (
    "➕ GURUH QO'SHISH\n\n"
    "Bir yoki bir nechta guruhni yuboring — har biri YANGI QATORDA.\n\n"
    "Misol:\n"
    "@guruh1\n"
    "@guruh2\n"
    "https://t.me/guruh3\n"
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
        lines.append(f"❌ {g} — topilmadi")
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
    "✍️ Reklama yuboring:\n\n"
    "• Faqat matn (formatlash bilan)\n"
    "• Rasm + caption (formatlash bilan)\n"
    "• Faqat rasm\n\n"
    "Bold, italic, link va barcha formatlash saqlanadi."
)

POST_ADDED = (
    "✅ Saqlandi (#{n})\n"
    "{kind}\n\n"
    "{preview}"
)

POST_KIND_TEXT = "📝 Matn"
POST_KIND_PHOTO = "🖼 Rasm + matn"
POST_KIND_PHOTO_ONLY = "🖼 Faqat rasm"

POST_EMPTY_ERROR = (
    "❌ Bo'sh post qabul qilinmaydi.\n"
    "Matn yoki rasm yuboring."
)

POST_PHOTO_ERROR = (
    "❌ Rasmni saqlab bo'lmadi. Qaytadan urinib ko'ring."
)

ASK_DEL_POST = "🗑 O'chirish uchun postni tanlang:"

POST_DELETED = (
    "🗑 O'chirildi:\n"
    "{preview}"
)

POST_NOT_FOUND = "❌ Post topilmadi."


# ─────────────────────────────────────────────────────────────────────────
# VAQT (INTERVAL)
# ─────────────────────────────────────────────────────────────────────────
def ask_interval(current: int) -> str:
    return (
        f"⏰ VAQT\n\n"
        f"Hozirgi: {current} daqiqa\n\n"
        f"Yangi qiymatni kiriting (daqiqada):\n"
        f"Kamida {MIN_INTERVAL_MIN} daqiqa."
    )

def interval_invalid_min() -> str:
    return f"❌ Kamida {MIN_INTERVAL_MIN} daqiqa bo'lishi kerak."

INTERVAL_INVALID_NUMBER = "❌ Faqat butun son kiriting. Qaytadan:"

def interval_set(minutes: int) -> str:
    return f"✅ Vaqt: {minutes} daqiqa"


# ─────────────────────────────────────────────────────────────────────────
# REFERAL
# ─────────────────────────────────────────────────────────────────────────
def referral_text(link: str, total: int, refs: list[dict]) -> str:
    lines = [
        "👥 SIZNING REFERALLARINGIZ\n",
        "🔗 Sizning taklif havolangiz:",
        link,
        "",
        f"✅ Faol referallar: {total} ta",
        "(ro'yxatdan o'tib, tasdiqlangan)",
    ]
    if refs:
        lines.append("")
        lines.append("📋 Ro'yxat:")
        for i, r in enumerate(refs, 1):
            mark = "✅" if r.get("counted") else "⏳"
            lines.append(f"{i}. {r['name']} — {mark}")
    else:
        lines.append("")
        lines.append("Hozircha referal yo'q. Havolani do'stlaringizga ulashing!")
    return "\n".join(lines)


REFERRAL_NEW = (
    "🎉 Sizning referalingiz faollashdi!\n\n"
    "👤 {name} ro'yxatdan o'tib, tasdiqlandi.\n"
    "👥 Jami faol referallaringiz: {total} ta"
)


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


# ─────────────────────────────────────────────────────────────────────────
# XATOLAR
# ─────────────────────────────────────────────────────────────────────────
GENERIC_ERROR = "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring."

SESSION_INVALID = (
    "🚫 Sessiyangiz Telegram tomonidan bekor qilindi.\n\n"
    "Qaytadan 🔑 Login qiling."
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
