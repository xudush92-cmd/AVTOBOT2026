"""Albom (bir nechta rasm/video) qo'shish, saqlash va guruhga yuborish.

Qamlov:
- bir nechta media bitta postga albom bo'lib yig'iladi (eski «faqat bitta
  rasm» cheklovi yo'q);
- «✅ Tayyor» tugmasi bosilmasa ham albom debounce yoki janitor orqali
  saqlanadi — media yo'qolib ketmaydi;
- media soni ``MAX_ALBUM_FILES`` bilan cheklanadi;
- worker albomni ``send_file`` ro'yxati bilan bir marta yuboradi, matnli
  postni esa link preview sozlamasiga rioya qilib yuboradi;
- shablon belgilari ({sana}, {vaqt}, {kun}, {A|B}) har bir yuborishda
  qayta hisoblanadi.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
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

from bot import login  # noqa: E402
from bot import posts  # noqa: E402
from config.config import MAX_ALBUM_FILES  # noqa: E402
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402
from core.utils import (  # noqa: E402
    media_kind_label,
    normalize_media,
    render_template,
)
from worker import worker as W  # noqa: E402


def fake_message(text: str = "", *, group_id: str | None = None, media: int = 0):
    """FTB xabarisiga o'xshatib tuzilgan oddiy obyekt (media yuklanmaydi)."""
    return SimpleNamespace(
        chat_id=2001,
        text=text if not media else None,
        caption=text if media else None,
        caption_entities=[],
        entities=[],
        photo=[object()] * (1 if media else 0),
        video=None,
        document=None,
        media_group_id=group_id,
        reply_text=AsyncMock(),
    )


def update_for(msg):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=2001), message=msg
    )


