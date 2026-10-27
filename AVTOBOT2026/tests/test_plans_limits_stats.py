"""Tarif paketlari, limitlar, kunlik/tungi cheklov va yuborish hisoboti.

Qamlov:
- paketsiz (eski) foydalanuvchi uchun limitlar = cheksiz;
- paket berilsa guruh/post soni shu paketga qadaladi;
- kunlik limit va faol soatlar workerga «kutiladi» degan buyruq beradi,
  lekin navbatni buzmaydi;
- yuborish jurnali (send_logs) hisobot, guruh salomatligi va ETA uchun
  ishlaydi hamda eskirgach tozalanadi;
- bonus kunlar mavjud muddat USTIGA qo'shiladi (give_new_term kabi uni
  almashtirmaydi), cheksiz tarifga tegmaydi;
- Status/Hisobot matnida foydalanuvchi o'z chegaralarini ko'radi.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from cryptography.fernet import Fernet  # noqa: E402

from bot import menu  # noqa: E402
from bot import texts as T  # noqa: E402
from config.config import DEFAULT_DURATION_DAYS  # noqa: E402
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402
from core.utils import calc_expires, format_expires  # noqa: E402
from worker import worker as W  # noqa: E402

FROZEN_NOW = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)


def iso_after(days: float) -> str:
    return (FROZEN_NOW + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


class PlanLimitsStatsTestCase(unittest.IsolatedAsyncioTestCase):
    UID = 2001

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        await db.upsert_user(
            self.UID, name="Ali", is_admin=1, tariff_expires_at=iso_after(30)
        )
        self._patches = [
            patch("core.utils.now_utc", return_value=FROZEN_NOW),
            patch("core.utils.now_local", return_value=FROZEN_NOW.astimezone().replace(tzinfo=None)),
        ]
        for patcher in self._patches:
            patcher.start()

    async def asyncTearDown(self) -> None:
        for patcher in reversed(self._patches):
            patcher.stop()
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    # ── 1. Limitlar ──
    async def test_no_plan_means_unlimited(self) -> None:
        self.assertEqual(await db.max_groups_for(self.UID), 0)
        self.assertEqual(await db.max_posts_for(self.UID), 0)
        for index in range(6):
            ok, reason = await db.add_chat(self.UID, f"@group{index}")
            self.assertTrue(ok, reason)
        for index in range(6):
            ok, reason, _ = await db.add_post(self.UID, f"post {index}", [], None)
            self.assertTrue(ok, reason)

    async def test_plan_caps_groups_and_posts(self) -> None:
        limits = await db.set_plan(self.UID, "SINOV")
        self.assertEqual(limits["max_groups"], 5)
        self.assertEqual(limits["max_posts"], 2)

        for index in range(5):
            ok, _ = await db.add_chat(self.UID, f"@group{index}")
            self.assertTrue(ok)
        ok, reason = await db.add_chat(self.UID, "@group6")
        self.assertFalse(ok)
        self.assertEqual(reason, "limit")

        self.assertTrue((await db.add_post(self.UID, "p1", [], None))[0])
        self.assertTrue((await db.add_post(self.UID, "p2", [], None))[0])
        ok, reason, post_id = await db.add_post(self.UID, "p3", [], None)
        self.assertFalse(ok)
        self.assertEqual(reason, "limit")
        self.assertIsNone(post_id)

    async def test_manual_limits_override_plan_label(self) -> None:
        await db.set_plan(self.UID, "PRO")
        self.assertTrue(
            await db.set_user_limits(
                self.UID, max_groups=7, daily_limit=10, active_hours="09:00-18:00"
            )
        )
        limits = await db.get_limits(self.UID)
        self.assertEqual(limits["plan"], "PRO")
        self.assertEqual(limits["max_groups"], 7)
        self.assertEqual(limits["daily_limit"], 10)
        self.assertEqual(limits["active_hours"], "09:00-18:00")
        self.assertEqual(await db.max_groups_for(self.UID), 7)
        # Noto'g'ri vaqt oynasi qabul qilinmaydi.
        self.assertFalse(await db.set_user_limits(self.UID, active_hours="25:00-99:00"))

    async def test_daily_limit_pauses_worker_without_losing_queue(self) -> None:
        await db.set_user_limits(self.UID, daily_limit=2)
        await db.add_chat(self.UID, "@g1")
        gid = int((await db.get_chat_records(self.UID))[0]["id"])
        user = await db.get_user(self.UID)
        allowed, wait_s, reason = await W.posting_window_state(self.UID, user)
        self.assertTrue(allowed)
        self.assertEqual(wait_s, 0)

        await db.log_send(self.UID, True, group_id=gid, post_id=None)
        await db.log_send(self.UID, True, group_id=gid, post_id=None)
        allowed, wait_s, reason = await W.posting_window_state(self.UID, user)
        self.assertFalse(allowed)
        self.assertIn("Kunlik limit", reason)
        self.assertGreaterEqual(wait_s, 60)
        self.assertLessEqual(wait_s, 3600)

        # Muvaffaqiyatsiz urinishlar kunlik limitni iste'mol qilmaydi.
        await db.set_user_limits(self.UID, daily_limit=3)
        await db.log_send(self.UID, False, group_id=gid, error="Forbidden")
        allowed, _, _ = await W.posting_window_state(self.UID, await db.get_user(self.UID))
        self.assertTrue(allowed)

    async def test_active_hours_pause_outside_window(self) -> None:
        await db.set_user_limits(self.UID, active_hours="09:00-11:00")
        user = await db.get_user(self.UID)
        # Qotirilgan "hozir" 12:00 → oyna tashqarisida.
        allowed, wait_s, reason = await W.posting_window_state(self.UID, user)
        self.assertFalse(allowed)
        self.assertIn("Ish vaqti", reason)
        self.assertLessEqual(wait_s, 3600)

        await db.set_user_limits(self.UID, active_hours="11:30-23:00")
        allowed, _, _ = await W.posting_window_state(
            self.UID, await db.get_user(self.UID)
        )
        self.assertTrue(allowed)

    # ── 2. Hisobot ──
    async def test_send_logs_stats_and_prune(self) -> None:
        await db.add_chat(self.UID, "@g1")
        await db.add_chat(self.UID, "@g2")
        records = await db.get_chat_records(self.UID)
        g1, g2 = int(records[0]["id"]), int(records[1]["id"])
        now = time.time()

        await db.log_send(self.UID, True, group_id=g1, post_id=1)
        await db.log_send(self.UID, True, group_id=g1, post_id=1)
        await db.log_send(self.UID, False, group_id=g2, error="Flooding")
        # Juda eski yozuv — saqlash muddatidan tashqarida.
        await db.log_send(self.UID, True, group_id=g1, sent_at=now - 400 * 86400)

        stats = await db.send_stats(self.UID)
        self.assertEqual(stats["sent_ok"], 3)
        self.assertEqual(stats["sent_failed"], 1)
        self.assertIn("Flooding", str(stats.get("last_error") or ""))

        health = await db.group_health(self.UID)
        by_group = {int(row["id"]): row for row in health}
        self.assertEqual(int(by_group[g1]["last_ok"]), 1)
        # 3 = 2 ta bugungi + 1 ta juda eski (hali tozalanmagan) yozuv.
        self.assertEqual(int(by_group[g1]["sent_ok"]), 3)
        self.assertEqual(int(by_group[g2]["last_ok"]), 0)
        self.assertEqual(int(by_group[g2]["sent_failed"]), 1)
        # Hech qachon sinovdan o'tmagan guruh "buzilgan" deb sanalmaydi.
        await db.add_chat(self.UID, "@g3")
        fresh_health = await db.group_health(self.UID)
        never_used = [row for row in fresh_health if row["value"] == "@g3"][0]
        self.assertIsNone(never_used["last_ok"])
        self.assertEqual(
            sum(1 for row in fresh_health if row.get("last_ok") == 0), 1
        )

        self.assertEqual(await db.count_sent_ok(self.UID, 0), 3)
        global_stats = await db.global_send_stats(0)
        self.assertEqual(int(global_stats["ok"]), 3)
        self.assertEqual(int(global_stats["failed"]), 1)
        self.assertEqual(int(global_stats["active_users"]), 1)
        self.assertIn("Flooding", [name for name, _count in global_stats["errors"]])

        removed = await db.prune_send_logs(retention_days=30)
        self.assertEqual(removed, 1)
        self.assertEqual(await db.count_sent_ok(self.UID, 0), 2)

    async def test_next_send_eta_follows_group_queue(self) -> None:
        await db.add_chat(self.UID, "@g1")
        record = await db.get_chat_records(self.UID)
        gid = int(record[0]["id"])
        self.assertIsNone(await db.next_send_eta(self.UID))

        future = time.time() + 600
        await db.record_chat_attempt(self.UID, gid, time.time(), 0)
        await db._conn().execute(
            "UPDATE groups SET next_send_at = ? WHERE id = ?", (future, gid)
        )
        await db._conn().commit()
        eta = await db.next_send_eta(self.UID)
        self.assertIsNotNone(eta)
        self.assertAlmostEqual(float(eta), future, delta=2)

    # ── 3. Bonus kunlar ──
    async def test_bonus_days_are_added_to_remaining_time(self) -> None:
        expires, err = await db.add_bonus_days(self.UID, 7, note="Test")
        self.assertIsNone(err)
        self.assertEqual(expires, iso_after(37))
        user = await db.get_user(self.UID)
        self.assertEqual(int(user["referral_bonus_days"]), 7)
        self.assertIn("Test", user["referral_bonus_note"] or "")

        # Qaytarma (manfiy) kunlar ham hisobga olinadi.
        expires, err = await db.add_bonus_days(self.UID, -2, note="Bekor qilindi")
        self.assertIsNone(err)
        self.assertEqual(expires, iso_after(35))

    async def test_bonus_days_do_not_limit_unlimited_tariff(self) -> None:
        await db.set_tariff_expires(self.UID, None)
        expires, err = await db.add_bonus_days(self.UID, 30)
        self.assertIsNone(err)
        self.assertIsNone(expires)
        user = await db.get_user(self.UID)
        self.assertIsNone(user["tariff_expires_at"] or None)

    async def test_expired_tariff_bonus_starts_from_now(self) -> None:
        await db.set_tariff_expires(self.UID, iso_after(-5))
        expires, err = await db.add_bonus_days(self.UID, DEFAULT_DURATION_DAYS)
        self.assertIsNone(err)
        self.assertEqual(expires, calc_expires(DEFAULT_DURATION_DAYS))

    async def test_unknown_user_reports_error(self) -> None:
        self.assertEqual(
            await db.add_bonus_days(999999, 5), (None, "Foydalanuvchi topilmadi.")
        )

    # ── 4. UI matnlari ──
    async def test_status_snapshot_and_texts(self) -> None:
        await db.set_plan(self.UID, "SINOV")
        await db.add_chat(self.UID, "@g1")
        await db.add_post(self.UID, "e'lon", [], None)
        await db.set_interval(self.UID, 45)

        snapshot = await menu._status_snapshot(self.UID)
        self.assertEqual(len(snapshot["chats"]), 1)
        self.assertEqual(snapshot["interval"], 45)
        self.assertEqual(snapshot["limits"]["max_groups"], 5)

        status = T.status_text(
            running=False,
            expired=False,
            groups=1,
            posts=1,
            interval=45,
            expires=format_expires(snapshot["expires"]),
            max_groups=5,
            max_posts=2,
            daily_left="0/30",
            active_hours="08:00-22:00",
            plan_label="🆓 Sinov",
            today_ok=4,
            today_failed=1,
            next_eta="2 daq. keyin",
        )
        self.assertIn("Sinov", status)
        self.assertIn("5", status)
        self.assertIn("4", status)
        self.assertIn("2 daq. keyin", status)

        report = T.report_text(
            today_ok=4,
            today_failed=1,
            week_ok=40,
            groups_total=1,
            groups_failed=1,
            next_eta="—",
            last_error="Flooding",
            daily_left="26 ta qoldi",
            active_hours="08:00-22:00",
            running=True,
        )
        self.assertIn("Flooding", report)
        self.assertIn("26 ta qoldi", report)
        self.assertIn("⚠️ 1 ta guruhda", report)
        report_global = T.report_text(
            today_ok=1,
            today_failed=0,
            week_ok=1,
            groups_total=1,
            groups_failed=0,
            next_eta="—",
            last_error="",
            daily_left="",
            active_hours="",
            running=True,
            global_today={"ok": 120, "failed": 5, "success_rate": 96.0},
        )
        self.assertIn("96% muvaffaqiyat", report_global)

        plan = T.plan_text(
            limits=snapshot["limits"],
            interval=45,
            expires=format_expires(snapshot["expires"]),
            daily_left="1/30",
        )
        self.assertIn("Sinov", plan)

    async def test_next_step_hint_points_to_missing_piece(self) -> None:
        self.assertIn("Guruh", T.status_next_step(0, 3))
        self.assertIn("Post", T.status_next_step(3, 0))
        self.assertEqual(T.status_next_step(3, 3), "")

    async def test_new_menu_buttons_open_their_screens(self) -> None:
        """Yangi yassi menyu tugmalari to'g'ri funksiyaga boradi."""
        from bot import groups as G
        from bot import menu as M
        from bot import posts as P
        from bot import referral as R
        from bot import timer as Tm

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=self.UID),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        targets = {
            T.BTN_FIND_GROUPS: (G, "discover_groups"),
            T.BTN_DEL_GROUP: (G, "begin_delete_groups"),
            T.BTN_ADD_POST: (P, "begin_add_post"),
            T.BTN_DEL_POST: (P, "begin_delete_posts"),
            T.BTN_TIMER: (Tm, "begin_set_interval"),
            T.BTN_REPORT: (M, "show_report"),
            T.BTN_REFERRAL: (R, "show_referral"),
        }
        for label, (module, name) in targets.items():
            with self.subTest(label=label):
                calls = []

                async def _spy(update, _name=name, _calls=calls):
                    _calls.append(_name)

                with patch.object(module, name, new=_spy):
                    handled = await M.route_menu_button(update, label)
                self.assertTrue(handled)
                self.assertEqual(calls, [name])

        # Start/Stop endi holatni yorliqda olib yuradi: "▶️ Start (🔴 OFF)".
        with patch.object(M, "handle_start", new=AsyncMock()) as start_spy:
            self.assertTrue(
                await M.route_menu_button(update, f"{T.BTN_START} (🔴 OFF)")
            )
            start_spy.assert_awaited_once()
        with patch.object(M, "handle_stop", new=AsyncMock()) as stop_spy:
            self.assertTrue(
                await M.route_menu_button(update, f"{T.BTN_STOP} (🟢 ON)")
            )
            stop_spy.assert_awaited_once()

    async def test_removed_buttons_are_not_routed_anymore(self) -> None:
        """Olib tashlangan tugmalar endi routerda javob bermaydi."""
        from bot import menu as M

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=self.UID),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        for label in (
            T.BTN_GROUPS,
            T.BTN_POSTS,
            T.BTN_ADD_GROUP,
            T.BTN_GROUP_INTERVAL,
            T.BTN_CHECK_GROUPS,
            T.BTN_EDIT_POST,
            T.BTN_PREVIEW_POST,
            T.BTN_TEST_SEND,
            T.BTN_ACCOUNT,
        ):
            with self.subTest(label=label):
                self.assertFalse(await M.route_menu_button(update, label))

    def test_menu_button_press_during_input_window_is_routed(self) -> None:
        """Kiritish oynasida menyu tugmasi bosilsa mavjud funksiya chaqiriladi."""
        source = (APP_DIR / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("Menu.handle_menu", source)
        self.assertIn("Menu.route_menu_button", source)

    async def test_status_report_plan_screens_render(self) -> None:
        """Ekranlar haqiqiy baza bilan xatosiz ochiladi (import/NameError regressiyasi)."""
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        await db.set_plan(self.UID, "PRO")
        await db.add_chat(self.UID, "@g1")
        await db.add_post(self.UID, "e'lon", [], None)
        await db.log_send(self.UID, True, group_id=1)
        await db.touch_last_active(self.UID)

        async def render(fn):
            update = SimpleNamespace(
                effective_user=SimpleNamespace(id=self.UID),
                message=SimpleNamespace(reply_text=AsyncMock()),
            )
            await fn(update)
            return update.message.reply_text.await_args.args[0]

        for fn, headings in (
            (menu.show_status, ("STATUS",)),
            # Hisobot endi paket/limitlarni ham o'z ichiga oladi — bitta ekran.
            (menu.show_report, ("HISOBOT", "PAKET")),
            (menu.show_plan, ("PAKET",)),
        ):
            with self.subTest(fn=fn.__name__):
                text = await render(fn)
                for heading in headings:
                    self.assertIn(heading, text.upper())
                self.assertGreater(len(text), 80)

    async def test_menu_buttons_route_to_new_screens(self) -> None:
        routes = {
            T.BTN_REPORT: "show_report",
            T.BTN_FIND_GROUPS: "discover_groups",
        }
        source = Path(APP_DIR / "bot/menu.py").read_text(encoding="utf-8")
        for label, target in routes.items():
            self.assertIn(label, source)
            self.assertIn(target, source)
        # Hisobot ekrani paket/limitlarni ham chiqaradi (bitta tugma, bitta ekran).
        self.assertIn("plan_text", source)
        # Yangi yassi menyu tugmalari main FSM escape ro'yxatida ham bo'lishi kerak.
        main_source = Path(APP_DIR / "main.py").read_text(encoding="utf-8")
        for name in (
            "BTN_FIND_GROUPS",
            "BTN_ADD_POST",
            "BTN_DEL_POST",
            "BTN_REPORT",
        ):
            self.assertIn(name, main_source)
        # Olib tashlangan tugmalar routerda bo'lmasligi kerak.
        for name in ("BTN_CHECK_GROUPS", "BTN_EDIT_POST", "BTN_ACCOUNT"):
            self.assertNotIn(name, source)
        # Klaviaturada alohida Status/Paket tugmasi qolmagan.
        kb_source = Path(APP_DIR / "bot/keyboards.py").read_text(encoding="utf-8")
        self.assertNotIn("KeyboardButton(T.BTN_STATUS)", kb_source)
        self.assertNotIn("KeyboardButton(T.BTN_PLAN)", kb_source)


if __name__ == "__main__":
    unittest.main()
