"""Callback router qamrovi testlari.

Muammo (VPS logi va Telegram skrinshotida aniqlangan):
``ordinary_prefixes`` ro'yxatida ``"disc:"`` bor, lekin uning ``elif``
branch'i zanjirda yo'q edi. Shu sabab ``disc:toggle`` (guruhni ✅
belgilash) callback'i hech qanday handler'ga yetib bormaydi:

- ✅ belgi chiqmaydi;
- alert (``q.answer``) chiqmaydi;
- logda ham xato bo'lmaydi — xato yo'q, kod **yetib borilmagan**.

Bu testlar shu tipdagi "o'lik zona"ning qaytmasligini kafolatlaydi:
ro'yxatdagi har bir prefiks kamida bitta branch'da qamralgan bo'lishi
SHART.

Qamrov:
- ``ordinary_prefixes`` dagi har bir prefiks qamrab olingan;
- ``disc:toggle`` — guruhni belgilash ishlaydi (✅ belgi chiqadi);
- belgilashdan keyin «Tanlanganlarni qo'shish» tugmasi paydo bo'ladi;
- ``disc:apply`` — tanlangan guruhlarni qo'shadi.
"""

from __future__ import annotations

import ast
import os
import re
import sys
import tempfile
import unittest
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

from bot import callbacks as CB  # noqa: E402
from bot import discover_sessions  # noqa: E402
from bot import groups as G  # noqa: E402
from bot import keyboards as KB  # noqa: E402
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402

UID = 88011
OTHER_UID = 88012


# ─────────────────────────────────────────────────────────────────────────
# ROUTER STATIK TAHLIL
# ─────────────────────────────────────────────────────────────────────────
def _router_source() -> str:
    return (APP_DIR / "bot" / "callbacks.py").read_text(encoding="utf-8")


def _ordinary_prefixes() -> tuple[str, ...]:
    """`ordinary_prefixes` ro'yxatini AST orqali oladi."""
    tree = ast.parse(_router_source())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ordinary_prefixes":
                    return tuple(
                        elt.value
                        for elt in ast.walk(node.value)
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    )
    raise AssertionError("ordinary_prefixes topilmadi")


def _handled_prefixes() -> set[str]:
    """Router'dagi barcha `data.startswith(...)` argumentlarini oladi."""
    src = _router_source()
    found: set[str] = set()
    for match in re.finditer(r'data\.startswith\(\s*\(?([^)]*?)\)?\s*\)', src):
        for const in re.findall(r'"([^"]+)"', match.group(1)):
            found.add(const)
    return found


class RouterCoverageTests(unittest.TestCase):
    """Router statik qamrovi — «o'lik zona» bo'lmasligi uchun."""

    def test_ordinary_prefixes_all_handled(self) -> None:
        """Ro'yxatdagi har bir prefiks kamida bitta branch'da qamralishi kerak.

        Qamrov **prefix yoki uning sub-prefixi** bo'lishi mumkin:
        ``intv:`` → ``intv:yes:``/``intv:no:``, ``tst:`` → ``tst:go:``,
        ``ref:`` → ``ref:share``. Muhim shuki, **butun** prefiks
        qamralanmagan bo'lsa — callback jimgina qaytadi va tugma
        umuman ishlamaydi (belgi chiqmaydi, alert chiqmaydi, logda xato
        bo'lmaydi).
        """
        prefixes = _ordinary_prefixes()
        handled = _handled_prefixes()
        missing = [
            p
            for p in prefixes
            if not any(h == p or h.startswith(p) for h in handled)
        ]
        self.assertEqual(
            missing,
            [],
            f"ordinary_prefixes dagi prefix'lar handler'siz: {missing} — "
            "callback jimgina qaytadi va tugma ishlamaydi",
        )

    def test_disc_prefix_handled(self) -> None:
        """`disc:` prefiksi albatta qamrab olingan bo'lishi kerak."""
        self.assertIn("disc:", _handled_prefixes())

    def test_disc_not_in_ordinary_prefixes(self) -> None:
        """`disc:` oddiy-user blokida bo'lmasligi kerak.

        Aks holda u 164-qatordagi blokda ushlanib, o'z handler'iga
        yetib borolmaydi.
        """
        self.assertNotIn(
            "disc:",
            _ordinary_prefixes(),
            "'disc:' alohida branch'da boshqariladi — oddiy-user blokiga qo'yilmaydi",
        )

    def test_prefix_without_branch_is_detected(self) -> None:
        """Test o'zi to'g'ri ishlayotganini tekshirish (regressiya himoyasi).

        Sun'iy prefiks qo'shilganda test uni topishi kerak — aks holda
        test o'zi «yashirib» qolishi mumkin.
        """
        with patch.object(
            sys.modules[__name__],
            "_ordinary_prefixes",
            return_value=("disc:", "yoq_bo'lgan_prefix:"),
        ):
            with self.assertRaises(AssertionError):
                self.test_ordinary_prefixes_all_handled()


# ─────────────────────────────────────────────────────────────────────────
# AMALIY TESTLAR — belgilanish oqimi
# ─────────────────────────────────────────────────────────────────────────
class FakeMessage:
    def __init__(self) -> None:
        self.text = ""
        self.out: list[str] = []
        self.markups: list = []

    async def reply_text(self, text, reply_markup=None, **kwargs):
        self.out.append(text)
        self.markups.append(reply_markup)
        return self

    async def edit_text(self, text, reply_markup=None, **kwargs):
        self.out.append(text)
        self.markups.append(reply_markup)

    @property
    def last(self) -> str:
        return self.out[-1] if self.out else ""

    @property
    def last_markup(self):
        return self.markups[-1] if self.markups else None


