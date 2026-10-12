"""Post tahrirlash, ko'rinish, sinov yuborish, guruh tekshiruvi va tez tasdiq.

Qamlov:
- post ro'yxatidagi tugmalar to'g'ri ishlaydi (``ped:<id>:<page>`` va
  ``pvw:id:<id>:<page>`` ikkala shakl ham);
- tahrirlashda matn yangilanadi, media yuborilmasa eski media saqlanadi,
  yangi media yuborilsa eskilari o'chiriladi;
- link preview yoqib/o'chiriladi va worker shuni hurmat qiladi;
- ``🧪 Sinov`` bir marta tasdiq bilan bitta guruhga yuboriladi (token eskirsa
  amal bajarilmaydi);
- 🔎 guruh tekshiruvi a'zolik/yozish huquqini aniq sabab bilan qaytaradi;
- tez tasdiqlash o'chirilgan holatda umuman ishlamaydi, yoqilganda faqat
  past riskli va sessiyasi tasdiqlangan arizalarni tasdiqlaydi.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
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

from admin import auto_approve as AA  # noqa: E402
from bot import callbacks as CB  # noqa: E402
from bot import groups as G  # noqa: E402
from bot import login  # noqa: E402
from bot import posts  # noqa: E402
from bot import texts as T  # noqa: E402
from config.config import SUPER_ADMIN  # noqa: E402
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402

UID = 2001
FROZEN_NOW = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)


class ToolTestCase(unittest.IsolatedAsyncioTestCase):
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

        self.sent: list[tuple[int, str]] = []

        async def _send(chat_id, text, **kwargs):
            self.sent.append((int(chat_id), str(text)))

        self.app = SimpleNamespace(
            bot=SimpleNamespace(
                send_message=_send,
                send_photo=AsyncMock(),
                send_video=AsyncMock(),
                send_document=AsyncMock(),
                send_audio=AsyncMock(),
                send_media_group=AsyncMock(),
            )
        )
        self._patches = [
            patch("core.utils.now_utc", return_value=FROZEN_NOW),
            patch.object(login, "application", self.app),
            patch.object(CB, "application", self.app),
            patch.object(posts, "user_media_dir", return_value=str(self.media_dir)),
            patch.object(posts, "ALBUM_DEBOUNCE_S", 0),
        ]
        for patcher in self._patches:
            patcher.start()

        await db.upsert_user(UID, name="Ali", is_admin=1, session="SESS")

    async def asyncTearDown(self) -> None:
        for patcher in reversed(self._patches):
            patcher.stop()
        login.user_states.clear()
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    # ── yordamchilar ──
    def write_media(self, name: str) -> str:
        path = self.media_dir / name
        path.write_bytes(b"x")
        return str(path)

    def callback(self, data: str):
        query = SimpleNamespace(
            data=data,
            from_user=SimpleNamespace(id=UID),
            message=SimpleNamespace(chat_id=UID, reply_text=AsyncMock()),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        return SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=UID),
            effective_chat=SimpleNamespace(type="private"),
            message=None,
        )

    async def press(self, data: str):
        update = self.callback(data)
        await CB.handle_callback(update, SimpleNamespace())
        return update

    # ── 1. Tahrirlash ──
    async def test_edit_keeps_media_when_only_text_sent(self) -> None:
        path = self.write_media("keep.jpg")
        ok, _, post_id = await db.add_post(
            UID, "eski matn", [], path, [{"path": path, "kind": "photo"}]
        )
        self.assertTrue(ok)

        text = await posts.begin_edit_post_state(UID, int(post_id))
        self.assertIn("eski matn", text)
        state = login.user_states[UID]
        self.assertEqual(state["mode"], "edit")

        msg = SimpleNamespace(
            chat_id=UID,
            text="yangi matn",
            caption=None,
            entities=[],
            caption_entities=[],
            photo=None,
            video=None,
            document=None,
            media_group_id=None,
            reply_text=AsyncMock(),
        )
        await posts.handle_add_post(SimpleNamespace(
            effective_user=SimpleNamespace(id=UID), message=msg
        ))

        post = await db.get_post(int(post_id), UID)
        self.assertEqual(post["text"], "yangi matn")
        self.assertEqual(len(post["media"]), 1)
        self.assertTrue(Path(path).exists(), "eski media saqlanib qolishi kerak")
        self.assertNotIn(UID, login.user_states)

    async def test_edit_with_new_media_removes_old_files(self) -> None:
        old_path = self.write_media("old.jpg")
        new_path = self.write_media("new.jpg")
        _, _, post_id = await db.add_post(
            UID, "matn", [], old_path, [{"path": old_path, "kind": "photo"}]
        )
        await posts.begin_edit_post_state(UID, int(post_id))

        async def fake_download(msg, uid, *, remaining=None):
            return [{"path": new_path, "kind": "photo"}], []

        msg = SimpleNamespace(
            chat_id=UID,
            text=None,
            caption="yangi rasm bilan",
            entities=[],
            caption_entities=[],
            photo=[object()],
            video=None,
            document=None,
            media_group_id=None,
            reply_text=AsyncMock(),
        )
        with patch.object(posts, "download_message_media", new=fake_download):
            await posts.handle_add_post(
                SimpleNamespace(effective_user=SimpleNamespace(id=UID), message=msg)
            )

        post = await db.get_post(int(post_id), UID)
        self.assertEqual([item["path"] for item in post["media"]], [new_path])
        self.assertEqual(post["photo"], new_path)
        self.assertFalse(Path(old_path).exists(), "eskirgan fayl o'chirilsin")

    async def test_edit_missing_post_is_safe(self) -> None:
        self.assertEqual(await posts.begin_edit_post_state(UID, 999999), "")

    # ── 2. Link preview ──
    async def test_link_preview_toggle_and_update_preserves_it(self) -> None:
        path = self.write_media("lp.jpg")
        _, _, post_id = await db.add_post(
            UID, "https://example.com", [], None, [{"path": path, "kind": "photo"}]
        )
        self.assertTrue((await db.get_post(int(post_id), UID))["link_preview"])

        # update_post(link_preview=None) — qiymat o'zgarishsiz qoladi.
        await db.update_post(UID, int(post_id), "yangi matn", [], None, None, None)
        self.assertTrue((await db.get_post(int(post_id), UID))["link_preview"])

        self.assertTrue(await db.set_post_link_preview(UID, int(post_id), False))
        post = await db.get_post(int(post_id), UID)
        self.assertFalse(post["link_preview"])
        await db.update_post(UID, int(post_id), "matn2", [], None, None, None)
        self.assertFalse((await db.get_post(int(post_id), UID))["link_preview"])

    async def test_link_preview_button_callback(self) -> None:
        _, _, post_id = await db.add_post(UID, "https://example.com", [], None)
        update = await self.press(f"lp:toggle:{int(post_id)}")
        text = update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("o'chirildi", text)
        self.assertFalse((await db.get_post(int(post_id), UID))["link_preview"])

        update = await self.press(f"lp:toggle:{int(post_id)}")
        text = update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("yoqildi", text)
        self.assertTrue((await db.get_post(int(post_id), UID))["link_preview"])

        # Begona post — tegilmaydi.
        other = 424242
        update = await self.press(f"lp:toggle:{other}")
        self.assertEqual(
            update.callback_query.edit_message_text.await_args.args[0],
            T.POST_NOT_FOUND,
        )

    # ── 3. Ko'rinish va tanlagich ──
    async def test_picker_callback_shapes(self) -> None:
        path = self.write_media("p.jpg")
        _, _, post_id = await db.add_post(
            UID, "ko'rinish testi", [], path, [{"path": path, "kind": "photo"}]
        )
        posts_list = await db.get_posts(UID)

        # Ro'yxat tugmasi shakli: ``ped:<id>:<page>``
        from bot import keyboards as KB

        edit_buttons = {
            button.callback_data
            for row in KB.kb_posts_edit(posts_list).inline_keyboard
            for button in row
        }
        self.assertIn(f"ped:{int(post_id)}:0", edit_buttons)
        self.assertIn("ped:cancel", edit_buttons)

        update = await self.press(f"ped:{int(post_id)}:0")
        sent_texts = [text for _, text in self.sent]
        self.assertTrue(any("ko'rinish testi" in text for text in sent_texts))
        self.assertEqual(login.user_states[UID]["mode"], "edit")
        self.assertIn("Tahrirlash oynasi", update.callback_query.edit_message_text.await_args.args[0])

        # Post amallari oynasi shakli: ``pvw:id:<id>:<page>``
        with patch.object(posts, "preview_post", new=AsyncMock(return_value=(True, "media"))):
            update = await self.press(f"pvw:id:{int(post_id)}:0")
        text = update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("KO'RINISH", text.upper())

        # Sahifalash ham ishlashi kerak.
        update = await self.press("pvw:page:0")
        self.assertIn("KO'RINISH", update.callback_query.edit_message_text.await_args.args[0].upper())

    async def test_preview_sends_album_and_single_media(self) -> None:
        first = self.write_media("a.jpg")
        second = self.write_media("b.jpg")
        _, _, album_id = await db.add_post(
            UID,
            "albom",
            [],
            first,
            [{"path": first, "kind": "photo"}, {"path": second, "kind": "photo"}],
        )
        self.app.bot.send_media_group.reset_mock()
        ok, kind = await posts.preview_post(UID, int(album_id))
        self.assertTrue(ok)
        self.assertEqual(kind, "album")
        self.app.bot.send_media_group.assert_awaited_once()

        _, _, single_id = await db.add_post(
            UID, "bitta", [], first, [{"path": first, "kind": "photo"}]
        )
        ok, kind = await posts.preview_post(UID, int(single_id))
        self.assertEqual(kind, "media")
        self.app.bot.send_photo.assert_awaited_once()

        # Matnli post — oddiy xabar.
        _, _, text_id = await db.add_post(UID, "faqat matn", [], None)
        ok, kind = await posts.preview_post(UID, int(text_id))
        self.assertEqual(kind, "text")

        # Noma'lum post.
        ok, message = await posts.preview_post(UID, 999)
        self.assertFalse(ok)
        self.assertEqual(message, T.POST_NOT_FOUND)

    async def test_preview_falls_back_when_media_fails(self) -> None:
        path = self.write_media("broken.jpg")
        _, _, post_id = await db.add_post(
            UID, "buzilgan", [], path, [{"path": path, "kind": "photo"}]
        )
        self.app.bot.send_photo = AsyncMock(side_effect=Exception("FloodWait"))
        ok, kind = await posts.preview_post(UID, int(post_id))
        self.assertTrue(ok)
        self.assertEqual(kind, "fallback")
        self.assertIn("buzilgan", self.sent[-1][1])

    # ── 4. Sinov yuborish ──
    async def test_test_send_flow_with_token(self) -> None:
        await db.add_chat(UID, "@target")
        gid = int((await db.get_chat_records(UID))[0]["id"])
        _, _, post_id = await db.add_post(UID, "sinov matni", [], None)

        # Post tanlash → guruh ro'yxati
        update = await self.press(f"tstp:{int(post_id)}:0")
        markup = update.callback_query.edit_message_text.await_args.kwargs["reply_markup"]
        buttons = {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        }
        self.assertIn(f"tstg:ask:{int(post_id)}:{gid}", buttons)

        # Guruh tanlash → tasdiq so'rovi (token bilan)
        update = await self.press(f"tstg:ask:{int(post_id)}:{gid}")
        confirm = update.callback_query.edit_message_text.await_args.kwargs["reply_markup"]
        data = [
            button.callback_data
            for row in confirm.inline_keyboard
            for button in row
            if button.callback_data
        ][0]
        self.assertTrue(data.startswith(f"tst:go:{int(post_id)}:{gid}:"))

        sent_calls = []

        async def fake_send(uid, pid, group_id):
            sent_calls.append((uid, pid, group_id))
            return True, "🧪 Sinov yuborildi"

        with patch.object(posts, "send_test_to_group", new=fake_send):
            update = await self.press(data)
        self.assertEqual(sent_calls, [(UID, int(post_id), gid)])
        # Tasdiq tokeni bir marta ishlatiladi — ikkinchi bosish ishlamaydi.
        with patch.object(posts, "send_test_to_group", new=fake_send):
            update = await self.press(data)
        self.assertEqual(len(sent_calls), 1)
        self.assertIn("eskirgan", update.callback_query.edit_message_text.await_args.args[0])

    async def test_test_send_logs_result(self) -> None:
        await db.add_chat(UID, "@target")
        gid = int((await db.get_chat_records(UID))[0]["id"])
        _, _, post_id = await db.add_post(UID, "sinov", [], None)

        pool = SimpleNamespace(
            acquire=AsyncMock(return_value=SimpleNamespace()),
            release=AsyncMock(),
        )
        from worker import worker as W

        with patch.object(W, "client_pool", pool), patch.object(
            W, "send_post", new=AsyncMock()
        ):
            ok, message = await posts.send_test_to_group(UID, int(post_id), gid)
        self.assertTrue(ok)
        self.assertIn("@target", message)
        stats = await db.send_stats(UID)
        self.assertEqual(stats["sent_ok"], 1)

        # Xato bo'lsa — muvaffaqiyatsiz yozuv qoladi.
        with patch.object(W, "client_pool", pool), patch.object(
            W, "send_post", new=AsyncMock(side_effect=RuntimeError("boom"))
        ):
            ok, _ = await posts.send_test_to_group(UID, int(post_id), gid)
        self.assertFalse(ok)
        stats = await db.send_stats(UID)
        self.assertEqual(stats["sent_failed"], 1)

    async def test_test_send_without_session(self) -> None:
        await db.add_chat(UID, "@target")
        gid = int((await db.get_chat_records(UID))[0]["id"])
        _, _, post_id = await db.add_post(UID, "sinov", [], None)
        await db.del_session(UID)
        from worker import worker as W

        with patch.object(W, "client_pool", SimpleNamespace(acquire=AsyncMock())):
            ok, message = await posts.send_test_to_group(UID, int(post_id), gid)
        self.assertFalse(ok)
        self.assertIn("Sessiya", message)

    # ── 5. Bloklangan foydalanuvchi cheklovni aylanmasin ──
    async def test_blocked_user_cannot_use_new_buttons(self) -> None:
        await db.set_blocked(UID, True)
        for data in ("alb:done", "ped:1:0", "pvw:1:0", "lp:toggle:1", "tstg:ask:1:1"):
            update = await self.press(data)
            self.assertEqual(
                update.callback_query.edit_message_text.await_args.args[0],
                T.BLOCKED,
                data,
            )

    # ── 6. Guruhni tekshirish ──
    async def test_group_check_reasons(self) -> None:
        from telethon.errors import (
            ChannelPrivateError,
            PeerIdInvalidError,
            UserNotParticipantError,
        )

        def fake_client(**behavior):
            class _Client:
                def __init__(self, *a, **kw):
                    pass

                async def connect(self):
                    return None

                async def disconnect(self):
                    return None

                async def get_me(self):
                    return behavior.get("me", SimpleNamespace(id=UID))

                async def get_permissions(self, entity, me):
                    error = behavior.get("permissions_error")
                    if error:
                        raise error
                    return behavior["permissions"]

            return _Client

        entity_ok = SimpleNamespace(broadcast=False, left=False, banned_rights=None,
                                    default_banned_rights=None)
        perms_ok = SimpleNamespace(
            has_left=False,
            participant=SimpleNamespace(left=False, banned_rights=None),
            is_creator=False,
            is_admin=False,
            send_messages=True,
            post_messages=False,
        )

        async def run(behavior, entity=entity_ok, group="@news"):
            with patch.object(G, "TelegramClient", fake_client(**behavior)), patch.object(
                G, "StringSession", lambda value: value
            ), patch.object(G, "resolve_group_entity", new=AsyncMock(return_value=entity)):
                return await G.check_group_access("SESS", group)

        self.assertEqual(await run({"permissions": perms_ok}), (True, "ok"))
        self.assertEqual(
            await run(
                {
                    "permissions": SimpleNamespace(
                        **{**perms_ok.__dict__, "send_messages": False}
                    )
                }
            ),
            (False, "no_write"),
        )
        self.assertEqual(await run({"permissions": None}), (False, "not_member"))
        self.assertEqual(
            await run({"permissions": perms_ok}, entity=SimpleNamespace(
                broadcast=False, left=True, banned_rights=None,
                default_banned_rights=None)),
            (False, "not_member"),
        )
        self.assertEqual(
            await run({"me": None}),
            (False, "unauthorized"),
        )
        self.assertEqual(
            await run({"permissions": perms_ok, "permissions_error": PeerIdInvalidError(None)}),
            (False, "not_found"),
        )
        self.assertEqual(
            await run(
                {"permissions": perms_ok, "permissions_error": UserNotParticipantError(None)}
            ),
            (False, "not_member"),
        )
        self.assertEqual(
            await run({"permissions": perms_ok, "permissions_error": ChannelPrivateError(None)}),
            (False, "private"),
        )
        self.assertEqual(
            await run({"permissions": perms_ok, "permissions_error": ValueError("x")}),
            (False, "invalid"),
        )

        # Telegram javob bermasa — "timeout" sababi bilan qaytadi (esanmagan holat).
        with patch.object(G, "TelegramClient", fake_client(permissions=perms_ok)), patch.object(
            G, "StringSession", lambda value: value
        ), patch.object(
            G,
            "resolve_group_entity",
            new=AsyncMock(side_effect=asyncio.TimeoutError()),
        ):
            self.assertEqual(await G.check_group_access("SESS", "@news"), (False, "timeout"))

    async def test_group_check_result_texts_and_button(self) -> None:
        for reason in ("ok", "unauthorized", "not_member", "no_write", "not_found",
                       "private", "invalid", "flood", "timeout", "error", "noma'lum"):
            text = T.group_check_result("@news", reason == "ok", reason)
            self.assertIn("@news", text)
            self.assertTrue(text.strip())
            if reason != "ok":
                self.assertNotIn(reason, text.split("\n")[0])

        await db.add_chat(UID, "@news")
        gid = int((await db.get_chat_records(UID))[0]["id"])
        with patch.object(
            G, "check_one_group", new=AsyncMock(return_value=("@news", False, "no_write"))
        ):
            update = await self.press(f"gchk:id:{gid}:0")
        text = update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("@news", text)
        self.assertIn("yozish", text.lower())

    async def test_check_one_group_reports_missing_data(self) -> None:
        value, ok, reason = await G.check_one_group(UID, 4242)
        self.assertEqual((value, ok, reason), ("", False, "not_found"))
        await db.add_chat(UID, "@news")
        gid = int((await db.get_chat_records(UID))[0]["id"])
        await db.del_session(UID)
        value, ok, reason = await G.check_one_group(UID, gid)
        self.assertEqual((value, ok, reason), ("@news", False, "unauthorized"))

    # ── 7. Tez (avtomatik) tasdiqlash ──
    async def seed_pending(self, uid: int = 5005) -> None:
        await db.upsert_user(uid, name="Yangi User", phone="+998901112233")
        await db.set_pending_approval(uid, "PENDING_SESSION")

    def approve_patches(self, risk: int):
        from admin import admin_actions

        return [
            patch.object(AA, "application", self.app),
            patch.object(AA, "compute_risk_score", new=lambda user, **kwargs: (
                risk, ["test-signal"] if risk else []
            )),
            patch.object(AA, "auto_approve_threshold", return_value=2),
            patch.object(AA, "AUTO_APPROVE_BATCH", 5),
            patch.object(admin_actions, "notify_after_approval", new=AsyncMock()),
        ]

    async def test_auto_approve_disabled_does_nothing(self) -> None:
        await db.upsert_user(5005, name="Yangi")
        await db.set_pending_approval(5005, "PENDING")
        with patch.object(AA, "auto_approve_threshold", return_value=-1):
            self.assertEqual(await AA.auto_approve_once(), 0)
        self.assertTrue((await db.get_user(5005))["awaiting_approval"])

    async def test_auto_approve_approves_low_risk(self) -> None:
        await self.seed_pending(5005)
        patches = self.approve_patches(0) + [
            patch.object(
                AA, "validate_telegram_session_owner", new=AsyncMock(return_value=AA.VALID)
            )
        ]
        for patcher in patches:
            patcher.start()
        try:
            self.assertEqual(await AA.auto_approve_once(), 1)
        finally:
            for patcher in reversed(patches):
                patcher.stop()
        user = await db.get_user(5005)
        self.assertTrue(user["is_admin"])
        self.assertFalse(user["awaiting_approval"])
        self.assertEqual(user["session"], "PENDING_SESSION")
        # Admin nazorati: avto-tasdiq haqida xabar bordi.
        self.assertIn("AVTO-TASDIQ", self.sent[-1][1])
        self.assertEqual(self.sent[-1][0], SUPER_ADMIN)

    async def test_auto_approve_skips_high_risk(self) -> None:
        await self.seed_pending(6006)
        patches = self.approve_patches(9) + [
            patch.object(
                AA, "validate_telegram_session_owner", new=AsyncMock(return_value=AA.VALID)
            )
        ]
        for patcher in patches:
            patcher.start()
        try:
            self.assertEqual(await AA.auto_approve_once(), 0)
        finally:
            for patcher in reversed(patches):
                patcher.stop()
        self.assertTrue((await db.get_user(6006))["awaiting_approval"])

    async def test_auto_approve_mismatch_clears_pending(self) -> None:
        await self.seed_pending(7007)
        patches = self.approve_patches(0) + [
            patch.object(
                AA,
                "validate_telegram_session_owner",
                new=AsyncMock(return_value=AA.MISMATCH),
            ),
            patch.object(AA, "revoke_telegram_session", new=AsyncMock(return_value=True)),
        ]
        for patcher in patches:
            patcher.start()
        try:
            self.assertEqual(await AA.auto_approve_once(), 0)
        finally:
            for patcher in reversed(patches):
                patcher.stop()
        user = await db.get_user(7007)
        self.assertFalse(user["awaiting_approval"])
        self.assertEqual(user["session"], "")
        self.assertTrue(user["is_admin"] == 0)

    async def test_auto_approve_temporary_error_keeps_application(self) -> None:
        await self.seed_pending(8008)
        patches = self.approve_patches(0) + [
            patch.object(
                AA,
                "validate_telegram_session_owner",
                new=AsyncMock(return_value=AA.TEMPORARY),
            )
        ]
        for patcher in patches:
            patcher.start()
        try:
            self.assertEqual(await AA.auto_approve_once(), 0)
        finally:
            for patcher in reversed(patches):
                patcher.stop()
        user = await db.get_user(8008)
        self.assertTrue(user["awaiting_approval"])
        self.assertTrue(user["pending_session"])

    async def test_auto_approve_rejects_when_user_has_no_pending(self) -> None:
        await db.upsert_user(9009, name="Pending yo'q")
        patches = self.approve_patches(0)
        for patcher in patches:
            patcher.start()
        try:
            self.assertEqual(await AA.auto_approve_once(), 0)
        finally:
            for patcher in reversed(patches):
                patcher.stop()


