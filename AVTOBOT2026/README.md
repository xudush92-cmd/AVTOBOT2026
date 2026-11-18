# 🤖 AVTOBOT v2

Telegram guruhlariga reklama postlarini avtomatik joylashtiruvchi bot.

---

## 📋 XUSUSIYATLAR

- ✅ Bir nechta guruhga bir vaqtda post yuborish
- ✅ Matn, rasm va rasm+caption
- ✅ Har bir post Telegram formatlashni saqlaydi (bold, italic, link)
- ✅ 🔍 Guruhlarni avtomatik topish — akkauntdagi yozish mumkin guruhlar bir tugma bilan qo'shiladi (qo'lda bulk qo'shish admin/legacy oqimida saqlangan)
- ✅ Umumiy posting oralig'i va guruh uchun alohida interval — 5–10080 daqiqa; anti-spam jitteri ±5 daqiqa
- ✅ Referal tizimi (faqat statistika — bonus kunlari berilmaydi)
- ✅ **Jamoa (team) tizimi** — jamoa admini o'z jamoasini mustaqil boshqaradi:
  tarif berish, bloklash, xabar yuborish, statistika. Boshqa adminlarning
  jamoalariga tasir qilmaydi
- ✅ **Do'st qo'shish (telefon bilan)** — jamoa admini do'stining telefon
  raqamini yozadi; do'st ro'yxatdan o'tganda avtomatik jamoaga birikadi
- ✅ **Yangi jamoa admini qo'shish** — super admin telefon raqam kiritsa, yangi
  admin avtomatik jamoa admini bo'ladi
- ✅ **Muddat chegarasi (anti-fraud)** — jamoa admini a'zosiga maksimal 60 kun;
  firibgar adminlardan himoya
