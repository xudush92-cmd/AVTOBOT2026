# 🔧 TUZATISHLAR RO'YXATI — AVTOBOT2026

> **Holat:** ✅ **BARCHA TUZATISHLAR BAJARILDI** (2026-11-14)
> **Filial:** `arena/03bc18db-avtobot2026` (asosiy: `main`, commit `4eca268`)
> **Testlar:** `574 passed, 62 subtests passed` (bazadagi 547 + 27 yangi)

---

## ✅ BAJARILGAN TUZATISHLAR

### A2. Jamoa admini panelidagi «Orqaga» o'z-o'ziga qaytardi 🔴 → ✅
**Boshqaruv:** `bot/teams.py` — `tadm:back` endi **asosiy menyuga** qaytaradi.

**Avval:** `tadm:back` → `show_team_admin_panel()` — ko'rinish o'zgarmasdi.
**Hozir:** `tadm:back` → `bot.menu.show_home()` — asosiy menyu + holat qatori.

**Qo'shimcha:** `main.py` — jamoa FSM'ida «Orqaga» endi `kb_login` emas,
`get_menu(uid)` (rolga mos menyu) ko'rsatadi.

---

### A3. Super admin oddiy foydalanuvchini jamoaga yo'naltira olmadi 🟡 → ✅
**Boshqaruv:** `admin/admin_actions.py`, `bot/keyboards.py`, `bot/texts.py`

- `kb_user_card()` → **«👥 Jamoaga biriktirish»** tugmasi (`uc:teambind:<uid>`).
- `uc:teambind` → jamoa adminlarini tanlash oynasi (`kb_team_bind_choose`).
- `uc:teambindgo:<uid>:<owner>` → `action_team_bind_go()`:
  - jamoa sig'imi tekshiriladi (`team_has_free_slot`);
  - allaqachon boshqa jamoada bo'lsa — rad etiladi;
  - `db.set_team_pending()` → `awaiting_approval = 1`;
  - **jamoa adminiga ariza** yuboriladi (`schedule_notify_super_for_approval`);
  - **foydalanuvchiga xabar** — jamoa adminining telefon raqami bilan.

**Muhim:** Tasdiqlash **jamoa adminida** qoladi — super admin faqat
**yo'naltiradi**, tasdiqlaydi emas. Bu A7 bilan birga ishlaydi.

---

### A6. Jamoada shaxsiy havola kerak emas edi 🟡 → ✅
**Boshqaruv:** `bot/teams.py`, `bot/texts.py`, `main.py`

- `bot/teams.py` — `admin_link()` funksiyasi **olib tashlandi**.
- `bot/teams.py` — «🔗 Havola» oynasida faqat **umumiy** jamoa havolasi.
- `bot/teams.py` — «Do'st qo'shish» xabari: faqat umumiy havola
  (`TEAM_ADD_FRIEND_DONE_WITH_ADMIN_LINK` → `TEAM_ADD_FRIEND_DONE`).
- `main.py` — `adm_<uid>` deep link **o'chirildi** (faqat `team_<id>` ishlaydi).

**Natija:** jamoa admini boshqa jamoaga a'zo qo'sha olmaydi
(`owner_admin_uid` tekshiruvi saqlanadi).

---

### A7. A'zo noto'g'ri adminning raqamiga murojaat qilardi 🟡 → ✅
**Boshqaruv:** `bot/login.py`, `bot/texts.py`

**Avval:** `LOGIN_SUCCESS_PENDING` — **har kimga bir xil**, undagi raqam
`ADMIN_CONTACT_PHONE` (super admin). Jamoa asosiga ham «tasdiq kutilmoqda»
xabari bor edi.

**Hozir — uch holat:**

| Kim | Yuboriladigan xabar | Telefon |
|---|---|---|
| **Jamoa asosi** (jamoa admini) | `TEAM_ADMIN_READY` — «👑 Siz jamoa admini bo'ldingiz!» + jamoa havolasi | ❌ Super admin raqami **yo'q** |
| **Jamoa a'zosi** (havola orqali) | `LOGIN_SUCCESS_PENDING_TEAM` — «⏳ Jamoa adminingiz sizni tasdiqlashni kutilmoqda» | ✅ **Jamoa adminining** raqami |
| **Jamoasiz user** | `LOGIN_SUCCESS_PENDING` — «⏳ admin tasdiqini kutilmoqda» | ✅ Super admin raqami |

