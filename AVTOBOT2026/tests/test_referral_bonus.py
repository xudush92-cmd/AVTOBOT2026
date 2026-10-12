"""Referal mukofoti, anti-fraud va tiklash qoidalari.

Qamlov:
- havola biriktirish faqat yangi foydalanuvchi va tasdiqlangan, bloklanmagan
  referrer uchun ishlaydi (o'zini o'zi taklif qilib bo'lmaydi);
- hisoblash (counted) va mukofot (bonus kun) IKKI BOSQICH: bonus faqat
  referal haqiqatan ishlay boshlagach beriladi;
- bir marta — takroriy chaqiruv bonusni ikkinchi marta qo'shmaydi;
- cheksiz tarifga ega referrerga kun qo'shilmaydi (lekin holat belgilanadi);
- oylik cap faqat o'rnatilganda ishlaydi (standart 0 = cheklovsiz);
- firibgar aniqlansa bonus kun qaytarib olinadi (clawback);
- referrer bloklangan paytda tasdiqlansa hisob yo'qolmaydi — blokdan chiqqach
  qayta hisoblanadi;
- tasdiqlanmagan takliflar ro'yxatida taklif qilingan kishining ismi
  ko'rsatilmaydi.
"""

from __future__ import annotations

import os
import sys
import tempfile
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

from bot import login  # noqa: E402
from bot import referral as RF  # noqa: E402
from config.config import REFERRAL_BONUS_DAYS, SUPER_ADMIN  # noqa: E402
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402

FROZEN_NOW = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
REFERRER = 1001
REFERRED = 2001