class AlbumTestCase(unittest.IsolatedAsyncioTestCase):
    """Haqiqiy vaqtinchalik SQLite + soxta media yuklash."""

    UID = 2001

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        self.media_dir = Path(self.temp.name) / "media"
        self.media_dir.mkdir()
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        login.user_states.clear()
        await db.upsert_user(self.UID, name="Ali", is_admin=1)

        # Debounce o'chiriladi: testlar tugma yoki sweep orqali yakunlaydi.
        self._patches = [patch.object(posts, "ALBUM_DEBOUNCE_S", 0)]
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
    def make_media_files(self, count: int) -> list[str]:
        paths = []
        for index in range(count):
            path = self.media_dir / f"pic{index}.jpg"
            path.write_bytes(b"fake-jpeg")
            paths.append(str(path))
        return paths

    def patch_download(self, paths: list[str], kind: str = "photo"):
        """``download_message_media`` o'rniga tayyor fayl ro'yxatini qaytaradi.

        Har bir chaqiruvda BITTA media qaytariladi (Telegram xabarida bitta
        rasm bo'lgani kabi) va so'ralgan ``remaining``dan oshmaydi.
        """
        calls: list[int | None] = []

        async def _fake(msg, uid, *, remaining=None):
            calls.append(remaining)
            if remaining is not None and remaining <= 0:
                return [], [f"❌ Bitta postda maksimal {MAX_ALBUM_FILES} ta media."]
            return [{"path": paths[0], "kind": kind}], []

        mock = AsyncMock(side_effect=_fake)
        patcher = patch.object(posts, "download_message_media", new=mock)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    # ── 1. Albom yig'ish ──
    async def test_multiple_media_become_one_album_post(self) -> None:
        paths = self.make_media_files(3)
        self.patch_download(paths)
        await posts.begin_add_post(update_for(fake_message()))

        for _ in range(3):
            await posts.handle_add_post(
                update_for(fake_message("Yangi aksiya", group_id="g1", media=1))
            )

        state = login.user_states[self.UID]
        self.assertEqual(len(state["album"]["items"]), 3)
        self.assertEqual(await db.count_posts(self.UID), 0)

        saved, note = await posts.finalize_pending_album(self.UID)
        self.assertTrue(saved)
        posts_list = await db.get_posts(self.UID)
        self.assertEqual(len(posts_list), 1)
        post = posts_list[0]
        self.assertEqual(len(normalize_media(post)), 3)
        self.assertEqual(post["text"], "Yangi aksiya")
        # Eski kod post["photo"]ga tayanadi — uni ham saqlab qo'yish kerak.
        self.assertEqual(post["photo"], paths[0])
        self.assertIn("3", note)

    async def test_debounce_finalizes_without_button(self) -> None:
        paths = self.make_media_files(2)
        self.patch_download(paths)
        with patch.object(posts, "ALBUM_DEBOUNCE_S", 0.01):
            await posts.begin_add_post(update_for(fake_message()))
            await posts.handle_add_post(
                update_for(fake_message("Chegirma", group_id="g2", media=1))
            )
            await asyncio.sleep(0.2)
        saved = await db.get_posts(self.UID)
        self.assertEqual(len(saved), 1)
        self.assertEqual(len(normalize_media(saved[0])), 1)
        self.assertNotIn("album", login.user_states.get(self.UID, {}))

    async def test_album_respects_max_files(self) -> None:
        paths = self.make_media_files(1)
        remaining_seen = self.patch_download(paths)
        await posts.begin_add_post(update_for(fake_message()))
        for _ in range(MAX_ALBUM_FILES + 2):
            await posts.handle_add_post(
                update_for(fake_message("Aksiya", group_id="g3", media=1))
            )

        # Limitga yetgan zahoti albom o'zi saqlanadi va holat yopiladi.
        self.assertNotIn("album", login.user_states.get(self.UID, {}))
        saved = await db.get_posts(self.UID)
        self.assertEqual(len(saved), 1)
        self.assertEqual(len(normalize_media(saved[0])), MAX_ALBUM_FILES)
        # So'ralgan joy kamayib bordi (yangi post boshlanmadi).
        self.assertEqual(remaining_seen[0], MAX_ALBUM_FILES)

    async def test_sweep_saves_abandoned_album(self) -> None:
        paths = self.make_media_files(2)
        self.patch_download(paths)
        await posts.begin_add_post(update_for(fake_message()))
        await posts.handle_add_post(
            update_for(fake_message("Eski albom", group_id="g4", media=1))
        )
        # Albom "eski" bo'ladi — xuddi foydalanuvchi tugmani bosmay qo'ygandek.
        login.user_states[self.UID]["album"]["ts"] = time.time() - 600

        swept = await posts.sweep_stale_albums(max_age_s=120)
        self.assertEqual(swept, 1)
        saved = await db.get_posts(self.UID)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["text"], "Eski albom")

    async def test_text_only_post_still_saved(self) -> None:
        await posts.begin_add_post(update_for(fake_message()))
        await posts.handle_add_post(update_for(fake_message("Faqat matn")))
        saved = await db.get_posts(self.UID)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["text"], "Faqat matn")
        self.assertEqual(normalize_media(saved[0]), [])
        self.assertEqual(media_kind_label(saved[0]), "📝 Matn")

    async def test_post_limit_blocks_extra_posts(self) -> None:
        await db.set_plan(self.UID, "SINOV")  # max_posts = 2
        await posts.begin_add_post(update_for(fake_message()))
        await posts.handle_add_post(update_for(fake_message("1-post")))
        await posts.begin_add_post(update_for(fake_message()))
        await posts.handle_add_post(update_for(fake_message("2-post")))
        await posts.begin_add_post(update_for(fake_message()))
        await posts.handle_add_post(update_for(fake_message("3-post")))
        self.assertEqual(await db.count_posts(self.UID), 2)

    # ── 2. Worker yuborish ──
    async def test_send_post_album_single_call(self) -> None:
        paths = self.make_media_files(3)
        client = SimpleNamespace(
            send_file=AsyncMock(), send_message=AsyncMock(), files=paths
        )
        post = {
            "text": "E'lon",
            "entities": [],
            "media": [{"path": path, "kind": "photo"} for path in paths],
            "photo": paths[0],
            "link_preview": 1,
        }
        with patch.object(W, "resolve_chat", new=AsyncMock(return_value="entity")):
            await W.send_post(client, "@group", post)

        client.send_file.assert_awaited_once()
        kwargs = client.send_file.await_args.kwargs
        self.assertEqual(kwargs["file"], paths[:MAX_ALBUM_FILES])
        self.assertEqual(kwargs["caption"], "E'lon")
        client.send_message.assert_not_awaited()

    async def test_send_post_single_media_and_text(self) -> None:
        path = self.make_media_files(1)[0]
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        with patch.object(W, "resolve_chat", new=AsyncMock(return_value="entity")):
            await W.send_post(
                client,
                "@group",
                {"text": "Bitta rasm", "entities": [], "media": [
                    {"path": path, "kind": "photo"}], "photo": path,
                 "link_preview": 1},
            )
        self.assertEqual(client.send_file.await_args.kwargs["file"], path)

        client2 = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        with patch.object(W, "resolve_chat", new=AsyncMock(return_value="entity")):
            await W.send_post(
                client2,
                "@group",
                {"text": "https://example.com", "entities": [], "media": [],
                 "photo": "", "link_preview": 0},
            )
        self.assertFalse(client2.send_message.await_args.kwargs["link_preview"])
        client2.send_file.assert_not_awaited()

    async def test_send_post_renders_template(self) -> None:
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        post = {"text": "{kun} {sana} {vaqt}", "entities": [], "media": [],
                "photo": "", "link_preview": 1}
        with patch.object(W, "resolve_chat", new=AsyncMock(return_value="entity")):
            await W.send_post(client, "@group", post)
        sent = client.send_message.await_args.kwargs["message"]
        self.assertNotIn("{", sent)
        self.assertRegex(sent, r"\d{2}:\d{2}")

    async def test_missing_media_files_are_skipped(self) -> None:
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        post = {"text": "Fayllar o'chgan", "entities": [], "media": [
            {"path": "/nonexistent/x.jpg", "kind": "photo"}], "photo": "",
            "link_preview": 1}
        with patch.object(W, "resolve_chat", new=AsyncMock(return_value="entity")):
            await W.send_post(client, "@group", post)
        client.send_file.assert_not_awaited()
        self.assertEqual(
            client.send_message.await_args.kwargs["message"], "Fayllar o'chgan"
        )

    # ── 3. Shablon/format yordamchilari ──
    def test_render_template_keeps_entities_and_spintax(self) -> None:
        text, entities = render_template(
            "🔥 {A|B} aksiya", [{"type": "bold", "offset": 0, "length": 2}]
        )
        self.assertTrue(text.startswith("🔥 "))
        self.assertNotIn("{A|B}", text)
        self.assertIn(text[2], "AB")
        self.assertEqual(entities[0]["type"], "bold")


if __name__ == "__main__":
    unittest.main()
