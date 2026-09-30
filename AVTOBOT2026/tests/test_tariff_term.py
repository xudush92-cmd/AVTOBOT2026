"""Tarif muddati: yangi muddat oldingisini bekor qiladi (ustiga qo'shilmaydi).

Qamrov:
- tayyor tugmalar (1/7/30/90 kun) mavjud muddat ustiga qo'shmaydi, balki uni
  almashtiradi: 30 kunlik userga yana 30 kun berilsa — 60 emas, 30 kun;
- qo'lda kiritilgan kunlar ham xuddi shunday ishlaydi;
- yangi muddat oldingisidan qisqa bo'lishi mumkin (oldingisi bekor bo'ladi);
- tugagan / cheksiz / noto'g'ri saqlangan muddat bilan ham natija bir xil;
- bir xil tugmani ikki marta bosish muddatni ikki barobar qilmaydi;
- oxirgi kun ogohlantirishi (``warned_at``) yangi muddat uchun qayta yoqiladi;
- admin va userga oldingi muddat bekor qilingani aniq aytiladi;
- tasdiqlash (approve) oqimi muddatga tegmaydi (faqat muddat bo'lmasa 30 kun).
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

import main  # noqa: E402
from admin import admin_actions  # noqa: E402
from bot import login  # noqa: E402
from bot import texts as T  # noqa: E402
from bot.keyboards import kb_expire_options  # noqa: E402
from config.config import DEFAULT_DURATION_DAYS, SUPER_ADMIN  # noqa: E402
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402
from core.utils import calc_expires  # noqa: E402

ISO_FORMAT = "%Y-%m-%d %H:%M:%S"
# Barcha testlarda "hozir" qotirilgan — kun hisobi aniq tekshiriladi.
FROZEN_NOW = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)


def iso_after(days: float) -> str:
    """Qotirilgan "hozir"dan ``days`` kun keyingi (manfiy bo'lsa oldingi) vaqt."""
    return (FROZEN_NOW + timedelta(days=days)).strftime(ISO_FORMAT)


class TermTestCase(unittest.IsolatedAsyncioTestCase):
    """Haqiqiy (vaqtinchalik) SQLite baza va qotirilgan vaqt bilan."""

    UID = 2001

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()

        login.user_states.clear()
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.app = SimpleNamespace(bot=self.bot)
        self._patches = [
            patch("core.utils.now_utc", return_value=FROZEN_NOW),
            patch.object(admin_actions, "application", self.app),
            patch.object(main, "application", self.app),
        ]
        for patcher in self._patches:
            patcher.start()

    async def asyncTearDown(self) -> None:
        for patcher in reversed(self._patches):
            patcher.stop()
        login.user_states.clear()
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    # ── yordamchilar ──
    async def seed_user(self, expires: str | None) -> None:
        await db.upsert_user(
            self.UID,
            name="Ali Valiyev",
            is_admin=1,
            tariff_expires_at=expires,
        )

    @staticmethod
    def callback_update():
        return SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock())
        )

    @staticmethod
    def message_update():
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )

    async def press(self, option: str, admin_uid: int = SUPER_ADMIN):
        """Adminning ``exp:<uid>:<option>`` tugmasini bosadi."""
        update = self.callback_update()
        await admin_actions.handle_expire(update, admin_uid, f"exp:{self.UID}:{option}")
        return update

    async def type_days(self, text: str):
        """Admin "✏️ Qo'lda kiritish" oynasiga matn yuboradi."""
        login.user_states[SUPER_ADMIN] = {
            "step": "admin_set_expire",
            "ts": time.time(),
            "target_uid": self.UID,
        }
        update = self.message_update()
        await main.handle_admin_fsm(update, SUPER_ADMIN, "admin_set_expire", text)
        return update

    @staticmethod
    def admin_text(update) -> str:
        if hasattr(update, "callback_query"):
            return update.callback_query.edit_message_text.await_args.args[0]
        return update.message.reply_text.await_args.args[0]

    async def expires(self) -> str | None:
        return await db.get_tariff_expires(self.UID)


