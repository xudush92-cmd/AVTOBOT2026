"""Automatik tasdiqlash uchun oddiy, tushuntiriladigan risk bali.

Maqsad: admin navbatida kutayotgan foydalanuvchini "ko'zni yumib" tasdiqlash
emas, balki aniq, kodda yozilgan belgilarga qarab avto-tasdiq qilinishi
mumkinmi-yu yo'qmi degan savolga javob berish. Ball qancha KATTA bo'lsa,
xavf shuncha yuqori.

Hozircha faqat bazada mavjud bo'lgan belgilar ishlatiladi (Telegram API'ga
ulanmaydi): username borligi, telefon to'ldirilganligi, telefon bloki
klasteri, referal manbasi va o'sha manbaning kunlik faolligi.
"""

from __future__ import annotations

from config.config import AUTO_APPROVE_ENABLED, AUTO_APPROVE_MAX_RISK
from core.utils import is_valid_phone

# Ballar — o'zgartirilsa testlar bilan birga yangilanadi.
WEIGHT_NO_USERNAME = 3
WEIGHT_NO_PHONE = 2
WEIGHT_PHONE_CLUSTER = 2
WEIGHT_BAD_PHONE = 3
WEIGHT_BLOCKED_REFERRER = 3
WEIGHT_REFERRER_SPAM = 2
WEIGHT_DUPLICATE_NAME = 1

AUTO_APPROVE_THRESHOLD = 2  # config blank bo'lsa ishlatiladigan standart


def compute_risk_score(
    user: dict,
    *,
    phone_cluster: int = 0,
    referrer_blocked: bool = False,
    referrer_today: int = 0,
    duplicate_name_users: int = 0,
) -> tuple[int, list[str]]:
    """(ball, sabablar) qaytaradi. Ball 0 — eng ishonchli."""
    score = 0
    reasons: list[str] = []

    if not (user.get("username") or "").strip():
        score += WEIGHT_NO_USERNAME
        reasons.append("Telegram username yo'q")

    phone = (user.get("phone") or "").strip()
    if not phone:
        score += WEIGHT_NO_PHONE
        reasons.append("telefon raqam kiritilmagan")
    elif not is_valid_phone(phone):
        score += WEIGHT_BAD_PHONE
        reasons.append("telefon formati noto'g'ri")
    elif phone_cluster > 2:
        # Bitta telefon blokinda bir nechta akkaunt — ommaviy ro'yxat belgisi.
        score += WEIGHT_PHONE_CLUSTER
        reasons.append(f"telefon blokinda {phone_cluster} ta akkaunt")

    if user.get("referrer_uid"):
        if referrer_blocked:
            score += WEIGHT_BLOCKED_REFERRER
            reasons.append("referrer bloklangan")
        if referrer_today >= 10:
            score += WEIGHT_REFERRER_SPAM
            reasons.append(f"referrer bugun {referrer_today} ta taklif qilgan")

    if duplicate_name_users > 3:
        score += WEIGHT_DUPLICATE_NAME
        reasons.append(f"shu ism bilan {duplicate_name_users} ta akkaunt")

    return score, reasons


def risk_label(score: int) -> str:
    if score <= 1:
        return "🟢 past"
    if score <= 3:
        return "🟡 o'rtacha"
    return "🔴 yuqori"


def auto_approve_threshold() -> int:
    """Joriy sozlama: 0 = avto-tasdiq o'chirilgan."""
    if not AUTO_APPROVE_ENABLED:
        return -1
    return AUTO_APPROVE_MAX_RISK or 0


def should_auto_approve(score: int) -> bool:
    """Funktsiya o'chirilgan bo'lsa yoki ball chegaradan oshsa — False."""
    threshold = auto_approve_threshold()
    if threshold < 0:
        return False
    return score <= threshold
