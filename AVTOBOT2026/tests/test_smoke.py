"""
AVTOBOT v2 — smoke test va izolyatsiya testlari.

Ishga tushirish (loyiha ildizidan):
    python tests/test_smoke.py

Yoki virtual muhit bilan:
    venv/bin/python tests/test_smoke.py

Testlar haqiqiy Telegram serverlariga ULANMAYDI — barcha tashqi
chaqiruvlar (Telethon client, HTTP) mock/qo'g'irchoq obyektlar bilan.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import time

# ── Env (config import bo'lishi uchun) ──
os.environ.setdefault("API_ID", "1234567")
os.environ.setdefault("API_HASH", "test" * 8)
os.environ.setdefault("BOT_TOKEN", "123:TEST")
os.environ.setdefault("ADMIN_ID", "111")
os.environ.setdefault("HEALTH_PORT", "18923")
os.environ.setdefault("HEALTH_TOKEN", "secret-token")

# Loyiha ildizini sys.path ga qo'shish (tests/ ichidan ishlatilganda)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAIL: list[str] = []


def check(name: str, cond: bool) -> None:
    status = "✅" if cond else "❌"
    print(f"{status} {name}")
    if not cond:
        FAIL.append(name)


# ─────────────────────────────────────────────────────────────────────────
# 1) BAZA (database.py)
# ─────────────────────────────────────────────────────────────────────────
async def test_db():
    from core import database as db

    # Toza bazadan boshlaymiz (avvalgi ishga tushirish qoldiqlarisiz)
    with contextlib.suppress(Exception):
        os.remove("data/avtobot.db")
    await db.init_db()

    await db.upsert_user(1000)
    u = await db.get_user(1000)
    check("DB: user yaratildi", u is not None and u["uid"] == 1000)

    await db.set_session(1000, "sess-str")
    await db.add_chat(1000, "@guruh1")
    await db.add_chat(1000, "@guruh2")
    ok, _, pid = await db.add_post(1000, "salom", [], None)
    check("DB: guruh+post qo'shildi", (await db.count_chats(1000)) == 2 and pid)

    # Tariff
    await db.set_tariff_expires(1000, "2099-01-01 00:00:00")
    check("DB: tariff o'rnatildi", not await db.is_tariff_expired(1000))
    await db.set_tariff_expires(1000, "2020-01-01 00:00:00")
    check("DB: muddati o'tgan aniqlanadi", await db.is_tariff_expired(1000))

    # Referal
    await db.upsert_user(2000)
    await db.set_referrer(2000, 1000)
    check("DB: referal yozuvi", (await db.count_referrals(1000)) == 0)
    await db.try_count_referral(2000)
    check("DB: referal hisoblandi", (await db.count_referrals(1000)) == 1)

    stats = await db.get_stats()
    check("DB: statistika", stats["total_users"] >= 2)

    # Blok
    await db.set_blocked(1000, True)
    check("DB: blok", await db.is_blocked(1000))
    await db.set_blocked(1000, False)

    await db.delete_user(1000)
    check("DB: cascade o'chirish", (await db.count_chats(1000)) == 0)
    await db.close_db()

    # O'lik kod olib tashlanganini tekshirish
    check("DB: o'lik kod olib tashlangan", not hasattr(db, "get_last_day_users"))


# ─────────────────────────────────────────────────────────────────────────
# 2) IZOLYATSIYA — har foydalanuvchi alohida (ASOSIY SAVOL)
# ─────────────────────────────────────────────────────────────────────────
async def test_isolation():
    """Ikki foydalanuvchi (A va B) ma'lumotlari aralashmasligini tekshiradi."""
    from core import database as db

    with contextlib.suppress(Exception):
        os.remove("data/avtobot.db")
    await db.init_db()

    A, B = 1111, 2222
    await db.upsert_user(A)
    await db.upsert_user(B)
    await db.set_session(A, "sess-A")
    await db.set_session(B, "sess-B")
    await db.add_chat(A, "@a-guruh-1")
    await db.add_chat(A, "@a-guruh-2")
    await db.add_chat(B, "@b-guruh")
    await db.add_post(A, "A post", [], None)
    await db.add_post(B, "B post", [], None)
    await db.set_interval(A, 7)
    await db.set_interval(B, 90)

    # 1) Guruhlar ajratilgan
    check(
        "Izolyatsiya: guruhlar har userda o'ziniki",
        await db.get_chats(A) == ["@a-guruh-1", "@a-guruh-2"]
        and await db.get_chats(B) == ["@b-guruh"],
    )

    # 2) A guruhini o'chirsa — B nikiga tegmaydi
    await db.remove_chat(A, 0)
    check(
        "Izolyatsiya: A guruhini o'chirsa B qoladi",
        await db.get_chats(A) == ["@a-guruh-2"] and await db.get_chats(B) == ["@b-guruh"],
    )
    await db.clear_chats(A)
    check(
        "Izolyatsiya: A barcha guruhini o'chsa ham B qoladi",
        (await db.count_chats(A)) == 0 and (await db.count_chats(B)) == 1,
    )

    # 3) Sessiyalar ajratilgan
    await db.del_session(A)
    check(
        "Izolyatsiya: A sessiyasi o'chsa B qoladi",
        (await db.get_session(A)) == "" and (await db.get_session(B)) == "sess-B",
    )

    # 4) Postlar va interval
    posts_b = await db.get_posts(B)
    check(
        "Izolyatsiya: postlar aralashmaydi",
        len(posts_b) == 1 and posts_b[0]["text"] == "B post",
    )
    check(
        "Izolyatsiya: interval har userda o'ziniki",
        (await db.get_interval(A)) == 7 and (await db.get_interval(B)) == 90,
    )

    # 5) Blok / running flaglari
    await db.set_blocked(A, True)
    await db.set_running(A, False)
    await db.set_running(B, True)
    check(
        "Izolyatsiya: A bloklansa B ochiq",
        await db.is_blocked(A) and not await db.is_blocked(B),
    )
    ua, ub = await db.get_user(A), await db.get_user(B)
    check(
        "Izolyatsiya: running flaglari mustaqil",
        not ua["running"] and ub["running"],
    )
    await db.set_blocked(A, False)

    # 6) A ni BUTUNLAY o'chirish → B to'liq saqlanadi
    await db.delete_user(A)
    check(
        "Izolyatsiya: A o'chirilsa B to'liq qoladi",
        await db.get_user(B) is not None
        and (await db.count_chats(B)) == 1
        and len(await db.get_posts(B)) == 1
        and (await db.get_session(B)) == "sess-B",
    )
    async with db._conn().execute("SELECT COUNT(*) AS n FROM posts") as cur:
        row = await cur.fetchone()
    check("Izolyatsiya: A ma'lumotlari cascade o'chgan", row["n"] == 1)

    # 7) Referal ajratilgan
    await db.upsert_user(3333)
    await db.set_referrer(3333, B)
    await db.try_count_referral(3333)
    check(
        "Izolyatsiya: referal faqat egasiga hisoblanadi",
        (await db.count_referrals(B)) == 1,
    )

    await db.close_db()


