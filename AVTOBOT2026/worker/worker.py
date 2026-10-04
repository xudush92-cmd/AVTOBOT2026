"""
Posting worker — asosiy sikl.

Har bir foydalanuvchi uchun:
1. Guruhlarni oladi
2. Postlarni oladi (rotation bilan)
3. Har bir guruhga yuboradi
4. Xatolarni kuzatadi
5. Har bir guruhning navbatdagi vaqtini kutadi
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    ChannelPrivateError,
    ChatWriteForbiddenError,
    FloodWaitError,
    PeerIdInvalidError,
    UserDeactivatedBanError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.types import (
    MessageEntityBold,
    MessageEntityBotCommand,
    MessageEntityCashtag,
    MessageEntityCode,
    MessageEntityCustomEmoji,
    MessageEntityEmail,
    MessageEntityHashtag,
    MessageEntityItalic,
    MessageEntityMention,
    MessageEntityMentionName,
    MessageEntityPhone,
    MessageEntityPre,
    MessageEntitySpoiler,
    MessageEntityStrike,
    MessageEntityTextUrl,
    MessageEntityUnderline,
    MessageEntityUrl,
)

from config.config import (
    JITTER_S,
    MAX_GROUP_FAILS,
    SEND_DELAY_S,
    START_JITTER_S,
    SUPER_ADMIN,
)
from core import database as db
from core.logger import log
from worker.client_pool import ClientPool, PoolBusyError, SessionInvalidError

# ─────────────────────────────────────────────────────────────────────────
# GLOBAL (main.py da o'rnatiladi)
# ─────────────────────────────────────────────────────────────────────────
client_pool: ClientPool | None = None
application = None


def set_deps(pool: ClientPool, app) -> None:
    """main.py dan chaqiriladi."""
    global client_pool, application
    client_pool = pool
    application = app


# ─────────────────────────────────────────────────────────────────────────
# ENTITY KONVERTOR (dict → Telethon)
# ─────────────────────────────────────────────────────────────────────────
def dicts_to_entities(items: list[dict]) -> list:
    """JSON'dan Telethon entity'larga."""
    out = []
    for d in items or []:
        t = d.get("type")
        off = int(d.get("offset", 0))
        ln = int(d.get("length", 0))
        try:
            if t == "bold":
                out.append(MessageEntityBold(off, ln))
            elif t == "italic":
                out.append(MessageEntityItalic(off, ln))
            elif t == "underline":
                out.append(MessageEntityUnderline(off, ln))
            elif t == "strikethrough":
                out.append(MessageEntityStrike(off, ln))
            elif t == "spoiler":
                out.append(MessageEntitySpoiler(off, ln))
            elif t == "code":
                out.append(MessageEntityCode(off, ln))
            elif t == "pre":
                out.append(
                    MessageEntityPre(off, ln, language=d.get("language", "") or "")
                )
            elif t == "text_link":
                out.append(MessageEntityTextUrl(off, ln, url=d.get("url", "")))
            elif t == "text_mention":
                uid = d.get("user_id")
                if uid:
                    out.append(MessageEntityMentionName(off, ln, user_id=int(uid)))
            elif t == "url":
                out.append(MessageEntityUrl(off, ln))
            elif t == "mention":
                out.append(MessageEntityMention(off, ln))
            elif t == "hashtag":
                out.append(MessageEntityHashtag(off, ln))
            elif t == "cashtag":
                out.append(MessageEntityCashtag(off, ln))
            elif t == "bot_command":
                out.append(MessageEntityBotCommand(off, ln))
            elif t == "email":
                out.append(MessageEntityEmail(off, ln))
            elif t == "phone_number":
                out.append(MessageEntityPhone(off, ln))
            elif t == "custom_emoji":
                cid = d.get("custom_emoji_id")
                if cid:
                    out.append(MessageEntityCustomEmoji(off, ln, document_id=int(cid)))
        except Exception:
            continue
    return out


# ─────────────────────────────────────────────────────────────────────────
# GURUHNI TOPISH
# ─────────────────────────────────────────────────────────────────────────
async def resolve_chat(client: TelegramClient, chat: str):
    """Saqlangan public URL, private invite yoki ID'dan entity topadi."""
    from bot.groups import resolve_group_entity

    return await resolve_group_entity(client, chat)