# ─────────────────────────────────────────────────────────────────────────
# TAYYOR TUGMALAR (1 / 7 / 30 / 90 kun)
# ─────────────────────────────────────────────────────────────────────────
class ButtonTermReplacesOldTermTests(TermTestCase):
    async def test_new_30_days_replaces_active_term_instead_of_adding(self) -> None:
        await self.seed_user(iso_after(20))

        await self.press("30")

        # Eski xato: 20 + 30 = 50 kun. To'g'risi: aynan hozirdan 30 kun.
        self.assertEqual(await self.expires(), iso_after(30))
        self.assertNotEqual(await self.expires(), iso_after(50))

    async def test_default_30_days_then_new_30_days_is_30_not_60(self) -> None:
        """Xatolik stsenariysi: tasdiqda 30 kun, keyin admin yana 30 kun beradi."""
        await db.upsert_user(self.UID, name="Ali Valiyev", awaiting_approval=1)
        self.assertTrue(
            await db.approve_user(self.UID, calc_expires(DEFAULT_DURATION_DAYS))
        )
        self.assertEqual(await self.expires(), iso_after(DEFAULT_DURATION_DAYS))

        await self.press("30")

        self.assertEqual(await self.expires(), iso_after(30))

    async def test_shorter_new_term_cancels_longer_old_term(self) -> None:
        await self.seed_user(iso_after(90))

        await self.press("7")

        self.assertEqual(await self.expires(), iso_after(7))

    async def test_every_preset_button_counts_from_now(self) -> None:
        for days in (1, 7, 30, 90):
            with self.subTest(days=days):
                await self.seed_user(iso_after(45))
                await self.press(str(days))
                self.assertEqual(await self.expires(), iso_after(days))

    async def test_expired_unlimited_or_broken_old_term_gives_full_days(self) -> None:
        for label, old in (
            ("tugagan", iso_after(-5)),
            ("cheksiz (NULL)", None),
            ("bo'sh satr", ""),
            ("buzilgan qiymat", "noto'g'ri-sana"),
        ):
            with self.subTest(old=label):
                await self.seed_user(old)
                await db.set_tariff_expires(self.UID, old)
                await self.press("30")
                self.assertEqual(await self.expires(), iso_after(30))

    async def test_pressing_same_button_twice_does_not_double_the_term(self) -> None:
        await self.seed_user(iso_after(10))

        await self.press("30")
        await self.press("30")

        self.assertEqual(await self.expires(), iso_after(30))

    async def test_new_term_reenables_last_day_warning(self) -> None:
        await self.seed_user(iso_after(0.5))
        await db.mark_warned(self.UID)
        self.assertTrue(await db.is_warned(self.UID))

        await self.press("30")

        self.assertFalse(await db.is_warned(self.UID))

    async def test_forever_still_removes_the_limit(self) -> None:
        await self.seed_user(iso_after(20))

        update = await self.press("forever")

        self.assertIsNone(await self.expires())
        self.assertIn("cheklanmagan", self.admin_text(update))

    async def test_admin_sees_that_old_term_was_cancelled(self) -> None:
        await self.seed_user(iso_after(20))

        update = await self.press("30")

        text = self.admin_text(update)
        self.assertIn("Yangi muddat berildi: 30 kun", text)
        self.assertIn(iso_after(30)[:10], text)
        self.assertIn("Oldingi muddat bekor qilindi", text)
        self.assertIn(iso_after(20)[:10], text)
        self.assertIn("ustiga qo'shilmaydi", text)
        self.assertNotIn("uzaytirildi", text)

    async def test_user_is_notified_with_the_new_date(self) -> None:
        await self.seed_user(iso_after(20))

        await self.press("30")

        self.bot.send_message.assert_awaited_once()
        target, text = self.bot.send_message.await_args.args
        self.assertEqual(target, self.UID)
        self.assertIn("yangilandi", text)
        self.assertIn(iso_after(30)[:10], text)
        self.assertNotIn("uzaytirildi", text)

    async def test_out_of_range_button_days_keep_existing_term(self) -> None:
        await self.seed_user(iso_after(20))

        for option in ("0", "-5", "3651"):
            with self.subTest(option=option):
                update = await self.press(option)
                self.assertEqual(await self.expires(), iso_after(20))
                self.assertIn("1–3650", self.admin_text(update))
        self.bot.send_message.assert_not_awaited()

    async def test_only_super_admin_can_change_term(self) -> None:
        await self.seed_user(iso_after(20))

        update = await self.press("30", admin_uid=555)

        self.assertEqual(await self.expires(), iso_after(20))
        update.callback_query.edit_message_text.assert_not_awaited()
        self.bot.send_message.assert_not_awaited()

    async def test_missing_user_is_reported_and_nothing_is_created(self) -> None:
        update = await self.press("30")

        self.assertIsNone(await db.get_user(self.UID))
        self.assertIn("topilmadi", self.admin_text(update))
        self.bot.send_message.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────
