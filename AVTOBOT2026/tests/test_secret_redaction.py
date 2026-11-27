"""
Maxfiylik: foydalanuvchi paroli va kodi logga tushmasligi kerak.

**Xavf:** 2FA parol va Telegram tasdiqlash kodi — maxfiy ma'lumot.
Log fayli serverda saqlanadi va qo'lda ochilishi mumkin. Agar u
logga tushsa, maxfiy ma'lumot sizib chiqadi.

**Asosiy xato (tuzatildi):** ``main.py::on_message()`` xatoni yozganda
``action=(update.message.text or "")[:40]`` — ya'ni foydalanuvchining
**kiritgan matni** — logga yozilardi. ``step == "password```` bo'lganda
bu 2FA parol edi.

**Yechim:**
1. ``core/errlog.py::redact()`` — ``key=value`` ko'rinishidagi maxfiy
   qiymatlarni yopadi;
2. ``core/errlog.py::log_error()`` — xato matni, sarlavha va traceback
   redaksiyadan o'tadi;
3. ``main.py::_safe_action_label()`` — foydalanuvchi matni o'rniga
   faqat **bosqich nomi** yoziladi (``step=password``).
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "991460501")

from core.errlog import log_error, log_event, log_gap, redact

UID = 991460501
SECRET = "MySecretPassword123"


class RedactTests(unittest.TestCase):
    """``redact()`` — maxfiy qiymatlarni yopishi kerak."""

    def test_redacts_password_assignment(self) -> None:
        out = redact("password=MySecretPassword123")
        self.assertNotIn("MySecretPassword123", out)
        self.assertIn("password=***", out)

    def test_redacts_code_assignment(self) -> None:
        out = redact("code=12345")
        self.assertNotIn("12345", out)

    def test_redacts_phone_assignment(self) -> None:
        out = redact("phone=+998901234567")
        self.assertNotIn("+998901234567", out)

    def test_redacts_token_and_hash(self) -> None:
        for key in ("token", "hash", "session", "auth_key", "secret"):
            with self.subTest(key=key):
                out = redact(f"{key}=ABCDEF123")
                self.assertNotIn("ABCDEF123", out)

    def test_is_case_insensitive(self) -> None:
        out = redact("PassWord=ABCDEF123")
        self.assertNotIn("ABCDEF123", out)

    def test_quoted_value_is_redacted(self) -> None:
        out = redact('password="MySecretPassword123"')
        self.assertNotIn("MySecretPassword123", out)

    def test_plain_text_without_key_is_kept(self) -> None:
        """Kalit yo'q matn o'zgarishi shart emas — faqat kalitli qiymatlar."""
        out = redact("Foydalanuvchi topilmadi")
        self.assertIn("Foydalanuvchi topilmadi", out)

    def test_empty_and_none(self) -> None:
        self.assertEqual(redact(None), "")
        self.assertEqual(redact(""), "")


class LogErrorRedactionTests(unittest.TestCase):
    """``log_error`` — xato matni va traceback redaksiyalanadi."""

    def test_error_message_is_redacted(self) -> None:
        with patch("core.errlog.log") as fake_log:
            log_error(UID, "Xato", ValueError(f"password={SECRET}"))
        written = " ".join(str(c.args[0]) for c in fake_log.call_args_list)
        self.assertNotIn(SECRET, written)

    def test_action_is_redacted(self) -> None:
        with patch("core.errlog.log") as fake_log:
            log_error(UID, "Xato", ValueError("x"), action=f"code={SECRET}")
        written = " ".join(str(c.args[0]) for c in fake_log.call_args_list)
        self.assertNotIn(SECRET, written)

    def test_extra_is_redacted(self) -> None:
        with patch("core.errlog.log") as fake_log:
            log_error(UID, "Xato", ValueError("x"), extra=f"token={SECRET}")
        written = " ".join(str(c.args[0]) for c in fake_log.call_args_list)
        self.assertNotIn(SECRET, written)

    def test_traceback_is_redacted(self) -> None:
        """Traceback ichidagi maxfiy qiymat ham yopilishi kerak."""
        try:
            raise RuntimeError(f"password={SECRET}")
        except RuntimeError as exc:
            with patch("core.errlog.log") as fake_log:
                log_error(UID, "Xato", exc)
        written = " ".join(str(c.args[0]) for c in fake_log.call_args_list)
        self.assertNotIn(SECRET, written)

    def test_context_is_redacted(self) -> None:
        with patch("core.errlog.log") as fake_log:
            log_error(UID, f"Xato password={SECRET}", ValueError("x"))
        written = " ".join(str(c.args[0]) for c in fake_log.call_args_list)
        self.assertNotIn(SECRET, written)


class LogGapAndEventRedactionTests(unittest.TestCase):
    """``log_gap`` va ``log_event`` — ham redaksiya qilinadi."""

    def test_gap_reason_is_redacted(self) -> None:
        with patch("core.errlog.log") as fake_log:
            log_gap(UID, f"Kod noto'g'ri: code={SECRET}")
        written = " ".join(str(c.args[0]) for c in fake_log.call_args_list)
        self.assertNotIn(SECRET, written)

    def test_event_is_redacted(self) -> None:
        with patch("core.errlog.log") as fake_log:
            log_event(UID, f"Kirish: password={SECRET}")
        written = " ".join(str(c.args[0]) for c in fake_log.call_args_list)
        self.assertNotIn(SECRET, written)


class SafeActionLabelTests(unittest.TestCase):
    """``main.py::_safe_action_label()`` — foydalanuvchi matni yo'q."""

    def _label(self, step: str | None) -> str | None:
        import main

        with patch.object(
            main, "_safe_action_label", main._safe_action_label, create=True
        ):
            pass
        # ``_safe_action_label`` ichida ``user_states`` ishlatiladi —
        # uni to'g'ridan-to'g'ri chaqiramiz.
        from bot.login import user_states

        user_states.clear()
        if step is not None:
            user_states[UID] = {"step": step, "ts": 0}
        try:
            return main._safe_action_label(UID)
        finally:
            user_states.clear()

    def test_no_state_returns_generic_step(self) -> None:
        self.assertEqual(self._label(None), "step=matn")

    def test_password_step_returns_step_name_only(self) -> None:
        label = self._label("password")
        self.assertEqual(label, "step=password")
        self.assertNotIn("=", label.split("=", 1)[1])

    def test_code_step_returns_step_name_only(self) -> None:
        self.assertEqual(self._label("code"), "step=code")

    def test_other_step_returns_step_name(self) -> None:
        self.assertEqual(self._label("set_interval"), "step=set_interval")


