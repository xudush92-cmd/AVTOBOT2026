# 🤖 AVTOBOT v2

Telegram guruhlariga reklama postlarini avtomatik joylashtiruvchi bot.

---

## 📋 XUSUSIYATLAR

- ✅ Bir nechta guruhga bir vaqtda post yuborish
- ✅ Matn, rasm va rasm+caption (formatlash saqlanadi: bold, italic, link)
- ✅ Bulk guruh qo'shish — butun ro'yxat bitta client bilan tekshiriladi
- ✅ Interval (vaqt) sozlash — minimum 5 daqiqa, maksimum yo'q
- ✅ Referal tizimi
- ✅ Super admin paneli (to'liq nazorat)
- ✅ Ommaviy xabar yuborish (broadcast) — FloodWait himoyasi bilan
- ✅ Muddat tizimi (admin qo'lda uzaytiradi, oxirgi kunda ogohlantirish)
- ✅ Bloklash / blokdan chiqarish
- ✅ Anti-spam himoya (rate limiter)
- ✅ 24/7 ishlaydi, restartdan keyin avtomatik tiklanadi
- ✅ Health server — monitoring (ixtiyoriy token himoyasi bilan)

---

## 🏗 ARXITEKTURA

```
AVTOBOT2026/
├── main.py            # Ishga tushirish, FSM router, janitorlar, restore
├── config/
│   ├── config.py      # Barcha sozlamalar (.env dan o'qiladi)
│   └── .env.example   # Sozlama namunasi
├── bot/               # Foydalanuvchi interfeysi (python-telegram-bot)
│   ├── login.py       # Login FSM: ism→familiya→telefon→SMS(numpad)→2FA
│   ├── menu.py        # Asosiy menyu (Start/Stop/Status router)
│   ├── groups.py      # Guruhlar: bulk qo'shish (batch tekshiruv), o'chirish
│   ├── posts.py       # Postlar: matn/rasm/caption saqlash
│   ├── timer.py       # Interval sozlash
│   ├── referral.py    # Referal tizimi
│   ├── callbacks.py   # Inline tugmalar routeri (numpad, tasdiqlar)
│   ├── keyboards.py   # Barcha klaviaturalar
│   └── texts.py       # Barcha matnlar (bir joydan boshqaruv)
├── admin/             # Super admin
│   ├── admin_panel.py # Panel: userlar, statistika, bloklanganlar, DB
│   ├── admin_actions.py # User kartasi: start/stop/sessiya/muddat/blok
│   └── broadcast.py   # Ommaviy xabar (pauza + RetryAfter himoyasi)
├── core/              # Yadro
│   ├── database.py    # SQLite (aiosqlite, WAL, foreign keys)
│   ├── rate_limit.py  # Anti-spam (har user, har amal limitlari)
│   ├── logger.py      # Rotatsiyali log (5MB × 3)
│   └── utils.py       # Vaqt, validatsiya, guruh parsing
└── worker/            # Posting yadrosi (Telethon)
    ├── worker.py      # posting_loop (har user) + WorkerManager
    ├── client_pool.py # Telethon clientlar pool'i (per-uid lock)
    └── health.py      # HTTP /health endpoint
```

### Ishlash sxemasi

1. **Bot API** (python-telegram-bot) — foydalanuvchi bilan chat, barcha menyular.
2. **User API** (Telethon) — foydalanuvchi sessiyasi bilan guruhlarga posting.
3. Har bir faol user uchun alohida `posting_loop` task (WorkerManager boshqaradi):
   guruhlar → navbatdagi post (rotation) → yuborish → interval + jitter kutish.
4. Clientlar `ClientPool`da qayta ishlatiladi (RAM tejash).
5. Janitorlar: stale login/FSM tozalash (har daqiqa), muddat tekshirish (har soat).

---

## ⚙️ O'RNATISH

### 1. Talablar

- Python 3.11+
- Telegram API_ID va API_HASH: https://my.telegram.org → API development tools
- Bot token: https://t.me/BotFather

### 2. Sozlash

```bash
pip install -r requirements.txt
cp config/.env.example .env
nano .env
```

`.env`da to'ldirilishi SHART bo'lgan maydonlar:

| Maydon | Izoh |
|---|---|
| `API_ID`, `API_HASH` | my.telegram.org dan |
| `BOT_TOKEN` | BotFather dan |
| `ADMIN_ID` | Super admin Telegram ID (@userinfobot) |

Ixtiyoriy: `HEALTH_TOKEN` (ochiq serverda tavsiya etiladi), `MAX_CONCURRENT_WORKERS`,
`MAX_CLIENT_POOL`, `POST_SEND_TIMEOUT_S`, `PHOTO_SEND_TIMEOUT_S`, `BROADCAST_DELAY_S`.

### 3. Ishga tushirish

```bash
python main.py
```

---

## 🚀 DEPLOY (24/7 ishlashi uchun)

### systemd (Linux server)

`/etc/systemd/system/avtobot.service`:

```ini
[Unit]
Description=AVTOBOT v2
After=network-online.target

[Service]
Type=simple
User=avtobot
WorkingDirectory=/opt/avtobot
ExecStart=/opt/avtobot/venv/bin/python main.py
Restart=always
RestartSec=5
# SIGTERM -> graceful shutdown
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now avtobot
sudo journalctl -u avtobot -f     # loglarni kuzatish
```

### Docker

`Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

```bash
docker build -t avtobot .
docker run -d --name avtobot --restart unless-stopped \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  -p 8080:8080 \
  avtobot
```

> Sessiyalar `data/avtobot.db` da saqlanadi — volume ulamasangiz har restartda
> login talab qilinadi.

---

## 📊 MONITORING

Health server: `http://<host>:8080/health`

```json
{
  "status": "ok",
  "uptime_seconds": 86400,
  "workers": {"active_workers": 3, "max": 50},
  "pool": {"total_clients": 3, "in_use": 1, "max": 50},
  "memory": {"used_mb": 210, "total_mb": 1024, "percent": 20.5}
}
```

`HEALTH_TOKEN` berilgan bo'lsa: `/health?token=XXX` yoki
`Authorization: Bearer XXX` sarlavhasi talab qilinadi (aks holda 401).
Uptime Robot kabi xizmatlarda shu URL ni kuzatishingiz mumkin.

---

## 🔐 XAVFSIZLIK

- `.env`, `*.session`, `data/`, `logs/` — gitignore'da, repoga tushmaydi.
- **Sessiyalar SQLite'da plaintext saqlanadi.** Bu user-session botlar uchun
  odatiy holat (workerlar sessiyani doim kerak bo'ladi), lekin server
  xavfsizligi to'liq sizning zimmadangiz:
  - faqat SSH kalit bilan kirish, parol loginni o'chirish;
  - `data/` papkasini muntazam zaxira qilish (admin panelida `db:backup` ham bor);
  - serverdagi boshqa userlardan fayl huquqlari bilan himoyalash (`chmod 700 data`).
- SMS kodlar hech qanday joyda saqlanmaydi; 2FA parol faqat operativ xotirada.
- Health server ochiq tarmoqda bo'lsa — `HEALTH_TOKEN` ni ALBATTA to'ldiring.

---

## 🧯 MUHIM XUSUSIYATLAR (batafsil)

| Hodisa | Bot munosabati |
|---|---|
| Guruhga yuborib bo'lmadi (3 marta) | Guruh avtomatik o'chiriladi, user xabar oladi |
| FloodWait | Telegram aytgan vaqtcha kutadi |
| Sessiya bekor qilindi | Userga xabar, qayta login so'raladi |
| Worker o'z-o'zidan tugadi | Manager ro'yxatdan tozalaydi (limit bo'shadi) |
| Restart | `running=1` userlar avtomatik tiklanadi |
| Muddat tugadi | Posting to'xtatiladi, user va adminga xabar |
| Oxirgi kun | Userga ogohlantirish (bir marta) |
| 3 martadan ko'p SMS so'rash | 30 daqiqa cooldown |
| 5 marta xato kod | Login yopiladi |
