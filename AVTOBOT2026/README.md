# 🤖 AVTOBOT v2

Telegram guruhlariga reklama postlarini avtomatik joylashtiruvchi bot.

---

## 📋 XUSUSIYATLAR

- ✅ Bir nechta guruhga bir vaqtda post yuborish
- ✅ Matn, rasm va rasm+caption
- ✅ Har bir post Telegram formatlashni saqlaydi (bold, italic, link)
- ✅ Bulk guruh qo'shish (bir vaqtda bir nechta)
- ✅ Interval (vaqt) sozlash — minimum 5 daqiqa, maksimum yo'q
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
- `SQLite` — user, sessiya, guruh va postlarni saqlash.

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
> `data/avtobot.db`, `.env` va server SSH kirishini begonalardan himoyalang;
> ularni hech qachon chat yoki GitHub'ga joylamang.

Rasmiy ma'lumot: [Telethon login/SMS o'zgarishi](https://github.com/LonamiWebs/Telethon/issues/4050).