# ─────────────────────────────────────────────────────────────────────────
# 3) RATE LIMITER (rate_limit.py)
# ─────────────────────────────────────────────────────────────────────────
async def test_rate_limiter():
    from core.rate_limit import RateLimiter

    rl = RateLimiter(window_s=1)
    ok_all = all(rl.is_allowed(1, "command") for _ in range(30))
    check("RateLimiter: limit ichida ruxsat", ok_all)
    check("RateLimiter: limit oshsa blok", not rl.is_allowed(1, "command"))
    # Har user alohida hisoblanadi
    check("RateLimiter: boshqa user ta'sir qilmaydi", rl.is_allowed(2, "command"))
    await asyncio.sleep(1.05)
    check("RateLimiter: oyna o'tgach ruxsat", rl.is_allowed(1, "command"))


# ─────────────────────────────────────────────────────────────────────────
# 4) WORKER MANAGER (worker/worker.py)
# ─────────────────────────────────────────────────────────────────────────
async def test_worker_manager():
    from worker.worker import WorkerManager

    wm = WorkerManager(max_workers=3)

    async def dying_worker(uid, stop):
        # O'z-o'zidan tugap qoladi (stop signalisiz)
        await asyncio.sleep(0.05)

    async def living_worker(uid, stop):
        try:
            await stop.wait()
        except asyncio.CancelledError:
            pass

    wm.set_worker_factory(dying_worker)
    for uid in (1, 2, 3, 4, 5):
        await wm.start_worker(uid)
    await asyncio.sleep(0.2)

    wm.set_worker_factory(living_worker)
    ok = [await wm.start_worker(uid) for uid in (10, 11, 12)]
    check(
        "WorkerManager: o'lik tasklar limitni to'smaydi",
        all(ok) and wm.stats()["active_workers"] == 3,
    )
    check("WorkerManager: limit ishlaydi", not await wm.start_worker(13))

    await wm.stop_all()
    check("WorkerManager: stop_all tozalaydi", wm.stats()["active_workers"] == 0)

    # Crash qilgan worker ham ro'yxatdan chiqadi
    async def crashing_worker(uid, stop):
        raise RuntimeError("test crash")

    wm.set_worker_factory(crashing_worker)
    await wm.start_worker(20)
    await asyncio.sleep(0.1)
    check(
        "WorkerManager: crash qilgan worker tozalanadi",
        not wm.is_running(20) and len(wm._workers) == 0,
    )