**Qo'shimcha:**
- `_team_admin_contact()` — jamoa adminining raqamini oladi
  (`db.get_phone(owner_admin_uid)`); yo'q bo'lsa → zaxira sifatida
  `ADMIN_CONTACT_PHONE`.
- `notify_super_for_approval()` — jamoa asosiga **ariza yubormaydi**
  (u allaqachon tasdiqlangan).
- `TEAM_PENDING_APPROVAL_CONTACT` — yangi matn (A3 oqimida a'zoga).

---

### A8. Super admin yaratgan jamoa nomi `Jamoa #<uid>` bo'lib qolardi 🟡 → ✅
**Boshqaruv:** `bot/teams.py`, `bot/keyboards.py`, `bot/texts.py`, `main.py`

- `kb_team_admin_panel()` → **«✏️ Jamoa nomi»** tugmasi (`tadm:rename`).
- `tadm:rename` → `TEAM_ADMIN_RENAME_ASK` matni, matn kiritish kutiladi.
- `handle_team_admin_rename()` → tekshiruvlar:
  - nom 2–40 belgi;
  - `get_team_by_name` bilan band emas (baza `UNIQUE(owner_admin_uid, name)`);
  - `db.update_team(team_id, name=...)`.
- `main.py` — `team_admin_rename` holati **FSM ro'yxatiga qo'shildi**
  (aks holda matn kiritilganda bot javob bermasdi).

**Natija:** jamoa admini o'z jamoasining nomini istalgan vaqtda o'zgartira
oladi — a'zolar va ariza xabarlarida professional nom ko'rinadi.

---

## ✅ TALAB BO'YICHA QOLDIRILGAN (o'zgartirilmagan)

### A1. Jamoa admini o'z ro'yxatida ko'rinmasin ✅
**Boshqaruv:** `bot/teams.py` — «👥 Foydalanuvchilar» ro'yxatida jamoa
asosi filtrlanadi.

```python
members = [m for m in members if int(m.get("uid") or 0) != int(uid)]
```

**Nima o'zgarmadi (ixtiyoriy):**
- **Statistika** (`bot/teams.py:1056`) — jamoa asosi hisobga olinadi
  (u jamoaning a'zosi).
- **Sig'im tekshiruvi** (`bot/teams.py:1157`) — jamoa asosi jamoaning
  sig'imi ichida (u jamoa egasi).
- **Xabar yuborish** (`bot/teams.py:1204`) — allaqachon `target == uid`
  bilan o'skaziladi ✅

---

## 📋 YANGI TESTLAR

| Fayl | Testlar | Qamrov |
|---|---|---|
| `tests/test_team_contact_and_naming.py` | 23 | A1, A2, A3, A6, A8 |
| `tests/test_login_pending_contact.py` | 4 | A7 (3 holat + jamoa asosi arizasi) |

**Jami:** 547 → **574 test**, hammasi o'tadi (`pytest` va `unittest`).

---

## 🚀 YANGILASH BUYRUQLARI (deploy)

```bash
# 1) VPS'ga yangilanishni olish
cd /path/to/AVTOBOT2026
git pull origin main

# 2) Service'ni qayta ishga tushirish
sudo systemctl restart avtobot3.service

# 3) Holatni tekshirish
sudo systemctl status avtobot3.service
sudo journalctl -u avtobot3.service -n 50 --no-pager
```

**Kutilayotgan log:**
```
🔁 N ta worker tiklandi     (faqat «running» bo'lgan userlar uchun)
```

> 🔁 **Restart xususiyati** (PR #35) allaqachon `main` da — shuning uchun
> yangi kodda ham `running=True` foydalanuvchilar avtomatik tiklanadi.
> **⛔ Stop bosganlar to'xtagan holda qoladi.**

---

## 📌 ESLATMA (deploydan keyin tekshirish)

Yangi kodda jamoa admini ro'yxatdan o'tganda **«Jamoa admini bo'ldingiz»**
xabari keladi va uning jamoasi `Jamoa #<uid>` nomi bilan avtomatik yaratilgan
bo'lsa — **«✏️ Jamoa nomi»** tugmasi orqali nomni almashtirish kerak
(foydalanuvchilarga ko'rinadigan texnik nom).
