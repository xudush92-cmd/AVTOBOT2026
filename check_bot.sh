#!/bin/bash
# AVTOBOT2026 — server holatini tekshirish skripti
# Ishlatish:  bash /tmp/check_bot.sh
# Natija: bot loglari, sozlamalar va baza holati

echo "════════ 1. SERVICE HOLATI ════════"
systemctl is-active avtobot3.service
systemctl status avtobot3.service --no-pager | head -8

echo ""
echo "════════ 2. OXIRGI LOGLAR (xatolar) ════════"
journalctl -u avtobot3.service -n 40 --no-pager

echo ""
echo "════════ 3. SOZLAMALAR (kod default'lari bilan) ════════"
cd /root/avtobot_v2/AVTOBOT2026
/root/avtobot_v2/AVTOBOT2026/venv/bin/python - <<'PY'
from config.config import (
    REFERRAL_BONUS_DAYS, MAX_ALBUM_FILES, ALLOW_VIDEO_MEDIA,
    TEAM_MEMBER_MAX_DAYS, TEAM_MIN_MEMBERS, TEAM_ADMIN_DEFAULT_DAYS,
    SUPER_ADMIN_MAX_DAYS, AUTO_APPROVE_ENABLED,
)
print(f"REFERRAL_BONUS_DAYS   = {REFERRAL_BONUS_DAYS}  (kerak: 0)")
print(f"MAX_ALBUM_FILES       = {MAX_ALBUM_FILES}  (kerak: 4)")
print(f"ALLOW_VIDEO_MEDIA     = {ALLOW_VIDEO_MEDIA}  (kerak: False)")
print(f"TEAM_MEMBER_MAX_DAYS = {TEAM_MEMBER_MAX_DAYS}  (kerak: 60)")
print(f"TEAM_MIN_MEMBERS     = {TEAM_MIN_MEMBERS}  (kerak: 2)")
print(f"TEAM_ADMIN_DAYS      = {TEAM_ADMIN_DEFAULT_DAYS}  (kerak: 30)")
print(f"SUPER_ADMIN_MAX_DAYS  = {SUPER_ADMIN_MAX_DAYS}  (kerak: 0 = chegarasiz)")
print(f"AUTO_APPROVE_ENABLED = {AUTO_APPROVE_ENABLED}  (kerak: False)")
PY

echo ""
echo "════════ 4. ASOSIY MENYU (Admin tugmasi bormi?) ════════"
/root/avtobot_v2/AVTOBOT2026/venv/bin/python - <<'PY'
import asyncio, os, sys
sys.path.insert(0, "/root/avtobot_v2/AVTOBOT2026")
from bot import keyboards as KB
from bot import texts as T

rows = KB.kb_main()          # jamoasiz oddiy user
flat = [b.text for r in rows.keyboard for b in r]
print("kb_main() tugmalari:")
for t in flat:
    print("   ", t)
print()
print("«👑 Admin bo'lish» kb_main da:      ", T.BTN_TEAM_ADMIN in flat)
print("«🎯 Jamoani tanlash» kb_main da:    ", T.BTN_TEAM_PICK in flat)
login = [b.text for r in KB.kb_login().keyboard for b in r]
print("«👑 Admin bo'lish» kb_login da:     ", T.BTN_TEAM_ADMIN in login)
PY

echo ""
echo "════════ 5. BAZA: jamoalar va adminlar ════════"
cd /root/avtobot_v2/AVTOBOT2026
/root/avtobot_v2/AVTOBOT2026/venv/bin/python - <<'PY'
import asyncio, sys
sys.path.insert(0, "/root/avtobot_v2/AVTOBOT2026")
from core import database as db

async def main():
    await db.init_db()
    rows = await db._fetchall("SELECT id, name, owner_admin_uid, max_users, expires_at FROM teams")
    print(f"Jamoalar soni: {len(rows)}")
    for r in rows:
        print("  ", dict(r))
    n = await db._fetchone("SELECT COUNT(*) AS c FROM users")
    print("Foydalanuvchilar:", n["c"] if n else 0)
    await db.close_db()

asyncio.run(main())
PY

echo ""
echo "════════ TAYYAR ════════"