def iso_after(days: float) -> str:
    return (FROZEN_NOW + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


class ReferralTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        login.user_states.clear()

        self.sent = []

        async def _send(chat_id, text, **kwargs):
            self.sent.append((int(chat_id), text))

        self.app = SimpleNamespace(bot=SimpleNamespace(send_message=_send))
        self._patches = [
            patch("core.utils.now_utc", return_value=FROZEN_NOW),
            patch.object(login, "application", self.app),
            patch.object(RF, "REFERRAL_BONUS_DAYS", 15),
            patch.object(RF, "REFERRAL_BONUS_MONTHLY_CAP_DAYS", 0),
            patch.object(RF, "REFERRAL_QUALIFY_MIN_SENDS", 1),
            patch.object(RF, "REFERRAL_DAILY_ALERT", 3),
        ]
        for patcher in self._patches:
            patcher.start()

        await db.upsert_user(
            REFERRER,
            name="Referrer Ali",
            is_admin=1,
            tariff_expires_at=iso_after(10),
        )

    async def asyncTearDown(self) -> None:
        for patcher in reversed(self._patches):
            patcher.stop()
        login.user_states.clear()
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    # ── yordamchilar ──
    async def register(self, uid: int = REFERRED, referrer: int = REFERRER) -> bool:
        return await RF.register_referral(uid, f"ref_{referrer}")

    async def activate(self, uid: int = REFERRED) -> None:
        """Foydalanuvchi tasdiqlanadi va referal hisoblanadi (admin yo'li)."""
        await db.upsert_user(uid, name="Vali", is_admin=1)
        await RF.on_referral_counted(uid)

    async def make_active(self, uid: int = REFERRED) -> None:
        """Referal «haqiqiy foydalanuvchi» mezonlarini bajaradi."""
        await self.activate(uid)
        await db.add_chat(uid, "@g1")
        await db.add_post(uid, "e'lon", [], None)
        record = await db.get_chat_records(uid)
        await db.log_send(uid, True, group_id=int(record[0]["id"]), post_id=1)

    def sent_to(self, chat_id: int) -> list[str]:
        return [text for target, text in self.sent if target == chat_id]

    # ── 1. Biriktirish ──
    async def test_referral_links_new_user_to_referrer(self) -> None:
        self.assertTrue(await self.register())
        user = await db.get_user(REFERRED)
        self.assertEqual(int(user["referrer_uid"]), REFERRER)
        self.assertFalse(user["referral_counted"])
        refs = await db.get_referrals(REFERRER)
        self.assertEqual(len(refs), 1)
        self.assertFalse(refs[0]["counted"])

    async def test_self_referral_and_bad_codes_rejected(self) -> None:
        self.assertFalse(await RF.register_referral(REFERRER, f"ref_{REFERRER}"))
        self.assertFalse(await RF.register_referral(REFERRER, f"ref_{REFERRER}"))
        self.assertFalse(await RF.register_referral(3003, "nima"))
        self.assertFalse(await RF.register_referral(3003, "ref_abc"))
        self.assertIsNone(await db.get_user(3003))

    async def test_existing_user_cannot_be_bound(self) -> None:
        await db.upsert_user(REFERRED, name="Tayyor user", is_admin=1)
        self.assertFalse(await self.register())

    async def test_unapproved_or_blocked_referrer_rejected(self) -> None:
        await db.upsert_user(4004, name="Kutayotgan", awaiting_approval=1)
        self.assertFalse(await RF.register_referral(REFERRED, "ref_4004"))
        await db.set_blocked(REFERRER, True)
        self.assertFalse(await RF.register_referral(5005, f"ref_{REFERRER}"))
        await db.set_blocked(REFERRER, False)
        self.assertTrue(await RF.register_referral(5005, f"ref_{REFERRER}"))

    async def test_anomaly_alert_sent_once(self) -> None:
        for index in range(5):
            self.assertTrue(await RF.register_referral(7000 + index, f"ref_{REFERRER}"))
        admin_messages = self.sent_to(SUPER_ADMIN)
        self.assertEqual(len(admin_messages), 1)
        self.assertIn("Referal anomaliyasi", admin_messages[0])
        # Ogohlantirish bir marta — keyingi qo'shilishlar takrorlamaydi.
        self.assertIn("3 ta", admin_messages[0])

    # ── 2. Hisoblash va mukofot ──
    async def test_bonus_not_granted_before_activity(self) -> None:
        await self.register()
        await self.activate()

        messages = self.sent_to(REFERRER)
        self.assertEqual(len(messages), 1)
        self.assertIn("faollashdi", messages[0])
        self.assertIn(f"{REFERRAL_BONUS_DAYS} kun", messages[0])

        # Mukofot hali yo'q.
        self.assertFalse(await RF.maybe_grant_referral_bonus(REFERRED))
        user = await db.get_user(REFERRER)
        self.assertEqual(int(user["referral_bonus_days"] or 0), 0)

    async def test_bonus_requires_group_post_and_send(self) -> None:
        await self.register()
        await self.activate()
        self.assertFalse(await RF.maybe_grant_referral_bonus(REFERRED))

        await db.add_chat(REFERRED, "@g1")
        self.assertFalse(await RF.maybe_grant_referral_bonus(REFERRED))
        await db.add_post(REFERRED, "e'lon", [], None)
        self.assertFalse(await RF.maybe_grant_referral_bonus(REFERRED))

        record = await db.get_chat_records(REFERRED)
        await db.log_send(REFERRED, False, group_id=int(record[0]["id"]), error="X")
        self.assertFalse(
            await RF.maybe_grant_referral_bonus(REFERRED),
            "muvaffaqiyatsiz urinish mukofot keltirmasin",
        )

        await db.log_send(REFERRED, True, group_id=int(record[0]["id"]))
        self.assertTrue(await RF.maybe_grant_referral_bonus(REFERRED))
        user = await db.get_user(REFERRER)
        self.assertEqual(int(user["referral_bonus_days"]), 15)
        self.assertEqual(user["tariff_expires_at"], iso_after(25))

        # Ikkinchi marta — takroriy mukofot bo'lmasligi kerak.
        await db.log_send(REFERRED, True, group_id=int(record[0]["id"]))
        self.assertFalse(await RF.maybe_grant_referral_bonus(REFERRED))
        user = await db.get_user(REFERRER)
        self.assertEqual(int(user["referral_bonus_days"]), 15)
        self.assertEqual(len(self.sent_to(REFERRER)), 2)

    async def test_worker_hook_grants_bonus(self) -> None:
        await self.register()
        await self.make_active()
        # Worker chaqiruvi ham bir xil natija beradi (log_send bu yerda qayta).
        self.assertTrue(await RF.maybe_grant_referral_bonus(REFERRED, 1))

    async def test_unlimited_tariff_referrer_gets_no_days(self) -> None:
        await db.set_tariff_expires(REFERRER, None)
        await self.register()
        await self.make_active()
        self.assertTrue(await RF.maybe_grant_referral_bonus(REFERRED))
        user = await db.get_user(REFERRER)
        self.assertIsNone(user["tariff_expires_at"] or None)
        self.assertEqual(int(user["referral_bonus_days"] or 0), 0)
        self.assertIn("cheksiz", self.sent_to(REFERRER)[-1])

    async def test_no_cap_by_default_every_friend_counts(self) -> None:
        # Cap 0 = cheklovsiz: har bir do'st uchun to'liq 15 kun.
        await self.register()
        await self.make_active()
        self.assertTrue(await RF.maybe_grant_referral_bonus(REFERRED))
        await self.register(8002)
        await self.make_active(8002)
        self.assertTrue(await RF.maybe_grant_referral_bonus(8002))
        await self.register(8003)
        await self.make_active(8003)
        self.assertTrue(await RF.maybe_grant_referral_bonus(8003))
        user = await db.get_user(REFERRER)
        self.assertEqual(int(user["referral_bonus_days"]), 45)

    async def test_monthly_cap_limits_bonus_when_set(self) -> None:
        with patch.object(RF, "REFERRAL_BONUS_MONTHLY_CAP_DAYS", 20):
            await self.register()
            await self.make_active()
            self.assertTrue(await RF.maybe_grant_referral_bonus(REFERRED))
            first = await db.get_user(REFERRER)
            self.assertEqual(int(first["referral_bonus_days"]), 15)

            await self.register(8002)
            await self.make_active(8002)
            self.assertTrue(await RF.maybe_grant_referral_bonus(8002))
            second = await db.get_user(REFERRER)
            # Chegara 20 kun: 15 ta berilgan, keyingisiga faqat 5 kun qoladi.
            self.assertEqual(int(second["referral_bonus_days"]), 20)

    # ── 3. Clawback va tiklash ──
    async def test_revoking_bonus_claws_back_days(self) -> None:
        await self.register()
        await self.make_active()
        self.assertTrue(await RF.maybe_grant_referral_bonus(REFERRED))

        result = await RF.revoke_referral_bonus(REFERRED, "soxta akkaunt")
        self.assertIsNotNone(result)
        self.assertEqual(int(result["referrer_uid"]), REFERRER)
        self.assertEqual(int(result["bonus_days"]), 15)

        referrer = await db.get_user(REFERRER)
        self.assertEqual(int(referrer["referral_bonus_days"]), 0)
        self.assertEqual(referrer["tariff_expires_at"], iso_after(10))
        self.assertIn("bekor qilindi", self.sent_to(REFERRER)[-1])

        # Qaytarib bo'lingan hisob yana bonus keltirmasin.
        self.assertFalse(await RF.maybe_grant_referral_bonus(REFERRED))

    async def test_revoke_without_bonus_is_noop(self) -> None:
        await self.register()
        await self.activate()
        self.assertEqual(await db.count_referrals(REFERRER), 1)
        result = await RF.revoke_referral_bonus(REFERRED)
        # Bonus berilmagan — qaytariladigan kun yo'q, lekin hisob olinadi.
        self.assertEqual(int(result["bonus_days"]), 0)
        self.assertEqual(await db.count_referrals(REFERRER), 0)

    async def test_referrer_unblock_recounts_pending_referral(self) -> None:
        await self.register()
        await db.upsert_user(REFERRED, name="Vali", is_admin=1)
        await db.set_blocked(REFERRER, True)

        # Bloklangan referrer tufayli hisoblanmaydi (eski nuqson).
        self.assertIsNone(await db.try_count_referral(REFERRED))
        self.assertEqual(await db.count_referrals(REFERRER), 0)

        await db.set_blocked(REFERRER, False)
        pending = await db.pending_referrals_of(REFERRER)
        self.assertEqual(pending, [REFERRED])
        await RF.on_referral_counted(REFERRED)
        self.assertEqual(await db.count_referrals(REFERRER), 1)
        # Endi bonus olishga ham yo'l ochiladi.
        await db.add_chat(REFERRED, "@g1")
        await db.add_post(REFERRED, "e'lon", [], None)
        record = await db.get_chat_records(REFERRED)
        await db.log_send(REFERRED, True, group_id=int(record[0]["id"]))
        self.assertTrue(await RF.maybe_grant_referral_bonus(REFERRED))

    # ── 4. Maxfiylik va sahifa ──
    async def test_pending_referee_name_is_masked(self) -> None:
        await self.register()
        await db.upsert_user(REFERRED, name="Yashirin Ism")
        refs = await db.get_referrals(REFERRER)
        self.assertNotIn("Yashirin Ism", refs[0]["name"])
        await db.upsert_user(REFERRED, name="Yashirin Ism", is_admin=1)
        await RF.on_referral_counted(REFERRED)
        refs = await db.get_referrals(REFERRER)
        self.assertIn("Yashirin Ism", refs[0]["name"])

    async def test_referral_page_and_share_text(self) -> None:
        await self.register()
        await self.activate()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=REFERRER),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(RF, "BOT_USERNAME", "avtobot2026"):
            await RF.show_referral(update)
        text = update.message.reply_text.await_args.args[0]
        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        self.assertIn(f"t.me/avtobot2026?start=ref_{REFERRER}", text)
        self.assertIn("Faol referallar: 1 ta", text)
        self.assertIn(f"+{REFERRAL_BONUS_DAYS} kun", text)
        buttons = {
            button.text
            for row in markup.inline_keyboard
            for button in row
        }
        self.assertIn("🔗 Havolani ochish", buttons)
        self.assertIn("📨 Do'stlarga yuborish", buttons)

        share = await RF.share_referral_message(REFERRER)
        self.assertIn(f"?start=ref_{REFERRER}", share)
        self.assertIn("AVTOBOT", share)

    async def test_referral_page_without_bonus_config(self) -> None:
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=REFERRER),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(RF, "REFERRAL_BONUS_DAYS", 0):
            await RF.show_referral(update)
        text = update.message.reply_text.await_args.args[0]
        self.assertIn("Hozircha referal yo'q", text)
        self.assertNotIn("Har bir faol referalga", text)


if __name__ == "__main__":
    unittest.main()
