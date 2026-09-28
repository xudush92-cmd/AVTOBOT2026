from __future__ import annotations

import os
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
os.environ.setdefault(
    "SESSION_ENCRYPTION_KEY",
    "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
)

from telethon.errors import FloodWaitError  # noqa: E402
from telethon.tl import types  # noqa: E402
from telethon.tl.functions.messages import CheckChatInviteRequest  # noqa: E402

import main as app_main  # noqa: E402
from bot import groups  # noqa: E402
from bot import login as bot_login  # noqa: E402
from core.utils import (  # noqa: E402
    group_reference_key,
    normalize_group_reference,
    parse_group_lines,
    parse_group_lines_with_errors,
)
from worker import worker as posting_worker  # noqa: E402


class GroupReferenceTests(unittest.TestCase):
    def test_public_links_and_message_links_become_username(self) -> None:
        username = "Toshkent_Xorazim_urganch_taxi"
        expected = f"@{username}"
        self.assertEqual(
            normalize_group_reference(f"https://t.me/{username}"), expected
        )
        self.assertEqual(
            normalize_group_reference(f"https://t.me/{username}/123?single"),
            expected,
        )
        self.assertEqual(
            normalize_group_reference(f"[Guruh](https://telegram.me/{username}/456)"),
            expected,
        )
        self.assertEqual(normalize_group_reference(f"t.me/{username}"), expected)

    def test_private_message_and_invite_links_are_canonical(self) -> None:
        self.assertEqual(
            normalize_group_reference("https://t.me/c/1234567890/77"),
            "-1001234567890",
        )
        self.assertEqual(
            normalize_group_reference("https://t.me/joinchat/AbC_def-123"),
            "https://t.me/+AbC_def-123",
        )
        self.assertEqual(
            normalize_group_reference("tg://join?invite=AbC_def-123"),
            "https://t.me/+AbC_def-123",
        )
        self.assertEqual(
            normalize_group_reference("tg://resolve?domain=Example_Group&post=12"),
            "@Example_Group",
        )

    def test_equivalent_public_references_are_deduplicated(self) -> None:
        parsed = parse_group_lines(
            "@Example_Group\nhttps://t.me/example_group\nhttps://t.me/Other_Group/10"
        )
        self.assertEqual(parsed, ["@Example_Group", "@Other_Group"])
        self.assertEqual(
            group_reference_key("@Example_Group"),
            group_reference_key("https://t.me/example_group/5"),
        )

    def test_case_sensitive_invites_are_not_deduplicated(self) -> None:
        parsed = parse_group_lines(
            "https://t.me/+AbC_def-123\nhttps://t.me/+abc_def-123"
        )
        self.assertEqual(
            parsed,
            ["https://t.me/+AbC_def-123", "https://t.me/+abc_def-123"],
        )

    def test_numeric_references_are_canonical(self) -> None:
        self.assertEqual(normalize_group_reference("-10000123"), "-10000123")
        self.assertEqual(normalize_group_reference("00042"), "42")

    def test_bad_formats_are_not_silently_stored(self) -> None:
        bad = [
            "https://example.org/Example_Group",
            "https://@t.me/Example_Group",
            "https://t.me:9999/Example_Group",
            "https://t.me/",
            "https://t.me/+",
            "https://t.me/joinchat/bad!",
            "https://t.me/c/abc/12",
            "https://t.me/Example_Group/not-a-post",
            "https://t.me/Example_Group/12/extra",
            "tg://join?invite=bad!",
            "@bad!",
            "a b",
            "-100abc",
            "0",
            "https://[bad",
        ]
        for value in bad:
            with self.subTest(value=value):
                self.assertEqual(normalize_group_reference(value), "")
        valid, invalid = parse_group_lines_with_errors(
            "https://t.me/Example_Group/12\n"
            "@example_group\nhttps://example.org/fake\nhttps://t.me/+AbC_def-123\n"
            "https://t.me/c/1234567890/77\n@bad!"
        )
        self.assertEqual(
            valid,
            ["@Example_Group", "https://t.me/+AbC_def-123", "-1001234567890"],
        )
        self.assertEqual(invalid, ["https://example.org/fake", "@bad!"])


class GroupResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_url_is_resolved_by_canonical_username(self) -> None:
        entity = SimpleNamespace(id=42)
        client = SimpleNamespace(get_entity=AsyncMock(return_value=entity))
        with patch.object(groups, "_is_group_entity", return_value=True):
            resolved = await groups.resolve_group_entity(
                client,
                "https://t.me/Toshkent_Xorazim_urganch_taxi",
            )
        self.assertIs(resolved, entity)
        client.get_entity.assert_awaited_once_with("@Toshkent_Xorazim_urganch_taxi")

    async def test_forbidden_entity_has_clear_private_reason(self) -> None:
        entity = types.ChannelForbidden(id=42, access_hash=1, title="Yopiq")
        client = SimpleNamespace(get_entity=AsyncMock(return_value=entity))
        with self.assertRaises(groups.GroupResolveError) as error:
            await groups.resolve_group_entity(client, "@Example_Group")
        self.assertEqual(error.exception.reason, "private")

    async def test_private_invite_does_not_auto_join(self) -> None:
        client = AsyncMock(return_value=SimpleNamespace())
        with self.assertRaises(groups.GroupResolveError) as error:
            await groups.resolve_group_entity(client, "https://t.me/+AbC_def-123")
        self.assertEqual(error.exception.reason, "not_member")
        client.assert_awaited_once()
        request = client.await_args.args[0]
        self.assertIsInstance(request, CheckChatInviteRequest)

    async def test_private_invite_accepts_existing_member_without_joining(self) -> None:
        entity = SimpleNamespace(id=42)
        client = AsyncMock(return_value=types.ChatInviteAlready(chat=entity))
        with patch.object(groups, "_is_group_entity", return_value=True):
            resolved = await groups.resolve_group_entity(
                client, "https://t.me/+AbC_def-123"
            )
        self.assertIs(resolved, entity)
        self.assertIsInstance(client.await_args.args[0], CheckChatInviteRequest)

    async def test_numeric_id_falls_back_to_joined_dialogs(self) -> None:
        entity = SimpleNamespace(id=1234567890)
        dialog = SimpleNamespace(id=-1001234567890, entity=entity)

        class Client:
            get_entity = AsyncMock(side_effect=ValueError("not cached"))

            async def iter_dialogs(self):
                yield dialog

        with (
            patch.object(groups, "_is_group_entity", return_value=True),
            patch.object(groups.utils, "get_peer_id", return_value=-1001234567890),
        ):
            resolved = await groups.resolve_group_entity(
                Client(), "https://t.me/c/1234567890/77"
            )
        self.assertIs(resolved, entity)

    async def test_worker_uses_the_shared_resolver(self) -> None:
        client = SimpleNamespace()
        entity = SimpleNamespace(id=42)
        resolver = AsyncMock(return_value=entity)
        with patch.object(groups, "resolve_group_entity", new=resolver):
            resolved = await posting_worker.resolve_chat(
                client, "https://t.me/Example_Group/12"
            )
        self.assertIs(resolved, entity)
        resolver.assert_awaited_once_with(client, "https://t.me/Example_Group/12")

    async def test_permission_check_accepts_joined_writable_group(self) -> None:
        entity = SimpleNamespace(left=False, broadcast=False)
        permissions = SimpleNamespace(
            has_left=False,
            is_creator=False,
            is_admin=False,
            send_messages=True,
        )
        client = SimpleNamespace(
            connect=AsyncMock(),
            disconnect=AsyncMock(),
            is_user_authorized=AsyncMock(return_value=True),
            get_me=AsyncMock(return_value=SimpleNamespace(id=100)),
            get_permissions=AsyncMock(return_value=permissions),
        )
        with (
            patch.object(groups, "TelegramClient", return_value=client),
            patch.object(groups, "StringSession", side_effect=lambda value: value),
            patch.object(
                groups,
                "resolve_group_entity",
                new=AsyncMock(return_value=entity),
            ),
        ):
            self.assertEqual(
                await groups.check_group_access("session", "@Example_Group"),
                (True, "ok"),
            )
        client.get_permissions.assert_awaited_once()
        client.get_me.assert_awaited_once()
        client.is_user_authorized.assert_not_awaited()
        client.disconnect.assert_awaited_once()

    async def test_legacy_group_checker_does_not_confuse_flood_with_invalid_session(
        self,
    ) -> None:
        client = SimpleNamespace(
            connect=AsyncMock(),
            disconnect=AsyncMock(),
            get_me=AsyncMock(side_effect=FloodWaitError(None, 30)),
            is_user_authorized=AsyncMock(return_value=False),
        )
        with (
            patch.object(groups, "TelegramClient", return_value=client),
            patch.object(groups, "StringSession", side_effect=lambda value: value),
        ):
            self.assertEqual(
                await groups.check_group_access("session", "@Example_Group"),
                (False, "flood"),
            )
        client.is_user_authorized.assert_not_awaited()
        client.disconnect.assert_awaited_once()

    def test_default_message_ban_is_rejected(self) -> None:
        rights = types.ChatBannedRights(until_date=None, send_messages=True)
        entity = SimpleNamespace(
            broadcast=False,
            banned_rights=None,
            default_banned_rights=rights,
        )
        permissions = SimpleNamespace(
            participant=SimpleNamespace(left=False, banned_rights=None),
            has_left=False,
            is_creator=False,
            is_admin=False,
            is_banned=False,
        )
        self.assertEqual(groups._posting_rejection(entity, permissions), "no_write")

    def test_broadcast_requires_post_messages_permission(self) -> None:
        entity = SimpleNamespace(broadcast=True)
        permissions = SimpleNamespace(
            participant=SimpleNamespace(left=False, banned_rights=None),
            has_left=False,
            is_creator=False,
            is_admin=True,
            post_messages=False,
        )
        self.assertEqual(groups._posting_rejection(entity, permissions), "no_write")
        permissions.post_messages = True
        self.assertIsNone(groups._posting_rejection(entity, permissions))


class GroupFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_flow_stores_valid_references_without_telegram(self) -> None:
        uid = 100
        status = SimpleNamespace(edit_text=AsyncMock())
        message = SimpleNamespace(
            reply_text=AsyncMock(side_effect=[status, SimpleNamespace()])
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=uid),
            message=message,
        )
        bot_login.user_states[uid] = {"step": "add_group"}
        try:
            with (
                patch.object(
                    groups.db, "get_session", new=AsyncMock(return_value="old-session")
                ) as get_session,
                patch.object(
                    groups.db, "get_chats", new=AsyncMock(return_value=["@existing"])
                ),
                patch.object(
                    groups.db, "add_chat", new=AsyncMock(return_value=(True, "ok"))
                ) as add_chat,
                patch.object(groups.db, "del_session", new=AsyncMock()) as del_session,
                patch.object(
                    groups, "check_group_access", new=AsyncMock()
                ) as check_access,
                patch.object(groups, "TelegramClient", side_effect=AssertionError),
            ):
                await groups.handle_add_groups(
                    update,
                    "[Guruh](https://t.me/Example_Group/12)\n"
                    "https://t.me/example_group/13\nhttps://t.me/+AbC_def-123\n"
                    "https://t.me/c/1234567890/77\n@EXISTING\n"
                    "https://example.org/bad\n@bad!",
                )
        finally:
            bot_login.user_states.pop(uid, None)

        get_session.assert_awaited_once_with(uid)
        check_access.assert_not_awaited()
        del_session.assert_not_awaited()
        self.assertEqual(
            [call.args for call in add_chat.await_args_list],
            [
                (uid, "@Example_Group"),
                (uid, "https://t.me/+AbC_def-123"),
                (uid, "-1001234567890"),
            ],
        )
        report = status.edit_text.await_args.args[0]
        self.assertIn("@EXISTING — allaqachon mavjud", report)
        self.assertIn("https://example.org/bad (noto'g'ri format)", report)
        self.assertIn("@bad! (noto'g'ri format)", report)

    async def test_user_invalid_only_keeps_group_input_open(self) -> None:
        uid = 101
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=uid), message=message
        )
        bot_login.user_states[uid] = {"step": "add_group"}
        try:
            with (
                patch.object(groups.db, "get_session", new=AsyncMock(return_value="s")),
                patch.object(groups.db, "add_chat", new=AsyncMock()) as add_chat,
            ):
                await groups.handle_add_groups(update, "https://example.org/bad")
            self.assertEqual(bot_login.user_states[uid]["step"], "add_group")
            self.assertIn("formati noto'g'ri", message.reply_text.await_args.args[0])
            add_chat.assert_not_awaited()
        finally:
            bot_login.user_states.pop(uid, None)

    async def test_admin_flow_stores_canonical_for_target_without_telegram(
        self,
    ) -> None:
        admin_uid = 999
        target_uid = 200
        status = SimpleNamespace(edit_text=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=status))
        update = SimpleNamespace(message=message)
        bot_login.user_states[admin_uid] = {
            "step": "admin_add_group",
            "target_uid": target_uid,
        }
        try:
            with (
                patch.object(
                    app_main.db,
                    "get_user",
                    new=AsyncMock(return_value={"uid": target_uid}),
                ),
                patch.object(
                    app_main.db,
                    "get_session",
                    new=AsyncMock(return_value="target-session"),
                ) as get_session,
                patch.object(app_main.db, "get_chats", new=AsyncMock(return_value=[])),
                patch.object(
                    app_main.db, "add_chat", new=AsyncMock(return_value=(True, "ok"))
                ) as add_chat,
                patch.object(
                    app_main.db,
                    "get_chat_records",
                    new=AsyncMock(return_value=[]),
                ),
                patch.object(
                    app_main.db, "del_session", new=AsyncMock()
                ) as del_session,
                patch.object(
                    groups, "check_group_access", new=AsyncMock()
                ) as check_access,
                patch.object(groups, "TelegramClient", side_effect=AssertionError),
            ):
                await app_main.handle_admin_fsm(
                    update,
                    admin_uid,
                    "admin_add_group",
                    "https://t.me/Example_Group/12\n"
                    "https://t.me/joinchat/AbC_def-123\n"
                    "https://t.me/c/1234567890/77\n@bad!",
                )
        finally:
            bot_login.user_states.pop(admin_uid, None)

        get_session.assert_awaited_once_with(target_uid)
        check_access.assert_not_awaited()
        del_session.assert_not_awaited()
        self.assertEqual(
            [call.args for call in add_chat.await_args_list],
            [
                (target_uid, "@Example_Group"),
                (target_uid, "https://t.me/+AbC_def-123"),
                (target_uid, "-1001234567890"),
            ],
        )
        status.edit_text.assert_awaited_once()
        self.assertIn("@bad! (noto'g'ri format)", status.edit_text.await_args.args[0])

    async def test_admin_invalid_only_keeps_target_input_open(self) -> None:
        admin_uid, target_uid = 999, 200
        update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
        bot_login.user_states[admin_uid] = {
            "step": "admin_add_group",
            "target_uid": target_uid,
        }
        try:
            with (
                patch.object(
                    app_main.db,
                    "get_user",
                    new=AsyncMock(return_value={"uid": target_uid}),
                ),
                patch.object(
                    app_main.db, "get_session", new=AsyncMock(return_value="s")
                ),
                patch.object(app_main.db, "add_chat", new=AsyncMock()) as add_chat,
            ):
                await app_main.handle_admin_fsm(
                    update, admin_uid, "admin_add_group", "https://other.example/abc"
                )
            self.assertEqual(bot_login.user_states[admin_uid]["target_uid"], target_uid)
            self.assertIn(
                "formati noto'g'ri", update.message.reply_text.await_args.args[0]
            )
            add_chat.assert_not_awaited()
        finally:
            bot_login.user_states.pop(admin_uid, None)


class GroupPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = groups.db.DB_PATH
        groups.db.DB_PATH = Path(self.temp.name) / "groups.db"
        await groups.db.init_db()
        for uid in (100, 200):
            await groups.db.upsert_user(uid, is_admin=1)
            await groups.db.set_session(uid, f"original-session-{uid}")

    async def asyncTearDown(self) -> None:
        await groups.db.close_db()
        groups.db.DB_PATH = self.old_path
        self.temp.cleanup()

    async def test_user_and_admin_save_canonical_without_changing_sessions(
        self,
    ) -> None:
        user_status = SimpleNamespace(edit_text=AsyncMock())
        user_update = SimpleNamespace(
            effective_user=SimpleNamespace(id=100),
            message=SimpleNamespace(
                reply_text=AsyncMock(side_effect=[user_status, SimpleNamespace()])
            ),
        )
        admin_uid = 999
        admin_status = SimpleNamespace(edit_text=AsyncMock())
        admin_update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock(return_value=admin_status))
        )
        bot_login.user_states[100] = {"step": "add_group"}
        bot_login.user_states[admin_uid] = {
            "step": "admin_add_group",
            "target_uid": 200,
        }
        try:
            with patch.object(groups, "TelegramClient", side_effect=AssertionError):
                await groups.handle_add_groups(
                    user_update,
                    "https://t.me/Example_Group/12\nhttps://t.me/+AbC_def-123",
                )
                await app_main.handle_admin_fsm(
                    admin_update,
                    admin_uid,
                    "admin_add_group",
                    "[Private](https://t.me/c/1234567890/77)\n"
                    "https://t.me/Example_Group/12",
                )
        finally:
            bot_login.user_states.pop(100, None)
            bot_login.user_states.pop(admin_uid, None)

        self.assertEqual(
            await groups.db.get_chats(100),
            ["@Example_Group", "https://t.me/+AbC_def-123"],
        )
        self.assertEqual(
            await groups.db.get_chats(200), ["-1001234567890", "@Example_Group"]
        )
        for uid in (100, 200):
            self.assertEqual(
                await groups.db.get_session(uid), f"original-session-{uid}"
            )


if __name__ == "__main__":
    unittest.main()