async def test_worker_isolation():
    """Ikkala workerni ishga tushirib, bittasini to'xtatamiz."""
    from worker.worker import WorkerManager

    wm = WorkerManager(max_workers=10)

    async def fakeworker(uid, stop):
        try:
            await stop.wait()
        except asyncio.CancelledError:
            pass

    wm.set_worker_factory(fakeworker)
    await wm.start_worker(1)
    await wm.start_worker(2)
    check(
        "Izolyatsiya: ikkala worker mustaqil ishlaydi",
        wm.is_running(1) and wm.is_running(2),
    )

    await wm.stop_worker(1)
    await asyncio.sleep(0.05)
    check(
        "Izolyatsiya: 1-to'xtadi, 2-ishlashda davom etadi",
        not wm.is_running(1) and wm.is_running(2),
    )
    await wm.stop_all()


# ─────────────────────────────────────────────────────────────────────────
# 5) CLIENT POOL (worker/client_pool.py) — mock bilan
# ─────────────────────────────────────────────────────────────────────────
async def test_client_pool():
    from worker import client_pool as cp

    class FakeClient:
        gate = None  # test uchun to'siq (faqat 'slow' sessiyaga)

        def __init__(self, session, api_id, api_hash):
            self.session = session
            self.connected = False
            self.disconnect_calls = 0

        def is_connected(self):
            return self.connected

        async def connect(self):
            if FakeClient.gate is not None and "slow" in str(self.session):
                await FakeClient.gate.wait()
            await asyncio.sleep(0.01)
            self.connected = True
            return self

        async def disconnect(self):
            self.connected = False
            self.disconnect_calls += 1
            return None

        async def is_user_authorized(self):
            return True

    cp.TelegramClient = FakeClient
    cp.StringSession = lambda s="": s

    pool = cp.ClientPool(1, "h", max_clients=3)

    # ── Oddiy acquire/release ──
    c1 = await pool.acquire(100, "sess1")
    check("Pool: acquire", c1 is not None and pool.stats()["in_use"] == 1)
    try:
        await pool.acquire(100, "sess1")
        check("Pool: band client PoolBusy", False)
    except cp.PoolBusyError:
        check("Pool: band client PoolBusy", True)
    await pool.release(100)
    c1b = await pool.acquire(100, "sess1")
    check("Pool: release'dan keyin qayta olish", c1b is c1)

    # ── Izolyatsiya: har user O'Z sessiyasi bilan alohida client ──
    # (alohida pool — asosiy test oqimiga xalaqit bermasligi uchun)
    iso = cp.ClientPool(1, "h", max_clients=2)
    cA = await iso.acquire(500, "sess-A")
    cB = await iso.acquire(600, "sess-B")
    check(
        "Izolyatsiya: har user alohida client, sessiya aralashmaydi",
        cA is not cB and cA.session == "sess-A" and cB.session == "sess-B",
    )
    await iso.stop()

    # ── Sessiya o'zgarsa eski client yopiladi ──
    c_new = await pool.acquire(100, "sess2")
    await asyncio.sleep(0.01)
    check("Pool: sessiya almashinuvi", c_new is not c1 and c1.disconnect_calls == 1)

    # ── Sekin ulanish BOSHQA userlarni bloklamaydi ──
    FakeClient.gate = asyncio.Event()
    slow = asyncio.create_task(pool.acquire(200, "slow-sess"))
    await asyncio.sleep(0.05)
    loop = asyncio.get_event_loop()
    t0 = loop.time()
    c_fast = await pool.acquire(300, "fast-sess")
    dt = loop.time() - t0
    check("Pool: sekin ulanish boshqalarni bloklamaydi", dt < 0.5 and c_fast is not None)

    FakeClient.gate.set()
    await slow
    check("Pool: slow ham tugadi", slow.done() and not slow.exception())
    FakeClient.gate = None
    check("Pool: slow poolga kirdi", pool.stats()["total_clients"] == 3)

    # ── Limit to'la → PoolBusy ──
    await pool.release(100)
    await pool.release(300)
    ok = False
    try:
        await pool.acquire(400, "s4")
    except cp.PoolBusyError:
        ok = True
    check("Pool: limit to'la → PoolBusy", ok)

    await pool.remove(100)
    check("Pool: remove", 100 not in pool._pool)

    await pool.stop()


