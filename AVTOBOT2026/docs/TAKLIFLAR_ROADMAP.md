# 🚀 AVTOBOT2026 — Rivojlantirish takliflari va yo'l xaritasi

Sana: 2026-10-12 · Asos: `cf8eda0` (main) · Audit qilingan kod: `bot/`, `core/`, `worker/`, `admin/`, `main.py`

Ushbu hujjat uchta savolga javob beradi:

1. **Referat (referal) tizimi qanday ishlaydi, firibgarlikdan himoya bormi, to'g'ri hisoblaydimi?**
2. **E'lon beruvchi bir nechta surat (albom) qo'sha oladimi?**
3. **Botni keng imkoniyatli, tushunarli va daromadli qilish uchun aniq takliflar ro'yxati.**

---

## 0. QISQA XULOSA — eng muhim 10 ta harakat

| # | Harakat | Ta'sir | Mehnat |
| - | ------- | ------ | ------ |
| 1 | Ko'p surat (albom, 2–10 ta) + video/dokument qo'llab-quvvatlash | ⭐⭐⭐ eng ko'p so'raladigan funksiya | 2–3 kun |
| 2 | Referalga **haqiqiy mukofot** (bonus kun) + anti-fraud qoidalari | ⭐⭐⭐ o'sish dvigateli | 2–3 kun |
| 3 | Referal hisobidagi 4 ta nuqsonni tuzatish (quyida 1.5) | ⭐⭐ ishonch | 0.5 kun |
| 4 | Yuborish statistikasi (`send_logs`) — hozir umuman yo'q | ⭐⭐⭐ sotuv argumenti + nazorat | 1–2 kun |
| 5 | Guruhlar soni bo'yicha **tarif paketlari** (hozir cheksiz → daromad boy berilmoqda) | ⭐⭐⭐ daromad | 2 kun |
| 6 | Kunlik yuborish limiti + "tungi tanaffus" (akkaunt ban xavfini kamaytirish) | ⭐⭐⭐ xavfsizlik | 1 kun |
| 7 | `/help` + birinchi kirishda 4 qadamli yo'riqnoma + "🧪 Sinov yuborish" | ⭐⭐ konversiya | 1 kun |
| 8 | Postni tahrirlash (`db.update_post` tayyor, ishlatilmayapti) | ⭐⭐ UX | 0.5 kun |
| 9 | Postga inline tugma (📞 Bog'lanish / 🌐 Sayt) + link preview sozlamasi | ⭐⭐ e'lon sifati | 1 kun |
| 10 | Tez tasdiqlash (risk ball past bo'lsa avto-approve) — admin kutishidagi "drop" | ⭐⭐⭐ konversiya | 1–2 kun |

> 💡 Bonus: `check_group_access()` (`bot/groups.py:188`) va `POSTS_LIMIT`
> (`bot/texts.py:541`) **allaqachon yozilgan, lekin hech qayerdan chaqirilmaydi** —
> ularni "yoqish" bir kundan kam vaqat oladi (3-bo'lim, P0.10–P0.11).

## 0.1 AMALGA OSHIRISH HOLATI (2026-10-12)

Yuqoridagi 10 ta harakat va **P0** ro'yxatidagi barcha bandlar kodda bor.
Testlar: `tests/test_album_media.py`, `tests/test_plans_limits_stats.py`,
`tests/test_referral_bonus.py`, `tests/test_post_tools_and_checks.py`
(230 ta test, hammasi o'tadi).

| Band | Holat | Qayerda amalga oshirilgan |
| ---- | ----- | ------------------------- |
| 1 / P0.1 — albom, video, hujjat | ✅ | `bot/media_ingest.py` (yuklash, filter, limit), `bot/posts.py` (albom yig'ish + debounce + `✅ Tayyor` tugmasi), `core/database.py` (`posts.media` JSON, `photo` ustuni bilan sinxron), `worker/worker.py` (`send_file([...])`) |
| 2 / P0.6 — referal mukofoti | ✅ | `bot/referral.py::maybe_grant_referral_bonus` (faqat haqiqiy faollikdan keyin), `db.grant_referral_bonus` (oylik cap), `worker` hook |
| 3 / 1.5 — referal nuqsonlari | ✅ | hisobdan chiqarish (`revoke_referral`), blokdan chiqqach qayta hisob (`pending_referrals_of` + unblock hooki), nomlar niqobi (`get_referrals`), anomaliya signali (`_flag_anomaly`) |
| 4 / P0.3 — yuborish statistikasi | ✅ | `send_logs` jadvali, `db.log_send/send_stats/group_health/global_send_stats/next_send_eta/prune_send_logs`, `📈 Hisobot` ekrani (`bot/menu.py::show_report`) |
| 5 / P0.4 — paketlar va guruh limiti | ✅ | `config.PLAN_DEFS` (SINOV/START/PRO/BUSINESS), `users.max_groups/max_posts/daily_limit/active_hours`, `db.set_plan`, `add_chat`/`add_post` da atomik limit tekshiruvi, `📦 Paket va limitlar` ekrani |
| 6 / P0.5 — kunlik limit + tungi tanaffus | ✅ | `worker.posting_window_state` (oyna tashqarisida va limit tugaganda kutadi, navbat buzilmaydi) |
| 7 / P0.8, P0.9 — `/help`, onboarding, sinov yuborish | ✅ | `main.cmd_help`, `main.cmd_status`, `T.HELP_TEXT`, `telegram` menyu buyruqlari; `🧪 Sinov` → bitta guruhga token bilan tasdiqlangan bir marta yuborish; `👁 Ko'rinish` — shaxsiy chatga preview |
| 8 / P0.2 — postni tahrirlash | ✅ | `✏️ Tahrirlash` → post tanlagich → `posts._save_post(mode="edit")` → `db.update_post` (media yangilanmasa eski media saqlanadi) |
| 9 / P1.4 — link preview | ✅ | `lp:toggle:<post_id>` + `db.set_post_link_preview`, worker `link_preview=` bilan yuboradi |
| 10 / P0.7 — tez tasdiqlash | ✅ (standart o'chirilgan) | `admin/auto_approve.py`: `AUTO_APPROVE_ENABLED=1` bo'lsa, risk ≤ `AUTO_APPROVE_MAX_RISK` va sessiya UID-bindingi tekshirilgan arizalar tasdiqlanadi; har biri adminga xabar qilinadi |
| P0.10 — 🔎 guruhni tekshirish | ✅ | `💬 Guruhlar → 🔎 Guruhni tekshirish` → `gchk:` oynasi (`check_group_access` endi ishlatiladi), sabablar: `not_member/no_write/private/not_found/flood/timeout/invalid` |
| P0.11 — yoqilmagan cheklovlar | ✅ | `POSTS_LIMIT` endi `add_post` limiti orqali ishlaydi; `MAX_MEDIA_FILES_PER_USER` (media kvotasi) ham qo'shildi |
| P1.3 / P1.8 / P1.9 — qisman | ✅ | post rotatsiyasi endi guruh bo'yicha; `{sana} {vaqt} {kun}` va `{A\|B}` shablonlari har yuborishda qayta hisoblanadi; tanlagichlar sahifalanadi (`:page:`) |
| P1.5 — guruh salomatligi | ✅ | `db.group_health` + `📈 Hisobot`da "⚠️ N ta guruhda oxirgi urinish xato"; o'chirilganda "🔎 Tekshirish" maslahati |
| P1.1, P1.2, P1.6, P1.7 (to'lov, ko'p akkaunt, kampaniya havolalari, admin grafik) | ⏳ | keyingi bosqich — bu bosqichda ataylab qoldirildi |

Qo'shimcha tuzatishlar (yuqorida rejalashtirilmagan, lekin topilgan):

- `KB.kb_referral` PTB 21.x'da yo'q bo'lgan `switch_pm_text` bilan
  qurulayotgan edi (RunTimeError) — `ref:share` callback'iga almashtirildi;
- post tanlagich callback shakli (`ped:<id>:<page>`) dispatcher tomonidan
  tushunilmas edi — `pvw:id:<id>:<page>` bilan birga qabul qilinadi;
- `handle_test_send_confirm` ichida `user_operation_lock` qayta olinayotgan
  edi (o'lik tugun) — olib tashlandi;
- `posts._send_single` fayl tutqichini yopmas edi — `with open(...)` qilindi;
- kiritish oynasida menyu tugmasi bosilanda mavjud bo'lmagan
  `Menu.handle_menu` chaqirilayotgan edi — `route_menu_button`ga o'zgartirildi.

Chiqarish tartibi va tekshirish ro'yxati alohida hujjatda:
[`YANGILASH.md`](YANGILASH.md). Eski baza bilan migratsiya
`tests/test_legacy_db_migration.py`da qoplangan.

Migratsiya: barcha yangi ustunlar (`users.*`, `posts.media`, `posts.link_preview`,
`referrals.qualified_at/bonus_days/revoked`, guruh navbat ustunlari)
`_migrate_schema` orqali qo'shiladi — eski `.db` fayli bilan ham ishga tushadi,
yangi jadval `send_logs` esa `init_db` ichida yaratiladi.

---

---

## 1. REFERAT (REFERAL) TIZIMI — TO'LIQ AUDIT

### 1.1 Hozir qanday ishlaydi (zanjir va kod manzillari)

```
👤 Foydalanuvchi A:  👥 Referal  →  https://t.me/{BOT_USERNAME}?start=ref_{A_uid}
                                     (bot/referral.py:29)

👤 Yangi B bosadi   →  main.py cmd_start()  →  register_referral(uid, "ref_A")
                                     (bot/referral.py:50)

   ├─ self-refer tekshiruvi (referrer_uid == uid → rad)
   ├─ B allaqachon mavjud user bo'lsa → rad
   └─ db.set_referrer(B, A)                          (core/database.py:859)
        ├─ A mavjud, is_admin = 1 (tasdiqlangan) va is_blocked = 0 bo'lishi shart
        ├─ B da referrer_uid NULL, is_admin = 0, is_blocked = 0 bo'lishi shart
        └─ `users.referrer_uid` + `referrals(referrer_uid, referred_uid)` atomar yoziladi

🛡 Admin Approve    →  admin/admin_actions.py:1430/1455 → _count_approval_referral
                    →  on_referral_counted (bot/referral.py:89)
                    →  db.try_count_referral(B)              (core/database.py:903)
                         ├─ B: is_admin = 1, referral_counted = 0
                         ├─ A: is_admin = 1, is_blocked = 0
                         ├─ referrals.counted = 1
                         └─ users.referral_counted = 1   →  A ga "🎉 referalingiz faollashdi"

📊 Ko'rsatish       →  count_referrals(A) = COUNT(counted = 1)   (core/database.py:943)
                       👥 Referal menyusi: havola + ✅ hisoblanganlar soni + ✅/⏳ ro'yxat
```

**To'g'ri qilingan ishlar (buni saqlang):** barcha yozuvlar `_write_lock` bilan atomar,
`referrals(referred_uid)` UNIQUE, telefon raqami UNIQUE indeks (`idx_users_phone_unique`),
kod so'rovi 3/soat, login 3/soat, pending sessiya Fernet bilan shifrlangan, admin qo'lda tasdiqlaydi.

### 1.2 Amaliy sinov natijalari (real bazada, vaqtinchalik DB)

Referal zanjirini 10 ta ssenariyda ishga tushirib tekshirdim (`set_referrer` → `approve_user` → `try_count_referral`):

| # | Ssenariy | Natija | Baho |
| - | -------- | ------ | ---- |
| 1 | O'zini o'zi taklif qilish (`A → A`) | rad etildi | ✅ |
| 2 | Mavjud bo'lmagan / tasdiqlanmagan referrer | rad etildi | ✅ |
| 3 | Oddiy holat: A tasdiqlangan, B yangi → B tasdiqlandi | `count = 1` | ✅ |
| 4 | Bitta juftlikni ikki marta bog'lash | 2-marta rad | ✅ |
| 5 | B qayta tasdiqlanganda (re-approve) | qayta hisoblanmadi | ✅ |
| 6 | **A bloklangan paytda B tasdiqlansa** | hisoblanmadi **va A blokdan chiqsa ham hech qachon hisoblanmaydi** | ❌ **nuqson** |
| 7 | **B (taklif qilingan) keyin firibgarlik uchun bloklansa** | A ning hisobi o'sha holicha qoladi (bekor bo'lmaydi) | ❌ **nuqson** |
| 8 | B butunlay o'chirilsa (`delete_user`) | cascade — hisob kamaydi | ✅ |
| 9 | Rad etilgan / tasdiqlanmagan referal | abadiy "⏳" bo'lib qoladi, tozalanmaydi | ⚠️ **tozalash yo'q** |
| 10 | `get_referrals` referrerga taklif qilinganlarning **ismi**ni ko'rsatadi | shaxsiy ma'lumot oqishi (kichik) | ⚠️ |

### 1.3 Xulosa: to'g'ri hisoblaydimi?

> **Ha — hisoblash mantig'i to'g'ri.** Ikki marta hisoblash, o'zini taklif qilish, mavjud
> foydalanuvchini "yopishtirish" va tasdiqlanmagan referrerdan foydalanishning barchasi to'g'ri
> bloklangan. Atomarlik (`_write_lock` + `rowcount` tekshiruvi) joyida.
>
> **Lekin 3 ta haqiqiy nuqson bor** (6, 7, 9-scenariylar) va **mukofot mexanizmi umuman yo'q** —
> referal soni shunchaki ko'rsatkich, u foydalanuvchiga hech narsa bermaydi. Mukofot qo'shilgach,
> hozirgi himoya yetarli bo'lmaydi (1.4-band).

### 1.4 Firibgarlikdan himoya: bor / yo'q

| Himoya | Holati | Izoh |
| ------ | ------ | ---- |
| O'zini taklif qilish (`uid == referrer_uid`) | ✅ bor | `bot/referral.py:70`, `db.set_referrer` |
| Faqat tasdiqlangan referrer (`is_admin=1, is_blocked=0`) | ✅ bor | `core/database.py:869` |
| Bir martalik hisoblash (`referral_counted`, `counted`) | ✅ bor | `core/database.py:903` |
| Bitta telefon = bitta UID (UNIQUE indeks) | ✅ bor | `_migrate_schema()` |
| Har bir yangi akkauntni **admin qo'lda tasdiqlashi** | ✅ bor | eng kuchli filtr — hozir asosiy himoya shu |
| Login/kod rate limitlari (3/soat) | ✅ bor | `core/rate_limit.py`, `bot/login.py` |
| **Mukofot olish uchun faollik sharti** (kamida 1 ta guruh + 1 marta start) | ❌ yo'q | tasdiq bilanoq hisoblanadi |
| **Clawback** — firibgar topilsa hisobni bekor qilish | ❌ yo'q | bloklansa ham hisob qoladi |
| **Kunlik/haftalik referal limiti** (anomaliya: 1 kunda 30 ta) | ❌ yo'q | admin hech narsa ko'rmaydi |
| **Yangi/bo'sh akkaunt risk skori** (username yo'q, avatar yo'q, akkaunt yoshi) | ❌ yo'q | `get_me()` natijasini saqlash kerak |
| Telefon prefiksi bo'yicha klasterlash (virtual raqamlar) | ❌ yo'q | oddiy SQL bilan amalga oshirish mumkin |
| **Qayta hisoblash (reconcile)** — vaqtincha blok tufayli yo'qolgan referal | ❌ yo'q | 6-senariy |
| Kampaniya/manba havolalari (`?start=src_<kod>`) | ❌ yo'q | qaysi kanal ishlagani noma'lum |
| Referal statistikasi (admin panelda) | ⚠️ zaif | faqat bitta son: `admin_actions.py:1657` |

**Muhim:** hozir referal hech qanday mukofot bermagani uchun firibgarlik motivida ham
past. Mukofot (bonus kun) qo'shsangiz — yuqoridagi 7 ta "yo'q" bandini **birga** qo'shish shart.

### 1.5 Tuzatishlar — tayyor kod parchalari

**(a) Blok tufayli yo'qolgan referalni qayta hisoblash** (`core/database.py` ga qo'shish):

```python
async def reconcile_referral(uid: int) -> int | None:
    """Shartlar bajarilganda hisoblanmagan referalni keyinchalik hisoblaydi.

    Blokdan chiqarish, qayta tasdiqlash yoki referrer faollashganda chaqiriladi.
    """
    return await try_count_referral(uid)
```

Chaqiruv nuqtalari: admin "Blokdan chiqarish" (`admin_actions.py` `unblock:`) va
`approve_user` dan keyin. `try_count_referral` o'zi idempotent — xavfsiz.

**(b) Firibgar aniqlanganda hisobni bekor qilish (clawback):**

```python
async def revoke_referral(uid: int) -> bool:
    """Taklif qilingan user bloklansa/ochirilsa referal bonusini bekor qiladi."""
    cur = await _execute_write(
        "UPDATE referrals SET counted = 0 WHERE referred_uid = ? AND counted = 1",
        (uid,),
    )
    return cur.rowcount > 0
```

`referrals.counted` — yagona hisob manbai bo'lgani uchun (`count_referrals` shu bo'yicha
sanaydi) bu bitta UPDATE yetarli. `users.referral_counted = 1` qoldiriladi: qayta
hisoblanishining oldini oladi. Admin panelga "↩️ Referalni bekor qilish" tugmasi qo'shing.

**(c) Faollik sharti (mukofot faqat haqiqiy foydalanuvchi uchun):**

```python
async def is_referral_qualified(uid: int) -> bool:
    """Kamida 1 ta guruh + 1 ta post + 1 marta muvaffaqiyatli yuborish."""
    chats = await get_chats(uid)
    posts = await get_posts(uid)
    sent = await count_sent_messages(uid)      # 4-banddagi send_logs jadvalidan
    return bool(chats) and bool(posts) and sent > 0
```

Mukofot berish ketma-ketligi: `approve` → `referrals.counted = 1` (ko'rsatkich) →
**faollik sharti bajarilganda** `bonus_granted = 1` + referrerga kun qo'shish.

**(d) Anomaliya signali** (admin panel + log):

```python
# Kunlik 10 tadan ortiq yangi referal → adminga ogohlantirish
if await db.count_referrals_today(referrer) > REFERRAL_DAILY_ALERT:   # =10
    await application.bot.send_message(SUPER_ADMIN, f"⚠️ Referal anomaliyasi: {referrer}")
```

### 1.6 Referalni daromad dvigateliga aylantirish

Hozir: **referal → hech narsa.** Tavsiya (bosqichli, sinab ko'rish oson):

| Variant | Mexanika | Afzallik | Kamchilik |
| ------- | -------- | -------- | --------- |
| **A. Bonus kun** ⭐ tavsiya | Har bir faol referal: **+3 kun**; 5 ta: +20 kun; 10 ta: **1 oy bepul** | sizga deyarli bepul (marjinal xarajat ~0), o'z-o'zini oqlaydi | firibgarlikni boshqarish kerak |
| B. Pul komissiyasi | Har bir to'lovchi referal uchun 10–20% | jozibador | naqd hisob-kitob, soliq, ishonch |
| C. Paket yangilash | 3 ta referal → PRO ga 7 kun | paketlarni targ'ib qiladi | sekin |
| D. Reyting/tanlov | Oyda top-3 referrerga PRO bepul | arzon, shov-shuv | vaqtinchalik effekt |

**Tavsiya: A + D.** Referal menyusiga aniq "narx" yozing:
`1 ta do'st = +3 kun · 10 ta do'st = 1 oy bepul · oyning top-3 = PRO bepul`.
Buning uchun `⏰ Tarif muddati` mantiqidan farqli, **qo'shib boruvchi** alohida funksiya kerak
(`add_bonus_days()` — mavjud `give_new_term()` muddatni bekor qiladi, uni ishlatmang).

---

## 2. KO'P SURAT (ALBOM) — hozir YO'Q, texnik reja

### 2.1 Muammo (kodda aniq)

- `main.py:1150` — handler faqat `filters.TEXT | filters.PHOTO`. **Video, dokument, albom qabul qilinmaydi.**
- `core/database.py:177` — `posts.photo` **bitta** ustun: bitta post = bitta rasm.
- `worker/worker.py:144` — `send_post()` faqat bitta fayl yuboradi (`client.send_file`).
- **Bugungi xatti-harakat:** foydalanuvchi 3 ta rasmni albom qilib yuborsa → birinchisi saqlanadi,
  state o'chadi (`user_states.pop`), qolgan 2 tasi "Noma'lum buyruq" javobiga tushadi.
  Foydalanuvchi nima bo'lganini tushunmaydi — **eng katta UX muammosi.**

### 2.2 Yechim rejasi (4 qadam)

**1) Baza — migratsiya (eski postlar buzilmaydi):**

```python
# core/database.py → _migrate_schema()
("media", "TEXT"),   # JSON: [{"path": "...", "kind": "photo"|"video"|"doc"}]
```

`_decode_post()` ichida: `media` bo'sh bo'lsa, eski `photo` dan ro'yxat yasab qo'yish
(backward compatibility — hech narsa migratsiya qilish shart emas).

**2) Handler — albomni yig'ish (PTB da albom alohida update bo'lib keladi):**

```python
# bot/posts.py
PENDING_ALBUMS: dict[tuple[int, str], dict] = {}
ALBUM_DEBOUNCE_S = 1.2
MAX_ALBUM_FILES = 10          # Telegram albom limiti

async def handle_add_post(update: Update) -> None:
    uid, msg = update.effective_user.id, update.message
    gid = msg.media_group_id
    if gid is None:                       # bitta rasm/matn — hozirgidek
        await _save_post(uid, [msg]); return
    key = (uid, gid)
    entry = PENDING_ALBUMS.setdefault(key, {"msgs": [], "task": None})
    entry["msgs"].append(msg)
    if entry["task"] is None:
        entry["task"] = asyncio.create_task(_flush_album(key))   # 1.2 s kutib yig'adi
```

`main.py:1150` filtrini kengaytiring:
`filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL`

**3) Worker — albom yuborish** (`worker/worker.py:144 send_post`):

```python
files = post.get("media") or ([post["photo"]] if post.get("photo") else [])
files = [m["path"] if isinstance(m, dict) else m for m in files]
files = [f for f in files if f and os.path.exists(f)]

if len(files) > 1:
    await client.send_file(target, files[:10], caption=text,
                           formatting_entities=entities or None)   # bitta xabar — albom
elif len(files) == 1:
    await client.send_file(target, files[0], caption=text,
                           formatting_entities=entities or None)
else:
    await client.send_message(target, text, formatting_entities=entities or None,
                              link_preview=post.get("link_preview", True))
```

Telethon `send_file()` ro'yxat qabul qiladi va uni **bitta albom** qilib yuboradi —
alohida-alohida 10 ta xabar emas (spam xavfi yo'qoladi).

**4) UX matni** — `➕ Post qo'shish`:

> 📸 **Bir nechta rasm yuboring:** 2–10 ta rasmni albom qilib yuboring, matnni (caption)
> oxirgi rasmga yozing. Video va fayl ham qo'llab-quvvatlanadi.
> Yakunlash uchun **✅ Tayyor** tugmasini bosing.

Natija: e'lon beruvchi "mashina 5 ta rasm bilan" degan haqiqiy e'lonni bitta xabarda
joylashtira oladi — bu sizning maqsadli auditoriyangiz (avto e'lonlar) uchun eng kritik funksiya.

---

## 3. IMKONIYATLARNI KENGAYTIRISH — ustuvor ro'yxat

### 🔴 P0 — 1–2 hafta (daromad va xavfsizlikka bevosita ta'sir)

| # | Taklif | Nima uchun | Qanday (kod nuqtasi) |
| - | ------ | ---------- | -------------------- |
| P0.1 | **Albom + video + hujjat** (2-band) | E'lon beruvchining asosiy talabi | yuqorida |
| P0.2 | **Postni tahrirlash** | `db.update_post()` tayyor, chaqirilmayapti (faqat o'chirish + qayta yozish) | `✏️ Tahrirlash` tugmasi → `db.update_post()` |
| P0.3 | **Yuborish statistikasi** — `send_logs(uid, group_id, post_id, ts, ok, error)` | Hozir **hech qanday** statistika yo'q: necha marta yuborildi, qaysi guruh ishladi — faqat logda. Bu ham sotuv argumenti, ham firibgarlikni aniqlash vositasi | `worker.py` `record_chat_attempt` yoniga yozuv; `📈 Hisobot` menyusi |
| P0.4 | **Guruhlar soni limiti + paketlar** | Hozir **cheksiz**: bir odam 300 ta guruh qo'shib server va o'z akkauntini yo'q qilishi mumkin. Limit = daromad + barqarorlik | `users.max_groups` ustuni, `add_chat` da tekshirish |
| P0.5 | **Kunlik yuborish limiti + tungi tanaffus** | Eng katta xavf: 5 daqiqa interval × 100 guruh = soatiga 12 ta xabar/akkaunt → Telegram **akkauntni cheklaydi**. Foydalanuvchi "bot ishlamayapti" deb ketadi | `users.daily_limit`, `users.active_hours` (standart 08:00–23:00), worker da tekshiruv |
| P0.6 | **Referal mukofoti + anti-fraud** (1.4–1.6) | O'sish | yuqorida |
| P0.7 | **Tez tasdiqlash (auto-approve)** | Hozir har bir ariza admin qo'lidan o'tadi — foydalanuvchi kutib qolib **ketadi**. Risk ball past (QR login, username bor, eski akkaunt) bo'lsa darhol tasdiqlash, admin keyin bekor qilishi mumkin | `admin_actions.approve*` oldidan `risk_score()` |
| P0.8 | `/help` + **onboarding** | Botda `/help` umuman yo'q; yangi odam ism→telefon→kod→kutish zanjirida nima bo'layotganini bilmaydi | `CommandHandler("help")` + birinchi kirishda 4 qadamli yo'riqnoma |
| P0.9 | **🧪 Sinov yuborish** | Foydalanuvchi e'lon guruhlarga qanday chiqishini oldindan ko'rishi kerak | 1 ta tanlangan guruhga bir marta yuborish yoki shaxsiy chatga preview |
| P0.10 | **🔎 "Guruhni tekshirish" tugmasi** | `check_group_access()` (`bot/groups.py:188`) **to'liq yozilgan**: a'zolik, yozish huquqi, xato sababi (`not_member`, `no_write`, `private`, `flood`…) — lekin uni **bot menyusi Hech QAERDAN chaqirmaydi**, faqat testlar. Shu sababli foydalanuvchi "bot ishlamayapti" deb shikoyat qiladi, aslida u guruhga a'zo emas | `💬 Guruhlar → 🔎 Tekshirish` da chaqirish; qo'shganda bir marta ogohlantirish |
| P0.11 | **Tayyor, lekin yoqilmagan cheklovlar** | `POSTS_LIMIT` matni (`bot/texts.py:541`) yozilgan, ammo **hech qayerda ishlatilmaydi** — post limiti yo'q. `users.max_groups` umunan mavjud emas | `add_post`/`add_chat` da tarif limitini tekshirish |

### 🟡 P1 — 2–6 hafta

| # | Taklif | Izoh |
| - | ------ | ---- |
| P1.1 | **To'lov tizimi** (Payme/Click/Uzcard yoki crypto) + avto-uzaytirish + to'lov eslatmasi | Hozir faqat qo'lda: `ADMIN_CONTACT_PHONE`ga yozish. Avtomatlashtirilmasa daromad chiziqli o'smaydi |
| P1.2 | **Bir hisobga bir nechta Telegram akkaunt** (2–5 ta) | Agentliklar va yirik e'lonchilar uchun eng kuchli xususiyat; ular eng ko'p to'laydigan segment |
| P1.3 | **Post rejalashtirish**: hafta kunlari, faqat ish soatlari, post aylanishi tartibi (navbat / tasodifiy / har guruhga alohida post), postning "amal qilish muddati" (N marta yuborilgach o'chish) | Hozir faqat oddiy `post_index % len(posts)` |
| P1.4 | **Inline tugmalar** post ostiga (📞 Bog'lanish / 🌐 Sayt / 💬 Kanal) + link preview sozlamasi | E'lon uchun konversiyani oshiradi; `link_preview` kodi allaqachon bor, foydalanuvchi sozlay olmaydi |
| P1.5 | **Guruh salomatligi paneli**: har guruh bo'yicha ✅/❌, oxirgi yuborish vaqti, xato sababi, "qayta ulash" | Hozir guruh 3 marta xatodan keyin jimgina o'chiriladi (`MAX_GROUP_FAILS`) — foydalanuvchi faqat xabardan biladi |
| P1.6 | **Kampaniya havolalari** `?start=src_<kod>` — qaysi kanal/guruh/reklama olib keldi | Referal bilan bir xil mexanika, alohida `sources` jadvali. Marketingsiz o'sish bo'lmaydi |
| P1.7 | Admin panelga **anti-fraud va kunlik grafik**: kunlik yuborishlar, top userlar, "xavfli" userlar (ko'p guruh + ko'p xato + ko'p referal) | Hozir statistika faqat 7 ta son (`db.get_stats()`) |
| P1.8 | **Spintaks/placeholder**: `{vaqt}`, `{sana}`, `{kun}` avtomatik almashtirish | E'lonlar "eski" ko'rinmasligi uchun; bir post turli ko'rinishda chiqadi |
| P1.9 | **Postlar ro'yxatini sahifalash** (hozir uzun ro'yxat bir necha xabarga bo'linadi) | 50 ta post bo'lganda juda noqulay |

### 🟢 P2 — 2–3 oy (strategik)

| # | Taklif | Izoh |
| - | ------ | ---- |
| P2.1 | **Guruhlar bozori (ikki tomonlama model)** ⭐ | Foydalanuvchilar o'z guruhlarini "e'lon maydoni" sifatida taklif qiladi, boshqalar shu guruhlarga post yuboradi (pullik). Bu sizni **bot sotuvchisidan platformaga** aylantiradi — daromad keskin o'sadi |
| P2.2 | **Ko'p tilli interfeys** (o'zbek / rus / ingliz) | `bot/texts.py` ni til fayllariga ajratish; MDH bozori = auditoriya ×3 |
| P2.3 | **Web kabineti** (aiohttp — health server allaqachon mavjud) | Guruh/post boshqarish, statistika grafiklari, to'lov. Telefonda post yozish noqulay |
| P2.4 | **Reseller/sherik paneli** (20–30% komissiya) | Agentliklar o'z mijozlarini olib keladi — sotuv armiyasi |
| P2.5 | **Adaptive anti-ban**: FloodWait/xato bo'yicha interval avtomatik oshadi | Hozir faqat ±5 daqiqa jitter; aqlli sekinlashuv akkaunt umrini uzaytiradi |
| P2.6 | AI yordamchisi: matnni formatlash, tavsiya etilgan yuborish vaqti, guruh mavzusiga mos post tanlash | Farqlovchi xususiyat |

---

## 4. FOYDALANUVCHI UCHUN TUSHUNARLI VA QULAY QILISH (UX)

Kodni o'qib chiqqandan keyingi eng muhim kuzatuv: **bot ishonchli va xavfsiz yozilgan,
lekin "insoniy" tomoni yetishmaydi.**

1. **Birinchi 60 soniya.** Yangi odam: ism → telefon → kod → "⏳ Tasdiq kutilmoqda..." →
   admin kelguncha **javobsiz kutadi**. Bu eng katta yo'qotish nuqtasi.
   → avto-approve (P0.7), kutish vaqtida "odatda 5–30 daqiqa" + nima qilish kerakligi haqida matn.
2. **Har bir ekranda bitta savol + namuna.** Masalan, interval so'rashda:
   `⏱ Necha daqiqada bir yuborilsin? (5–10080)\nMasalan: 60` — hozir shunchaki so'rov.
3. **Holat doim ko'rinib tursin.** `📊 Status` ga qo'shing: `✅ Bugun yuborildi: 42 ta ·
   ❌ Xato: 3 ta · 💬 Faol guruh: 18/20 · ⏭ Keyingi yuborish: 14:32`.
   Bu P0.3 statistikasisiz ishlamaydi.
4. **Xatolar oddiy tilda.** `ChatWriteForbiddenError` o'rniga: "Bu guruhda yozishga ruxsat
   yo'q — akkauntingizni guruhga qo'shing yoki adminlik bering." `bot/groups.py` da bunday
   matnlar bor (`_REASON_TEXT`), lekin worker tomonida yo'q.
5. **Tugma nomlarini soddalashtiring.** `⏱ Posting oralig'i` va `⏱ Guruh intervali` —
   chalkash. Tavsiya: `⏱ Umumiy oralig'` va `🎯 Guruh alohida oralig'i`.
6. **Bekor qilish har joyda bo'lsin** (hozir `⬅️ Orqaga` bor — yaxshi; uni saqlang).
7. **Bo'sh holatlar (empty state) yo'riqnoma bilan.** "Guruhlar yo'q" o'rniga:
   "1-botda guruhga a'zo bo'ling → 2-havolani shu yerga yuboring".
8. **Post soni/ogohlantirish:** `⚠️ Faqat 1 ta post qo'shilgan — hamma guruhlarga bir xil
   e'lon ketadi. 2–3 ta turlicha e'lon qo'shish tavsiya etiladi.`

---

## 5. FOYDALANUVCHILARNI KO'PAYTIRISH VA DAROMADNI OSHIRISH

### 5.1 Daromad modeli — paketlar (hozir faqat "kun" sotiladi)

Bugun: admin qo'lda 1/7/30/90 kun beradi, guruh soni cheksiz, akkaunt soni 1 ta.
**Daromad yo'qotilayotgan 3 ta joy:** guruh limiti yo'q, akkaunt limiti yo'q, avto-to'lov yo'q.

| Paket | Guruhlar | Postlar | Akkaunt | Albom | Statistika | Narx (oyiga, taxminiy) |
| ----- | -------- | ------- | ------- | ----- | ---------- | ---------------------- |
| 🆓 Sinov (3 kun) | 5 | 2 | 1 | ✅ | ❌ | bepul |
| 🥉 START | 20 | 10 | 1 | ✅ | 7 kun | 49 000 so'm |
| 🥈 PRO ⭐ | 60 | cheksiz | 2 | ✅ | 30 kun | 99 000 so'm |
| 🥇 BUSINESS | 200 | cheksiz | 5 | ✅ | cheksiz + reseller | 249 000 so'm |

> Narxlar **taxminiy mos yozuvlar** — bozoringizni sinab ko'rib o'zgartiring.
> Muhim: **yillik to'lov = 10 oy narxi** (oldindan to'langan oqim) va **referal bonus kunlari**
> (1.6, variant A) birga ishlasin.

### 5.2 Foydalanuvchi olish kanallari (aniq va arzon)

1. **Referal + bonus kun** (1.6) — eng arzon kanal, o'z-o'zini moliyalashtiradi.
2. **Kampaniya havolalari** (P1.6) — qaysi kanal ishlaganini o'lchang, faqat ishlaydiganiga pul to'lang.
3. **Kontent**: 60 soniyalik "bot bilan 3 ta rasmli e'lonni 20 ta guruhga qo'yish" videosi —
   maqsadli auditoriya (avto e'lonchilar, uy-joy ijarasi, xizmatlar) guruhlarida tarqating.
4. **Guruh bozori** (P2.1) — guruh egalarini ham platformaga olib kiradi; ikki tomonlama o'sish.
5. **Sheriklik** (P2.4) — Telegram kanal adminlari va SMM agentliklariga 25% komissiya.
6. **Bepul sinovni 3 kunga qisqartiring + "birinchi to'lovda 20% chegirma"** — sinovdan
   to'lovga o'tish konversiyasini o'lchang.

### 5.3 Konversiyani o'ldiradigan narsalarni yo'qotish (hozir mavjud)

- Admin qo'lda tasdiqlash → kutish (P0.7).
- `/help` va yo'riqnoma yo'qligi (P0.8).
- Albom yo'qligi — e'lonchi 3-rasmni yo'qotib, botni "ishlamaydi" deb baholaydi (2-band).
- Kod kelmasligi (AWS IP) — README da yaxshi yozilgan, lekin foydalanuvchiga bot ichida
  **"📷 QR Login"ni birinchi o'ringa** qo'yish kerak.

---

## 6. 90 KUNLIK YO'L XARITASI

**1-hafta (barqarorlik + eng katta bo'shliq)**
- Albom/ko'p surat + video (2-band) · Post tahrirlash · `/help` + onboarding matnlari
- Referal: 1.5(a)(b) tuzatishlari

**2-hafta (o'lchash + himoya)**
- `send_logs` statistikasi + `📈 Hisobot` · Kunlik limit + tungi tanaffus
- Guruh limiti (`max_groups`) · Admin panelga kunlik grafik

**3–4-hafta (daromad)**
- Paketlar (START/PRO/BUSINESS) · Referal bonus kunlari + anti-fraud (1.4–1.6)
- Tez tasdiqlash (auto-approve, risk ball) · Kampaniya havolalari

**2-oy (kuchli foydalanuvchi)**
- To'lov tizimi + avto-uzaytirish · Ko'p akkaunt (2–5) · Post rejalashtirish + inline tugmalar
- Guruh salomatligi paneli · Spintaks

**3-oy (platforma)**
- Guruhlar bozori (P2.1) · Ko'p tillilik (uz/ru) · Web kabineti (birinchi versiya)
- Reseller paneli · Adaptive anti-ban

---

## 7. KPI VA XAVFLAR

### O'lchanadigan ko'rsatkichlar (hozir hech biri o'lchanmayapti!)

| KPI | Hozir | Maqsad (3 oy) |
| --- | ----- | ------------- |
| Ro'yxatdan o'tish → tasdiqlash konversiyasi | noma'lum | >80% |
| Tasdiqlangan user → birinchi yuborish | noma'lum | >60% |
| 30 kun ichida qayta to'lov (retention) | noma'lum | >50% |
| Har bir faol userdan o'rtacha daromad (ARPU) | noma'lum | PRO narxining 60% |
| Referal orqali kelgan yangi userlar ulushi | noma'lum | >30% |
| Muvaffaqiyatli yuborish foizi (✅/❌) | noma'lum (logda) | >95% |

> Birinchi ish: **statistika (P0.3)** — usiz qolgan barcha qarorlar taxmin bo'lib qoladi.

### Xavflar — jiddiy e'tibor bering

1. **Telegram akkauntlari bloklanishi (eng katta xavf).** 5 daqiqalik minimum interval +
   cheksiz guruh + kunlik limitsiz = foydalanuvchi akkaunti cheklanadi va u botni ayblaydi.
   → P0.5 shart. Bundan tashqari, `MIN_INTERVAL_MIN` ni 5 dan **kamida 15 daqiqaga**
   ko'tarishni jiddiy o'ylab ko'ring (sog'lom sukut: 60 daqiqa).
2. **Telegram ToS.** Avtomatlashtirilgan posting kulrang zona; shaffof foydalanish shartlari
   va foydalanuvchi roziligi (ogohlantirish matni) qo'shing.
3. **Spam shikoyatlari.** Albom + tez-tez yuborish shikoyatni oshiradi — kunlik limit va
   "guruhga alohida interval" (sizning kuchli tomoningiz) buni yumshatadi.
4. **Firibgarlik mukofot paydo bo'lgandan keyin boshlanadi** — 1.4-banddagi 7 ta himoyani
   mukofot bilan **birga** chiqaring.
5. **Yagona nuqta (single point of failure):** bitta `SUPER_ADMIN`, bitta SQLite, bitta jarayon.
   Backup (bor ✅), lekin `data/.session.key` va DB ni alohida joyda saqlang — README da yozilgan,
   unga amal qiling.

---

## 8. KEYINGI QADAM

Ushbu hujjatdagi har bir band kodga bog'langan (fayl + qator). Agar xohlasangiz,
keyingi qadamda quyidagilarni **to'liq kod + testlar bilan** yozib beraman:

1. **P0 bloki**: albom (migratsiya + handler + worker) + post tahrirlash + `send_logs` statistikasi
2. **Referal bloki**: 1.5 dagi 4 ta tuzatish + bonus kunlar + anti-fraud + `tests/test_referral_fraud.py`
3. **Paket bloki**: `max_groups` + `daily_limit` + tarif paketlari + admin panel tugmalari

Qaysi biridan boshlaymiz?
