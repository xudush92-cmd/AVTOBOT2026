"""Xabardan media (rasm/video/fayl) yuklab olish — postlar uchun umumiy qatlam.

Foydalanuvchi va admin oqimlari bitta manbadan foydalansin uchun alohida
modulga ajratildi. Bot API orqali yuklab olishda 20 MB cheklovi bor, shu
sabab hajm tekshiruvi oldindan qilinadi (yuklab bo'lib xatolik olishdan
ko'ra tushunarli xabar berish afzal).
"""

from __future__ import annotations

import os
import uuid

from telegram import Message

from config.config import MAX_ALBUM_FILES, MAX_MEDIA_BYTES, MAX_MEDIA_FILES_PER_USER
from core.logger import log

# Ruxsat etilgan kengaytmalar → media turi. Bunday ro'yxat fayl nomini
# tozalashga ham yordam beradi (xavfli kengaytmalar saqlanmaydi).
_EXTENSION_KINDS: dict[str, str] = {
    ".jpg": "photo",
    ".jpeg": "photo",
    ".png": "photo",
    ".webp": "photo",
    ".gif": "photo",
    ".bmp": "photo",
    ".mp4": "video",
    ".mov": "video",
    ".webm": "video",
    ".mkv": "video",
    ".mp3": "audio",
    ".m4a": "audio",
    ".ogg": "audio",
    ".pdf": "document",
    ".txt": "document",
    ".doc": "document",
    ".docx": "document",
    ".xls": "document",
    ".xlsx": "document",
    ".ppt": "document",
    ".pptx": "document",
}

def entity_to_dict(entity) -> dict:
    """Telegram entity'ni JSON saqlash uchun dict'ga aylantiradi."""
    data = {"type": entity.type, "offset": entity.offset, "length": entity.length}
    if getattr(entity, "url", None):
        data["url"] = entity.url
    if getattr(entity, "language", None):
        data["language"] = entity.language
    if getattr(entity, "custom_emoji_id", None):
        data["custom_emoji_id"] = entity.custom_emoji_id
    if getattr(entity, "user", None):
        data["user_id"] = entity.user.id
    return data


def message_text_and_entities(msg: Message) -> tuple[str, list[dict]]:
    """Xabardagi matn va formatlashni (caption ham) birga qaytaradi."""
    text = msg.text or msg.caption or ""
    entities = list(msg.entities or []) + list(msg.caption_entities or [])
    return text, [entity_to_dict(entity) for entity in entities]


def user_media_dir(uid: int) -> str:
    """Foydalanuvchi media papkasi."""
    from config.config import MEDIA_DIR

    path = os.path.join(str(MEDIA_DIR), str(uid))
    os.makedirs(path, exist_ok=True)
    return path


def count_user_media_files(uid: int) -> int:
    try:
        return len(os.listdir(user_media_dir(uid)))
    except OSError:
        return 0


def _target_path(uid: int, extension: str) -> str:
    return os.path.join(user_media_dir(uid), f"{uuid.uuid4().hex}{extension}")


def _pick_media(msg: Message) -> tuple[object | None, str, str, int]:
    """(TelegramFile-beruvchi obyekt, kengaytma, tur, hajm) ni tanlaydi."""
    if msg.photo:
        photo = msg.photo[-1]  # eng yuqori sifat
        return photo, ".jpg", "photo", int(getattr(photo, "file_size", 0) or 0)
    if msg.video:
        suffix = _safe_suffix(getattr(msg.video, "mime_type", ""), {".mp4": "video"})
        return msg.video, suffix or ".mp4", "video", int(
            getattr(msg.video, "file_size", 0) or 0
        )
    if msg.document:
        name = getattr(msg.document, "file_name", "") or ""
        suffix = os.path.splitext(name)[1].lower()
        if suffix not in _EXTENSION_KINDS:
            # Noma'lum dokumentni ruxsat etilgan formatga keltiramiz yoki rad etamiz.
            mime = (getattr(msg.document, "mime_type", "") or "").lower()
            if "image" in mime:
                suffix = ".png"
            elif "video" in mime:
                suffix = ".mp4"
            elif "audio" in mime:
                suffix = ".mp3"
            else:
                return None, "", "", 0
        return (
            msg.document,
            suffix,
            _EXTENSION_KINDS[suffix],
            int(getattr(msg.document, "file_size", 0) or 0),
        )
    return None, "", "", 0


def _safe_suffix(mime: str | None, mapping: dict[str, str]) -> str | None:
    lowered = (mime or "").lower()
    for suffix, kind in mapping.items():
        if kind in lowered:
            return suffix
    return None


async def download_message_media(
    msg: Message, uid: int, *, remaining: int | None = None
) -> tuple[list[dict], list[str]]:
    """Bitta xabardagi media fayllarni diskka tushiradi.

    Args:
        remaining: qolgan ruxsat etilgan fayllar soni (albom limiti).

    Returns:
        (yuklangan media ro'yxati, xato matnlari)
        media elementi: ``{"path": str, "kind": "photo|video|audio|document"}``
    """
    items: list[dict] = []
    errors: list[str] = []

    source, extension, kind, size = _pick_media(msg)
    if source is None:
        if msg.photo or msg.video or msg.document:
            errors.append(
                "❌ Bu format qo'llab-quvvatlanmaydi. Rasm (jpg, png, webp), "
                "video (mp4) yoki hujjat (pdf, docx) yuboring."
            )
        return items, errors

    if size and size > MAX_MEDIA_BYTES:
        errors.append(
            f"❌ Fayl juda katta: {_format_mb(size)}. "
            f"Maksimal {_format_mb(MAX_MEDIA_BYTES)}."
        )
        return items, errors

    limit = MAX_ALBUM_FILES if remaining is None else min(MAX_ALBUM_FILES, remaining)
    if limit <= 0:
        errors.append(f"❌ Bitta postda maksimal {MAX_ALBUM_FILES} ta media.")
        return items, errors

    available = MAX_MEDIA_FILES_PER_USER - count_user_media_files(uid)
    if available <= 0:
        errors.append(
            f"❌ Sizning media saqlagichingiz to'lgan ({MAX_MEDIA_FILES_PER_USER} ta "
            "fayl). Eski postlarni o'chiring yoki admin bilan bog'laning."
        )
        return items, errors

    path = _target_path(uid, extension)
    try:
        tg_file = await source.get_file()
        await tg_file.download_to_drive(custom_path=path)
    except Exception as exc:
        from core.utils import safe_unlink

        safe_unlink(path)
        log(f"media yuklash xato {uid}: {type(exc).__name__}", "error")
        errors.append(
            "❌ Faylni yuklab bo'lmadi (tarmoq xatosi yoki hajmi katta). "
            "Qaytadan urinib ko'ring."
        )
        return items, errors

    items.append({"path": path, "kind": kind})
    return items, errors


def _format_mb(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MB"


def remove_media(paths: list[str]) -> None:
    """Fayllarni diskdan o'chiradi (post o'chirilganda yoki almashtirilganda)."""
    from core.utils import safe_unlink

    for path in paths:
        safe_unlink(path)


def post_media_paths(post: dict | None) -> list[str]:
    from core.utils import normalize_media

    return [item["path"] for item in normalize_media(post)]
