"""Startup API yuzasi regressiya testlari.

PTB (python-telegram-bot) 20.x versiyasidan boshlab ``set_my_commands`` kabi
Telegram API metodlari ``Application``'dan olib tashlanib, faqat ``Bot``
obyektida qoldirilgan. ``main.py`` dagi ``await app.set_my_commands(...)``
chaqiruvi serverda ``AttributeError`` berib, botni crash-loopga tushirgan.

Bu test ``main.py`` va boshqa modullardagi ``app.*`` / ``application.*``
chaqiruvlarini PTB'ning haqiqiy ``Application`` klassi bilan statik
solishtiradi — noto'g'ri metod yana yozilsa, test serverga yetmasdan qizil
yonadi.
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from telegram.ext import Application  # noqa: E402

# app.xxx( yoki application.xxx( — lekin app.bot.xxx / application.bot.xxx emas.
_APP_CALL_RE = re.compile(r"\b(?:app|application)\.([a-z_]+)\s*\(")


def _collect_application_calls(path: Path) -> set[str]:
    """Fayldagi app.* / application.* (.botsiz) metod nomlarini yig'adi."""
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        # app.bot.* chaqiruvlari Bot yuzasi — ularni bu tekshiruvdan chiqaramiz.
        cleaned = re.sub(r"\b(?:app|application)\.bot\.[a-z_]+\s*\(", "", line)
        for match in _APP_CALL_RE.finditer(cleaned):
            names.add(match.group(1))
    return names


class StartupApiSurfaceTests(unittest.TestCase):
    def test_main_uses_bot_for_set_my_commands(self) -> None:
        """set_my_commands faqat app.bot orqali chaqirilishi shart."""
        source = (APP_DIR / "main.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "await app.set_my_commands(",
            source,
            "Application'da set_my_commands yo'q — app.bot.set_my_commands ishlating",
        )
        self.assertIn("await app.bot.set_my_commands(", source)

    def test_every_app_call_in_main_exists_on_application(self) -> None:
        """main.py dagi har bir app.* metodi PTB Application'da mavjud bo'lishi kerak."""
        calls = _collect_application_calls(APP_DIR / "main.py")
        missing = sorted(name for name in calls if not hasattr(Application, name))
        self.assertEqual(
            missing,
            [],
            f"Application'da mavjud bo'lmagan app.* chaqiruvlari: {missing}",
        )

    def test_application_calls_across_modules_exist_on_application(self) -> None:
        """bot/ va admin/ modullaridagi application.* chaqiruvlari ham yaroqli bo'lsin."""
        broken: list[str] = []
        for module_dir in ("bot", "admin", "worker"):
            for path in (APP_DIR / module_dir).rglob("*.py"):
                for name in _collect_application_calls(path):
                    if not hasattr(Application, name):
                        broken.append(f"{path.relative_to(APP_DIR)}: application.{name}")
        self.assertEqual(broken, [], f"Yaroqsiz application.* chaqiruvlari: {broken}")


if __name__ == "__main__":
    unittest.main()
