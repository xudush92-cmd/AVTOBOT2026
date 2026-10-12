# 🤖 Bot matnlari — ro'yxatdan o'tish, qo'llanma, referal

> Manba: `bot/texts.py`. Funksiyalar namunaviy qiymatlar bilan ko'rsatilgan (masalan, ism `Ali`, havola `https://t.me/...`). Haqiqiy botda qiymatlar almashadi.


## 1. Ro'yxatdan o'tish va login

**`WELCOME_SHORT`**

```text
🤖 AVTOBOT

Telegram guruhlaringizga reklama postlarini avtomatik joylashtiruvchi bot.

📌 Boshlash (🔑 Login yoki /start):
1. Ism va familiyangizni bitta xabarda kiriting
2. Telefon raqamingizni kiriting — Telegram kodi darhol so'raladi
3. Kodni faqat botdagi RAQAMLI TUGMALAR orqali kiriting (matn qabul qilinmaydi); kerak bo'lsa 📷 QR Login yoki 2FA ishlatiladi
4. Login tugagach so'rov admin tasdig'iga tushadi
5. Admin tasdiqlagach sessiya avtomatik faollashadi — kodni qayta kiritish shart emas

📱 Yordam: +998938670592
```

**`ASK_FULL_NAME`**

```text
📋 RO'YXATDAN O'TISH (1/2)

👤 Ism va familiyangizni bitta xabarda kiriting:

Masalan: Akmal Karimov

➡️ Keyingi qadam: telefon raqami va Telegram tasdiq kodi.
```

**`FULL_NAME_INVALID`**

```text
❌ Ism va familiyani to'liq, faqat harflar bilan kiriting.

Masalan: Akmal Karimov
```

**`FULL_NAME_ACCEPTED`**

```text
✅ {full_name}

📋 RO'YXATDAN O'TISH (2/2)

📱 Telegram telefon raqamingizni yuboring:

Format: +998XXXXXXXXX
```

**`REGISTRATION_CODE_REQUEST`**

```text
✅ {phone} qabul qilindi.

🔑 Endi Telegram tasdiq kodi darhol so'raladi. Kodni botdagi RAQAMLI TUGMALAR orqali kiriting — matn ko'rinishidagi kod qabul qilinmaydi.

⏳ Login tugagach so'rovingiz admin tasdig'iga tushadi. Tasdiqdan keyin kodni QAYTA kiritish shart emas.
```

**`PHONE_INVALID`**

```text
❌ Telefon raqam noto'g'ri.

Format: +998XXXXXXXXX
Faqat raqamlar, + belgisi bilan boshlanadi.
```

**`PHONE_ACCEPTED`**

```text
📱 {phone} raqami uchun kod so'ralmoqda...

ℹ️ Telethon login kodi odatda SMSga emas, Telegram ilovasidagi rasmiy "Telegram" (777000) chatiga keladi.
```

**`PHONE_ALREADY_USED`**

```text
❌ Bu telefon boshqa AVTOBOT foydalanuvchisiga biriktirilgan.

Xato bo'lsa admin bilan bog'laning: +998938670592
```

**`CODE_TOO_SHORT`**

```text
Kamida 5 ta raqam kiriting!
```

**`CODE_TOO_LONG`**

```text
Maksimal 6 ta raqam!
```

**`CODE_EXPIRED`**

```text
⏰ Kod muddati tugadi.

Yangi kod so'ralmoqda...
```

**`CODE_CANCELLED`**

```text
❌ Login bekor qilindi.
```

**`CODE_TIMEOUT`**

```text
⏰ Login vaqti tugadi.

Qaytadan 🔑 Login bosing.
```

**`CODE_MAX_WRONG`**

```text
❌ {count} marta noto'g'ri kod kiritildi.

Qaytadan 🔑 Login bosing.

📱 Yordam: +998938670592
```

**`CODE_UNAVAILABLE`**