# ─────────────────────────────────────────────────────────────────────────
# 6) LOGIN — SMS yozuvlari tozalanishi (bot/login.py)
# ─────────────────────────────────────────────────────────────────────────
async def test_login_prune():
    from bot import login as Login

    Login.sms_attempts[999] = [time.time() - 10_000]  # eskirgan
    Login.sms_attempts[998] = [time.time()]           # yangi — qoladi
    pruned = Login.prune_sms_attempts()
    check(
        "Login: eski SMS yozuv tozalanadi",
        pruned == 1 and 999 not in Login.sms_attempts and 998 in Login.sms_attempts,
    )


# ─────────────────────────────────────────────────────────────────────────
# 7) GURUHLAR — sessiyasiz fatal (bot/groups.py)
# ─────────────────────────────────────────────────────────────────────────
async def test_groups_fatal():
    from bot.groups import add_groups_for
    from core import database as db

    await db.init_db()
    await db.upsert_user(555)  # sessiyasiz
    added, dup, err, fatal = await add_groups_for(555, ["@x"])
    check("Groups: sessiyasiz → fatal xabar", fatal is not None and not added)
    await db.close_db()


# ─────────────────────────────────────────────────────────────────────────
# 8) HEALTH SERVER + TOKEN (worker/health.py)
# ─────────────────────────────────────────────────────────────────────────
async def test_health_token():
    from worker.health import HealthServer

    hs = HealthServer()
    hs.set_stats_providers(
        lambda: {"active_workers": 1, "max": 5},
        lambda: {},
    )
    await hs.start()
    import aiohttp

    async with aiohttp.ClientSession() as sess:
        async with sess.get("http://127.0.0.1:18923/health") as r:
            check("Health: tokensiz → 401", r.status == 401)
        async with sess.get("http://127.0.0.1:18923/health?token=secret-token") as r:
            check("Health: token bilan → 200", r.status == 200)
            data = await r.json()
            check("Health: ma'lumot to'g'ri", data["status"] == "ok")
        async with sess.get(
            "http://127.0.0.1:18923/health",
            headers={"Authorization": "Bearer secret-token"},
        ) as r:
            check("Health: Bearer bilan → 200", r.status == 200)
    await hs.stop()


# ─────────────────────────────────────────────────────────────────────────
# 9) MATNLAR (bot/texts.py)
# ─────────────────────────────────────────────────────────────────────────
async def test_texts():
    from bot import texts as T

    check("Texts: CANCEL_WORDS bor", "bekor" in T.CANCEL_WORDS)
    check("Texts: FSM_TIMEOUT bor", "Vaqt tugadi" in T.FSM_TIMEOUT)
    check("Texts: ASK_ADD_GROUP hint", "bekor" in T.ASK_ADD_GROUP)
    check("Texts: ask_interval hint", "bekor" in T.ask_interval(60))


# ─────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────
async def main() -> None:
    await test_db()
    await test_isolation()
    await test_rate_limiter()
    await test_worker_manager()
    await test_worker_isolation()
    await test_client_pool()
    await test_login_prune()
    await test_groups_fatal()
    await test_health_token()
    await test_texts()

    print()
    total = 0
    if FAIL:
        print(f"❌ {len(FAIL)} ta test o'tmadi: {FAIL}")
        sys.exit(1)
    print("✅ BARCHA TESTLAR O'TDI")


if __name__ == "__main__":
    asyncio.run(main())
