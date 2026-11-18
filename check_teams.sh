#!/bin/bash
# AVTOBOT2026 — jamoa va adminlar holatini tekshirish (2-qism)
# Ishlatish:  bash /tmp/check_teams.sh

cd /root/avtobot_v2/AVTOBOT2026

echo "════════ JAMOALAR ════════"
/root/avtobot_v2/AVTOBOT2026/venv/bin/python - <<'PY'
import asyncio, sys
sys.path.insert(0, "/root/avtobot_v2/AVTOBOT2026")
from core import database as db

async def main():
    await db.init_db()
    teams = await db.get_all_teams()
    print(f"Jamoalar soni: {len(teams)}")
    for t in teams:
        members = await db.get_team_members(int(t["id"]))
        print(f"  [{t['id']}] {t['name']}")
        print(f"      owner_admin_uid={t.get('owner_admin_uid')} "
              f"max_users={t.get('max_users')} "
              f"a'zolar={len(members)} "
              f"expires_at={t.get('expires_at')}")
        for m in members:
            print(f"        - uid={m.get('uid')} "
                  f"name={m.get('name')!r} "
                  f"is_admin={m.get('is_admin')} "
                  f"awaiting={m.get('awaiting_approval')} "
                  f"team_admin={m.get('is_team_admin')}")
    await db.close_db()

asyncio.run(main())
PY

echo ""
echo "════════ SUPER ADMIN BOYLIK RAMKASI ════════"
/root/avtobot_v2/AVTOBOT2026/venv/bin/python - <<'PY'
import asyncio, sys
sys.path.insert(0, "/root/avtobot_v2/AVTOBOT2026")
from core import database as db
from config.config import SUPER_ADMIN_ID

async def main():
    await db.init_db()
    print(f"SUPER_ADMIN_ID = {SUPER_ADMIN_ID}")
    u = await db.get_user(SUPER_ADMIN_ID)
    if u:
        print("Super admin bazada:", {k: u.get(k) for k in
              ("uid", "name", "is_admin", "is_team_admin", "team_id", "session")})
    else:
        print("⚠️ Super admin bazada YO'Q — /start bilan kiritish kerak")
    await db.close_db()

asyncio.run(main())
PY

echo ""
echo "════════ YANGI ISHLATILGAN USULLAR (main.py da borligi) ════════"
grep -c "BTN_TEAM_ADMIN" main.py bot/keyboards.py bot/menu.py
echo ""
echo "════════ TAYYAR ════════"