```text
❌ Telegram hozir tasdiq kodini bera olmadi.

Ko'p urinish bo'lgan bo'lsa bir necha soat kuting. AWS/VPS IP manzili cheklangan bo'lsa, QR Login usulidan foydalaning.
```

**`CODE_HINT_WRONG`**

```text
❌ Noto'g'ri kod ({count}/{max}). Qaytadan kiriting:
```

**`CODE_HINT_RESENT`**

```text
⏰ Yangi kod yuborildi!
Telegram ilovasidan ENG SO'NGGI kodni oling.
```

**`SMS_LIMIT_REACHED`**

```text
⚠️ Tasdiq kodini {attempts} marta so'radingiz.

Iltimos, {minutes} daqiqa kuting va qaytadan urinib ko'ring.

📱 Yordam: +998938670592
```

**`QR_PREPARING`**

```text
⏳ Xavfsiz QR Login tayyorlanmoqda...
```

**`QR_CAPTION`**

```text
📷 TELEGRAM QR LOGIN

1. Pastdagi «Telegramda tasdiqlash» tugmasini bosing; yoki
2. QR rasmni boshqa ekranda ochib, Telegram → Settings → Devices → Link Desktop Device orqali skaner qiling.

⚠️ Tasdiqlasangiz, AVTOBOT guruhlarga sizning akkauntingiz nomidan post yuborishi uchun Telegram sessiyasi yaratiladi.

⏱ QR qisqa vaqt amal qiladi.
```

**`QR_WAITING`**

```text
📷 QR tasdiqlanishi kutilmoqda.

Rasmdagi tugmani bosing yoki QR kodni Telegram Devices bo'limidan skaner qiling.
```

**`QR_EXPIRED`**

```text
⏰ QR kod muddati tugadi.

Qaytadan 🔑 Login bosing va yangi QR yarating.
```

**`QR_WRONG_ACCOUNT`**

```text
❌ Boshqa Telegram akkaunti tasdiqlandi.

Bot bilan gaplashayotgan aynan shu akkaunt orqali QR Login qiling.
```

**`QR_ERROR`**

```text
❌ QR Login yakunlanmadi.

Qaytadan 🔑 Login bosing yoki birozdan keyin urinib ko'ring.
```

**`API_CREDENTIALS_INVALID`**

```text
❌ API_ID yoki API_HASH noto'g'ri.

Bu qiymatlar BotFather'dan emas, https://my.telegram.org → API development tools bo'limidan olinishi kerak.
```

**`ASK_PASSWORD`**

```text
🔐 Hisobingizda 2FA (ikki bosqichli himoya) yoqilgan.

Iltimos, 2FA parolingizni MATN ko'rinishida yuboring.

✅ Parol DISK-ga saqlanmaydi.
```

**`PASSWORD_WRONG`**

```text
❌ Noto'g'ri parol. Qaytadan kiriting:
```

**`REGISTRATION_PENDING`**

```text
✅ Ro'yxatdan o'tish so'rovingiz qabul qilindi!

⏳ Login yakunlandi va sessiya xavfsiz saqlandi. Endi admin tasdig'i kutilmoqda — kodni qayta kiritish shart emas.

📞 Tezroq tasdiqlanish uchun: +998938670592
```

**`LOGIN_SUCCESS_PENDING`**

```text
✅ Login muvaffaqiyatli!

🔐 Sessiya xavfsiz (shifrlangan) holatda saqlandi.
⏳ Endi so'rovingiz admin tasdiqini kutmoqda.

ℹ️ Admin tasdiqlagach sessiya avtomatik faollashadi — qayta Login bosish yoki kod kiritish shart emas.

📞 Tezroq tasdiqlanish uchun: +998938670592
```

**`LOGIN_SUCCESS_APPROVED`**

```text
✅ Tizimga muvaffaqiyatli kirdingiz!

Endi guruh va post qo'shib, ▶️ Start bosishingiz mumkin.
```

**`LOGIN_ALREADY_PENDING`**

```text
⏳ So'rovingiz admin tasdiqini kutmoqda.

📱 Admin: +998938670592
```

