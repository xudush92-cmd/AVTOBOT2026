#!/bin/bash
# AVTOBOT2026 — jamoa yaratish oqimini serverda sinab ko'rish (test jamoasi)
# Ishlatish:  bash /tmp/test_jamoa_flow.sh
# Ogohlantirish: haqiqiy baza o'zgaradi — test jamoasi oxirida O'CHIRILADI.

cd /root/avtobot_v2/AVTOBOT2026

/root/avtobot_v2/AVTOBOT2026/venv/bin/python - <<'PY'
import asyncio, sys, time
sys.path.insert(0, "/root/avtobot_v2/AVTOBOT2026")
from core import database as db
from bot import teams as Tm
from bot import texts as T
from config.config import TEAM_MIN_MEMBERS, TEAM_ADMIN_DEFAULT_DAYS

TEST_UID = 999999001          # test foydalanuvchi (real emas)


class FakeMsg:
    def __init__(self, texts):
        self.text = texts
        self.out = []
    async def reply_text(self, text, reply_markup=None, **kw):
        self.out.append(text)


class FakeUpdate:
    def __init__(self, uid, texts):
        self.effective_user = type("U", (), {"id": uid})()
        self.message = FakeMsg(texts)


async def main():
    await db.init_db()

    print("═" * 60)
    print("1. Ro'yxatdan o'tmagan user «👑 Admin bo'lish» bosadi")
    print("═" * 60)
    up = FakeUpdate(TEST_UID, T.BTN_TEAM_ADMIN)
    await Tm.begin_team_admin_register(up, TEST_UID)
    print("  Javob:", up.message.out[-1][:150])
    from bot.login import user_states
    print("  State step:", user_states.get(TEST_UID, {}).get("step"))
    print("  ✅ Kutilgan: team_admin_size")

    print()
    print("═" * 60)
    print("2. Sig'im (5 ta foydalanuvchi) kiritiladi")
    print("═" * 60)
    up = FakeUpdate(TEST_UID, "5")
    await Tm.handle_team_admin_size(up, TEST_UID, "5")
    print("  Javob:", up.message.out[-1][:150])
    print("  State step:", user_states.get(TEST_UID, {}).get("step"))

    print()
    print("═" * 60)
    print("3. Jamoa nomi kiritiladi")
    print("═" * 60)
    up = FakeUpdate(TEST_UID, "TEST Jamoasi 12345")
    await Tm.handle_team_admin_name(up, TEST_UID, "TEST Jamoasi 12345")
    for line in up.message.out:
        print("  ", line[:200])

    print()
    print("═" * 60)
    print("4. Natijani bazadan tekshirish")
    print("═" * 60)
    u = await db.get_user(TEST_UID)
    print(f"  is_admin        = {u.get('is_admin')}")
    print(f"  is_team_admin   = {u.get('is_team_admin')}")
    print(f"  team_id         = {u.get('team_id')}")
    print(f"  owner_admin_uid = {u.get('owner_admin_uid')}")
    print(f"  admin_max_users = {u.get('admin_max_users')}")
    print(f"  admin_expires   = {u.get('admin_expires_at')}")
    print(f"  awaiting        = {u.get('awaiting_approval')}")

    teams = await db.get_teams(TEST_UID)
    for t in teams:
        print(f"  Jamoa: id={t['id']} name={t['name']} "
              f"max_users={t['max_users']} owner={t['owner_admin_uid']}")

    admin_rows = await db.get_team_admins()
    print(f"  Jamoa adminlari soni: {len(admin_rows)}")
    for a in admin_rows:
        print(f"    - {a.get('name')} uid={a.get('uid')} "
              f"team_id={a.get('team_id')} limit={a.get('admin_max_users')}")

    print()
    print("═" * 60)
    print("5. TOZALASH — test jamoasi va test user o'chiriladi")
    print("═" * 60)
    for t in teams:
        ok = await db.delete_team(int(t["id"]))
        print(f"  delete_team({t['id']}) = {ok}")
    await db.delete_user(TEST_UID)
    print(f"  delete_user({TEST_UID}) = done")
    user_states.pop(TEST_UID, None)

    left = await db.get_all_teams()
    print(f"  Qolgan jamoalar: {len(left)}")
    await db.close_db()

    print()
    print("═" * 60)
    print("TEST YAKUNLANDI")
    print("═" * 60)

asyncio.run(main())
PY