- ✅ **Jamoadan chiqish** — a'zo jamoasidan chiqsa, jamoa muddati ham tugaydi
- ✅ **Jamoadan chiqarish** — jamoa admini a'zoni jamoasidan chiqaradi
- ✅ **Jamoani topshirish** — super admin jamoani boshqa jamoa adminga o'tkazadi
  (a'zolar, sig'im va muddat yangi admin ostiga o'tadi)
- ✅ **Do'stlar ro'yxati** — taklif qilingan raqamlarni ko'rish va bekor qilish
- ✅ Super admin paneli (to'liq nazorat)
- ✅ Ommaviy xabar yuborish (broadcast)
- ✅ Muddat tizimi (admin yangi muddat beradi — oldingi muddat bekor bo'lib,
  yangisi hozirdan boshlab hisoblanadi)
- ✅ Bloklash / blokdan chiqarish
- ✅ Anti-spam himoya
- ✅ Oddiy registratsiya: ism → telefon → Telegram kodi → admin tasdiqi
  (tasdiqdan keyin kod qayta kiritilmaydi)
- ✅ Sessiya admin tasdig'igacha Fernet bilan shifrlangan `pending_session`
  sifatida saqlanadi
- ✅ 24/7 ishlaydi, restartdan keyin avtomatik tiklanadi

---

## 🏗 ARXITEKTURA

- `python-telegram-bot` — bot menyusi va foydalanuvchi bilan muloqot.
- `Telethon` — foydalanuvchi sessiyasi bilan guruhlarga post yuborish.
- `SQLite` — user, shifrlangan sessiya, guruh, guruhga xos interval/navbat va postlarni saqlash.

Posting oralig'i aniq sekundli jadval emas: foydalanuvchining umumiy
intervali (5–10080 daqiqa) barcha guruhlarga boshlang'ich qiymat bo'ladi.
Foydalanuvchi menyusi yassi: alohida guruh intervali **faqat super admin**
tomonidan user kartasi → **Guruhlar** bo'limidan boshqariladi.
Override olib tashlansa, guruh umumiy intervalni meros qilib oladi.
Har bir guruhning navbatdagi yuborish vaqti SQLite'da saqlanadi, shuning uchun
restartda jadval tiklanadi. Har yuborishdan keyingi intervalga `±5 daqiqa`
tasodifiy anti-spam farqi qo'shiladi (minimum 5 daqiqa saqlanadi); Telegram
FloodWait bo'lsa, uning kutish vaqti ham hisobga olinadi. Eski DB'dagi guruhlar
uchun migratsiya yangi ustunlarni qo'shadi, intervalni esa umumiy sozlamadan oladi.

**🔍 Guruhlarni topish (foydalanuvchi oqimi):** foydalanuvchi tugmani bossa,
bot ulangan Telethon sessiyasi orqali akkauntning barcha dialoglarini
(`iter_dialogs`) ko'rib chiqadi va a'zo hamda yozish huquqi bor
guruh/megaguruplarni avtomatik qo'shadi. **Broadcast kanallar, jumladan
akkaunt egasi bo'lgan kanallar ham, siyosat bo'yicha qo'shilmaydi** — faqat
guruhlar olinadi. Username borlar `@username`, yopiq guruhlar marked peer ID
(`-100...`, `-...`) bilan saqlanadi; takror va huquqsiz dialoglar o'tkazib
yuboriladi, paket limiti hurmat qilinadi. Keraksiz guruhlar **➖ Guruh
o'chirish** ro'yxatidan o'chiriladi.

Anti-spam himoyasi: har guruh tekshiruvi orasida 1–3 soniyali tasodifiy pauza,
har foydalanuvchi uchun 10 daqiqalik cooldown, Telegram FloodWait berganda
ko'rsatilgan vaqtgacha bloklash va bir vaqtda faqat bitta skaner ishlashi.
Faqat o'qish so'rovlari ishlatiladi — xabar yuborilmaydi, guruhga
kirilmaydi/chiqilmaydi. Qo'lda havola orqali qo'shish dvigateli (`@username`,
`t.me` linki, private invite, `-100...` ID; faqat format tekshiruvi)
admin/legacy oqimlar uchun saqlanib qolgan. Start tasdiqlanganda saqlangan
sessiya `get_me()` bilan bir marta tekshiriladi; vaqtinchalik FloodWait yoki
tarmoq xatosida Startni keyinroq qayta sinash mumkin. Tekshiruv xatosi
sessiyani avtomatik o'chirmaydi.
Admin paneldagi SQLite eksport `session` va `pending_session` sirlarisiz
sanitizatsiya qilinadi; server backup esa SQLite online backup API bilan
izchil snapshot yaratadi.

### Oddiy foydalanuvchi registratsiyasi (yangi oqim)

1. **/start** yoki **🔑 Login** bosilganda bot birinchi xabardayoq ism va
   familiyani **bitta xabarda** so'raydi.
2. Telefon raqami kiritiladi va format tekshiriladi (`+998XXXXXXXXX`).
3. Telefon validatsiyadan o'tishi bilan Telegram tasdiq kodi **darhol**
   so'raladi — admin tasdig'i kutilmaydi. Kod faqat botdagi **raqamli
   tugmalar** orqali kiritiladi (matn ko'rinishidagi kod qabul qilinmaydi);
   kerak bo'lsa **📷 QR Login** yoki **2FA** ishlatiladi.
4. Login tugagach sessiya aktiv `session` emas, Fernet bilan shifrlangan
   `pending_session` sifatida saqlanadi va `awaiting_approval=1` qilinadi
   (bitta atomik SQL UPDATE). Bundan oldin:
   - Telegram qaytargan akkaunt UID'i bot foydalanuvchisining UID'iga
     mosligi tekshiriladi;
   - Telegram qaytargan telefon normalize qilinadi;
   - telefon boshqa UID'ga biriktirilgan bo'lsa sessiya umuman saqlanmaydi.
5. Super adminga tasdiq xabari boradi: muddat tanlash oynasi, **60 daqiqalik
   posting oralig'i** va "qayta kod kiritish shart emas" eslatmasi bilan.
6. Admin **📅 Muddatni tanlang** oynasidan kunni tanlaydi (1/7/30/90/180/365)
   va **✅ Tasdiqlash** bosganda pending sessiya Telegram orqali yana
   tekshiriladi (`get_me()` UID solishtiriladi) va faqat aynan shu UID'ga
   tegishli bo'lsa atomik ravishda `pending_session` → `session` ko'chiriladi:
   - pending sessiya **revoke qilinmaydi** — u aynan shu UID uchun
     tekshirilgan authorization;
   - foydalanuvchidan ikkinchi marta kod yoki Login talab qilinmaydi, unga
     darhol **asosiy menyu** yuboriladi;
   - sessiya boshqa akkauntga tegishli bo'lsa (`mismatch`) authorization
     Telegramda revoke qilinadi, pending holat tozalanadi va foydalanuvchi
     qaytadan Login qilishi mumkin;
   - sessiya yaroqsiz/revoked bo'lsa (`invalid`) pending holat tozalanadi va
     tasdiq legacy yo'l bilan yakunlanadi — foydalanuvchi bir marta Login
     qiladi;
   - FloodWait/timeout/tarmoq xatosida (`temporary`) pending sessiya
     **o'chirilmaydi va revoke qilinmaydi** — admin keyinroq yana tasdiqlaydi.
7. Ariza rad etilsa avval pending authorization Telegramda xavfsiz revoke
   qilinadi, keyin user o'chiriladi. Revoke vaqtinchalik xato bersa user va
   pending ma'lumotlari saqlanadi.
8. Birinchi marta tasdiqlangan foydalanuvchiga **tanlangan muddat**
   (standart `DEFAULT_DURATION_DAYS` — 30 kun) va **60 daqiqalik posting
   oralig'i**
   (`DEFAULT_INTERVAL_MIN`, `MIN_INTERVAL_MIN`–`MAX_INTERVAL_MIN` oralig'iga
   clamp qilinadi) oladi. Bu super admin qo'shgan yangi foydalanuvchiga ham
   tegishli. Allaqachon tasdiqlangan foydalanuvchining qo'lda o'zgartirilgan
   intervali qayta tasdiqlash yoki Login paytida **o'zgarmaydi**.
9. Eski (pending sessiyasiz) `awaiting_approval` arizalar uchun legacy oqim
   ishlaydi: admin tasdiqlaydi, so'ng foydalanuvchi bir marta Login qiladi.

#### Rate limitlar

- **UID bo'yicha login: 3 ta / soat** — yangi va tasdiqlanmagan
  foydalanuvchilar ham shu limitga tushadi, uni **/start** orqali aylanib
  o'tib bo'lmaydi.
- **Telefon raqami bo'yicha kod so'rovi: 3 ta / soat** — `bot/login.py`dagi
  alohida in-memory limiter; tekshiruv har doim Telegram
  `send_code_request()` chaqirilishidan **oldin** bajariladi.
- Muddat o'tgan kodni qayta so'rash: 1 marta / 30 daqiqa (o'zgarmagan).
- Janitor har daqiqada UID limiter, telefon limiter va SMS yozuvlarini
  tozalaydi.

Sessiya hamda pending-sessiya qiymatlari hech qachon log, admin xabari yoki
DB eksportida ko'rsatilmaydi; SQLite eksport `session` va `pending_session`
ustunlarini bo'shatib, `VACUUM` qiladi.

### Tarif muddati (yangi muddat oldingisini bekor qiladi)

Foydalanuvchi kartasidagi **⏰ Tarif muddati** orqali berilgan muddat
**hozirdan boshlab** hisoblanadi va oldingi muddatni **bekor qiladi** — u
mavjud muddat ustiga **qo'shilmaydi** (tayyor `1/7/30/90/180/365 kun` tugmalari
ham, **✏️ Qo'lda kiritish** ham):

| Holat | Natija |
| --- | --- |
| Tasdiqda 30 kun berilgan, admin yana `30 kun` beradi | hozirdan **30 kun** (60 emas) |
| 20 kun qolgan userga `30 kun` | hozirdan **30 kun** (50 emas) |
| 90 kun qolgan userga `7 kun` | hozirdan **7 kun** (oldingisi bekor) |
| Muddati tugagan yoki cheksiz userga `N kun` | hozirdan **N kun** |
| Bir xil tugmani ikki marta bosish | muddat ikki barobar bo'lmaydi |
| `♾ Cheksiz` | muddat cheklovi olib tashlanadi |

- Admin xabarida **bekor qilingan oldingi muddat** ko'rsatiladi; userga esa
  yangi sana yuboriladi.
- Yangi muddat berilganda `warned_at` tozalanadi — "oxirgi kun"
  ogohlantirishi yangi muddat uchun qayta ishlaydi.
- Tasdiqlash (approve) va qayta Login mavjud muddat ustiga kun **qo'shmaydi**
  va uni almashtirmaydi: standart `DEFAULT_DURATION_DAYS` (30 kun) faqat userda
  muddat yozilmagan bo'lsagina beriladi.
- Kod: `admin/admin_actions.py` → `give_new_term()` (tugma ham, qo'lda
  kiritish ham shu yagona funksiyadan foydalanadi).

### Tasdiqlashda muddat tanlash

Tasdiqlash **ikki bosqichli** — avval muddat tanlanadi, keyin tasdiqlash
yakunlanadi. Bu **barcha adminlar uchun** bir xil:

| Admin | Tugmalar | Chegara |
| --- | --- | --- |
| 🛡 Super admin | 1 / 7 / 30 / 90 / 180 / 365 kun | Cheksiz (`SUPER_ADMIN_MAX_DAYS=0`) |
| 👑 Jamoa admini | 1 / 7 / 30 / 60 kun | **Maksimal 60 kun** (`TEAM_MEMBER_MAX_DAYS=60`) |

Muddat chegarasi **firibgar jamoa adminlaridan himoya** qiladi: ular a'zosiga
uzun muddat berib, uddadan olib, botni tark etishi mumkin edi. Jamoa admini
chegaradan oshgan muddat so'rasa — tizim uni avtomatik qisqartiradi, chegara
oshsan rad etiladi.

### Super admin orqali foydalanuvchi qo'shish

**🖥 Super Admin → ➕ Foydalanuvchi qo'shish** orqali avval ism-familiya
bitta xabarda, so'ng telefon kiritiladi. Telegram kodi matn qilib
jo'natilmaydi — botdagi raqamli tugmalar, o'chirish va tasdiqlash tugmasi
orqali teriladi; 2FA paroli esa matn bo'lib qoladi. Login muvaffaqiyatli
tugagach, foydalanuvchining haqiqiy Telegram ID si avtomatik aniqlanadi,
sessiya o'sha ID ga saqlanadi va boshqaruv kartasi darhol ochiladi — admin
hisobiga yozilmaydi. Jarayonning istalgan bosqichida **“Sessiya yaratishni
to'xtatish”** tugmasi bilan bekor qilish mumkin.

---

## ✨ IMKONIYATLAR (2026-10 holati)

- **🖼 Albom (faqat surat)** — bitta postga **4 tagacha rasm** yuborish mumkin.
  Bir nechta media yuborilsa ular bitta post bo'lib saqlanadi va guruhga
  **bitta albom** bo'lib chiqadi (alohida-alohida spam bo'lmaydi).
  **Video butunlay rad etiladi** (`ALLOW_VIDEO_MEDIA=1` bilan qayta yoqiladi).
- **🔍 Guruhlarni topish** — bitta tugma bilan akkauntdagi yozish mumkin bo'lgan
  guruh va megaguruplar avtomatik aniqlanib qo'shiladi (broadcast kanallar,
  jumladan o'z kanali ham, qo'shilmaydi; takror va huquqsizlar o'tkazib
  yuboriladi); anti-spam pauza, 10 daqiqalik cooldown va FloodWait himoyasi
  bilan ishlaydi; ➖ Guruh o'chirish ro'yxatidan keraksizlari tozalanadi.
- **🧭 Yassi menyu** — barcha asosiy amallar bitta ekranda: Start/Stop (holat
  ON/OFF tugmaning o'zida), Hisobot (statistika **va** paket/limitlar bitta
  ekranda), Guruh topish/o'chirish, Post qo'shish/o'chirish, Posting oralig'i,
  Referal. Alohida Status va Paket tugmalari yo'q. Ichki menyular (post
  tahrirlash/ko'rinish/sinov, guruh tekshirish, qo'lda guruh qo'shish,
  sessiyani uzish) foydalanuvchi klaviaturasidan olib tashlandi; dvigatel kodi
  admin/legacy sifatida saqlanadi.
- **🔗 Link preview** — har bir post uchun havoladan kartochka yoqish/o'chirish.
- **⏱ Interval har bir guruhga alohida (admin)** — umumiy sozlama saqlanib
  qolgan holda, faqat super admin user kartasidan sozlaydi.
- **📈 Hisobot** — bugun/hafta yuborishlari, xatolar sababi, qaysi guruhda
  muammo borligi va keyingi yuborish vaqti.
- **📦 Tarif paketlari va limitlar** — SINOV/START/PRO/BUSINESS (guruh, post,
  kunlik yuborish soni), kunlik limit va **tungi tanaffus** (faol soatlar) —
  akkaunt Telegram chekloviga uchlamasin.
- **👥 Referal** — taklif havolasi va faol referallar ro'yxati. **Bonus kunlari
  olib tashlangan**: referal endi faqat statistika (kim kimni taklif qilgani)
  uchun, muddatga hech qanday kun qo'shilmaydi. Jamoa admini o'z jamoasining
  havolasini tarqatsa, kelgan foydalanuvchilar avtomatik shu jamoaga birikadi.
- **👑 Jamoa admini** — foydalanuvchilar jamoalarni ko'rib, o'z jamoasini
  tanlaydi (minimal 2 ta foydalanuvchi). Jamoani yaratgan admin **darhol
  tasdiqlangan** bo'ladi (tasdiq kutilmaydi). Jamoa admini:
  jamoasiga **tarif (muddat) beradi**, foydalanuvchilarni tasdiqlaydi,
  bloklaydi, xabar yuboradi va statistikani ko'radi. Boshqa adminlarning
  jamoalariga **hech qanday ta'sir qilmaydi**. Jamoa admini ham oddiy
  foydalanuvchi kabi o'z postlarini yubora oladi. Jamoa adminining muddati
  tugasa **yoki bloklansa** — uning jamoasi ham to'xtaydi. Super admin jamoa
  adminlarining muddati va sig'imini boshqaradi; muddat uzaytirilganda
  adminning **o'z tarif muddati ham** yangilanadi.
- **➕ Do'st qo'shish** (jamoa admini) — do'stingizning **telefon raqamini**
  yozing (`+998123456789`). Do'st ro'yxatdan o'tganda avtomatik sizning
  jamoangizga birikadi va siz tasdiqlaysiz. Admin do'stiga taklif havolasini
  ham yuborishi mumkin.
- **🚪 Jamoadan chiqish** (oddiy a'zo) — «👥 Jamoam» orqali jamoasidan
  chiqishi mumkin. Chiqsa — **berilgan jamoa muddati ham tugaydi** va
  e'lon yuborish to'xtaydi. Jamoa egasi jamoasidan chiqmaydi.
- **🚪 Jamoadan chiqarish** (jamoa admini) — a'zo kartasida «🚪 Jamoadan
  chiqarish» tugmasi. A'zo jamoadan butunlay chiqadi va postingi to'xtaydi.
- **📋 Do'stlar ro'yxati** (jamoa admini) — taklif qilingan raqamlar
  ro'yxati (`⏳` — kelmagan, `✅` — biriktirilgan) va **🗑 bekor qilish**
  tugmasi. Do'stga yuborish uchun **jamoa havolasi** va **shaxsiy havolа**
  ikkalasi ham beriladi.
- **🔄 Jamoani topshirish** (super admin) — jamoa admini kartasida
  «🔄 Jamoani topshirish» tugmasi. Tanlangan admin jamoaning yangi egasi
  bo'ladi — a'zolar, sig'im va muddat unga o'tadi. Eski admin jamoa
  boshqaruvidan chiqadi.
- **📊 A'zolar ro'yxati indikatorlari** — 🟢 faol | ⚪ to'xtatilgan |
  ⏳ tasdiq kutilmoqda | ⌛ muddati tugagan | 🚫 bloklangan. Muddati
  tugagan a'zolar soni alohida ko'rsatiladi.
- **🎯 Jamoani tanlash** (jamoasiz foydalanuvchi) — ixtiyoriy. Boshqa yangi
  foydalanuvchilar **to'g'ridan-to'g'ri ro'yxatdan o'tadi** — hech qanday
  savol berilmaydi.
- **👑 Admin bo'lish** — o'z jamoangizni yarating. Super admin telefoningizni
  kiritsa — siz avtomatik jamoa admini bo'lasiz.
- **⚡ Tez tasdiqlash** (`AUTO_APPROVE_ENABLED=1` bo'lsa) — past riskli arizalar
  admin navbatini kutmasdan tasdiqlanadi; har bir avto-tasdiq adminga xabar
  qilinadi.
- **🤖 `/help`, `/status`** — bot ichidan chiqmasdan qisqa yo'riqnoma va holat.

Siz yuborgan media va sessiyangiz haqida batafsil: quyidagi “Xavfsizlik”
bo'limi va `docs/` hujjatlari.

---

## 📈 RIVOJLANTIRISH

Hozirgi holat auditi, referal tizimi tahlili, ko'p surat (albom) texnik rejasi,
imkoniyatlar ro'yxati, daromad modeli va 90 kunlik yo'l xaritasi (0.1-bo'lim —
nima allaqachon qilingan):
[`docs/TAKLIFLAR_ROADMAP.md`](docs/TAKLIFLAR_ROADMAP.md).

Serverga chiqarish tartibi, zaxira, tekshirish ro'yxati, limitlarni bosqichma-
bosqich yoqish va orqaga qaytish rejasi:
[`docs/YANGILASH.md`](docs/YANGILASH.md).

---

## 🚀 O'RNATISH

```bash
git clone https://github.com/xudush92-cmd/AVTOBOT2026.git
cd AVTOBOT2026/AVTOBOT2026
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config/.env.example .env
nano .env
python main.py
```

`API_ID` va `API_HASH` **BotFather'dan olinmaydi**. Ularni
[my.telegram.org](https://my.telegram.org) → **API development tools**
bo'limidan olish kerak. `BOT_TOKEN` esa BotFather'dan olinadi.

---

## 🔐 AWS/VPSDA LOGIN KODI KELMASA

Telegram 2023-yildan beri uchinchi tomon ilovalari (jumladan Telethon) uchun
kodni odatda SMS orqali emas, avvaldan ochiq turgan rasmiy Telegram
ilovasidagi **“Telegram” (777000)** chatiga yuboradi. Yetkazish usulini
Telegram serverining o'zi tanlaydi; `force_sms` endi ishlamaydi.

Bot raqamli tugmalarni ko'rsatib, logda quyidagiga o'xshash yozuv chiqarsa:

```text
Kod so'rovi qabul qilindi ... delivery=SentCodeTypeApp
```

bu `API_ID/API_HASH`, MTProto ulanishi va kod so'rovi ishlaganini bildiradi.
Ammo Telegram AWS/data-center IP manzilini xavfli deb baholasa, so'rovga
muvaffaqiyatli javob berib, kodni amalda yetkazmasligi ham mumkin. Buni bot
SMSga majburlab o'tkaza olmaydi.

Bot API/IP reputatsiyasini himoyalash uchun login oqimi qat'iy cheklangan:

- yangi va tasdiqlanmagan foydalanuvchi ham UID bo'yicha **3 marta/soat**
  login limitiga tushadi (uni **/start** orqali aylanib o'tib bo'lmaydi);
- bitta telefon raqami uchun **3 ta/soat** kod so'rovi limiti bor va u
  har doim `send_code_request()`dan **oldin** tekshiriladi;
- muddati o'tgan kodni faqat **bir marta** qayta so'rash mumkin;
- tugallanmagan login 5 daqiqada yopiladi.

Yangi oqimda kod admin tasdig'idan **oldin** so'raladi: foydalanuvchi ism,
telefon va kodni kiritib loginni tugatadi, sessiya shifrlangan
`pending_session` sifatida saqlanadi. Admin tasdig'idan keyin u atomik
faollashadi — foydalanuvchi kodni qayta kiritmaydi. `Login`ni qayta-qayta
bosish yetkazishni tezlashtirmaydi va Telegram flood/risk cheklovini
kuchaytirishi mumkin.

### Tavsiya etilgan yechim

1. Kod oynasidagi **“📷 Kod kelmadimi? QR Login”** tugmasini bosing.
2. **“Telegramda tasdiqlash”** tugmasini bosing; yoki QRni boshqa ekranda
   ochib, Telegram → **Settings → Devices → Link Desktop Device** orqali
   skaner qiling.
3. Telegram ko'rsatgan yangi sessiyani tasdiqlang.
4. 2FA yoqilgan bo'lsa, bot so'raganda 2FA parolni kiriting.

QR orqali faqat bot bilan gaplashayotgan aynan o'sha Telegram akkaunti
ulanishi mumkin; boshqa akkaunt tasdiqlansa login bekor qilinadi.

### Diagnostika

```bash
cd AVTOBOT2026/AVTOBOT2026
tail -n 100 logs/avtobot.log | grep -Ei 'request_code|Kod so.rovi|Flood|QR|xato'
```

- `ApiIdInvalidError` — `.env` dagi `API_ID/API_HASH` noto'g'ri.
- `FloodWaitError` / `PhoneNumberFloodError` — ko'p urinish; logda berilgan
  muddatgacha qayta bosmang.
- `TimeoutError` — AWS chiqish tarmog'i/NAT/Firewall orqali Telegram MTProto
  ulanishini tekshiring.
- `delivery=SentCodeTypeApp`, lekin kod yo'q — Telegram tomondagi yetkazish
  yoki AWS IP reputatsiyasi; QR Login ishlating.

> **Xavfsizlik:** Telethon StringSession akkauntga kirish kaliti hisoblanadi.
> U DB ichida Fernet bilan shifrlanadi. `SESSION_ENCRYPTION_KEY` berilmasa
> kalit `data/.session.key` faylida yaratiladi; DB backup bilan birga shu
> kalitni ham alohida, xavfsiz joyda saqlang. `data/avtobot.db`, kalit,
> `.env` va server SSH kirishini begonalardan himoyalang; ularni hech qachon
> chat yoki GitHub'ga joylamang. Ikki bot alohida AWS host/IP'da ishlasa,
> har biriga alohida `API_ID`, `API_HASH`, `BOT_TOKEN` va encryption key bering.

Rasmiy ma'lumot: [Telethon login/SMS o'zgarishi](https://github.com/LonamiWebs/Telethon/issues/4050).
