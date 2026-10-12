"""A reja: qo'lda tasdiqlash + kvitansiya (bot/payments.py).

Qamlov:
- o'chirilgan holatda (PAYMENTS_ENABLED=0) hech qanday 💳/navbat tugmasi yo'q;
- 💳 → yagona ochiq so'rov, karta/izoh ma'lumoti;
- kvitansiya rasmi adminga tugmalar bilan boradi, bir xil rasm belgilanadi;
- ✅ tasdiqlash: paket, muddat (tugagan → hozirdan, aks holda oxiriga),
  paid_total; takroriy bosish muddatni ikki marta uzaytirmaydi;
- ❌ rad etish va foydalanuvchi bekor qilishi; boshqa userning so'rovi yo'q;
- TTL (kvitansiyasiz) expired, muddat oldin bir marta eslatma, eski
  kvitansiya fayllari o'chiriladi, navbat ogohlantirishi throttle bilan;
- to'lovdan keyin muddat tufayli to'xtagan posting tiklanadi.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
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

from admin import admin_panel  # noqa: E402
from telegram import InlineKeyboardMarkup  # noqa: E402

from bot import keyboards as KB  # noqa: E402
from bot import menu  # noqa: E402
from bot import payments as P  # noqa: E402
from bot import texts as T  # noqa: E402
from config import config as CFG  # noqa: E402
from config.config import SUPER_ADMIN, _parse_plan_prices  # noqa: E402
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402

PRICES = {"START": 150000, "PRO": 300000}
UID = 4101
OTHER = 4102
ADMIN_UID = SUPER_ADMIN


# ─────────────────────────────────────────────────────────────────────────
# Soxta Telegram obyektlari
# ─────────────────────────────────────────────────────────────────────────
class FakeMessage:
    def __init__(self, photo=None, text: str = "") -> None:
        self.photo = photo or []
        self.text = text
        self.caption = None
        self.replies: list[tuple[str, object]] = []

    async def reply_text(self, text, reply_markup=None, **_kw):
        self.replies.append((text, reply_markup))
        return self


class FakeQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = FakeMessage()
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()
        self.edit_message_caption = AsyncMock()


class FakeTgFile:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    async def download_to_drive(self, custom_path: str):
        Path(custom_path).parent.mkdir(parents=True, exist_ok=True)
        Path(custom_path).write_bytes(self.payload)


class FakePhoto:
    def __init__(self, payload: bytes, file_id: str = "FILE-1") -> None:
        self.payload = payload
        self.file_id = file_id

    async def get_file(self):
        return FakeTgFile(self.payload)


def msg_update(uid: int, msg: FakeMessage):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=uid, username=None),
        message=msg,
        callback_query=None,
    )


def cb_update(uid: int, data: str):
    query = FakeQuery(data)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=uid, username=None),
        message=None,
        callback_query=query,
    ), query


def all_callbacks(markup) -> list[str]:
    if markup is None:
        return []
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


def iso(delta_days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


class PaymentTestCase(unittest.IsolatedAsyncioTestCase):
    enabled = True

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()

        self.application = SimpleNamespace(
            bot=SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock())
        )
        P.set_application(self.application)
        P._last_queue_alert_at = None
        menu.set_worker_manager(None)

        stack = ExitStack()
        stack.enter_context(patch.object(CFG, "PAYMENTS_ENABLED", self.enabled))
        stack.enter_context(patch.object(CFG, "PLAN_PRICES", dict(PRICES)))
        stack.enter_context(patch.object(CFG, "MEDIA_DIR", Path(self.temp.name) / "media"))
        stack.enter_context(patch.object(CFG, "PAYMENT_QUEUE_ALERT", 1))
        stack.enter_context(patch("bot.texts.PLAN_PRICES", dict(PRICES)))
        stack.enter_context(patch("bot.texts.PAY_CARD", "8600 1234 5678 9012"))
        self.stack = stack

        await self.seed(UID, expires=iso(10), session="s1")
        self.calls = []

    async def asyncTearDown(self) -> None:
        self.stack.close()
        P.set_application(None)
        menu.set_worker_manager(None)
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    async def seed(self, uid: int, *, expires: str | None, session: str = "s1", is_admin: int = 1, **extra):
        await db.upsert_user(
            uid,
            name=f"User{uid}",
            is_admin=is_admin,
            tariff_expires_at=expires,
            session=session,
            **extra,
        )

    async def start(self, uid: int, plan: str = "PRO") -> dict:
        update, _q = cb_update(uid, f"pay:new:{plan}")
        await P.handle_pay_callback(update, uid, f"pay:new:{plan}")
        payment = await db.get_open_payment(uid)
        self.assertIsNotNone(payment)
        return payment

    async def send_receipt(self, uid: int, payload: bytes = b"receipt-A") -> None:
        msg = FakeMessage(photo=[FakePhoto(b"small", "S"), FakePhoto(payload, "BIG")])
        handled = await P.handle_receipt(msg_update(uid, msg))
        self.assertTrue(handled)

    async def admin_click(self, action: str, pid: int):
        """Admin kvitansiya kartasidagi tugma (rasmli xabar — caption tahrirlanadi)."""
        update, q = cb_update(ADMIN_UID, f"pay:{action}:{pid}")
        q.message.photo = [FakePhoto(b"card")]
        q.message.caption = "KARTA"
        await P.handle_pay_callback(update, ADMIN_UID, f"pay:{action}:{pid}")
        return q

    async def expires_of(self, uid: int) -> str | None:
        user = await db.get_user(uid)
        return user.get("tariff_expires_at")

    def sent_to_user(self, uid: int) -> list[str]:
        return [
            c.args[1] if len(c.args) > 1 else c.kwargs.get("text", "")
            for c in self.application.bot.send_message.await_args_list
            if (c.args and c.args[0] == uid)
        ]


# ─────────────────────────────────────────────────────────────────────────
# O'CHIRILGAN HOLAT (standart) — hech narsa o'zgarmaydi
# ─────────────────────────────────────────────────────────────────────────
class PaymentsDisabledTests(PaymentTestCase):
    enabled = False

    async def test_plan_panel_has_no_pay_buttons(self) -> None:
        self.assertIsNone(P.plan_panel_markup())
        self.assertEqual(P.plan_panel_text(), "")

    async def test_plan_screen_is_unchanged(self) -> None:
        update = msg_update(UID, FakeMessage())
        await menu.show_plan(update)
        text, markup = update.message.replies[-1]
        self.assertNotIn("TO'LOV NARXLARI", text)
        self.assertNotIsInstance(markup, InlineKeyboardMarkup)

    async def test_admin_panel_has_no_queue_button(self) -> None:
        self.assertNotIn("adm:pay", all_callbacks(KB.kb_admin_panel()))
        self.assertEqual(await P.queue_line(), "")

    async def test_start_payment_is_refused(self) -> None:
        update, _q = cb_update(UID, "pay:new:PRO")
        await P.handle_pay_callback(update, UID, "pay:new:PRO")
        self.assertEqual(await db.get_payment_history(UID), [])
        self.assertEqual(_q.message.replies[-1][0], T.PAY_DISABLED)

    async def test_photo_is_not_taken_as_receipt(self) -> None:
        msg = FakeMessage(photo=[FakePhoto(b"x")])
        self.assertFalse(await P.handle_receipt(msg_update(UID, msg)))
        self.assertEqual(msg.replies, [])

    async def test_janitor_does_nothing(self) -> None:
        summary = await P.janitor_tick()
        self.assertEqual(summary, {"expired": 0, "reminded": 0, "pruned": 0, "alert": False})
        self.application.bot.send_message.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────
# KONFIGURATSIYA
# ─────────────────────────────────────────────────────────────────────────
class PlanPriceParsingTests(unittest.TestCase):
    def test_valid_entries_are_kept_and_bad_ones_skipped(self) -> None:
        parsed = _parse_plan_prices("start:150000, PRO:300 000,XXX:5,BUSINESS:abc,PRO,BUSINESS:0")
        self.assertEqual(parsed, {"START": 150000, "PRO": 300000})

    def test_empty_value_gives_no_prices(self) -> None:
        self.assertEqual(_parse_plan_prices(""), {})


class SchemaMigrationTests(PaymentTestCase):
    async def test_new_columns_and_table_exist(self) -> None:
        async with db._conn().execute("PRAGMA table_info(users)") as cur:
            user_cols = {row["name"] for row in await cur.fetchall()}
        async with db._conn().execute("PRAGMA table_info(payment_requests)") as cur:
            pay_cols = {row["name"] for row in await cur.fetchall()}
        self.assertTrue({"paid_total", "paid_last_at", "pay_reminded_at", "pay_paused"} <= user_cols)
        self.assertTrue({"status", "provider", "provider_txn", "proof_path", "proof_hash"} <= pay_cols)


# ─────────────────────────────────────────────────────────────────────────
# MIJOZ OQIMI
# ─────────────────────────────────────────────────────────────────────────
class ClientFlowTests(PaymentTestCase):
    async def test_plan_screen_shows_prices_and_pay_buttons(self) -> None:
        update = msg_update(UID, FakeMessage())
        await menu.show_plan(update)
        text, markup = update.message.replies[-1]
        self.assertIn("TO'LOV NARXLARI", text)
        self.assertIn("300 000 so'm", text)
        callbacks = all_callbacks(markup)
        self.assertIn("pay:new:START", callbacks)
        self.assertIn("pay:new:PRO", callbacks)
        self.assertIn("pay:status", callbacks)

    async def test_pressing_pay_creates_one_pending_request(self) -> None:
        payment = await self.start(UID, "PRO")
        self.assertEqual(payment["status"], "pending")
        self.assertEqual(payment["amount"], 300000)
        self.assertEqual(payment["days"], CFG.PAYMENT_DAYS)
        self.assertEqual(payment["reference"], f"{CFG.PAY_REF_PREFIX}-{UID}-PRO")

        # Ikkinchi bosish yangi so'rov ochmaydi — ochiq so'rovni ko'rsatadi.
        await self.start(UID, "PRO")
        history = await db.get_payment_history(UID)
        self.assertEqual(len(history), 1)

    async def test_instruction_contains_card_and_reference(self) -> None:
        update, q = cb_update(UID, "pay:new:START")
        await P.handle_pay_callback(update, UID, "pay:new:START")
        text, markup = q.message.replies[-1]
        self.assertIn("8600 1234 5678 9012", text)
        self.assertIn("150 000 so'm", text)
        self.assertIn(f"{CFG.PAY_REF_PREFIX}-{UID}-START", text)
        self.assertIn(f"pay:cancel:{(await db.get_open_payment(UID))['id']}", all_callbacks(markup))

    async def test_unapproved_user_cannot_start_payment(self) -> None:
        await self.seed(OTHER, expires=None, session="", is_admin=0)
        update, q = cb_update(OTHER, "pay:new:PRO")
        await P.handle_pay_callback(update, OTHER, "pay:new:PRO")
        self.assertIsNone(await db.get_open_payment(OTHER))
        self.assertIn("Hisob faol emas", q.message.replies[-1][0])

    async def test_unknown_plan_is_refused(self) -> None:
        update, q = cb_update(UID, "pay:new:BUSINESS")
        await P.handle_pay_callback(update, UID, "pay:new:BUSINESS")
        self.assertIsNone(await db.get_open_payment(UID))
        self.assertIn("narx belgilanmagan", q.message.replies[-1][0])

    async def test_receipt_is_attached_and_card_sent_to_admin(self) -> None:
        payment = await self.start(UID, "PRO")
        await self.send_receipt(UID)

        stored = await db.get_payment(payment["id"])
        self.assertTrue(stored["proof_path"])
        self.assertTrue(os.path.exists(stored["proof_path"]))
        self.assertEqual(len(stored["proof_hash"]), 64)

        self.application.bot.send_photo.assert_awaited_once()
        args, kwargs = self.application.bot.send_photo.await_args
        self.assertEqual(args[0], SUPER_ADMIN)
        self.assertIn("AVTO-", kwargs["caption"])
        self.assertIn("300 000 so'm", kwargs["caption"])
        buttons = all_callbacks(kwargs["reply_markup"])
        self.assertIn(f"pay:ok:{payment['id']}", buttons)
        self.assertIn(f"pay:no:{payment['id']}", buttons)

    async def test_photo_without_open_request_falls_through(self) -> None:
        msg = FakeMessage(photo=[FakePhoto(b"img")])
        self.assertFalse(await P.handle_receipt(msg_update(UID, msg)))
        self.application.bot.send_photo.assert_not_awaited()

    async def test_second_receipt_after_first_is_refused(self) -> None:
        await self.start(UID, "PRO")
        await self.send_receipt(UID, b"first")
        msg = FakeMessage(photo=[FakePhoto(b"second", "X")])
        self.assertTrue(await P.handle_receipt(msg_update(UID, msg)))
        self.assertIn("allaqachon yuborilgan", msg.replies[-1][0])
        self.assertEqual(self.application.bot.send_photo.await_count, 1)

    async def test_same_receipt_used_twice_is_flagged(self) -> None:
        await self.seed(OTHER, expires=iso(5), session="s2")
        await self.start(UID, "PRO")
        await self.send_receipt(UID, b"SAME-RECEIPT")
        await self.start(OTHER, "START")
        await self.send_receipt(OTHER, b"SAME-RECEIPT")

        caption = self.application.bot.send_photo.await_args_list[-1].kwargs["caption"]
        self.assertIn("yana 1 ta so'rovda", caption)

    async def test_status_shows_current_and_history(self) -> None:
        await self.start(UID, "PRO")
        update, q = cb_update(UID, "pay:status")
        await P.handle_pay_callback(update, UID, "pay:status")
        text = q.message.replies[-1][0]
        self.assertIn("Kvitansiya kutilmoqda", text)
        self.assertIn("Oxirgi to'lovlar", text)

    async def test_user_can_cancel_own_request_and_proof_is_removed(self) -> None:
        payment = await self.start(UID, "PRO")
        await self.send_receipt(UID)
        proof = (await db.get_payment(payment["id"]))["proof_path"]

        update, q = cb_update(UID, f"pay:cancel:{payment['id']}")
        await P.handle_pay_callback(update, UID, f"pay:cancel:{payment['id']}")

        self.assertEqual((await db.get_payment(payment["id"]))["status"], "cancelled")
        self.assertFalse(os.path.exists(proof))
        self.assertIn("bekor qilindi", q.message.replies[-1][0])

    async def test_user_cannot_cancel_someone_elses_request(self) -> None:
        await self.seed(OTHER, expires=iso(5), session="s2")
        payment = await self.start(OTHER, "START")
        update, _q = cb_update(UID, f"pay:cancel:{payment['id']}")
        await P.handle_pay_callback(update, UID, f"pay:cancel:{payment['id']}")
        self.assertEqual((await db.get_payment(payment["id"]))["status"], "pending")


# ─────────────────────────────────────────────────────────────────────────
# ADMIN: TASDIQLASH / RAD ETISH
# ─────────────────────────────────────────────────────────────────────────
class AdminDecisionTests(PaymentTestCase):
    async def _ready_request(self, uid: int = UID, plan: str = "PRO") -> int:
        payment = await self.start(uid, plan)
        await self.send_receipt(uid, f"proof-{payment['id']}".encode())
        return int(payment["id"])

    async def test_approve_on_expired_tariff_extends_from_now(self) -> None:
        await self.seed(UID, expires=iso(-2), session="s1")
        pid = await self._ready_request()
        q = await self.admin_click("ok", pid)

        expires = datetime.strptime(await self.expires_of(UID), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        expected = datetime.now(timezone.utc) + timedelta(days=CFG.PAYMENT_DAYS)
        self.assertLess(abs((expires - expected).total_seconds()), 120)

        user = await db.get_user(UID)
        self.assertEqual(user["plan"], "PRO")
        self.assertEqual(user["max_groups"], CFG.PLAN_DEFS["PRO"]["max_groups"])
        self.assertEqual(user["paid_total"], 300000)
        self.assertIsNotNone(user["paid_last_at"])
        self.assertEqual((await db.get_payment(pid))["status"], "approved")
        self.assertEqual((await db.get_payment(pid))["decided_by"], SUPER_ADMIN)
        self.assertTrue(any("TO'LOV QABUL QILINDI" in t for t in self.sent_to_user(UID)))
        self.assertIn("TASDIQLANDI", q.edit_message_caption.await_args.kwargs["caption"])

    async def test_approve_on_active_tariff_adds_to_end(self) -> None:
        end = iso(10)
        await self.seed(UID, expires=end, session="s1")
        pid = await self._ready_request()
        await self.admin_click("ok", pid)

        new_end = datetime.strptime(await self.expires_of(UID), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        old_end = datetime.strptime(end, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        self.assertLess(abs((new_end - old_end - timedelta(days=CFG.PAYMENT_DAYS)).total_seconds()), 5)

    async def test_double_approve_extends_only_once(self) -> None:
        await self.seed(UID, expires=iso(10), session="s1")
        pid = await self._ready_request()
        await self.admin_click("ok", pid)
        once = await self.expires_of(UID)
        q = await self.admin_click("ok", pid)

        self.assertEqual(await self.expires_of(UID), once)
        self.assertEqual((await db.get_user(UID))["paid_total"], 300000)
        self.assertIn("allaqachon", q.edit_message_caption.await_args.kwargs["caption"])
        self.assertEqual(len(self.sent_to_user(UID)), 1)

    async def test_reject_then_user_can_request_again(self) -> None:
        pid = await self._ready_request()
        await self.admin_click("no", pid)
        self.assertEqual((await db.get_payment(pid))["status"], "rejected")
        self.assertTrue(any("rad etildi" in t for t in self.sent_to_user(UID)))

        # Rad etilgan so'rovdan keyin yangi so'rov ochish mumkin.
        new_payment = await self.start(UID, "START")
        self.assertNotEqual(new_payment["id"], pid)

    async def test_approve_after_reject_does_not_pay(self) -> None:
        pid = await self._ready_request()
        await self.admin_click("no", pid)
        await self.admin_click("ok", pid)
        self.assertEqual((await db.get_payment(pid))["status"], "rejected")
        self.assertEqual((await db.get_user(UID))["paid_total"], 0)

    async def test_non_admin_cannot_approve(self) -> None:
        pid = await self._ready_request()
        update, _q = cb_update(UID, f"pay:ok:{pid}")
        await P.handle_pay_callback(update, UID, f"pay:ok:{pid}")
        self.assertEqual((await db.get_payment(pid))["status"], "pending")
        self.assertEqual((await db.get_user(UID))["paid_total"], 0)

    async def test_approve_cancelled_request_is_refused(self) -> None:
        payment = await self.start(UID, "PRO")
        await self.send_receipt(UID)
        update, _q = cb_update(UID, f"pay:cancel:{payment['id']}")
        await P.handle_pay_callback(update, UID, f"pay:cancel:{payment['id']}")
        await self.admin_click("ok", payment["id"])
        self.assertEqual((await db.get_payment(payment["id"]))["status"], "cancelled")
        self.assertEqual((await db.get_user(UID))["paid_total"], 0)

    async def test_queue_lists_only_receipts_waiting_for_decision(self) -> None:
        await self.seed(OTHER, expires=iso(5), session="s2")
        await self.start(UID, "PRO")  # kvitansiyasiz — navbatda bo'lmaydi
        pid = await self._ready_request(OTHER, "START")
        queue = await db.payment_queue()
        self.assertEqual([row["id"] for row in queue], [pid])
        self.assertIn("1 ta", await P.queue_line())

    async def test_paused_posting_resumes_after_payment(self) -> None:
        await self.seed(UID, expires=iso(-1), session="s1", pay_paused=1)
        await db.set_running(UID, False)
        pid = await self._ready_request()

        wm = SimpleNamespace(is_running=lambda uid: False, start_worker=AsyncMock(return_value=True))
        menu.set_worker_manager(wm)
        with patch.object(db, "get_chats", AsyncMock(return_value=[{"id": 1}])), patch.object(
            db, "get_posts", AsyncMock(return_value=[{"id": 1}])
        ):
            await self.admin_click("ok", pid)

        wm.start_worker.assert_awaited_once_with(UID)
        self.assertTrue((await db.get_user(UID))["running"])
        self.assertEqual((await db.get_user(UID))["pay_paused"], 0)
        self.assertTrue(any("Posting avtomatik tiklandi" in t for t in self.sent_to_user(UID)))

    async def test_manual_stop_is_not_resumed_by_payment(self) -> None:
        # Muddat tugamagan, lekin admin qo'lda to'xtatgan (pay_paused=0).
        await self.seed(UID, expires=iso(10), session="s1", pay_paused=0)
        pid = await self._ready_request()
        wm = SimpleNamespace(is_running=lambda uid: False, start_worker=AsyncMock(return_value=True))
        menu.set_worker_manager(wm)
        await self.admin_click("ok", pid)
        wm.start_worker.assert_not_awaited()
        self.assertFalse((await db.get_user(UID))["running"])


# ─────────────────────────────────────────────────────────────────────────
# JANITOR: TTL, ESLATMA, TOZALASH, NAVBAT OGOHLANTIRISHI
# ─────────────────────────────────────────────────────────────────────────
class JanitorTests(PaymentTestCase):
    async def _backdate_request(self, pid: int, minutes: int) -> None:
        stamp = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
        await db._conn().execute(
            "UPDATE payment_requests SET created_at = ?, updated_at = ? WHERE id = ?",
            (stamp, stamp, pid),
        )
        await db._conn().commit()

    async def test_request_without_receipt_expires_after_ttl(self) -> None:
        payment = await self.start(UID, "PRO")
        await self._backdate_request(payment["id"], CFG.PAYMENT_REQUEST_TTL_MIN + 5)
        summary = await P.janitor_tick()

        self.assertEqual(summary["expired"], 1)
        self.assertEqual((await db.get_payment(payment["id"]))["status"], "expired")
        self.assertTrue(any("muddati o'tdi" in t for t in self.sent_to_user(UID)))

    async def test_request_with_receipt_is_not_expired_by_ttl(self) -> None:
        payment = await self.start(UID, "PRO")
        await self.send_receipt(UID)
        await self._backdate_request(payment["id"], CFG.PAYMENT_REQUEST_TTL_MIN + 500)
        await P.janitor_tick()
        self.assertEqual((await db.get_payment(payment["id"]))["status"], "pending")

    async def test_reminder_is_sent_once_before_expiry(self) -> None:
        await self.seed(OTHER, expires=iso(2), session="s2")
        await P.janitor_tick()
        reminders = [t for t in self.sent_to_user(OTHER) if "Eslatma" in t]
        self.assertEqual(len(reminders), 1)
        self.assertIn("2 kun qoldi", reminders[0])

        await P.janitor_tick()
        self.assertEqual(len([t for t in self.sent_to_user(OTHER) if "Eslatma" in t]), 1)

    async def test_no_reminder_for_far_expiry(self) -> None:
        await P.janitor_tick()  # UID muddati 10 kun — eslatma yo'q
        self.assertEqual(self.sent_to_user(UID), [])

    async def test_reminder_flag_resets_after_payment(self) -> None:
        await self.seed(UID, expires=iso(2), session="s1")
        await P.janitor_tick()
        self.assertIsNotNone((await db.get_user(UID))["pay_reminded_at"])
        pid = await self._ready_request_for(UID)
        await self.admin_click("ok", pid)
        self.assertIsNone((await db.get_user(UID))["pay_reminded_at"])

    async def _ready_request_for(self, uid: int) -> int:
        payment = await self.start(uid, "PRO")
        await self.send_receipt(uid, b"reminder-proof")
        return int(payment["id"])

    async def test_old_receipt_file_is_pruned_after_retention(self) -> None:
        pid = await self._ready_request_for(UID)
        await self.admin_click("ok", pid)
        proof = (await db.get_payment(pid))["proof_path"]
        self.assertTrue(os.path.exists(proof))

        stamp = (datetime.now(timezone.utc) - timedelta(days=CFG.PAYMENT_PROOF_RETENTION_DAYS + 1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        await db._conn().execute("UPDATE payment_requests SET updated_at = ? WHERE id = ?", (stamp, pid))
        await db._conn().commit()

        summary = await P.janitor_tick()
        self.assertEqual(summary["pruned"], 1)
        self.assertFalse(os.path.exists(proof))
        self.assertEqual((await db.get_payment(pid))["proof_path"], "")

    async def test_queue_alert_is_throttled(self) -> None:
        await self._ready_request_for(UID)  # navbat = 1 >= PAYMENT_QUEUE_ALERT(1)
        first = await P.janitor_tick()
        second = await P.janitor_tick()
        self.assertTrue(first["alert"])
        self.assertFalse(second["alert"])
        admin_msgs = [
            c for c in self.application.bot.send_message.await_args_list if c.args and c.args[0] == SUPER_ADMIN
        ]
        self.assertEqual(len(admin_msgs), 1)
        self.assertIn("To'lovlar navbati", admin_msgs[0].args[1])


# ─────────────────────────────────────────────────────────────────────────
# ADMIN PANEL ULANISHI
# ─────────────────────────────────────────────────────────────────────────
class AdminPanelWiringTests(PaymentTestCase):
    async def test_panel_has_queue_button_and_count_line(self) -> None:
        await self._ready_request_for_panel()
        self.assertIn("adm:pay", all_callbacks(KB.kb_admin_panel()))
        line = await P.queue_line()
        self.assertIn("Kutilayotgan to'lovlar: 1 ta", line)

    async def _ready_request_for_panel(self) -> None:
        payment = await self.start(UID, "PRO")
        await self.send_receipt(UID, b"panel")
        self.assertIsNotNone(payment)

    async def test_queue_view_for_admin_sends_card_per_receipt(self) -> None:
        await self._ready_request_for_panel()
        update, q = cb_update(ADMIN_UID, "adm:pay")
        await admin_panel.handle_admin_callback(update, ADMIN_UID, "adm:pay")
        q.edit_message_text.assert_awaited()
        # Navbatdagi kvitansiya uchun karta (send_photo) yuboriladi.
        self.assertGreaterEqual(self.application.bot.send_photo.await_count, 2)

    async def test_queue_view_is_refused_for_regular_user(self) -> None:
        update, q = cb_update(UID, "adm:pay")
        await admin_panel.handle_admin_callback(update, UID, "adm:pay")
        q.edit_message_text.assert_not_awaited()


class MainRoutingTests(PaymentTestCase):
    """main.py: rasm va /pay buyrug'i to'lov moduliga to'g'ri yo'naltiriladi."""

    async def test_photo_with_open_request_becomes_receipt(self) -> None:
        import main

        await self.start(UID, "PRO")
        msg = FakeMessage(photo=[FakePhoto(b"routed-receipt")])
        with patch.object(main.rate_limiter, "is_allowed", return_value=True):
            await main._on_message_locked(msg_update(UID, msg), SimpleNamespace(args=[]))

        payment = await db.get_open_payment(UID)
        self.assertTrue(payment["proof_path"])
        self.assertTrue(any("Kvitansiya qabul qilindi" in text for text, _ in msg.replies))

    async def test_photo_without_request_keeps_old_behaviour(self) -> None:
        import main

        msg = FakeMessage(photo=[FakePhoto(b"random")])
        with patch.object(main.rate_limiter, "is_allowed", return_value=True):
            await main._on_message_locked(msg_update(UID, msg), SimpleNamespace(args=[]))

        self.assertEqual(len(msg.replies), 1)
        self.assertEqual(msg.replies[0][0], T.USE_MENU_BUTTONS)
        self.assertEqual(await db.get_payment_history(UID), [])

    async def test_pay_command_shows_price_panel(self) -> None:
        import main

        update = msg_update(UID, FakeMessage())
        await main.cmd_pay(update, SimpleNamespace(args=[]))
        text, markup = update.message.replies[-1]
        self.assertIn("TO'LOV NARXLARI", text)
        self.assertIn("pay:new:PRO", all_callbacks(markup))

    async def test_pay_command_refused_when_disabled(self) -> None:
        import main

        with patch.object(CFG, "PAYMENTS_ENABLED", False):
            update = msg_update(UID, FakeMessage())
            await main.cmd_pay(update, SimpleNamespace(args=[]))
        self.assertEqual(update.message.replies[-1][0], T.PAY_DISABLED)


if __name__ == "__main__":
    unittest.main()