**`LOGIN_NOT_APPROVED`**

```text
⛔ Siz hali tasdiqlanmagansiz.

📱 Admin bilan bog'laning: +998938670592
```

**`PENDING_SESSION_MISMATCH`**

```text
⚠️ Xavfsizlik tekshiruvi: so'ralgan sessiya boshqa Telegram akkauntiga tegishli bo'lgani uchun u bekor qilindi.

🔑 Iltimos, qaytadan Login qiling va kodni botdagi raqamli tugmalar orqali kiriting.

📱 Yordam: +998938670592
```

**`APPROVAL_FIRST_STEPS`**

```text


👇 Keyingi 3 qadam:
1️⃣ 💬 Guruhlar → ➕ Guruh qo'shish (har biri yangi qatorda)
2️⃣ 📝 Postlar → ➕ Post qo'shish (bir nechta rasm = bitta albom)
3️⃣ ▶️ Start — va 🔎 Tekshirish bilan guruhlar tayyorligini tekshiring

💡 To'liq yo'riqnoma: /help
```

**`USER_APPROVED`**

```text
✅ Hisobingiz tasdiqlandi!

📅 Tarif: 30 kun
⏱ Posting oralig'i: 60 daqiqa

🔑 Endi bir marta Login bosing va kodni botdagi raqamli tugmalar orqali kiriting.

👇 Keyingi 3 qadam:
1️⃣ 💬 Guruhlar → ➕ Guruh qo'shish (har biri yangi qatorda)
2️⃣ 📝 Postlar → ➕ Post qo'shish (bir nechta rasm = bitta albom)
3️⃣ ▶️ Start — va 🔎 Tekshirish bilan guruhlar tayyorligini tekshiring

💡 To'liq yo'riqnoma: /help
```

**`USER_APPROVED_ACTIVE`**

```text
✅ Hisobingiz tasdiqlandi va sessiya faollashtirildi!

📅 Tarif: 30 kun
⏱ Posting oralig'i: 60 daqiqa

ℹ️ Kodni qayta kiritish shart emas — botdan foydalanishingiz mumkin.

👇 Keyingi 3 qadam:
1️⃣ 💬 Guruhlar → ➕ Guruh qo'shish (har biri yangi qatorda)
2️⃣ 📝 Postlar → ➕ Post qo'shish (bir nechta rasm = bitta albom)
3️⃣ ▶️ Start — va 🔎 Tekshirish bilan guruhlar tayyorligini tekshiring

💡 To'liq yo'riqnoma: /help
```

**`USER_REJECTED`**

```text
❌ So'rovingiz rad etildi.

📞 Savollar uchun: +998938670592
```

**`BLOCKED`**

```text
🚫 Bot to'xtatildi.

Admin bilan bog'laning: +998938670592
```

**`code_hint_sent()`** — kod yuborilgandan keyingi izoh

```text
✅ Telegram kod so'rovini qabul qildi.
📍 Yetkazish usuli: +998 90 123 45 67

Kod 1 daqiqada kelmasa, pastdagi 📷 QR Login tugmasini bosing.
```

**`rate_limit_text()`** — urinishlar cheklanganda

```text
⏳ Juda ko'p so'rov yubordingiz.

10 daqiqa kuting va qaytadan urinib ko'ring.
```

**`numpad_text()`** — kod kiritish klaviaturasi matni

```text
🔑 TASDIQ KODI

📩 Telegramdan kelgan kodni quyidagi tugmalar orqali kiriting.

🔢 Kod:  ● ● ▪ ▪ ▪

💡 Kodni matn sifatida YOZMANG — Telegram xavfsizlik tizimi bunday kodni bekor qiladi. Faqat tugmalar orqali kiriting.
```


## 2. Qo'llanma: bot qanday ishlaydi

**`WELCOME_GUIDE`** — yangi foydalanuvchi uchun 30 soniyalik yo'riqnoma