class FakeQuery:
    def __init__(self) -> None:
        self.out: list[str] = []
        self.answers: list[str] = []
        self.markups: list = []
        self.data: str = ""
        self.from_user = SimpleNamespace(id=UID)

    async def answer(self, text="", show_alert=False, **kwargs):
        self.answers.append(text)

    async def edit_message_text(self, text, reply_markup=None, **kwargs):
        self.out.append(text)
        self.markups.append(reply_markup)


class FakeUpdate:
    def __init__(self, uid: int) -> None:
        self.effective_user = SimpleNamespace(
            id=uid, full_name=f"User {uid}", username=f"user{uid}"
        )
        self.message = FakeMessage()
        self.callback_query = FakeQuery()
        self.callback_query.message = self.message


def _last_markup(up):
    """Oxirgi yuborilgan/tahrirlangan klaviaturani qaytaradi."""
    if up.callback_query.markups:
        return up.callback_query.markups[-1]
    if up.message.markups:
        return up.message.markups[-1]
    return None


class DiscoverToggleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "router.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        await db.upsert_user(UID, name="Vali", session="SESS", is_admin=1)
        discover_sessions.reset()
        G.reset_discover_guards()

    async def asyncTearDown(self) -> None:
        discover_sessions.reset()
        G.reset_discover_guards()
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    def _session(self, count: int = 2):
        groups = [
            discover_sessions.DiscoveredGroup(
                reference=f"@guruh{i}",
                title=f"Guruh {i}",
                members=10,
                key=f"@guruh{i}",
            )
            for i in range(count)
        ]
        return discover_sessions.start_session(UID, groups)

    async def test_disc_toggle_selects_group(self) -> None:
        """`disc:toggle` — guruhni belgilashi kerak (✅ belgi chiqishi kerak)."""
        self._session(2)

        up = FakeUpdate(UID)
        up.callback_query.data = "disc:toggle:0"
        await CB.handle_callback(up, None)

        self.assertTrue(
            up.callback_query.answers,
            "alert chiqishi kerak — callback handler'ga yetib borishi kerak",
        )
        self.assertIn("Tanlandi", up.callback_query.answers[-1])

    async def test_disc_toggle_updates_markup(self) -> None:
        """Belgilangan guruh ro'yxatda ✅ bilan ko'rinishi kerak."""
        session = self._session(2)

        up = FakeUpdate(UID)
        up.callback_query.data = "disc:toggle:0"
        await CB.handle_callback(up, None)

        self.assertIn("@guruh0", session.selected, "guruh belgilangan bo'lishi kerak")

        markup = _last_markup(up)
        self.assertIsNotNone(markup, "klaviatura yangilanishi kerak")
        texts = [b.text for row in markup.inline_keyboard for b in row]
        self.assertTrue(
            any(t.startswith("✅") for t in texts),
            f"belgi (✅) chiqishi kerak, lekin topildi: {texts}",
        )

    async def test_disc_toggle_shows_apply_button(self) -> None:
        """Belgilangandan keyin «Tanlanganlarni qo'shish» tugmasi paydo bo'lishi kerak."""
        self._session(2)

        up = FakeUpdate(UID)
        up.callback_query.data = "disc:toggle:0"
        await CB.handle_callback(up, None)

        markup = _last_markup(up)
        self.assertIsNotNone(markup, "klaviatura yangilanishi kerak")
        data = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertIn(
            "disc:apply",
            data,
            "belgilangandan keyin «Tanlanganlarni qo'shish» tugmasi kerak",
        )

    async def test_disc_toggle_twice_unselects(self) -> None:
        """Ikkinchi marta bosish — belgi olib tashlanishi kerak."""
        session = self._session(2)

        up = FakeUpdate(UID)
        up.callback_query.data = "disc:toggle:0"
        await CB.handle_callback(up, None)
        await CB.handle_callback(up, None)

        self.assertNotIn("@guruh0", session.selected)

    async def test_disc_apply_adds_selected_groups(self) -> None:
        """«Tanlanganlarni qo'shish» — tanlangan guruhlar bazaga qo'shilishi kerak."""
        self._session(2)

        up = FakeUpdate(UID)
        up.callback_query.data = "disc:toggle:0"
        await CB.handle_callback(up, None)
        up.callback_query.data = "disc:apply"
        await CB.handle_callback(up, None)

        records = await db.get_chat_records(UID)
        values = [r["value"] for r in records]
        self.assertIn("@guruh0", values, "tanlangan guruh qo'shilishi kerak")
        self.assertNotIn("@guruh1", values, "belgilanmagan guruh qo'shilmasligi kerak")

    async def test_disc_toggle_unknown_index_alerts(self) -> None:
        """Noto'g'ri indeks — foydalanuvchiga xabar berilishi kerak."""
        self._session(1)

        up = FakeUpdate(UID)
        up.callback_query.data = "disc:toggle:99"
        await CB.handle_callback(up, None)

        self.assertTrue(up.callback_query.answers)
        self.assertIn("topilmadi", up.callback_query.answers[-1])

    async def test_disc_callback_without_session_expires(self) -> None:
        """Sessiya yo'q — «muddati tugagan» xabari berilishi kerak."""
        discover_sessions.reset()

        up = FakeUpdate(UID)
        up.callback_query.data = "disc:toggle:0"
        await CB.handle_callback(up, None)

        self.assertTrue(up.callback_query.answers)
        self.assertIn(
            "muddati tugagan",
            up.callback_query.answers[-1].lower(),
            "sessiya yo'q bo'lsa foydalanuvchi xabardan oqishi kerak",
        )


if __name__ == "__main__":
    unittest.main()