# QO'LDA KIRITISH ("Necha kun muddat bermoqchisiz?")
# ─────────────────────────────────────────────────────────────────────────
class ManualTermReplacesOldTermTests(TermTestCase):
    async def test_manual_days_replace_active_term_instead_of_adding(self) -> None:
        await self.seed_user(iso_after(20))

        await self.type_days("15")

        self.assertEqual(await self.expires(), iso_after(15))
        self.assertNotEqual(await self.expires(), iso_after(35))

    async def test_manual_days_can_be_shorter_than_old_term(self) -> None:
        await self.seed_user(iso_after(200))

        await self.type_days("3")

        self.assertEqual(await self.expires(), iso_after(3))

    async def test_manual_days_with_expired_or_unlimited_term(self) -> None:
        for label, old in (("tugagan", iso_after(-1)), ("cheksiz", None)):
            with self.subTest(old=label):
                await self.seed_user(old)
                await db.set_tariff_expires(self.UID, old)
                await self.type_days("45")
                self.assertEqual(await self.expires(), iso_after(45))

    async def test_manual_input_clears_fsm_and_reports_cancelled_term(self) -> None:
        await self.seed_user(iso_after(20))

        update = await self.type_days("15")

        self.assertNotIn(SUPER_ADMIN, login.user_states)
        text = self.admin_text(update)
        self.assertIn("Yangi muddat berildi: 15 kun", text)
        self.assertIn("Oldingi muddat bekor qilindi", text)
        self.assertIn(iso_after(20)[:10], text)
        self.assertNotIn("uzaytirildi", text)

        self.bot.send_message.assert_awaited_once()
        target, user_text = self.bot.send_message.await_args.args
        self.assertEqual(target, self.UID)
        self.assertIn("yangilandi", user_text)
        self.assertIn(iso_after(15)[:10], user_text)

    async def test_manual_input_resets_last_day_warning(self) -> None:
        await self.seed_user(iso_after(0.5))
        await db.mark_warned(self.UID)

        await self.type_days("30")

        self.assertFalse(await db.is_warned(self.UID))

    async def test_invalid_manual_input_keeps_term_and_waits_for_retry(self) -> None:
        await self.seed_user(iso_after(20))

        for text in ("0", "-3", "3651", "abc", "1.5", ""):
            with self.subTest(text=text):
                update = await self.type_days(text)
                self.assertEqual(await self.expires(), iso_after(20))
                self.assertIn("1 dan 3650 gacha", self.admin_text(update))
                # FSM holati saqlanadi — admin qayta urinib ko'ra oladi.
                self.assertEqual(
                    login.user_states[SUPER_ADMIN]["step"], "admin_set_expire"
                )
        self.bot.send_message.assert_not_awaited()

    async def test_manual_prompt_says_term_is_not_added(self) -> None:
        await self.seed_user(iso_after(20))
        update = self.callback_update()

        await admin_actions.handle_expire(update, SUPER_ADMIN, f"exp:{self.UID}:manual")

        text = self.admin_text(update)
        self.assertNotIn("qo'shmoqchisiz", text)
        self.assertIn("muddat bermoqchisiz", text)
        self.assertIn("bekor bo'ladi", text)
        self.assertEqual(login.user_states[SUPER_ADMIN]["step"], "admin_set_expire")
        self.assertEqual(login.user_states[SUPER_ADMIN]["target_uid"], self.UID)


