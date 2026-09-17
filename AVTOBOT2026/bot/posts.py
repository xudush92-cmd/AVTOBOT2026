"""
Postlar bilan ishlash.

Funksiyalar:
- Post qo'shish (matn / rasm / rasm+caption)
- Post o'chirish
- Postlarni ko'rsatish
"""

from __future__ import annotations

import contextlib
import os
import time
import uuid

from telegram import Update
from telegram.ext import ContextTypes

from bot import keyboards as KB
from bot import texts as T
from config.config import MEDIA_DIR
from core import database as db
from core.logger import log
from core.utils import safe_unlink, truncate


# ─────────────────────────────────────────────────────────────────────────
# ENTITY KONVERTOR (PTB → dict)
# ─────────────────────────────────────────────────────────────────────────
def entity_to_dict(e) -> dict:
    """Telegram entity'ni JSON saqlash uchun dict'ga aylantiradi."""
    d = {"type": e.type, "offset": e.offset, "length": e.length}
    if getattr(e, "url", None):
        d["url"] = e.url
    if getattr(e, "language", None):
        d["language"] = e.language
    if getattr(e, "custom_emoji_id", None):
        d["custom_emoji_id"] = e.custom_emoji_id
    if getattr(e, "user", None):
        d["user_id"] = e.user.id
    return d


def user_media_dir(uid: int) -> str:
    """Foydalanuvchi uchun media papka."""
    path = os.path.join(str(MEDIA_DIR), str(uid))
    os.makedirs(path, exist_ok=True)
    return path


# ─────────────────────────────────────────────────────────────────────────
# POST QO'SHISH — BOSHLASH
# ─────────────────────────────────────────────────────────────────────────
async def begin_add_post(update: Update) -> None:
    """📝 Post qo'shish tugmasi bosilganda."""
    uid = update.effective_user.id
    from bot.login import user_states

    user_states[uid] = {"step": "add_post", "ts": time.time()}
    await update.message.reply_text(T.ASK_ADD_POST)
  

# ─────────────────────────────────────────────────────────────────────────
# POST QO'SHISH — HANDLER
# ─────────────────────────────────────────────────────────────────────────
async def handle_add_post(update: Update) -> None:
    """Foydalanuvchi post (matn/rasm) yubordi."""
    from bot.login import user_states

    uid = update.effective_user.id
    user_states.pop(uid, None)

    msg = update.message
    text = msg.text or msg.caption or ""
    entities_src = list(msg.entities or []) + list(msg.caption_entities or [])

    # Rasm yuklab olish
    photo_path: str | None = None
    if msg.photo:
        try:
            photo = msg.photo[-1]
            tg_file = await photo.get_file()
            user_dir = user_media_dir(uid)
            photo_path = os.path.join(user_dir, f"{uuid.uuid4().hex}.jpg")
            await tg_file.download_to_drive(custom_path=photo_path)
        except Exception as e:
            log(f"rasm yuklash xato {uid}: {type(e).__name__}: {e}", "error")
            await msg.reply_text(T.POST_PHOTO_ERROR)
            return

    # Bo'sh post?
    if not text.strip() and not photo_path:
        await msg.reply_text(T.POST_EMPTY_ERROR)
        return

    # Entities'ni dict'ga aylantirish
    entities_dict = [entity_to_dict(e) for e in entities_src]

    # Bazaga saqlash
    ok, reason, post_id = await db.add_post(
        uid, text, entities_dict, photo_path
    )
    if not ok:
        safe_unlink(photo_path)
        await msg.reply_text(T.GENERIC_ERROR)
        return

    # Post turini aniqlash
    if photo_path and text.strip():
        kind = T.POST_KIND_PHOTO
    elif photo_path:
        kind = T.POST_KIND_PHOTO_ONLY
    else:
        kind = T.POST_KIND_TEXT

    preview = truncate(text or "(rasm)", 100)
    new_count = await db.count_posts(uid)
    log(f"📝 Post qo'shildi: {uid} (#{post_id})")

    await msg.reply_text(
        T.POST_ADDED.format(n=new_count, kind=kind, preview=preview),
        reply_markup=KB.kb_main(),
    )


# ─────────────────────────────────────────────────────────────────────────
# POST O'CHIRISH — BOSHLASH
# ─────────────────────────────────────────────────────────────────────────
async def begin_delete_posts(update: Update) -> None:
    """🗑 Post o'chirish tugmasi bosilganda."""
    uid = update.effective_user.id
    posts = await db.get_posts(uid)

    if not posts:
        await update.message.reply_text(T.POSTS_EMPTY)
        return

    await update.message.reply_text(
        T.ASK_DEL_POST,
        reply_markup=KB.kb_posts_delete(posts),
    )


# ─────────────────────────────────────────────────────────────────────────
# POSTNI O'CHIRISH (callback uchun)
# ─────────────────────────────────────────────────────────────────────────
async def delete_post_by_index(uid: int, index: int) -> tuple[bool, str]:
    """
    Indeks bo'yicha postni o'chirish.

    Returns:
        (True, preview)  — o'chirildi
        (False, '')      — topilmadi
    """
    post = await db.remove_post(uid, index)
    if not post:
        return False, ""

    # Rasmni diskdan o'chirish
    if post.get("photo"):
        safe_unlink(post["photo"])

    text = (post.get("text") or "").strip().replace("\n", " ")
    preview = truncate(text or "(rasm)", 80)
    log(f"🗑 Post o'chirildi: {uid} idx={index}")
    return True, preview
