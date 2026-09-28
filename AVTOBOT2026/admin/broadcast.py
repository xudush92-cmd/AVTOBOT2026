"""Super admin broadcast: preview, background send, progress va cancellation."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field

from telegram import Update

from bot import keyboards as KB
from bot import texts as T
from config.config import SUPER_ADMIN
from core import database as db
from core.logger import log
from core.update_locks import user_update_lock

application = None
broadcast_pending: dict[int, dict] = {}


@dataclass
class BroadcastJob:
    task: asyncio.Task | None = None
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    sent: int = 0
    failed: int = 0
    total: int = 0
    chat_id: int = 0
    message_id: int = 0


broadcast_jobs: dict[int, BroadcastJob] = {}


def set_application(app) -> None:
    global application
    application = app


def _progress_text(job: BroadcastJob, *, finished: bool = False) -> str:
    processed = job.sent + job.failed
    if job.cancel.is_set() and finished:
        heading = "⛔ BROADCAST TO'XTATILDI"
    elif finished:
        heading = "✅ BROADCAST TUGADI"
    else:
        heading = "📤 BROADCAST YUBORILMOQDA"
    return (
        f"{heading}\n\n"
        f"Jami: {job.total}\n"
        f"Ko'rib chiqildi: {processed}\n"
        f"✅ Yuborildi: {job.sent}\n"
        f"❌ Xato: {job.failed}"
    )


async def begin_broadcast(update: Update) -> None:
    uid = update.callback_query.from_user.id
    q = update.callback_query
    if uid != SUPER_ADMIN:
        return
    job = broadcast_jobs.get(uid)
    if job and job.task and not job.task.done():
        await q.edit_message_text(
            _progress_text(job),
            reply_markup=KB.kb_broadcast_progress(),
        )
        return

    from bot.login import user_states

    broadcast_pending.pop(uid, None)
    user_states[uid] = {"step": "admin_broadcast", "ts": __import__("time").time()}
    await q.edit_message_text(
        "📢 BROADCAST\n\n"
        "Yubormoqchi bo'lgan xabaringizni yuboring.\n\n"
        "Matn, rasm yoki rasm+matn qo'llab-quvvatlanadi.",
        reply_markup=KB.kb_admin_back(),
    )


async def receive_broadcast(update: Update) -> None:
    uid = update.effective_user.id
    if uid != SUPER_ADMIN:
        return

    from bot.login import user_states

    user_states.pop(uid, None)
    msg = update.message
    broadcast_pending[uid] = {
        "text": msg.text or msg.caption or "",
        "photo_id": msg.photo[-1].file_id if msg.photo else None,
    }

    marker = "\n\n👆 BROADCAST PREVIEW"
    if msg.photo:
        preview = (msg.caption or "")[: 1024 - len(marker)] + marker
        await msg.reply_photo(
            photo=msg.photo[-1].file_id,
            caption=preview,
            reply_markup=KB.kb_broadcast_confirm(),
        )
    else:
        preview = (msg.text or "")[: 4096 - len(marker)] + marker
        await msg.reply_text(
            preview,
            reply_markup=KB.kb_broadcast_confirm(),
        )


async def handle_broadcast_callback(update: Update, uid: int, data: str) -> None:
    if uid != SUPER_ADMIN:
        return
    q = update.callback_query

    if data == "bc:cancel":
        broadcast_pending.pop(uid, None)
        await q.edit_message_text(
            T.ACTION_CANCELLED,
            reply_markup=KB.kb_admin_back(),
        )
        return

    if data == "bc:stop":
        job = broadcast_jobs.get(uid)
        if not job or not job.task or job.task.done():
            await q.edit_message_text(
                "ℹ️ Faol broadcast yo'q.",
                reply_markup=KB.kb_admin_back(),
            )
            return
        job.cancel.set()
        await q.edit_message_text(
            _progress_text(job) + "\n\n⏳ To'xtatilmoqda...",
            reply_markup=KB.kb_broadcast_progress(),
        )
        return

    if data == "bc:status":
        job = broadcast_jobs.get(uid)
        if not job:
            await q.edit_message_text(
                "ℹ️ Broadcast topilmadi.", reply_markup=KB.kb_admin_back()
            )
            return
        await q.edit_message_text(
            _progress_text(job, finished=bool(job.task and job.task.done())),
            reply_markup=(
                KB.kb_admin_back()
                if job.task and job.task.done()
                else KB.kb_broadcast_progress()
            ),
        )
        return

    if data != "bc:send":
        return
    content = broadcast_pending.pop(uid, None)
    if not content:
        await q.edit_message_text(
            "❌ Broadcast ma'lumoti eskirgan. Qaytadan boshlang.",
            reply_markup=KB.kb_admin_back(),
        )
        return
    current = broadcast_jobs.get(uid)
    if current and current.task and not current.task.done():
        await q.edit_message_text(
            _progress_text(current), reply_markup=KB.kb_broadcast_progress()
        )
        return

    users = await db.get_broadcast_users()
    job = BroadcastJob(
        total=len(users),
        chat_id=q.message.chat_id,
        message_id=q.message.message_id,
    )
    broadcast_jobs[uid] = job
    await q.edit_message_text(
        _progress_text(job), reply_markup=KB.kb_broadcast_progress()
    )
    job.task = asyncio.create_task(
        _run_broadcast(uid, content, users, job),
        name=f"broadcast-{uid}",
    )


async def _run_broadcast(
    uid: int, content: dict, users: list[dict], job: BroadcastJob
) -> None:
    try:
        for index, user in enumerate(users, 1):
            if job.cancel.is_set():
                break
            target = int(user["uid"])
            try:
                if content.get("photo_id"):
                    await application.bot.send_photo(
                        target,
                        photo=content["photo_id"],
                        caption=content.get("text") or "",
                    )
                else:
                    await application.bot.send_message(
                        target, content.get("text") or ""
                    )
                job.sent += 1
            except Exception as exc:
                job.failed += 1
                log(
                    f"Broadcast xato {target}: {type(exc).__name__}",
                    "warning",
                )
            if index % 10 == 0:
                await _edit_progress(job)
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        job.cancel.set()
        raise
    finally:
        await _edit_progress(job, finished=True)
        log(
            f"📢 Broadcast: sent={job.sent}, failed={job.failed}, "
            f"cancelled={job.cancel.is_set()}"
        )


async def _edit_progress(job: BroadcastJob, *, finished: bool = False) -> None:
    async with user_update_lock(SUPER_ADMIN):
        with contextlib.suppress(Exception):
            await application.bot.edit_message_text(
                chat_id=job.chat_id,
                message_id=job.message_id,
                text=_progress_text(job, finished=finished),
                reply_markup=(
                    KB.kb_admin_back() if finished else KB.kb_broadcast_progress()
                ),
            )


async def shutdown() -> None:
    jobs = [job for job in broadcast_jobs.values() if job.task and not job.task.done()]
    for job in jobs:
        job.cancel.set()
    tasks = [job.task for job in jobs if job.task]
    if not tasks:
        return
    _done, pending = await asyncio.wait(tasks, timeout=10)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