```text
👋 Xush kelibsiz! 30 soniyada tayyor bo'lasiz:

1️⃣ 💬 Guruhlar → guruhlar ro'yxatini yukoring
2️⃣ 📝 Postlar → e'loningizni yuboring (bir nechta rasm ham bo'ladi)
3️⃣ ▶️ Start → va 🔎 bilan tekshiring

Istalgan payt 📊 Status yoki /help deb yozing.
```

**`HELP_TEXT`** — ❓ Yordam / /help

```text
🤖 AVTOBOT — QISQA YO'RIQNOMA

Bot sizning Telegram akkauntingiz orqali reklama e'lonlaringizni guruhlariga avtomatik joylashtiradi.

4 QADAM:
1️⃣ 💬 Guruhlar → ➕ Guruh qo'shish — @username yoki t.me havolalarini (har biri yangi qatorda) yuboring. Akkauntingiz o'sha guruhlarda bo'lishi va yozish huquqiga ega bo'lishi kerak.
2️⃣ 📝 Postlar → ➕ Post qo'shish — matn, rasm, video yoki 10 tagacha rasmni albom qilib yuboring.
3️⃣ ⏱ Posting oralig'i — nechada bir yuborilsin (5 dan 7 kungacha daqiqa). Har bir guruhga alohida: 💬 Guruhlar → ⏱ Guruh intervali.
4️⃣ ▶️ Start — va 🔎 Tekshirish bilan guruhlar tayyorligini tasdiqlang.

📈 Hisobot — necha marta yuborilgani, xatolar va keyingi navbat.
👥 Referal — do'stingizni taklif qiling: har bir faol do'st +15 kun tarif.
🧪 Sinov yuborish — bitta guruhga bir marta, to'liq rejimni yoqmasdan.

⚠️ Muhim:
• Bot guruhga o'zi kirmaydi — avval akkauntingiz a'zo bo'lsin.
• Juda tez oraliq + ko'p guruh Telegram tomonidan cheklovga olib keladi; kunlik limit va tungi tanaffus sizni himoya qiladi.
• Sessiyangiz faqat shifrlangan holda saqlanadi, hech kimga ko'rsatilmaydi.

📱 Yordam: +998938670592
```

**`START_CONFIRM`** — ▶️ Start tasdiqlash

```text
▶️ Postingni boshlaymizmi?

💬 {groups} ta guruhga
📝 {posts} ta postdan navbatma-navbat
⏰ Umumiy interval: taxminan {interval} daqiqa.
Alohida sozlangan guruhlar o'z intervalida ishlaydi.
ℹ️ Anti-spam uchun 5 daqiqagacha tasodifiy farq bo'lishi mumkin.
```

**`START_NO_GROUPS`**

```text
❌ Avval ➕ Guruh qo'shing.
```

**`START_NO_POSTS`**

```text
❌ Avval 📝 Post qo'shing.
```

**`START_ALREADY`**

```text
⚠️ Allaqachon ishlamoqda.
```

**`START_DONE`**

```text
✅ Posting boshlandi!

💬 {groups} ta guruh
📝 {posts} ta post
⏰ Umumiy interval: taxminan {interval} daqiqa
Alohida sozlangan guruhlar o'z intervalida ishlaydi.
ℹ️ Anti-spam farqi: 5 daqiqagacha
```

**`START_BUSY`**

```text
⚠️ Tizim band. Bir oz kuting va qaytadan urinib ko'ring.
```

**`STOP_CONFIRM`**

```text
⛔ Postingni to'xtatasizmi?
```

**`STOP_NOT_RUNNING`**

```text
⚠️ Hozir ishlamayapti.
```

**`STOP_DONE`**

```text
⛔ Posting to'xtatildi.
```

**`GROUPS_EMPTY`**

```text
❌ Guruhlar yo'q. ➕ Guruh qo'shish orqali qo'shing.
```

**`POSTS_EMPTY`**

```text
❌ Postlar yo'q. 📝 Post qo'shish orqali qo'shing.
```

**`ASK_ADD_GROUP`**

