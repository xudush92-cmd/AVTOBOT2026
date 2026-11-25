# 🔧 TUZATISHLAR RO'YXATI — AVTOBOT2026

> **Holat:** ✅ **BARCHA TUZATISHLAR BAJARILDI** (2026-11-22)
> **Filial:** `arena/8b2153b2-avtobot2026` (asosiy: `main`, commit `6d6e148` — **PR #43 merged**)
> **Testlar:** `684 passed, 62 subtests passed` (bazadagi 667 + 17 yangi)
> **Deploy:** ⏳ VPS'ga o'tkazilishi kutilmoqda (buyruq quyida)

---

## ✅ BAJARILGAN TUZATISHLAR

### 🔴 X5. Guruhni belgilash (✅) tugmasi umuman ishlamaydi ✅

**Boshqaruv:** `bot/callbacks.py` — `ordinary_prefixes` ro'yxati.

**Sabab:** callback router'da **«o'lik zona»** bor edi:

```python
ordinary_prefixes = (..., "disc:")        # ro'yxatda "disc:" bor

if uid != SUPER_ADMIN and data.startswith(ordinary_prefixes):
    if   data.startswith("go:"): ...
    elif data.startswith("stop:"): ...
    elif data.startswith("gchk:"): ...
    return                                   # ← jimgina qaytadi

if data.startswith("disc:"):                # ← HEQ QACHON yetib borMAYdi!
    await G.handle_discover_callback(update, uid, data)
```

`disc:` ro'yxatda bor, lekin uning **`elif` branch'i zanjirda yo'q** →
`disc:toggle` (guruhni ✅ belgilash) hech qanday handler'ga yetib bormadi.

**Belgilari:**
- ✅ belgi chiqmaydi;
- alert (`q.answer`) chiqmaydi;
- **logda ham xato bo'lmaydi** — xato yo'q, kod *yetib borilmagan*.

**Hozir:** `"disc:"` `ordinary_prefixes` dan **chiqarilgan** → o'z
handler'iga (`handle_discover_callback`) yetib boradi.

**Qo'shimcha himoya:** `tests/test_callback_router_coverage.py` —
router'dagi har bir prefix kamida bitta branch'da qamralganini
**avtomatik** tekshiradi. Kelinglikda bu tipdagi «o'lik zona» qaytmaydi.

---

### 🔴 X1. «🔍 Guruhlarni topish» tugmasi ishlamaydi ✅

**Boshqaruv:** `bot/groups.py` — `discover_groups()`, `bot/my_groups.py` — `mg:find`.

**Sabab:** `mg:find` — **inline callback**, lekin `discover_groups` butunlay
`update.message.reply_text(...)` ishlatardi. Inline kontekstda
`update.message` = `None` → `AttributeError: 'NoneType' object has no
attribute 'reply_text'` (VPS logida tasdiqlangan).

**Hozir:** barcha `update.message.reply_text` → `reply_text_safe(...)`
ga o'tkazildi (inline kontekstda `callback_query.message` ga qaytadi).
`status_msg` ham xavfsiz olinadi (`want_message=True`) va `None` bo'lsa
`_status_edit` jim qoladi.

### 🔴 X2/X3. «✏️ Jamoa nomi» va «📨 Xabar yuborish» ishlamaydi ✅

**Boshqaruv:** `bot/keyboards.py`, `bot/teams.py`.

**Sabab:** `edit_message_text` faqat **InlineKeyboardMarkup** qabul qiladi,
lekin `KB.kb_input_cancel()` — **ReplyKeyboardMarkup** →
`BadRequest: Inline keyboard expected` (VPS logida tasdiqlangan).

**Hozir:** `kb_input_cancel_inline()` yaratildi (Inline variant) va
` tadm:rename` / `tadm:message` da ishlatiladi. Reply klaviatura
(matnli xabar) uchun `kb_input_cancel()` o'zgarishsiz qoldi.

### 🟡 X4. «⏰ Vaqt» (interval) oynasi inline kontekstda buziladi ✅

**Boshqaruv:** `bot/timer.py` — `begin_set_interval()`.

**Sabab:** `mg:global` inline dan chaqiriladi, funksiya esa
`update.message.reply_text` ishlatardi.

**Hozir:** `reply_text_safe(...)` ishlatiladi.

### 🟡 X6. Xato va kamchiliklar logga yozilmaydi ✅

**Boshqaruv:** `core/errlog.py` (yangi), `main.py`, `bot/callbacks.py`,
`bot/teams.py`, `bot/groups.py`, `bot/my_groups.py`, `bot/menu.py`,
`bot/referral.py`, `bot/login.py`.

**Yangi modul:** `core/errlog.py` — 3 ta funksiya:
- `log_error(uid, context, exc, action=...)` — 💥 to'liq traceback;
- `log_gap(uid, reason, action=...)` — ⚠️ kamchilik (xato emas);
- `log_event(uid, event, action=...)` — ℹ️ oddiy voqea.

**Qo'shilgan xato ushlash:**
- `main.py::on_message` — matnli xabarda xato → log + foydalanuvchiga javob;
- `main.py::on_error` — PTB handler xatosi → to'liq traceback;
- `bot/callbacks.py` — inline tugma xatosi (avvalgi kuchliroq yozuv bilan);
- `bot/teams.py` — jamoa admini paneli xatosi.

**Kamchilik yozuvlari** (faqat gapsiz natija holatlariga):
sessiya yo'q · FloodWait · Cooldown · skaner allaqachon ishlayapti ·
guruh topilmadi · taklif boshqa jamoada · a'zo topilmadi · jamoa topilmadi ·
admin huquqi yo'q · login oynasi vaqti tugadi · amal bekor qilindi ·
noma'lum menyu tugmasi · referal qayd etilmadi.

**Yuklama:** log aylanmasi 5 MB × 4 = **20 MB doimiy chegara**. Xato yozuvi
~2 KB; 100 xato/kun → ~200 KB/kun (**ta'sir ~0.3%**). Kamchilik yozuvi
faqat gapsiz natijalarda — normal oqimda yozilmaydi, shuning uchun log
shovqin bilan to'lmaydi.

---

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

## ✅ TUZATISHLAR — PR #40 (2026-11-14) — «💬 Guruhlar» oynasi UX

> **Filial:** `arena/c7a82447-avtobot2026` (asosiy: `main`, commit `f53be05` — **PR #41 merged**)
> **Testlar:** `656 passed, 62 subtests passed` (bazadagi 638 + 18 yangi)

### 🟡 U1. Qo'shilgan guruhlar ko'rinmaydi

**Boshqaruv:** `bot/my_groups.py` — `handle_my_groups_callback` (`mg:del`,
`mg:page` amallari).

**Sabab:** oyna yangilanganda faqat sarlavha qoldirilardi:

```python
await q.edit_message_text(
    "💬 <b>GURUHLAR</b>",        # ← ro'yxat va havolalar YO'Q
    parse_mode="HTML",
    reply_markup=KB.kb_my_groups(groups, 0),
)
```

Ya'ni **biror guruhni o'chirsangiz yoki sahifa almashsa**, oyna bo'sh
ko'rinib qolardi — foydalanuvchi "gurchilar ko'rinmaydi" deb shikoyat
qilardi.

**Hozir:** matn/markup yig'ish mantiği `build_groups_window()` funksiyasiga
chiqarildi; `mg:del`, `mg:page` va `disc:apply` — hammasi **bir xil to'liq
oynani** ko'rsatadi (soni + havolalar + o'chirish tugmalari).

### 🟡 U2. «🔍 Guruhlarni topish» tugmasi ikki joyda

**Boshqaruv:** `bot/keyboards.py` — `kb_my_groups()`.

**Sabab:** inline oynada ham, asosiy menyuda ham bor edi — bir xil amal
ikki joyda, chalkashlik keltiradi.

**Hozir:** `kb_my_groups()` da olib tashlandi. Tugma **faqat asosiy
menyuda** qoldi. (`mg:find` handler o'zicha saqlanadi — eski xabarlardan
bosilsa ham ishlasin.)

### 🟡 U3. «🚫 Bekor qilish» oynani yopmaydi

**Boshqaruv:** `bot/groups.py` — `handle_discover_callback`, `disc:cancel`.

**Sabab:** xabar tahrirlanardi va «🚫 Bekor qilindi...» deb qoldirilardi —
foydalanuvchi uchun oyna yopilgan emas.

**Hozir:** xabar **o'chiriladi**. O'chirish imkoni bo'lmasa (eskirgan
xabar), hech narsa qoldirilmaydi — faqat klaviatura olib tashlanadi.
Xuddi shunday `mg:back` ham oynani o'chiradi («💬 Guruhlar yopildi»
xabari qolmaydi).