class MessageTextNeverLoggedTests(unittest.TestCase):
    """``main.py::on_message`` — foydalanuvchi matni logga tushmasligi kerak.

    ⚠️ Bu — asosiy regressiya testi. Avval ``action`` ga
    ``update.message.text`` yozilardi.
    """

    def test_on_message_source_has_no_message_text(self) -> None:
        """Kod manbasida foydalanuvchi matni logga berilmasligi kerak.

        ⚠️ Faqat **kod** tekshiriladi — docstring emas (izohda so'z
        sifatida ishlatilishi normal).
        """
        import ast
        import inspect

        import main

        src = inspect.getsource(main.on_message)
        tree = ast.parse(src)
        # Docstring'ni chiqarib tashlaymiz.
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if (
                isinstance(body, list)
                and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body.pop(0)

        code = ast.unparse(tree)
        self.assertNotIn("message.text", code)
        self.assertNotIn("msg.text", code)
        self.assertNotIn(".text", code)

    def test_repo_has_no_raw_text_in_log_action(self) -> None:
        """Butun repozitoriyada ``action=`` ga matn berilmasligi kerak."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parent.parent
        offenders: list[str] = []
        for path in root.rglob("*.py"):
            rel = path.relative_to(root)
            if "tests" in rel.parts:
                continue
            txt = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(txt.split("\n"), 1):
                if "action=" not in line:
                    continue
                # Kalit nomi bilan qiymat berilgan joy — ruxsat etilgan.
                if any(
                    marker in line
                    for marker in (
                        "action=data",
                        "action=f\"",
                        "action='",
                        'action="',
                        "action=None",
                    )
                ):
                    continue
                if "action=(" in line and "message.text" in line:
                    offenders.append(f"{rel}:{lineno}")
        self.assertEqual(offenders, [], f"Xavfli joylar: {offenders}")


class LogFilePermissionTests(unittest.TestCase):
    """Log fayli faqat egasi tomonidan o'qilishi kerak.

    Log faylida telefon raqam, foydalanuvchi nomlari va xato
    tafsilotlari saqlanadi — uni boshqa foydalanuvchilar o'qolmasi kerak.
    """

    def test_log_file_is_owner_only(self) -> None:
        import os
        import stat

        from config.config import LOG_FILE

        path = str(LOG_FILE)
        if not os.path.exists(path):
            self.skipTest("Log fayli hali yaratilmagan")

        mode = stat.S_IMODE(os.stat(path).st_mode)
        self.assertEqual(
            mode & 0o077,
            0,
            f"Log fayli ommaviy bo'lishi kerak emas (chmod={oct(mode)})",
        )


if __name__ == "__main__":
    unittest.main()