```text
➕ GURUH QO'SHISH

Bir yoki bir nechta guruhni yuboring — har biri YANGI QATORDA.
Qo'shishda faqat havola/ID formati tekshiriladi, Telegram'ga ulanilmaydi. Post yuborish uchun akkaunt guruhga a'zo va yozish huquqiga ega bo'lishi kerak; bot avtomatik kirmaydi.

Qabul qilinadi:
@guruh_username
https://t.me/guruh_username
https://t.me/guruh_username/123
https://t.me/+private_invite
https://t.me/c/1234567890/123
-1001234567890
```

**`ASK_ADD_POST`**

```text
✍️ REKLAMA POSTINI YUBORING

1️⃣ Faqat matn (formatlash bilan — bold, italic, link saqlanadi)
2️⃣ Bitta rasm / video / fayl (caption bilan yoki sansiz)
3️⃣ 10 TAGACHA RASMNI ALBOM QILIB YUBORING

💡 Ko'p suratli e'lon: rasmlarni birga (album) tanlab, matnni caption
   qilib yozing yoki rasmdan keyin alohida xabar qiling.
   Yakunlash uchun ✅ «Tayyor» tugmasi yoki biroz kutish kifoya.

🔤 Ixtiyoriy shablonlar (har yuborishda yangilanadi):
   {sana} → 12.10.2026 · {vaqt} → 14:05 · {kun} → Shanba
   {Yangi|Ajoyib|Darhol} → tasodifiy variant (spam-ga o'xshamasligi uchun)
```

**`ASK_DEL_GROUP`**

```text
➖ O'chirish uchun guruhni tanlang:
```

**`ASK_DEL_POST`**

```text
🗑 O'chirish uchun postni tanlang:
```

**`POST_EMPTY_ERROR`**

```text
❌ Bo'sh post qabul qilinmaydi.
Matn yoki rasm yuboring.
```

**`POST_PHOTO_ERROR`**

```text
❌ Rasmni saqlab bo'lmadi. Qaytadan urinib ko'ring.
```

**`GROUPS_EMPTY_HINT`**

```text
❌ Guruhlar yo'q.

1️⃣ Akkauntingiz guruhga a'zo bo'lsin (yoki guruhga kiring)
2️⃣ ➕ Guruh qo'shish tugmasini bosing
3️⃣ @username yoki https://t.me/guruh nomini yuboring (bir nechta bo'lsa — har biri yangi qatorda)
```

**`GROUP_PICKER_CHECK`**

```text
🔎 Tekshirish uchun guruhni tanlang.

Bot sizning Telegram akkauntingiz orqali shu guruhga yozish mumkinmi-yu yo'qmi ekanini tekshiradi (post yuborilmaydi).
```

**`USE_MENU_BUTTONS`**

```text
⚠️ Iltimos, menyudagi tugmalardan foydalaning.
```

**`GENERIC_ERROR`**

```text
❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.
```

**`SESSION_INVALID`**

```text
🚫 Sessiyangiz Telegram tomonidan bekor qilindi.

Qaytadan 🔑 Login qiling.
```

**`SESSION_EXPIRED_SEND`**

```text
🚫 Sessiyangiz bekor qilindi. Qaytadan 🔑 Login qiling.
```

**`EXPIRED_TEXT`**

```text
⏸ KUTISH REJIMI

Muddatingiz tugadi. Posting to'xtatildi.

📱 Davom ettirish uchun: +998938670592
```

**`LAST_DAY_WARNING`**

```text
⚠️ DIQQAT!

Bugun tarifingizning oxirgi kuni.

Ertaga posting avtomatik to'xtaydi.

📱 Davom ettirish uchun: +998938670592
```

**`POSTS_LIMIT_REACHED`**

```text
❌ Paket chegarasi: {max_posts} ta post (hozir {used} ta).
```

**`GROUPS_LIMIT_REACHED`**

