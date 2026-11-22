# 🔧 TUZATISHLAR RO'YXATI — AVTOBOT2026

> **Holat:** ✅ **BARCHA TUZATISHLAR BAJARILDI** (2026-11-14)
> **Filial:** `main` — PR #37 merge qilingan (merge commit `20f82e5`)
> **Testlar:** `597 passed, 62 subtests passed` (bazadagi 574 + 23 yangi)
> **Deploy:** ⏳ VPS'ga o'tkazilishi kutilmoqda (buyruq quyida)

---

## ✅ BAJARILGAN TUZATISHLAR

### 🔴 A9. Jamoa statistikasi «Xatolik yuz berdi» berardi ✅

**Boshqaruv:** `bot/teams.py` — `tadm:stats` action.

**Sabab:** async generator ichida `await` ishlatilgan:

```python
# ❌ AVVAL — TypeError: 'async_generator' object is not iterable
"groups": sum(await db.count_chats(int(m["uid"])) for m in members),
"posts":  sum(await db.count_posts(int(m["uid"])) for m in members),
```

`sum(... for ...)` — bu **async generator** yaratadi, uni `sum` bilan
yig'ib bo'lmaydi. Natija: statistika oynasi "Xatolik yuz berdi" beradi.

**Hozir:** aniq `await` sikli bilan ketma-ket hisoblanadi:

```python
groups_total = 0
posts_total = 0
for m in members:
    groups_total += await db.count_chats(int(m["uid"]))
    posts_total += await db.count_posts(int(m["uid"]))
```

**Qo'shimcha:** statistikadagi «Foydalanuvchilar» soni endi jamoa
asosisiz (admin) hisoblanadi — panel va ro'yxat bilan mos keladi.

---

### 🟡 A10. Jamoa admini ichki oynalarda noto'g'ri «Orqaga» ✅

**Boshqaruv:** `bot/keyboards.py`, `bot/teams.py`

**Avval:** a'zolar ro'yxati, takliflar ro'yxati va statistika
oynalaridagi «Orqaga» → `tadm:back` → **asosiy menyu** (jamoa panelini
yaxshi tashlab qoldirib).