# ─────────────────────────────────────────────────────────────────────────
# UMUMIY YORDAMCHI VA MATNLAR
# ─────────────────────────────────────────────────────────────────────────
class GiveNewTermHelperTests(TermTestCase):
    async def test_returns_previous_and_new_expiry(self) -> None:
        old = iso_after(20)
        await self.seed_user(old)

        result = await admin_actions.give_new_term(SUPER_ADMIN, self.UID, 30)

        self.assertEqual(result, (old, iso_after(30)))
        self.assertEqual(await self.expires(), iso_after(30))

    async def test_previous_is_none_when_user_had_no_term(self) -> None:
        await self.seed_user(None)
        await db.set_tariff_expires(self.UID, "")

        result = await admin_actions.give_new_term(SUPER_ADMIN, self.UID, 7)

        self.assertEqual(result, (None, iso_after(7)))

    async def test_missing_user_returns_none_and_writes_nothing(self) -> None:
        self.assertIsNone(await admin_actions.give_new_term(SUPER_ADMIN, 999, 30))
        self.assertIsNone(await db.get_user(999))

    async def test_other_users_terms_are_not_touched(self) -> None:
        await self.seed_user(iso_after(20))
        await db.upsert_user(3002, name="Vali Aliyev", tariff_expires_at=iso_after(5))

        await admin_actions.give_new_term(SUPER_ADMIN, self.UID, 30)

        self.assertEqual(await db.get_tariff_expires(3002), iso_after(5))


class ApprovalKeepsExistingTermTests(TermTestCase):
    async def test_approval_default_is_used_only_when_term_is_missing(self) -> None:
        await db.upsert_user(self.UID, name="Ali Valiyev", awaiting_approval=1)
        await db.approve_user(self.UID, calc_expires(DEFAULT_DURATION_DAYS))
        self.assertEqual(await self.expires(), iso_after(DEFAULT_DURATION_DAYS))

        # Admin yangi muddat beradi, so'ng user qayta tasdiqlanadi / login qiladi.
        await self.press("90")
        await db.upsert_user(self.UID, awaiting_approval=1)
        await db.approve_user(self.UID, calc_expires(DEFAULT_DURATION_DAYS))

        self.assertEqual(await self.expires(), iso_after(90))


class TermTextsAndKeyboardTests(unittest.TestCase):
    def test_preset_buttons_are_not_additive_and_callbacks_are_unchanged(self) -> None:
        markup = kb_expire_options(2001)
        buttons = {
            button.callback_data: button.text
            for row in markup.inline_keyboard
            for button in row
        }

        for days in (1, 7, 30, 90):
            label = buttons[f"exp:2001:{days}"]
            self.assertEqual(label, f"{days} kun")
            self.assertFalse(label.startswith("+"))
        self.assertIn("exp:2001:forever", buttons)
        self.assertIn("exp:2001:manual", buttons)

    def test_admin_text_mentions_days_new_date_and_cancelled_term(self) -> None:
        with patch("core.utils.now_utc", return_value=FROZEN_NOW):
            text = T.new_term_admin_text(30, iso_after(30), iso_after(20))

        self.assertIn("30 kun", text)
        self.assertIn(iso_after(30)[:10], text)
        self.assertIn("Oldingi muddat bekor qilindi", text)
        self.assertIn(iso_after(20)[:10], text)

    def test_admin_text_when_old_term_was_unlimited(self) -> None:
        text = T.new_term_admin_text(30, iso_after(30), None)

        self.assertIn("Oldingi muddat bekor qilindi: cheksiz", text)

    def test_user_text_shows_only_the_new_date(self) -> None:
        text = T.new_term_user_text(iso_after(30))

        self.assertIn("yangilandi", text)
        self.assertIn(iso_after(30)[:10], text)


class ExpireScreenTests(TermTestCase):
    async def test_expire_screen_explains_replace_semantics(self) -> None:
        await self.seed_user(iso_after(20))
        update = self.callback_update()

        await admin_actions.action_show_expire(update, SUPER_ADMIN, self.UID)

        text = self.admin_text(update)
        self.assertIn("Hozirgi muddat", text)
        self.assertIn(iso_after(20)[:10], text)
        self.assertIn("ustiga qo'shilmaydi", text)
        self.assertNotIn("uzaytirish", text.lower())


if __name__ == "__main__":
    unittest.main()