```text
❌ Paket chegarasi: {max_groups} ta guruh (hozir {used} ta).

Ko'proq guruh uchun paketni kengaytiring:
📱 +998938670592
```

**`ask_interval()`** — posting oralig'ini so'rash

```text
⏱ UMUMIY POSTING ORALIG'I

Hozirgi umumiy oraliq: taxminan 45 daqiqa
Alohida interval berilmagan guruhlarda shu qiymat ishlaydi.

Yangi qiymatni kiriting (daqiqada):
5–10080 daqiqa. Anti-spam uchun real vaqt 5 daqiqagacha farq qilishi mumkin.
```

**`interval_set()`** — oraliq saqlangandan keyin

```text
✅ Umumiy posting oralig'i 45 daqiqaga o'rnatildi.
Alohida sozlangan guruhlar o'z intervalini saqlaydi.
ℹ️ Anti-spam uchun real vaqt 5 daqiqagacha farq qilishi mumkin.
```

**`status_next_step()`** — Status: keyingi qadam (guruh/post yo'q)

```text
👇 Boshlash uchun:
1️⃣ 💬 Guruhlar → ➕ Guruh qo'shish
2️⃣ 📝 Postlar → ➕ Post qo'shish
3️⃣ ▶️ Start
```

**`status_next_step()`** — Status: keyingi qadam (post yo'q)

```text
👇 Keyingi qadam: 📝 Postlar → ➕ Post qo'shish
```

**`test_send_done()`** — 🧪 Sinov yuborish muvaffaqiyatli

```text
🧪 Sinov yuborildi!

📛 @mening_guruhim

Guruhga kirib ko'ring — e'lon qanday chiqqanini tekshiring.
Hammasi yaxshi bo'lsa ▶️ Start bilan barcha guruhlarga yoqing.
```

**`test_send_failed()`** — 🧪 Sinov yuborish xato

```text
❌ Sinov yuborilmadi (Chat not found).

Ko'pincha sabab: akkaunt o'sha guruhga a'zo emas yoki unda yozish taqiqlangan. 💬 Guruhlar → 🔎 Tekshirish bilan aniqlang.
```


## 3. Tugmalar (menyu) matnlari

| Konstanta | Matn |
| --- | --- |
| `BTN_ACCOUNT` | ⚙️ Hisob |
| `BTN_ADD_GROUP` | ➕ Guruh qo'shish |
| `BTN_ADD_POST` | ➕ Post qo'shish |
| `BTN_ADMIN` | 🖥 Super Admin |
| `BTN_ADMIN_ADD_CANCEL` | ❌ Sessiya yaratishni to'xtatish |
| `BTN_ALBUM_DONE` | ✅ Tayyor — postni saqlash |
| `BTN_BACK` | ⬅️ Orqaga |
| `BTN_BLOCKED` | 🚫 Bloklangan |
| `BTN_CHECK_GROUPS` | 🔎 Guruhni tekshirish |
| `BTN_DEL_GROUP` | ➖ Guruh o'chirish |
| `BTN_DEL_POST` | 🗑 Post o'chirish |
| `BTN_EDIT_POST` | ✏️ Postni tahrirlash |
| `BTN_GROUPS` | 💬 Guruhlar |
| `BTN_GROUP_INTERVAL` | ⏱ Guruh intervali |
| `BTN_LOGIN` | 🔑 Login |
| `BTN_PAY_CANCEL` | ❌ So'rovni bekor qilish |
| `BTN_PAY_QUEUE` | 💰 To'lovlar navbati |
| `BTN_PAY_STATUS` | 🧾 To'lov holatim |
| `BTN_PENDING` | ⏳ Tasdiq kutilmoqda... |
| `BTN_PLAN` | 💳 Obuna |
| `BTN_POSTS` | 📝 Postlar |
| `BTN_PREVIEW_POST` | 👁 Ko'rinishi |
| `BTN_REFERRAL` | 👥 Referal |
| `BTN_REPORT` | 📈 Hisobot |
| `BTN_START` | ▶️ Start |
| `BTN_STATUS` | 📊 Status |
| `BTN_STOP` | ⛔ Stop |
| `BTN_TEST_SEND` | 🧪 Sinov yuborish |
| `BTN_TIMER` | ⏱ Posting oralig'i |


## 4. Referal (👥 Referal bo'limi)

**`referral_text()`** — 👥 Referal ekrani (hali referal yo'q)

```text
👥 SIZNING REFERALLARINGIZ

🔗 Taklif havolangiz:
https://t.me/avtobot_bot?start=ref_123456

✅ Faol referallar: 0 ta
🎁 Har bir faol referalga: +15 kun tarif
    (hozircha jami +0 kun olgansiz)
    Shart: do'stingiz tasdiqlanishi, kamida 1 ta guruh va
    1 ta post qo'shib, 1 marta muvaffaqiyatli yuborishi kerak.

Hozircha referal yo'q. Havolani do'stlaringizga ulashing!
```

**`referral_text()`** — 👥 Referal ekrani (ro'yxat bilan)

```text
👥 SIZNING REFERALLARINGIZ

🔗 Taklif havolangiz:
https://t.me/avtobot_bot?start=ref_123456

✅ Faol referallar: 1 ta
🎁 Har bir faol referalga: +15 kun tarif
    (hozircha jami +15 kun olgansiz)
    Shart: do'stingiz tasdiqlanishi, kamida 1 ta guruh va
    1 ta post qo'shib, 1 marta muvaffaqiyatli yuborishi kerak.
📅 Bugun qo'shilganlar: 1 ta

📋 Ro'yxat:
1. Ali — ⏳ admin tasdig'i kutilmoqda
2. Vali — ⏳ admin tasdig'i kutilmoqda

⏳ = do'stingiz hali post yubora boshlamagan. U ishlay
    boshlagach bonus sizga avtomatik keladi.
```

**`referral_share_text()`** — 📨 Do'stlarga yuborish uchun tayyor matn

```text
Men Telegram guruhlarga e'lonlarimni avtomatik joylash uchun AVTOBOT ishlataman 👇

• bir nechta guruhga bir vaqtda
• bir nechta rasm (albom) bilan
• har bir guruhga o'z oralig'ini qo'yish mumkin
• qachon va nechta e'lon chiqqanini ko'rsatib turadi

🔗 Bepul boshlash: https://t.me/avtobot_bot?start=ref_123456
```

**`referral_counted_text()`** — do'st tasdiqlanganda taklif qilgan kishiga

```text
🎉 Sizning referalingiz faollashdi!

👤 Ali ro'yxatdan o'tib, tasdiqlandi.
👥 Jami faol referallaringiz: 1 ta

🎁 Bonus 15 kun uchun shart: u kamida 1 ta guruh va
1 ta post bilan 1 marta e'lon yuborishi kerak.
Shart bajarilgach kunlar avtomatik qo'shiladi.
```

**`referral_bonus_granted()`** — do'st ishlaganda bonus berilganda

```text
🎁 REFERAL BONUSI berildi!

👤 Ali birinchi e'lonlarini yubora boshladi.
➕ Tarifingizga +15 kun qo'shildi.
📅 Endi muddat: 2026-11-10 12:00
👥 Jami faol referallaringiz: 1 ta
```

**`referral_bonus_zero()`** — bonus 0 kun bo'lganda (muddatsiz tarif)

```text
🎉 Referalingiz ishlay boshladi!

👤 Ali
👥 Jami faol referallaringiz: 1 ta

ℹ️ Bonus kun qo'shilmadi: sizning tarifingiz cheksiz yoki
oylik bonus chegarasiga yetgan bo'lsangiz.
```

**`referral_revoked_note()`** — bonus qaytarib olinganda

```text
⚠️ Referal hisobi bekor qilindi

👤 Ali hisob-faydasiz yoki qoidabuzar deb topildi.
↩️ Olingan +15 kun bonus tarifdan qaytarib olindi.

Sabab: bloklandi
```
