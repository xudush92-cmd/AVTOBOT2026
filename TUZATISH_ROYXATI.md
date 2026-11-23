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
