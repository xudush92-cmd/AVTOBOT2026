"""
Log tizimi.

Xususiyatlari:
- Faylga va konsolga yozadi
- Rotatsiya: 5 MB dan keyin yangi fayl
- 3 ta eski fayl saqlanadi
- UTF-8 (o'zbek harflari uchun)
"""

from __future__ import annotations

import contextlib
import logging
import sys
from logging.handlers import RotatingFileHandler

from config.config import LOG_FILE

# ─────────────────────────────────────────────────────────────────────────
# FORMATLAR
# ─────────────────────────────────────────────────────────────────────────
FILE_FORMAT = "[%(asctime)s] %(levelname)s: %(message)s"
FILE_DATEFMT = "%Y-%m-%d %H:%M:%S"

CONSOLE_FORMAT = "[%(asctime)s] %(levelname)s: %(message)s"
CONSOLE_DATEFMT = "%H:%M:%S"

# ─────────────────────────────────────────────────────────────────────────
# LOGGER
# ─────────────────────────────────────────────────────────────────────────
logger = logging.getLogger("AvtoBot")
logger.setLevel(logging.INFO)

# Takroriy handler qo'shilishini oldini olish
if not logger.handlers:
    # 1) Faylga yozish (rotatsiya bilan)
    file_handler = RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, FILE_DATEFMT))
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)

    # 2) Konsolga yozish
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, CONSOLE_DATEFMT))
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)


# ─────────────────────────────────────────────────────────────────────────
# QULAYLIK FUNKSIYASI
# ─────────────────────────────────────────────────────────────────────────
def log(message: str, level: str = "info") -> None:
    """
    Qulay log yozish funksiyasi.

    Misol:
        log("Bot ishga tushdi")
        log("Xatolik yuz berdi", "error")
        log("Diqqat!", "warning")
    """
    getattr(logger, level.lower(), logger.info)(message)


# ─────────────────────────────────────────────────────────────────────────
# LOG FAYLINI TOZALASH
# ─────────────────────────────────────────────────────────────────────────
def clear_log_file() -> bool:
    """
    Log faylini xavfsiz tozalash.

    RotatingFileHandler faylni ochiq ushlab turadi, shuning uchun faylni
    tashqaridan ustidan yozish (yoki o'chirib qayta yaratish) handlerni
    buzadi: keyingi yozuvlar eski offset'da davom etib, fayl noaniq holatga
    tushadi. Bu yerda handler oqimi yopilmasdan truncate qilinadi, natijada
    rotatsiya va logging ishlashda davom etadi.

    Returns:
        True  — kamida bitta fayl handleri tozalandi
        False — fayl handleri topilmadi
    """
    cleared = False
    for handler in logger.handlers:
        stream = getattr(handler, "stream", None)
        if stream is None:
            continue
        with contextlib.suppress(Exception):
            handler.acquire()
            try:
                handler.flush()
                stream.seek(0)
                stream.truncate(0)
                cleared = True
            finally:
                handler.release()
    return cleared