### 🟡 U4. Skaner allaqachon qo'shilgan guruhlarni takror taklif qiladi

**Boshqaruv:** `bot/groups.py` — `discover_groups()`.

**Holat:** filtr allaqachon bor edi va **ishlaydi**:

```python
existing_keys = {build_key(v) for v in await db.get_chats(uid)}
...
if key in existing_keys:
    duplicate_count += 1
    continue          # ← allaqachon qo'shilgan guruh chiqmaydi
```

**Bu yerda:** mavjud xatti-harakatni **o'zgartirmadik**, faqat
**regressiya testlari** qo'shdik (`test_already_added_groups_excluded_from_next_scan`)
— kelgusi o'zgarishlarda buzilmasligi uchun.

### 🟡 U5. «✅ Qo'shish»dan keyin guruhlar ko'rinmaydi

**Boshqaruv:** `bot/groups.py` — `handle_discover_callback`, `disc:apply`.

**Sabab:** faqat hisobot («Qo'shildi: N ta») ko'rsatilardi va asosiy
menyu klaviaturasi qo'yilardi — qo'shilgan guruhlar ro'yxati ko'rinmardi.

**Hozir:** hisobot **va** yangilangan «💬 Guruhlar» oynasi bir xil xabarda
chiqadi. Agar xabar tahrirlab bo'lmasa, yangi xabar yuboriladi.

### 🔧 U6. Eskirgan skaner xabari chatda qolib ketardi

**Boshqaruv:** `bot/groups.py` — `handle_discover_callback`, `disc:apply`.

**Kamchilik (review'da topildi):** agar skaner xabarini tahrirlab bo'lmasa
(eskirgan yoki klaviyaturasiz), yangi guruhlar oynasi xabari yuborilardi —
lekin **eskirgan skaner xabari ham o'rnida qolardi**. Chatda ikkita xabar
qolib ketardi.

**Hozir:** yangi xabar yuborilgandan keyin eskirgan skaner xabari ham
**o'chiriladi** (`q.delete_message()`).

**Tekshiruv:** `test_apply_deletes_stale_scanner_when_new_message_sent`

---

## ✅ TUZATISHLAR — PR #41 (2026-11-22) — Guruh nomi (title)

> **Filial:** `arena/c7a82447-avtobot2026` (asosiy: `main`, commit `e9b2e5e`)
> **Testlar:** `656 passed, 62 subtests passed` (bazadagi 638 + 18 yangi)

### 🟡 V1. Guruh nomi ko'rinmaydi — qaysi guruh ekanini bilib bo'lmaydi

**Boshqaruv:** `bot/keyboards.py` — `kb_my_groups()`; `bot/my_groups.py` —
`build_groups_window()`.

**Sabab:** bazada faqat `value` (username yoki ID) saqlanardi —
guruhning **display name** (title) umuman yo'q edi. Shuning uchun:

- `🗑` tugmasi `🗑 1. @taxi_xorazm_toshken_gruppasi` ko'rsatardi —
  foydalanuvchi bu **username** ni ko'radi va guruhni tanib olmaydi
  (asl nomi «Taxi Xorazm Toshken guruhi» bo'lishi mumkin);
- ro'yxatda faqat `https://t.me/...` havola chiqardi, nomi yo'q.

**Hozir:**

1. **Baza** — `groups` jadvaliga `title TEXT DEFAULT ''` ustuni qo'shildi
   (`ALTER TABLE` — xavfsiz migratsiya, eski ma'lumot o'chmaydi).
2. **`db.add_chat(uid, value, title="")`** — yangi ixtiyoriy parametr.
3. **`db.set_chat_title(uid, group_id, title)`** — faqat bo'sh nomni
   to'ldiradi (mavjud nomni qayta yozmaydi).
4. **Skaner** — topilgan guruh nomi (`group.title`) darhol bazaga saqlanadi.
5. **Qo'lda kiritish** — nom **fon task**da Telegram'dan olinadi (asosiy
   oqim tez va Telegram'siz ishlaydi — avvalgi kafolat saqlanadi).
6. **«💬 Guruhlar» oynasi** — nomi yo'q guruhlar uchun fon task ishga
   tushadi va nomni saqlaydi.
7. **`🗑` tugmasi** — endi **nomni** ko'rsatadi:
   `🗑 1. Taxi Xorazm Toshken`. Nomi yo'q bo'lsa — username.
8. **Ro'yxat** — `1. Taxi Xorazm Toshken — https://t.me/taxi_x`.

### 🔒 Yopiq guruhlar (maxfiylik saqlanadi)

Marked ID (`-1001234567890`) **ko'rsatilmaydi** — avvalgi xatti-harakat
saqlangan. Nomi bo'lsa faqat nomi chiqadi.

**Tekshiruv:** `tests/test_group_titles.py` — 18 ta yangi test
(migratsiya, baza API, ko'rsatish, skaner, fon task).

---

## 🔴 TUZATISHLAR — PR #42 (2026-11-22) — «Guruhlar yo'q» muammosi

> **Filial:** `arena/361ef30e-avtobot2026` (asosiy: `main`, commit `5de3380` — **PR #42 merged**)
> **Testlar:** `667 passed, 62 subtests passed` (bazadagi 656 + 11 yangi)
> **Holat:** ✅ PR #42 merged — deploy kutilmoqda

### 🔴 W1. Guruhlar qo'shilgan deb ko'rsatiladi, lekin bazada yo'q

**Boshqaruv:** `core/database.py` — `add_chat()`; `bot/groups.py` —
`disc:apply`; `bot/my_groups.py` — `build_groups_window()`;
`bot/callbacks.py` — o'chirish tugmasi.

**Belgilari (production'da `6169018469` bo'yicha tekshirilgan):**

| Vaqt | Natija |
|---|---|
| 17:30:05 | log: `✅ Tanlangan guruhlar qo'shildi: 6169018469 → +3` |
| 18:28:10 | skaner: 0 ta yangi guruh (dedup ishladi — bazada 3 ta bor edi) |
| 19:12:03 | skaner: 3 ta topildi, `takror 0` — bazada **yo'q** |
| hozir | `groups` jadvalida `uid=6169018469` uchun **0 ta** qator |

`sqlite_sequence.groups = 560` — demak 3 ta qator (558–560) **yaratilgan**,
keyin **o'chirilgan** (AUTOINCREMENT qiymati saqlanadi).

**Sabab zanjiri:**

1. `groups.uid → users(uid) ON DELETE CASCADE` + `PRAGMA foreign_keys=ON`
   — `users` qatori o'chsa, guruhlar ham **jinsiy** yo'qoladi.
2. `db.add_chat()` — FK xatosi (`IntegrityError`) va UNIQUE xatosi
   **bir xil** klassda; FK xatosi ham **«duplicate»** deb yolg'on
   qaytarilardi → haqiqiy sabab logda ko'rinmasdi.
3. `add_chat()` `commit()` dan keyin **tekshirmaydi** — yozuv commitdan
   keyin yo'qolsa, u ham `True, "ok"` qaytarib, logda `+3` yozilardi.
4. Guruh o'chirishda (`my_groups.py`, `callbacks.py`) **`log()` yo'q** —
   faqat Telegram'ga xabar yuborilardi, iz qolmaydi.
5. `disc:apply` — natija bazadagi haqiqiy ro'yxat bilan **tekshirilmasdi**.

**Hozir:**

1. **`add_chat()`** — FK xatosi `duplicate` dan ajratiladi, alohida
   `foreign_key` qaytariladi va **logda** ko'rinadi.
2. **`add_chat()`** — `commit()` dan keyin yozuv bazada borini
   tekshiradi; yo'q bo'lsa `False, "error"` qaytaradi (va log yozadi).
3. **`delete_user()`** — bog'liq guruhlar va referallar **aniq**
   o'chiriladi (FK CASCADE ishonchiga tayanmaydi).
4. **O'chirishda log** — `my_groups.py` va `callbacks.py` da `log()`
   qo'shildi: `🗑 <uid> guruh o'chirildi (foydalanuvchi/tugma)`.
5. **`disc:apply`** — qo'shishdan keyin bazadagi haqiqiy ro'yxatni
   tekshiradi; bazada 0 ta bo'lsa foydalanuvchiga **«❌ Guruhlar
   qo'shilmadi»** xabari chiqadi (avval yolg'on «qo'shildi» deyardi).
6. **Bo'sh «💬 Guruhlar» oynasi** — skanerda topilgan guruhlar bo'lsa,
   «Tanlanganlarni qo'shish» eslatmasi chiqadi (foydalanuvchi nima
   qilishini biladi).

**Tekshiruv:** `tests/test_group_visibility_fix.py` (10 ta test) +
`tests/test_live_flow_smoke.py` (1 ta to'liq oqim testi).

---

## 🎯 TUZATISHLAR — PR #43 (2026-11-22) — Tanlangan guruhlar yo'qolmasligi

> **Filial:** `arena/8b2153b2-avtobot2026` (asosiy: `main`, commit `6d6e148` — **PR #43 merged**)
> **Testlar:** `684 passed, 62 subtests passed` (bazadagi 667 + 17 yangi)
> **Holat:** ✅ PR #43 merged — deploy kutilmoqda

### 🎯 X1. Tanlangan guruhlar «yo'qoladi» — foydalanuvchi chalkashadi

**Boshqaruv:** `bot/groups.py`, `bot/my_groups.py`, `bot/keyboards.py`,
`bot/texts.py`.

**Belgilari (production, `6169018469`):**

- Skaner 3 ta guruh topadi va foydalanuvchi ularni ✅ belgilaydi;
- Foydalanuvchi **«Tanlanganlarni qo'shish (3)»** tugmasini **bosmaydi** —
  o'rniga **«Guruhlar»** tugmasini bosadi;
- Natijada **«Sizda hali guruh yo'q»** chiqadi — foydalanuvchi tanlagan
  guruhlarni **yo'qotganini** bilmaydi.

**Sabab:** «💬 Guruhlar» oynasi skanerdagi **tanlanishni ko'rmasdi** va
uni qo'shish imkoniyatini **bermasdi**. Skaner oynasida esa faqat
**«🚫 Bekor qilish»** bor edi — u tanlanishni **butunlay tozalaydi**.

**Hozir:**

1. **«💬 Guruhlar» oynasi** — skanerdagi tanlanishni ko'rsatadi:
   - `ℹ️ Skanerda 3 ta guruh topilgan, 2 tasi tanlangan — lekin ular hali
     qo'shilmagan.`
   - **«✅ Tanlanganlarni qo'shish (2)»** tugmasi chiqadi
     (`mg:apply`) — bo'sh va to'ldirilgan oynada ham.
2. **`mg:apply` handler** — skanerdagi **«✅ Tanlanganlarni qo'shish»**
   bilan **bir xil** funksiyani ishlatadi (`apply_selected_groups`), ya'ni
   natija har ikki yo'lda ham bir xil.
3. **Skaner oynasida «⬅️ Guruhlar» tugmasi** (`disc:groups`) — skanerdan
   chiqishda **tanlanish saqlanadi**; foydalanuvchi keyinchalik
   «Guruhlar» oynasidan qo'shishi mumkin.
4. **`apply_selected_groups`** — `apply` mantiqi modul darajasida
   ajratildi, ikkala yo'l ham **bir xil** kodni ishlatadi.
5. **«🚫 Bekor qilish»** — o'z xatti-harakatini saqlaydi (skaner oynasi
   yopiladi, tanlanish tozalanadi).

**Tekshiruv:** `tests/test_pending_selection.py` (10 ta test) +
`tests/test_live_flow_smoke.py` (2 ta test — to'liq oqim).

### 🎯 X2. Tugma chalkash — foydalanuvchi oxiridagini bosmaydi

**Boshqaruv:** `bot/texts.py`, `bot/keyboards.py`, `bot/groups.py`.

**Belgilari:** foydalanuvchi skanerda guruhlarni tanlab chiqadi va
**oxiridagi tugmani bosmaydi** — natijada guruhlar qo'shilmaydi va u
«guruhlar yo'q» deb o'ylaydi. Sabab: tugma matni **«✅ Tanlanganlarni
qo'shish (3)»** edi — `✅` belgisi **guruh belgilash** tugmasi bilan
bir xil bo'lgani uchun chalkash edi, va saqlash amali **tushuntirilmagandi**.

**Hozir:**

1. **Tugma matni** — «✅ Tanlanganlarni qo'shish (N)» →
   **«💾 Tanlanganlarni saqlash (N)»**. «💾» belgisi **saqlashni**
   ko'rsatadi va belgilash tugmasidan farqlanadi.
2. **Skaner matni** — endi oxirgi tugmani aniq tushuntiradi:
   > ⚠️ Tanlagandan keyin ro'yxatning **pastidagi** «💾 Tanlanganlarni
   > saqlash» tugmasini bosish shart — shundagina guruhlar saqlanadi.
3. **Tasdiqlash bosqichi** — saqlash tugmasi bosilganda avval
   **tasdiqlash oynasi** ochiladi:
   ```
   💾 Tanlangan 2 ta guruhni saqlash

   Ro'yxat:
   • Toshkent Taksi
   • Xorazm Taksi

   Ularni «💬 Guruhlar» ro'yxatiga qo'shasizmi?

   [✅ Ha, saqla]  [❌ Yo'q, bekor qil]
   ```
   «✅ Ha, saqla» bosilgandagina guruhlar bazaga yoziladi. «❌ Yo'q,
   bekor qil» — hech narsa saqlanmaydi va sessiya tozalanadi.
4. **Ikki yo'l bir xil** — skanerdagi va «Guruhlar» oynasidagi saqlash
   tugmalari **bir xil** tasdiqlash oqimini ishlatadi.

**Tekshiruv:** `tests/test_pending_selection.py` (6 ta yangi test:
tasdiqlash oynasi, «ha»/«yo'q», tugma matni, skaner matni).

---

## 📋 YANGI TESTLAR

| Fayl | Testlar | Qamrov |
|---|---|---|
| `tests/test_team_contact_and_naming.py` | 23 | A1, A2, A3, A6, A8 |
| `tests/test_login_pending_contact.py` | 4 | A7 (3 holat + jamoa asosi arizasi) |
| `tests/test_team_panel_stats_and_referral.py` | 23 | **A9, A10, A11, A12** + A1 kengaytirilishi |
| `tests/test_inline_fixes_and_error_logging.py` | 16 | **X1, X2, X3, X4, X6** |
| `tests/test_callback_router_coverage.py` | **11** (yangi) | **X5** — belgilanish + router qamrovi |
| `tests/test_discover_group_window_ux.py` | **14** (yangi) | **U1, U2, U3, U4, U5** |
| `tests/test_group_titles.py` | **18** (yangi) | **V1** — guruh nomi (migratsiya, baza, ko'rsatish, fon task) |
| `tests/test_group_visibility_fix.py` | **10** (yangi) | **W1** — «Guruhlar yo'q» tuzatishi (FK, commit tekshiruvi, o'chirish logi, bo'sh oyna eslatmasi) |
| `tests/test_live_flow_smoke.py` | **2** (yangi) | **W1, X1** — to'liq oqim: skaner → qo'shish → ko'rish → o'chirish; tanlanish saqlanishi |
| `tests/test_pending_selection.py` | **16** (yangi) | **X1, X2** — tanlangan guruhlar yo'qolmasligi + tasdiqlash |

**Jami:** 547 → **684 test**, hammasi o'tadi (`pytest` va `unittest`).

> Eski testlar (`test_menu_simplified.py`, `test_my_groups_screen.py`)
> `mg:find` mavjudligini talab qilardi — yangi UX ga moslab yangilandi.

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


---

## 📛 TUZATISHLAR — PR #44 (2026-11-23) — Guruh nomi hamma oynalarda

> **Filial:** `arena/724b5f17-avtobot2026` (asosiy: `main`, commit `b8b10d3`)
> **Testlar:** `697 passed, 62 subtests passed` (bazadagi 684 + 13 yangi)
> **PR:** #44 — ✅ **MERGED** (merge commit `9c1d704`)
> **Holat:** ⏳ VPS'ga o'tkazish kutilmoqda

### 🟡 Y1. Interval oynalarida guruh **ID** si ko'rinadi

**Belgilari (screenshot, `6169018469`):**

```
⏱ GURUH INTERVALI
-1003119200089 · Umumiy 6 daq
-1003757610510 · Umumiy 6 daq
@guruh99999999  · Umumiy 6 daq
```

Foydalanuvchi guruhni **ID** orqali tanib olmaydi. Bazada esa nomlar
**bor**:

```
6169018469 | -1003119200089 | КАНГЛИ ЯККА ТУРОНГИЛ МФЙ
6169018469 | -1003757610510 | QARNDOSHLAR
6169018469 | @guruh99999999   | Guruh
```

**Sabab:** PR #41 nomni faqat **«💬 Guruhlar»** oynasiga qo'shgan edi.
Boshqa oynalar (interval tanlash, o'chirish, qo'shish) **to'g'ridan-to'g'ri**
`value` (ID) ni chiqarardi.

**Asosiy sabab:** `db.get_chat_record()` ning `SELECT` ro'yxatida **`title`
yo'q edi** — faqat `get_chat_records()` da bor edi. Shu sababli bitta guruhni
ko'rsatadigan oynalarda nom **hamma vaqt** bo'sh chiqardi.

**Hozir:**

1. **`db.get_chat_record()`** — `title` ustuni `SELECT` ga qo'shildi.
2. **`kb_group_interval_picker()`** — interval tugmalarida **nom** chiqadi
   (nomi yo'q bo'lsa — username/ID).
3. **`my_groups.show_group_interval()`** — «Guruh: \<nom\>».
4. **`timer.handle_group_interval_callback()`** — «Guruh: \<nom\>» va
   «✏️ \<nom\> uchun intervalni…».
5. **`my_groups`** — o'chirish xabari «🗑 O'chirildi: \<nom\>».
6. **`texts.groups_delete_text()`** — o'chirish ro'yxatida **nom**.
7. **`groups.show_groups()`** — qo'shish yo'lidagi ro'yxatda **nom**.

**Qo'shimcha:** `group_label()` logikasi `core/utils.py` ga ko'chirildi —
bitta manba, hamma oynada bir xil natija.

**🔎 LIVE BAZA TEKSHIRUVI (2026-11-23):**

```bash
sqlite3 data/avtobot.db "SELECT COUNT(*), SUM(CASE WHEN title IS NULL OR title='' THEN 1 ELSE 0 END), SUM(CASE WHEN title<>'' THEN 1 ELSE 0 END) FROM groups;"
# → 284 | 281 | 3
```

| Jami | Nomi yo'q | Nomi bor |
| ---- | --------- | -------- |
| **284** | **281** | **3** |

Nomi bor 3 ta guruh — `6169018469` ning guruhlari, **2026-11-23 03:51:47** da
**skaner** orqali qo'shilgan (bir vaqtda, nomlari to'g'ri saqlangan):

```
6169018469 | -1003119200089 | КАНГЛИ ЯККА ТУРОНГИЛ МФЙ
6169018469 | -1003757610510 | QARNDOSHLAR
6169018469 | @guruh99999999   | Guruh
```

**Xulosa:** skaner oqimi (`add_chat(..., title=...)`) **ishlayapti**.
281 ta guruh — **PR #41 dan OLDIN** qo'shilgan (`title` ustuni yo'q paytda),
ularning nomi hali olilmagan.

**Tekshiruv:** `tests/test_group_names_everywhere.py` (13 ta test):
`group_label` mantiqi, `get_chat_record` title, interval tugmalari,
bitta guruh oynasi, qo'lda interval, «💬 Guruhlar» oynasi, o'chirish
xabari, o'chirish ro'yxati, `show_groups()`.


---

## 🔧 TUZATISHLAR — PR #45 (2026-11-23) — Admin panel: muddat +/- va «Orqaga» yopadi

> **Filial:** `arena/b9039601-avtobot2026` (asosiy: `main`, commit `cc7684c`)
> **Testlar:** `715 passed, 62 subtests passed` (bazadagi 697 + 18 yangi)
> **PR:** #45 — ✅ **MERGED** (merge commit `d174f93`)
> **Holat:** ⏳ VPS'ga o'tkazish kutilmoqda

### 🔵 Z1. Super admin boshqa adminlarga muddat **+ / −** qo'yishi

**Hozirgi holat:**
- **Jamoa admini** — faqat `+` bor («📅 Muddatni uzaytirish»).
- **Oddiy admin** — faqat muddatni **almashtirish** (1/7/30/90/cheksiz), `+`/`−` yo'q.

**Endi:**
- `core.utils.shift_expires()` — muddatni `±` kun siljitadi (yagona manba).
- **Jamoa admini kartasi** — «⏳ Muddatni kamaytirish» tugmasi qo'shildi.
- **Muddat oynasi** — yuqorida `+1/+7/+30…`, pastida `−1/−7/−30…`.
- **Oddiy admin** — «⏰ Tarif muddati» oynasida «➕ Ko'paytirish» va
  «➖ Kamaytirish» tugmalari (`expadd:` / `expsub:`).
- Jamoa admini uchun ham, oddiy admin uchun ham **bir xil qoida**:
  `+` — mavjud muddatga qo'shiladi, `−` — mavjud muddatdan ayiriladi.

### 🔵 Z2. Admin oynasi «⬅️ Orqaga» bosilganda **yopiladi**

**Hozirgi holat:** `adm:back` → `show_panel()` → asosiy panel **tahrirlanadi**
va **ochiq qoladi**.

**Endi:**
- `close_admin_window()` — xabar **o'chiriladi** (o'chirib bo'lmasa —
  klaviatura olib tashlanadi).
- `adm:back` → oyna yopiladi + qayta ochish uchun **panel tugmalari**
  yangi xabarda ko'rsatiladi.
- `adm:teamadmins` → jamoa adminlari ro'yxati **yangi xabarda** ochiladi
  (eski oyna yopiladi).

### 🔵 Z3. Admin panel **minimal va aniq**

- Tugmalar **qisqartirildi** va **2 qatorga** joylandi (11 ta saqlanadi):
  `➕ User qo'shish`, `👥 Userlar`, `👑 Jamoa adminlari`, `📊 Statistika`,
  `⏳ Tasdiq kutilmoqda`, `🕓 Muddati tugagan`, `📢 Xabar yuborish`,
  `🚫 Bloklanganlar`, `💾 Ma'lumotlar bazasi`, `🖥 Tizim holati`.
- Statistika **2 qatorga** siqildi (`👥 Userlar: N | ✅ Admin: N | …`).
- `send_super_admin_panel()` matni `show_panel()` bilan **bir xil** qilindi
  (avval ikki xil matn bor edi).
- `/help` ga qisqa qadamlar (`WELCOME_GUIDE`) qo'shildi — bu matn
  yozilgan, lekin **hech qayerda ishlatilmasdi**.

**Tekshiruv:** `tests/test_admin_panel_term.py` (18 ta test):
`shift_expires` mantiqi (4), jamoa admini muddati +/- (4), oddiy admin
muddat +/- (4), oyna yopish (3), panel minimal (2), `+`/`−` oynalari (1).


---

## 🛡 TUZATISHLAR — PR #46 (2026-11-23) — Worker himoyasi: leak va PeerFlood

> **Filial:** `arena/367cf38f-avtobot2026` (asosiy: `main`, commit `d35cbef`)
> **Testlar:** `723 passed, 62 subtests passed` (bazadagi 715 + 8 yangi)
> **Holat:** ⏳ PR ochilmoqda

### 🔴 V1. Worker connection **leak** — pool to'ladi, yangi user Start bosolmaydi

**Sabab:** `worker/worker.py` — `client_pool.acquire()` dan keyin
`posting_window_state()` (kunlik limit / tungi tanaffus) `allowed=False`
bo'lsa `continue` qilinardi. Lekin `client_pool.release(uid)` faqat
yuborish bloki ichidagi `finally` da chaqirilardi — **`continue` o'sha
blokdan o'tib ketardi**.

**Ta'siri:** `references` refcount osib qolardi → client **hech qachon
"idle" bo'lmasdi** → pool 50 ta client bilan to'lsa, `evicted` topilmaydi
→ `PoolBusyError` → **yangi foydalanuvchi «▶️ Start» bosolmay qoladi**.

**Tuzatish:** limit/to'xtash holatida `client_pool.release(uid)` — `continue`
dan **oldin** chaqiriladi.

### 🔴 V2. **PeerFlood** — akkaunt butunlay ban bo'lardi

**Sabab:** `PeerFloodError` va `UserBannedInChannelError` **import qilinmagandi**
— ular umumiy `except Exception` ga tushib, `fail += 1` qilib, keyingi
intervalda **yana urinish** qilardi.

**Ta'siri:** Telegram akkauntga «juda ko'p so'rov» (PeerFlood) deb
cheklov qo'ygan bo'lsa, worker har intervalda yana urinish qilib,
akkauntni tez **butunlay ban** (PostFlood) qilardi. Bu — **akkauntni
yo'qotish** demak.

**Tuzatish:**
- `PeerFloodError` — **alohida** ushlanadi:
  - yuborish **butunlay to'xtatiladi** (boshqa guruhlarga ham);
  - `PEER_FLOOD_PAUSE_S` (standart **1 soat**, `.env` bilan o'zgartiriladi)
    kutish;
  - akkaunt **o'chirilmaydi** — faqat kutadi;
  - foydalanuvchiga **xabar** yuboriladi (guruhlar sonini kamaytirish tavsiya).
- `UserBannedInChannelError` — guruh darajasidagi xato sifatida
  qo'shildi (3 urinishdan keyin guruh ro'yxatdan chiqadi).

### 📌 Yangi sozlamalar

```bash
# .env (ixtiyoriy) — PeerFlood'da kutish vaqti (soniya, standart 3600)
PEER_FLOOD_PAUSE_S=3600
```

> 📌 **Baza sxemasi o'zgarmadi.**
> 📌 **Start / Stop / interval / kunlik limit** semantikasi o'zgarmadi.
> 📌 Faqat **xato holatlar** to'g'ri ishlaydi.

**Tekshiruv:** `tests/test_worker_safety.py` (8 ta test): PeerFlood
alohida ushlanishi, `release` `continue` dan oldin, `references` kamayishi,
`PEER_FLOOD_PAUSE_S` mavjudligi.

**✅ PR #46 MERGED** — `8dcf4fc`
(https://github.com/xudush92-cmd/AVTOBOT2026/pull/46)

---

## 🔒 PR #47 — Jamoa xavfsizligi: taklif, bloklash va sig'im

> 📌 **PR #46 (worker leak + PeerFlood) dan davomi.** Alohida PR — har bir
> o'zgarish alohida ko'rib chiqilishi uchun.

### 🔴 V3. Jamoa taklifi **kodsiz** qo'llanardi

**Sabab:** `bot/login.py::_handle_phone_locked()` — telefon raqam
yozilgach **darhol** `_auto_bind_team_invite()` chaqirilardi. Bu — Telegram
tasdiq kodi **so'ralmasdan**, ya'ni raqamning haqiqiy egasi
tekshirilmasdan.

**Ta'siri:** Begona odam o'z raqamini yozib, Telegram kodiga ehtiyoj
yo'q holda **jamoa admini** bo'lib qolishi mumkin edi. Super admin
taklif qilgan raqam — kodsiz jamoa adminiga aylanardi.

**Tuzatish:**
- `_handle_phone_locked()` — taklif **butunlay** olib tashlandi.
- Yangi `_apply_team_invite_after_login()` — taklifni **faqat** Telegram
  login **muvaffaqiyatli** bo'lgandan keyin qo'llaydi.
  - ✅ SMS kod (numpad) → `attempt_signin(..., update=update)`
  - ✅ 2FA parol → `handle_password()` → `finalize_login(uid, update=update)`
  - ✅ QR login → `finalize_login(uid, update=None)` (ism bazadan olinadi)
  - ✅ Kodsiz tasdiqlash (`SentCodeSuccess`) → `request_code(...,
    update=update)` → `finalize_login(uid, update=update)`
- `finalize_login()` va `_finalize_login_locked()` endi ixtiyoriy
  `update` parametrini oladi.

### 🔴 V4. Jamoa admini **super admin blokini** bekor qila olardi

**Sabab:** Kim bloklagani saqlanmasdi — faqat `is_blocked` (0/1) bor edi.
Jamoa admini `tadm:unblock:<uid>` bosganda **har qanday** blokni
chiqara olardi.

**Ta'siri:** Super admin tomonidan bloklangan foydalanuvchi jamoa admini
orqali «ochilib» ketardi — bloklash cheklovi ma'nosiz bo'lardi.

**Tuzatish:**
- `users` jadvaliga **`blocked_by`** ustuni qo'shildi (migratsiya bilan,
  eski DB ma'lumotlari saqlanadi; `0` = tizim/super admin).
- Jamoa admini bloklaganda `blocked_by = <jamoa admini uid>` yoziladi.
- Blokdan chiqarishda: **faqat `blocked_by == uid`** bo'lsa mumkin.
  Aks holda — «🚫 Bu foydalanuvchi super admin tomonidan bloklangan».
- Super admin (`admin/admin_actions.py`) bloklaganda `blocked_by = 0`
  qoladi — jamoa admini uni bekor qila olmaydi.

### 🔴 V5. Jamoa sig'imi **noto'g'ri** hisoblanardi

**Sabab:** `approve_team_member()` — sig'imni `len(members)` bilan
tekshirardi, bu yerda **jamoa admini ham** hisobga olinardi. Yana
`team_has_free_slot()` (taklif berish, ariza yuborish, referal,
super admin biriktirish) — **boshqa** o'lchovni ishlatardi.

**Ta'siri:** Sig'im 2 bo'lgan jamoada: admin (1) + 1 arizachi = 2 →
`2 >= 2` → «sig'im to'lgan» deb rad etilardi. Ya'ni jamoaga **bitta
odam** ham sig'imar qabul qilinmas edi. Bundan tashqari, **taklif
berish** bosqichi rad etsa, **tasdiqlash** bosqichi esa o'tib ketardi —
ikki bosqich turli o'lchov bilan ishlagan.

**Tuzatish:** Sig'im — jamoaning **a'zolari** soni. Jamoa admini (jamoa
egasi) hisobga **olmaydi**. Arizachi allaqachon jamoaga biriktirilgan
bo'lgani uchun u hisobga olinadi.

- `count_team_members()` — standart `include_admin=False`
  (jamoa admini hisobdan chiqariladi).
- `team_has_free_slot()` — `include_admin=False` bilan hisoblaydi.
- `approve_team_member()` — `count_team_members(..., include_admin=False)`.

Natijada **barcha** bosqichlar **bir xil** o'lchovni ishlatadi:
taklif berish → ariza → tasdiqlash.

### 📌 Baza sxemasi

```sql
ALTER TABLE users ADD COLUMN blocked_by INTEGER DEFAULT 0;
```

> 📌 Migratsiya avtomatik ishlaydi (`_migrate_schema()`) — eski DB
> fayllari va ma'lumotlari saqlanadi.
> 📌 **Start / Stop / interval / kunlik limit** semantikasi o'zgarmadi.
> 📌 Scanner, guruh nomlari va boshqa funksiyalar o'zgarmadi.

**Tekshiruv:** `tests/test_team_security.py` (12 ta test): taklif
telefon bosqichida qo'llanmasligi, `blocked_by` saqlanishi, jamoa
adminining super admin blokini chiqara olmasligi, sig'imda admin
hisobga olinmasligi.

**✅ PR #48 MERGED** — `e92fe12`
(https://github.com/xudush92-cmd/AVTOBOT2026/pull/48)

> 📌 Ko'rib chiqishda sig'im o'lchovida ziddiyat topildi va tuzatildi:
> `team_has_free_slot()` (taklif/a'riza/referal/super admin) va
> `approve_team_member()` (tasdiqlash) — boshqa-boshqa o'lchov ishlatgan.
> Endi **barcha** bosqichlar bir xil: jamoanin **a'zolari** soni
> (jamoa egasi hisobga olinmaydi).
> 📌 Qo'shimcha: `request_code()` ga `update` qo'shildi — kodsiz
> tasdiqlash (`SentCodeSuccess`) oqimida ham taklif to'g'ri qo'llanadi.


---

## 🛡️ PR #49 — Muddat va jamoa xavfsizligi (auditning qolgan bandlari)

> 📌 **PR #46 (worker leak + PeerFlood)** va **PR #48 (jamoa taklifi,
> bloklash manbai, sig'im)** dan davomi. Alohida PR — har bir o'zgarish
> alohida ko'rib chiqilishi uchun.

### 🔴 V6. Jamoa admini muddat eslatmasi **har daqiqada** yuborilardi

**Sabab:** `main.py::check_team_admin_expiry()` — xabar yuborgandan keyin
**hech qanday belgi qo'ymasdi**. `admin_expires_at` o'zgarmay qoladi,
shuning uchun `get_expired_team_admins()` har chaqiruvda **shu adminga
qaytaradi** — janitor har daqiqada ishga tushsa, xabar ham **har
daqiqada** yuborilardi.

**Ta'siri:** Foydalanuvchi, jamoa a'zolari va super admin bir xil xabarni
daqiqa davomida yana-yana oladi.

**Tuzatish:**
- `users` jadvaliga **`admin_expiry_notified_at`** ustuni qo'shildi
  (avtomatik migratsiya).
- Xabar yuborilgach belgi qo'yiladi — keyingi chaqiruvda xabar
  yana yuborilmaydi.
- `set_admin_expires()` va `set_team_admin()` — muddat yangilangananda
  belgi **tozalanadi**, shunda yangi muddat tugaganda ogohlantirish
  yana bir marta yuboriladi.

### 🔴 V7. Jamoadan chiqishda muddat **chekisiz** bo'lib qolardi

**Sabab:** `core/database.py::leave_team()` — jamoa admini bergan muddatni
`tariff_expires_at = None` (chekisiz) qilib qo'yardi. Hujjat va
foydalanuvchiga yuboriladigan xabar «uning muddati ham tugdi» deb
aytadi.

**Ta'siri:** Foydalanuvchi xabar oladi va muddat tugaganini o'ylaydi —
lekin bazada cheksiz qoladi va muddat **hech qachon tugmaydi**. Xabar
yolg'on, funksiya esa muddatni **uzaytirib** yuboradi.

**Tuzatish:** Endi muddat **bugun tugagan** (`calc_expires(0)`) qilib
qo'yiladi — haqiqatan ham tugaydi. Super admin bergan muddat
(jamoasiz tasdiqlash) **saqlanadi** — o'zgarmaydi.

### 🔴 V8. «Kamaytirish» cheksiz muddatni **darhol tugatardi**

**Sabab:** `core/utils.py::shift_expires(None, -1)` — `calc_expires(0)`
qaytarardi, ya'ni muddat **shu zahoti tugaydi**. Docstring esa
«o'zgartirilmaydi (cheksiz qoladi)» deb yozgan edi — kod bilan ziddiyat.

**Ta'siri:** Super admin jamoa adminining muddatini «kamaytirish» tugmasi
bossa va o'sha muddat cheksiz bo'lsa, uning jamoasi va jamoasi
**darhol to'xtaydi** — bu «kamaytirish» emas.

**Tuzatish:**
- `shift_expires()` endi `None` + manfiy kun holatida **`None` qaytaradi**
  (rad etiladi) va `str | None` qaytaradi.
- Ikkala chaqiruv joyi ham (oddiy admin va jamoa admini muddati) endi
  foydalanuvchiga tushunarli xabar beradi: «❌ Cheksiz muddatni
  kamaytirib bo'lmaydi. 💡 Avval muddat bering (+ tugmasi), keyin
  kamaytiring.»

### 🔴 V9. Jamoa admini **o'zini bloklay** olardi

**Sabab:** `bot/teams.py` — jamoa egasining `owner_admin_uid` o'zining
qiymatiga teng (`create_team_for_admin` shuni yozadi). `block`/`unblock`/
`term` shartlari esa `owner_admin_uid == uid` ni tekshiradi — ya'ni
jamoa admini **o'ziga** nisbatan amal bajarishi mumkin edi.
(`kick` da `is_team_admin` tekshiruvi bor edi, `block`da — yo'q.)

**Ta'siri:** Jamoa admini o'zini bloklab, keyin o'zi ochib ketishi
mumkin edi — o'z jamoasiga nisbatan nazoratdan chiqib ketadi.

**Tuzatish:** `block`, `unblock` va `term` amallarida jamoa egasiga
«🚫 O'zingizga nisbatan amal bajarib bo'lmaydi» deb rad etiladi.

### 📌 Baza sxemasi

```sql
ALTER TABLE users ADD COLUMN admin_expiry_notified_at TEXT;
```

> 📌 Migratsiya avtomatik ishlaydi (`_migrate_schema()`) — eski DB
> fayllari va ma'lumotlari saqlanadi (eski DB bilan sinovdan o'tdi).
> 📌 **Start / Stop / interval / kunlik limit** semantikasi o'zgarmadi.
> 📌 Scanner, guruh nomlari va boshqa funksiyalar o'zgarmadi.

**Tekshiruv:** `tests/test_expiry_and_self_guard.py` (14 ta test):
xabarning bir marta yuborilishi, belgi qo'yilishi va tozalanishi,
chiqishda muddatning cheksiz bo'lmasligi, `shift_expires` rad etishi,
jamoa adminining o'ziga amal bajarolmasligi.

**✅ PR #49 MERGED** — `d053f27`
(https://github.com/xudush92-cmd/AVTOBOT2026/pull/49)

---

## ✅ Audit yakunlandi — barcha bandlar tuzatildi

| PR | Holat | Bandlar |
|---|---|---|
| #46 | MERGED `8dcf4fc` | 1–2: worker leak, PeerFlood/akkaunt ban |
| #48 | MERGED `e92fe12` | 3–5: jamoa taklifi, bloklash manbai, sig'im |
| #49 | MERGED `d053f27` | 6–9: muddat eslatmasi, chiqishda cheksiz, kamaytirish, o'zini bloklash |

> 📌 Natija: **749 test** (62 subtest), unittest **OK**, Ruff — yangi
> xato yo'q. Baza migratsiyasi avtomatik (eski DB ma'lumotlari
> saqlanadi).

---

## 🔧 PR #50 — Inline callback xatolari (UID `6169018469`)

Server logida ikkita xato ko'ringan:

```
1) AttributeError: 'NoneType' object has no attribute 'reply_text'
2) BadRequest: Message is not modified
```

### Sabab

**1) `NoneType.reply_text`** — inline kontekstda `update.message` = `None`.
`bot/timer.py` `gint:manual` branchida `q.message.reply_text(...)` chaqirgan,
`bot/my_groups.py` `mg:manual` branchida esa `update.message.reply_text(...)`.
Inline callback'da bu ikkalasi ham `None` → `AttributeError`.

**2) `Message is not modified`** — Telegram yangi matn va klaviatura avvalgisi
bilan **bir xil** bo'lsa `BadRequest` beradi. Bu normal holat (foydalanuvchi
bir xil tugmani ikki marta bosadi), lekin kod uni xato deb hisoblab,
butun laytni sindirardi. `bot/timer.py::_show_group_interval_options()`
va `bot/my_groups.py::show_group_interval()` shu holatga tushardi.

Qo'shimcha: `bot/timer.py` `gint:back` branchida `render_groups_inline()`
`edit=False` bilan chaqirilardi — bu yana ham `update.message.reply_text`
ga olib kelardi.

### Tuzatish

**Yangi yordamchi** — `core/utils.py::edit_text_safe()`:

- `MessageIsNotModified` → jim qoldiriladi, muvaffaqiyat deb hisoblanadi;
- boshqa xatolar → logga yoziladi, lekin **yeyilmaydi** (oqim buzilmaydi);
- `query is None` → `False` qaytaradi (xato bermaslik).

`core/utils.py::reply_text_safe()` ham kuchaytirildi — endi `in_place=True`
rejimida `edit_text_safe()` orqali ishlaydi, ya'ni "not modified" xatosi
ham yutib o'tiladi.

**Qo'llangan joylar:**

| Fayl | O'zgarish |
|---|---|
| `core/utils.py` | `edit_text_safe()` qo'shildi; `reply_text_safe()` kuchaytirildi |
| `bot/timer.py` | Barcha `q.edit_message_text` → `edit_text_safe`; `q.message.reply_text` → `reply_text_safe`; `gint:back` endi `edit=True` bilan ishlaydi |
| `bot/my_groups.py` | `render_groups_inline()`, `show_group_interval()`, `mg:manual` — xavfsiz yordamchilar |
| `bot/groups.py` | `gchk:` handler va skaner natijalari — xavfsiz yordamchilar |
| `admin/admin_panel.py` | `adm:back` va `adm:teamadmins` — `reply_text_safe` |
| `bot/callbacks.py` | `ref:share` — `reply_text_safe` |

> 📌 **Telegram API o'zgarmadi** — bir xil `editMessageText` va `sendMessage`
> chaqiriladi, faqat xatolar endi oqimni sindirmaydi.
> 📌 **Tugmalar, matnlar va klaviaturalar o'zgarmadi** — faqat xato
> boshqaruvi o'zgardi.

### Tekshiruv

**Yangi test fayl** — `tests/test_callback_safe_edits.py` (16 ta test +
3 subtest):

- `edit_text_safe`: muvaffaqiyat, `None` query, "not modified" (3 ta
  variant), boshqa xato loglanadi, umumiy istisno yutib o'tiladi;
- `reply_text_safe`: inline kontekstda ishlaydi, `in_place` + "not modified";
- `gint:list`, `gint:manual`, `gint:reset`, `gint:back`;
- `mg:manual`, `render_groups_inline`, `show_group_interval`;
- `gchk:page`.

**Live-simulyatsiya** — `tests/live_sim_gint.py`: haqiqiy
`telegram.error.BadRequest` klassi bilan 6 ta oqim tekshiriladi.

**Natijalar:**

| Tekshiruv | Natija |
|---|---|
| Yangi testlar | **16 passed**, 3 subtest |
| To'liq pytest | **765 passed**, 65 subtest |
| To'liq unittest | **765 OK** |
| Ruff (baseline diff) | **bo'sh** — yangi xato yo'q |
| `compileall` + import | **OK** |
| Eski kod bilan simulyatsiya | `AttributeError` va "not modified" xatolari **takrorlandi** ✅ |
| Yangi kod bilan simulyatsiya | **6/6 oqim xatosiz** ✅ |