# ─────────────────────────────────────────────────────────────────────────
# POST YUBORISH
# ─────────────────────────────────────────────────────────────────────────
async def send_post(client: TelegramClient, chat: str, post: dict) -> None:
    """Bitta postni bitta guruhga yuboradi."""
    text = post.get("text", "")
    entities = dicts_to_entities(post.get("entities", []))
    target = await resolve_chat(client, chat)

    photo_path = post.get("photo")
    if photo_path:
        import os

        if os.path.exists(photo_path):
            await client.send_file(
                entity=target,
                file=photo_path,
                caption=text,
                formatting_entities=entities or None,
            )
            return

    await client.send_message(
        entity=target,
        message=text,
        formatting_entities=entities or None,
        link_preview=bool(post.get("link_preview", True)),
    )


# ─────────────────────────────────────────────────────────────────────────
# YORDAMCHI — SLEEP YOKI STOP
# ─────────────────────────────────────────────────────────────────────────
async def sleep_or_stop(stop: asyncio.Event, seconds: float) -> bool:
    """
    Berilgan vaqt kutadi. Stop signali kelsa — True qaytaradi.
    """
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
        return True
    except asyncio.TimeoutError:
        return False


# ─────────────────────────────────────────────────────────────────────────
# POSTING SIKL (har bir worker uchun)
# ─────────────────────────────────────────────────────────────────────────
async def posting_loop(uid: int, stop: asyncio.Event) -> None:
    """Guruhlarning umumiy va alohida intervaliga ko'ra navbat bilan post yuboradi.

    ``groups.interval_min`` bo'sh bo'lsa foydalanuvchining umumiy intervali
    ishlatiladi. ``next_send_at`` restartdan keyin ham navbatni saqlaydi.
    """
    log(f"🟢 Worker:{uid} ishga tushdi")

    first_delay = random.randint(0, START_JITTER_S)
    if first_delay:
        log(f"⏳ Worker:{uid} start jitter {first_delay}s")
        if await sleep_or_stop(stop, first_delay):
            return

    post_index = 0
    group_fails: dict[str, int] = {}
    scheduler_poll_s = 60

    try:
        while not stop.is_set():
            # Uzoq ishlayotgan worker ham ruxsat/tarif o'zgarishini tekshiradi.
            user = await db.get_user(uid)
            if (
                not user
                or not user.get("is_admin")
                or user.get("is_blocked")
                or await db.is_tariff_expired(uid)
            ):
                await db.set_running(uid, False)
                log(f"⛔ Worker:{uid} ruxsat/tarif sabab to'xtadi", "warning")
                break

            session = await db.get_session(uid)
            if not session:
                await db.set_running(uid, False)
                log(f"❌ Worker:{uid} sessiya yo'q — to'xtaydi", "warning")
                break

            chats = await db.get_chat_records(uid)
            posts = await db.get_posts(uid)

            if not chats or not posts:
                if await sleep_or_stop(stop, 30):
                    break
                continue

            now = time.time()
            due_chats: list[dict] = []
            next_times: list[float] = []
            for chat_record in chats:
                next_at = chat_record.get("next_send_at")
                try:
                    next_at = float(next_at) if next_at is not None else None
                except (TypeError, ValueError):
                    next_at = None
                if next_at is None or next_at <= now:
                    due_chats.append(chat_record)
                else:
                    next_times.append(next_at)

            if not due_chats:
                wait_s = (
                    min(scheduler_poll_s, max(1.0, min(next_times) - now))
                    if next_times
                    else scheduler_poll_s
                )
                if await sleep_or_stop(stop, wait_s):
                    break
                continue

            try:
                client = await client_pool.acquire(uid, session)
            except SessionInvalidError:
                log(f"🚫 Worker:{uid} — sessiyani tasdiqlab bo'lmadi", "warning")
                await db.set_running(uid, False)
                await client_pool.remove(uid)
                with contextlib.suppress(Exception):
                    await application.bot.send_message(
                        uid,
                        "🚫 Telegram sessiyasini tasdiqlab bo'lmadi. "
                        "Mavjud sessiya saqlandi; Hisob bo'limidan tekshiring.",
                    )
                break
            except PoolBusyError as exc:
                cause = exc.__cause__
                wait_s = (
                    int(getattr(cause, "seconds", 30)) + 5
                    if isinstance(cause, FloodWaitError)
                    else 30
                )
                log(
                    f"⏳ Worker:{uid} — pool/Telegram vaqtincha band, {wait_s}s kutadi",
                    "warning",
                )
                if await sleep_or_stop(stop, wait_s):
                    break
                continue

            try:
                post = posts[post_index % len(posts)]
                post_index += 1
                ok, fail = 0, 0
                removed_groups: list[str] = []

                for chat_record in due_chats:
                    if stop.is_set():
                        break

                    chat = str(chat_record["value"])
                    group_id = int(chat_record["id"])
                    jitter_s = random.randint(-JITTER_S, JITTER_S)
                    flood_wait_until: float | None = None
                    attempted_at: float | None = None

                    try:
                        await asyncio.wait_for(
                            send_post(client, chat, post), timeout=20
                        )
                        ok += 1
                        group_fails[chat] = 0
                        log(f"✅ {uid} → {chat}")

                    except FloodWaitError as exc:
                        wait_s = int(getattr(exc, "seconds", 30)) + 5
                        attempted_at = time.time()
                        flood_wait_until = attempted_at + wait_s
                        log(f"⏳ {uid} → {chat} FloodWait {wait_s}s", "warning")

                    except (
                        ChatWriteForbiddenError,
                        ChannelPrivateError,
                        PeerIdInvalidError,
                        UsernameNotOccupiedError,
                        UsernameInvalidError,
                        ValueError,
                    ) as exc:
                        fail += 1
                        group_fails[chat] = group_fails.get(chat, 0) + 1
                        log(
                            f"❌ {uid} → {chat}: {type(exc).__name__} "
                            f"({group_fails[chat]}/{MAX_GROUP_FAILS})",
                            "warning",
                        )
                        if group_fails[chat] >= MAX_GROUP_FAILS:
                            removed_groups.append(chat)

                    except asyncio.TimeoutError:
                        # Tarmoq uzilishi guruh yoki sessiya yaroqsizligini
                        # anglatmaydi; navbatdagi urinishgacha interval saqlanadi.
                        fail += 1
                        log(f"⏱ {uid} → {chat} vaqtincha timeout", "warning")

                    except (AuthKeyUnregisteredError, UserDeactivatedBanError) as exc:
                        log(f"🚫 {uid} sessiya yaroqsiz: {type(exc).__name__}", "error")
                        await db.set_running(uid, False)
                        await client_pool.remove(uid)
                        with contextlib.suppress(Exception):
                            await application.bot.send_message(
                                uid,
                                "🚫 Telegram sessiyasi ishlamayapti. Mavjud "
                                "sessiya saqlandi; Hisob bo'limidan tekshiring.",
                            )
                        return

                    except Exception as exc:
                        fail += 1
                        log(f"❌ {uid} → {chat}: {type(exc).__name__}", "error")

                    if attempted_at is None:
                        attempted_at = time.time()
                    next_send_at = await db.record_chat_attempt(
                        uid,
                        group_id,
                        attempted_at,
                        jitter_s,
                        flood_wait_until,
                    )
                    if next_send_at is not None:
                        wait_s = max(0, int(next_send_at - time.time()))
                        log(f"⏳ {uid} → {chat} navbat: {wait_s}s")

                    if flood_wait_until is not None:
                        if await sleep_or_stop(
                            stop, max(0, flood_wait_until - time.time())
                        ):
                            break

                    if not stop.is_set():
                        await sleep_or_stop(stop, SEND_DELAY_S)

                # Ketma-ket muvaffaqiyatsiz yuborilgan guruhlar eski qoidadagidek
                # MAX_GROUP_FAILS urinishdan keyin ro'yxatdan olib tashlanadi.
                for bad in removed_groups:
                    await db.remove_chat_by_value(uid, bad)
                    group_fails.pop(bad, None)
                    log(f"🗑 {uid} guruh o'chirildi (avto): {bad}")
                    with contextlib.suppress(Exception):
                        await application.bot.send_message(
                            uid,
                            f"⚠️ Quyidagi guruhga {MAX_GROUP_FAILS} marta "
                            f"xabar yuborib bo'lmadi:\n\n"
                            f"📛 {bad}\n\n"
                            "Sabab: bot chiqarilgan, yozish taqiqlangan yoki "
                            "guruh mavjud emas.\n"
                            "Guruh ro'yxatdan AVTOMATIK o'chirildi.",
                        )

                log(f"📊 {uid} ✅{ok} ❌{fail} / {len(due_chats)} navbatda")

            finally:
                await client_pool.release(uid)

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        log(f"💥 Worker:{uid} kutilmagan xato: {type(exc).__name__}", "error")
        with contextlib.suppress(Exception):
            await application.bot.send_message(
                SUPER_ADMIN,
                f"⚠️ Worker xato\nUID: {uid}\n{type(exc).__name__}",
            )
    finally:
        await db.set_running(uid, False)
        log(f"🔴 Worker:{uid} to'xtadi")


