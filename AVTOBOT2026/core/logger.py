"""
Log tizimi.

Xususiyatlari:
- Faylga va konsolga yozadi
- Rotatsiya: 5 MB dan keyin yangi fayl
- 3 ta eski fayl saqlanadi
- UTF-8 (o'zbek harflari uchun)
"""

from __future__ import annotations

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