**Hozir:** ichki oynalardan «Orqaga» → `tadm:panel` → **jamoa admini
paneli** (tog'ri mantiq):

| Oyna | «Orqaga» naga olib boradi |
|---|---|
| Jamoa admini paneli | `tadm:back` → asosiy menyu |
| A'zolar ro'yxati | `tadm:panel` → jamoa paneli |
| Takliflar ro'yxati | `tadm:panel` → jamoa paneli |
| Statistika | `tadm:panel` → jamoa paneli |

---

### 🟡 A11. Eski panel oynasi chatda qolib ketardi ✅

**Boshqaruv:** `core/utils.py`, `bot/menu.py`, `bot/teams.py`

`reply_text_safe()` ga **`in_place=True`** (keyword-only) parametri
qo'shildi — inline kontekstda mavjud xabarni **o'zida tahrirlaydi**
(yangi xabar yubormaydi).

```python
await reply_text_safe(update, text, reply_markup=markup, in_place=True)
```

**Natija:**
- `show_home(..., in_place=True)` — asosiy menyu eski oynani almashtiradi;
- `show_team_admin_panel()` — panel eski oynani almashtiradi;
- oddiy `reply` semantikasi **saqlanadi** (default `in_place=False`).

---

### 🟡 A12. Jamoa admini referal oynasida ortiqcha tugmalar ✅

**Boshqaruv:** `bot/referral.py`, `bot/keyboards.py`, `bot/texts.py`

**Avval:** jamoa adminida ham shaxsiy `ref_<uid>` havolasi, «Havolani
ochish», «Do'stlarga yuborish» va referal statistikasi chiqardi.

**Hozir:** jamoa admini uchun **faqat umumiy jamoa havolasi**:

- `kb_team_link_only()` — bitta tugma (🔗 Jamoa havolasi);
- `T.team_link_text()` — shaxsiy statistikasiz matn;
- «Do'stlarga yuborish» matni ham jamoa havolasini ishlatadi.

**Ordinary users:** o'zgarish yo'q — shaxsiy referal saqlanadi.

---

### 🔴 A2. Jamoa admini panelidagi «Orqaga» o'z-o'ziga qaytardi ✅

**Boshqaruv:** `bot/teams.py` — `tadm:back` endi **asosiy menyuga** qaytaradi.

**Qo'shimcha:** `main.py` — jamoa FSM'ida «Orqaga» endi `kb_login` emas,
`get_menu(uid)` (rolga mos menyu) ko'rsatadi.

---

### 🟡 A3. Super admin oddiy foydalanuvchini jamoaga yo'naltira olmadi ✅

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

### 🟡 A6. Jamoada shaxsiy havola kerak emas edi ✅

**Boshqaruv:** `bot/teams.py`, `bot/texts.py`, `main.py`

- `bot/teams.py` — `admin_link()` funksiyasi **olib tashlandi**.
- `bot/teams.py` — «🔗 Havola» oynasida faqat **umumiy** jamoa havolasi.
- `bot/teams.py` — «Do'st qo'shish» xabari: faqat umumiy havola.
- `main.py` — `adm_<uid>` deep link **o'chirildi** (faqat `team_<id>` ishlaydi).

**Natija:** jamoa admini boshqa jamoaga a'zo qo'sha olmaydi
(`owner_admin_uid` tekshiruvi saqlanadi).

---

### 🟡 A7. A'zo noto'g'ri adminning raqamiga murojaat qilardi ✅

**Boshqaruv:** `bot/login.py`, `bot/texts.py`

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

---

### 🟡 A8. Super admin yaratgan jamoa nomi `Jamoa #<uid>` bo'lib qolardi ✅

**Boshqaruv:** `bot/teams.py`, `bot/keyboards.py`, `bot/texts.py`, `main.py`

- `kb_team_admin_panel()` → **«✏️ Jamoa nomi»** tugmasi (`tadm:rename`).
- `tadm:rename` → `TEAM_ADMIN_RENAME_ASK` matni, matn kiritish kutiladi.
- `handle_team_admin_rename()` → tekshiruvlar:
  - nom 2–40 belgi;
  - `get_team_by_name` bilan band emas (baza `UNIQUE(owner_admin_uid, name)`);
  - `db.update_team(team_id, name=...)`.
- `main.py` — `team_admin_rename` holati **FSM ro'yxatiga qo'shildi**.

---

### ✅ A1. Jamoa admini o'z ro'yxatida ko'rinmasin ✅

**Boshqaruv:** `bot/teams.py` — «👥 Foydalanuvchilar» ro'yxatida jamoa
asosi filtrlanadi.

```python
members = [m for m in members if int(m.get("uid") or 0) != int(uid)]
```

**Qo'shimcha (A1 kengaytirilishi):** `core/database.py` —
`count_team_members(team_id, *, include_admin=True)`.

- `include_admin=True` (standart) — **sig'im** hisobi (admin jamoaning a'zosi);
- `include_admin=False` — **ko'rsatiladigan** a'zolar soni (panel + statistika).

Endi paneldagi son (`Foydalanuvchilar: 1/5 ta`) ro'yxatdagi son bilan
**mos keladi**.

---

## 📋 YANGI TESTLAR

| Fayl | Testlar | Qamrov |
|---|---|---|
| `tests/test_team_contact_and_naming.py` | 23 | A1, A2, A3, A6, A8 |
| `tests/test_login_pending_contact.py` | 4 | A7 (3 holat + jamoa asosi arizasi) |
| `tests/test_team_panel_stats_and_referral.py` | 23 | **A9, A10, A11, A12** + A1 kengaytirilishi |

**Jami:** 547 → **597 test**, hammasi o'tadi (`pytest` va `unittest`).

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

1. **Statistika** — jamoa adminida «📊 Statistika» tugmasi endi xatosiz
   ochiladi (avval "Xatolik yuz berdi" berardi).
2. **Referal** — jamoa adminida «👥 Referal» faqat jamoa havolasini
   ko'rsatadi (shaxsiy referal tugmalari va statistikasi yo'q).
3. **Navigatsiya** — jamoa adminida ichki oynalardan «Orqaga» panelga
   qaytadi; panelning «Orqaga» asosiy menyuga.
4. Jamoa admini ro'yxatdan o'tganda **«Jamoa admini bo'ldingiz»**
   xabari keladi va uning jamoasi `Jamoa #<uid>` nomi bilan avtomatik
   yaratilgan bo'lsa — **«✏️ Jamoa nomi»** tugmasi orqali nomni
   almashtirish kerak (foydalanuvchilarga ko'rinadigan texnik nom).