# ─────────────────────────────────────────────────────────────────────────
# WORKER MANAGER
# ─────────────────────────────────────────────────────────────────────────
class WorkerManager:
    """
    Workerlarni boshqaradi.

    - Har bir foydalanuvchi uchun worker task yaratadi
    - Limitga rioya qiladi (MAX_CONCURRENT_WORKERS)
    - Graceful shutdown (SIGTERM/SIGINT)
    """

    def __init__(self, max_workers: int | None = None):
        from config.config import MAX_CONCURRENT_WORKERS

        self.max_workers = max_workers or MAX_CONCURRENT_WORKERS
        self._workers: dict[int, dict] = {}  # uid -> {task, stop_event}
        self._shutdown_event = asyncio.Event()
        self._worker_factory = None
        self._lock = asyncio.Lock()

    # ─────────────────────────────────────────────────────────────
    # SOZLASH
    # ─────────────────────────────────────────────────────────────
    def set_worker_factory(self, factory) -> None:
        """Worker factory'ni o'rnatish (posting_loop)."""
        self._worker_factory = factory

    def setup_signals(self) -> None:
        """SIGTERM/SIGINT uchun handler."""
        import signal

        def _handler(signum, frame):
            log(f"🛑 Signal {signum} qabul qilindi")
            self._shutdown_event.set()

        with contextlib.suppress(Exception):
            signal.signal(signal.SIGTERM, _handler)
        with contextlib.suppress(Exception):
            signal.signal(signal.SIGINT, _handler)

    # ─────────────────────────────────────────────────────────────
    # HOLAT
    # ─────────────────────────────────────────────────────────────
    def is_running(self, uid: int) -> bool:
        """Foydalanuvchi workeri ishlayaptimi?"""
        info = self._workers.get(uid)
        if not info:
            return False
        task = info.get("task")
        return bool(task and not task.done())

    # ─────────────────────────────────────────────────────────────
    # ISHGA TUSHIRISH
    # ─────────────────────────────────────────────────────────────
    async def start_worker(self, uid: int) -> bool:
        """Worker'ni atomar ravishda ishga tushiradi."""
        async with self._lock:
            if self.is_running(uid):
                return False
            for stale_uid, info in list(self._workers.items()):
                if info["task"].done():
                    self._workers.pop(stale_uid, None)
            if len(self._workers) >= self.max_workers:
                log(f"⚠️ Worker limiti to'la ({self.max_workers})", "warning")
                return False
            if not self._worker_factory:
                log("❌ Worker factory o'rnatilmagan", "error")
                return False

            stop_event = asyncio.Event()
            task = asyncio.create_task(
                self._worker_factory(uid, stop_event),
                name=f"worker-{uid}",
            )
            self._workers[uid] = {"task": task, "stop_event": stop_event}
            task.add_done_callback(
                lambda finished, worker_uid=uid: self._remove_finished(
                    worker_uid, finished
                )
            )
            total = len(self._workers)
        log(f"✅ Worker:{uid} boshlandi (jami {total})")
        return True

    def _remove_finished(self, uid: int, task: asyncio.Task) -> None:
        info = self._workers.get(uid)
        if info and info.get("task") is task:
            self._workers.pop(uid, None)

    # ─────────────────────────────────────────────────────────────
    # TO'XTATISH
    # ─────────────────────────────────────────────────────────────
    async def stop_worker(self, uid: int, timeout: float = 10.0) -> bool:
        """Worker'ni to'xtatish (graceful)."""
        async with self._lock:
            info = self._workers.pop(uid, None)
        if not info:
            return False

        stop_event = info["stop_event"]
        task = info["task"]

        stop_event.set()

        try:
            await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            log(f"⚠️ Worker:{uid} timeout, cancel qilinadi", "warning")
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        except Exception:
            pass

        log(f"🔴 Worker:{uid} to'xtatildi (jami {len(self._workers)})")
        return True

    async def stop_all(self) -> None:
        """Barcha workerlarni to'xtatish."""
        uids = list(self._workers.keys())
        log(f"🛑 Barcha workerlar to'xtatilmoqda ({len(uids)} ta)")
        await asyncio.gather(
            *[self.stop_worker(u) for u in uids],
            return_exceptions=True,
        )

    # ─────────────────────────────────────────────────────────────
    # SHUTDOWN
    # ─────────────────────────────────────────────────────────────
    async def wait_shutdown(self) -> None:
        """Shutdown signalini kutadi."""
        await self._shutdown_event.wait()

    # ─────────────────────────────────────────────────────────────
    # STATISTIKA
    # ─────────────────────────────────────────────────────────────
    def stats(self) -> dict:
        """Workerlarning holati."""
        running = sum(
            1
            for info in self._workers.values()
            if info["task"] and not info["task"].done()
        )
        return {
            "active_workers": running,
            "total_workers": len(self._workers),
            "max": self.max_workers,
        }

    def get_running_uids(self) -> list[int]:
        """Ishlayotgan worker uidlari."""
        return [
            uid
            for uid, info in self._workers.items()
            if info["task"] and not info["task"].done()
        ]
