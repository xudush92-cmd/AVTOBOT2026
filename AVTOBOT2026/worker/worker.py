"""
Posting worker — asosiy sikl.

Har bir foydalanuvchi uchun:
1. Guruhlarni oladi
2. Postlarni oladi (rotation bilan)
3. Har bir guruhga yuboradi
4. Xatolarni kuzatadi
5. Interval kutadi
"""

from __future__ import annotations

import asyncio
import contextlib
import random

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
    MIN_INTERVAL_MIN,
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
    """Guruh entity'sini topadi."""
    s = chat.strip()
    if s.startswith("@"):
        return await client.get_entity(s)
    if s.lstrip("-").isdigit():
        return await client.get_entity(int(s))
    if s.startswith("https://t.me/") or s.startswith("t.me/"):
        return await client.get_entity(s)
    return await client.get_entity(s)


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
    """
    Asosiy posting sikli.

    Ishlash:
    - 0-60 soniya tasodifiy kechikish (start jitter)
    - Har sikl:
        1. Guruhlarni olish
        2. Postlarni olish
        3. Navbatdagi postni tanlash (rotation)
        4. Har bir guruhga yuborish
        5. Xatolarni kuzatish
        6. Interval kutish
    """
    log(f"🟢 Worker:{uid} ishga tushdi")

    # ── START JITTER ──
    first_delay = random.randint(0, START_JITTER_S)
    if first_delay:
        log(f"⏳ Worker:{uid} start jitter {first_delay}s")
        if await sleep_or_stop(stop, first_delay):
            return

    # Post indeksi (rotation uchun)
    post_index = 0
    # Har bir guruh uchun ketma-ket xato hisoblagichi
    group_fails: dict[str, int] = {}

    try:
        while not stop.is_set():
            # Har siklda ruxsatlarni qayta tekshiramiz: blok/tarif/sessiya
            # uzoq ishlayotgan worker ichida ham darhol kuchga kiradi.
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

            # Ma'lumotlarni olish
            chats = await db.get_chats(uid)
            posts = await db.get_posts(uid)
            interval = await db.get_interval(uid)

            if not chats or not posts:
                if await sleep_or_stop(stop, 30):
                    break
                continue

            # Client olish
            try:
                client = await client_pool.acquire(uid, session)
            except SessionInvalidError:
                log(f"🚫 Worker:{uid} — sessiya yaroqsiz", "warning")
                await db.del_session(uid)
                await db.set_running(uid, False)
                await client_pool.remove(uid)
                with contextlib.suppress(Exception):
                    await application.bot.send_message(
                        uid,
                        "🚫 Sessiyangiz Telegram tomonidan bekor qilindi.\n"
                        "Qaytadan 🔑 Login qiling.",
                    )
                break
            except PoolBusyError:
                log(f"⏳ Worker:{uid} — pool band, 30s kutadi", "warning")
                if await sleep_or_stop(stop, 30):
                    break
                continue

            # Yuborish
            try:
                # Navbatdagi post
                post_index %= len(posts)
                post = posts[post_index]
                post_index += 1

                ok, fail = 0, 0
                removed_groups: list[str] = []

                for chat in chats:
                    if stop.is_set():
                        break

                    try:
                        await asyncio.wait_for(
                            send_post(client, chat, post), timeout=20
                        )
                        ok += 1
                        group_fails[chat] = 0
                        log(f"✅ {uid} → {chat}")

                    except FloodWaitError as e:
                        wait_s = int(getattr(e, "seconds", 30)) + 5
                        log(f"⏳ {uid} → {chat} FloodWait {wait_s}s", "warning")
                        if await sleep_or_stop(stop, wait_s):
                            break

                    except (
                        ChatWriteForbiddenError,
                        ChannelPrivateError,
                        PeerIdInvalidError,
                        UsernameNotOccupiedError,
                        UsernameInvalidError,
                        ValueError,
                    ) as e:
                        fail += 1
                        group_fails[chat] = group_fails.get(chat, 0) + 1
                        log(
                            f"❌ {uid} → {chat}: {type(e).__name__} "
                            f"({group_fails[chat]}/{MAX_GROUP_FAILS})",
                            "warning",
                        )
                        if group_fails[chat] >= MAX_GROUP_FAILS:
                            removed_groups.append(chat)

                    except asyncio.TimeoutError:
                        fail += 1
                        group_fails[chat] = group_fails.get(chat, 0) + 1
                        log(
                            f"⏱ {uid} → {chat} timeout "
                            f"({group_fails[chat]}/{MAX_GROUP_FAILS})",
                            "warning",
                        )
                        if group_fails[chat] >= MAX_GROUP_FAILS:
                            removed_groups.append(chat)

                    except (AuthKeyUnregisteredError, UserDeactivatedBanError) as e:
                        log(f"🚫 {uid} sessiya yaroqsiz: {type(e).__name__}", "error")
                        await db.del_session(uid)
                        await db.set_running(uid, False)
                        await client_pool.remove(uid)
                        with contextlib.suppress(Exception):
                            await application.bot.send_message(
                                uid,
                                "🚫 Sessiyangiz bekor qilindi. Qaytadan 🔑 Login qiling.",
                            )
                        return

                    except Exception as e:
                        fail += 1
                        log(f"❌ {uid} → {chat}: {type(e).__name__}", "error")

                    if not stop.is_set():
                        await sleep_or_stop(stop, SEND_DELAY_S)

                # Xato bergan guruhlarni o'chirish
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

                log(f"📊 {uid} ✅{ok} ❌{fail} / {len(chats)}")

            finally:
                await client_pool.release(uid)

            # Keyingi sikl
            delay = interval * 60 + random.randint(-JITTER_S, JITTER_S)
            delay = max(MIN_INTERVAL_MIN * 60, delay)
            log(f"⏳ {uid} keyingi tur {delay}s ({interval} daq)")

            if await sleep_or_stop(stop, delay):
                break

    except asyncio.CancelledError:
        pass
    except Exception as e:
        log(f"💥 Worker:{uid} kutilmagan xato: {type(e).__name__}", "error")
        with contextlib.suppress(Exception):
            await application.bot.send_message(
                SUPER_ADMIN,
                f"⚠️ Worker xato\nUID: {uid}\n{type(e).__name__}",
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
