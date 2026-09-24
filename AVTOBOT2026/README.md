# 🤖 AVTOBOT v2

Telegram guruhlariga reklama postlarini avtomatik joylashtiruvchi bot.

---

## 📋 XUSUSIYATLAR

- ✅ Bir nechta guruhga bir vaqtda post yuborish
- ✅ Matn, rasm va rasm+caption
- ✅ Har bir post Telegram formatlashni saqlaydi (bold, italic, link)
- ✅ Bulk guruh qo'shish (bir vaqtda bir nechta)
- ✅ Taxminiy posting oralig'i — 5–10080 daqiqa; anti-spam jitteri ±5 daqiqa
- ✅ Referal tizimi
- ✅ Super admin paneli (to'liq nazorat)
- ✅ Ommaviy xabar yuborish (broadcast)
- ✅ Muddat tizimi (admin qo'lda uzaytiradi)
- ✅ Bloklash / blokdan chiqarish
- ✅ Anti-spam himoya
- ✅ 24/7 ishlaydi, restartdan keyin avtomatik tiklanadi

---

## 🏗 ARXITEKTURA

- `python-telegram-bot` — bot menyusi va foydalanuvchi bilan muloqot.
- `Telethon` — foydalanuvchi sessiyasi bilan guruhlarga post yuborish.
- `SQLite` — user, shifrlangan sessiya, guruh va postlarni saqlash.

Posting oralig'i aniq sekundli jadval emas: har siklda sozlangan qiymatga
`±5 daqiqa` tasodifiy anti-spam farqi qo'shiladi (minimum 5 daqiqa saqlanadi).
Admin paneldagi SQLite eksport `session` va `pending_session` sirlarisiz
sanitizatsiya qilinadi; server backup esa SQLite online backup API bilan
izchil snapshot yaratadi.

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

- yangi foydalanuvchi uchun **admin tasdig'i kod so'rovidan oldin** keladi;
- har bir foydalanuvchi ko'pi bilan **3 marta/soat** login boshlashi mumkin;
- muddati o'tgan kodni faqat **bir marta** qayta so'rash mumkin;
- tugallanmagan login 5 daqiqada yopiladi.

Shuning uchun yangi foydalanuvchi ism va telefonini kiritgach tasdiqni
kutadi. Admin tasdiqlaganidan keyin u yana **🔑 Login** bosib kod yoki QR
orqali kiradi. `Login`ni qayta-qayta bosish yetkazishni tezlashtirmaydi va
Telegram flood/risk cheklovini kuchaytirishi mumkin.

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
