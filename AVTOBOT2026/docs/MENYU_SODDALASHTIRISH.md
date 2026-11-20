# 🧭 Foydalanuvchi menyusini soddalashtirish (2026-11)

Foydalanuvchi tugmalari ko'pligidan chalg'imasligi uchun menyu **yassi**
(ichki menyusiz) ko'rinishga keltirildi. Barcha asosiy amallar bitta ekranda.

## Yangi asosiy menyu

```text
[ ▶️ Start ] [ ⛔ Stop ]
[ 🔍 Guruhlarni topish ] [ 💬 Guruhlar ]
[ ➕ Post qo'shish ] [ 🗑 Post o'chirish ]
[ ⏱ Interval ] [ 👥 Referal ]
[ 👥 Jamoam ]        ← faqat jamoa a'zosi/adminida
```

**Oxirgi qator roli bo'yicha o'zgaradi:**

| Foydalanuvchi | Tugma |
| ------------- | ----- |
| 🛡 Super admin | Faqat `🖥 Admin paneli` |
| 👑 Jamoa admini | `👥 Jamoam` — o'z jamoasini boshqaradi |
| 👤 Jamoa a'zosi | `👥 Jamoam` — jamoa kartasi + **🚪 Jamoadan chiqish** |
| 🧑 Oddiy (jamoasiz) | Jamoa tugmalari **yo'q** |

- **Start va Stop — doimiy ikki tugma.** Holat (ON/OFF) ularning
  yorlig'ida emas: tugma bosilganda alohida xabar bilan aytiladi.
- **`📈 Hisobot`, `📊 Status` va `📦 Paket` butunlay olib tashlandi.**
  `/status` buyrug'i ham olib tashlandi (buyruqlar ro'yxatidan).
- **Ikki xil interval bitta tugmada** — `⏱ Interval` ochilganda
  `🌐 Barcha guruhlar uchun` yoki `⏱ Bitta guruh uchun` tanlanadi.

## ⏱ Interval oynasi

```text
⏱ INTERVAL

Umumiy interval: 60 daqiqa

Qaysini o'zgartirmoqchisiz?

[ 🌐 Barcha guruhlar uchun ]
[ ⏱ Bitta guruh uchun ]
```

- `🌐 Barcha guruhlar uchun` — umumiy interval (barcha guruh bir vaqtda).
- `⏱ Bitta guruh uchun` — bitta tanlangan guruh uchun alohida interval;
  `↩️ Umumiy intervalni ishlatish` orqali orqaga qaytariladi.

## 💬 Guruhlar oynasi

```text
💬 GURUHLAR

Guruhlar soni: 12 ta

🔗 Guruh havolalari:

1. https://t.me/taxi_tashkent
2. https://t.me/avtoelon_uz

[ 🗑 1. @taxi_tashkent ]
[ 🗑 2. @avtoelon_uz ]
```

- Yuqorida — **guruh havolalari** (raqam bilan, ochiq link).
  Yopiq guruhlarda (`-100...`) Telegram ochiq havola bermaydi —
  u holda havola ro'yxatda chiqmaydi.
- Pastda — har bir guruh uchun **faqat** o'chirish tugmasi (`🗑 N. guruh`).
- Interval tugmalari bu oynada **yo'q** — ular `⏱ Interval` oynasida.

## Asosiy o'zgarishlar

| Eski holat | Yangi holat |
| ---------- | ----------- |
| ➕ Guruh qo'shish (qo'lda havola yuborish) | **🔍 Guruhlarni topish** — bot ulangan akkauntning barcha dialoglarini ko'rib, yozish huquqi bor guruhlarni topadi va **ro'yxat qilib ko'rsatadi**; foydalanuvchi ✅ belgilaydi, faqat belgilanganlar qo'shiladi |
| 💬 Guruhlar ichki menyusi | Olib tashlandi — 💬 Guruhlar oynasi ro'yxat + havolalar + o'chirish |
| ⏱ Guruh intervali (har guruhga alohida) | **⏱ Interval** oynasida — `🌐 Barcha guruhlar` / `⏱ Bitta guruh uchun` |
| ⏱ Posting oralig'i | **⏱ Interval** oynasining `🌐 Barcha guruhlar uchun` qismiga ko'chdi |
| 🔎 Guruhni tekshirish | Olib tashlandi — topish paytida yozish huquqi avtomatik tekshiriladi |
| 📝 Postlar ichki menyusi | Olib tashlandi — ➕ Post qo'shish / 🗑 Post o'chirish asosiy ekranda |
| ✏️ Tahrirlash / 👁 Ko'rinish / 🧪 Sinov | Foydalanuvchi tugmalaridan olib tashlandi (dvigatel kodi saqlanadi) |
| ⚙️ Hisob (sessiyani uzish) | Olib tashlandi — sessiya muammosida qayta Login yoki admin |
| 📊 Status (alohida tugma) | Olib tashlandi — holat Start/Stop bosilganda xabar bilan beriladi |
| 📈 Hisobot | **Butunlay olib tashlandi** — foydalanuvchilar foydalanmaydi |
| 📦 Paket va limitlar | **Butunlay olib tashlandi** (`ref:plan` ham olib tashlandi) |
| ▶️ Start (🔴 OFF) / ⛔ Stop (🟢 ON) | **▶️ Start** va **⛔ Stop** — doimiy alohida tugmalar |

Saqlanib qolgan tugmalar: ▶️ Start, ⛔ Stop, 🔍 Guruhlarni topish,
💬 Guruhlar, ➕ Post qo'shish, 🗑 Post o'chirish, ⏱ Interval, 👥 Referal.

**Jamoa bilan bog'liq tugma:** `👥 Jamoam` — faqat jamoa a'zosi va jamoa
adminida. Jamoasiz foydalanuvchida jamoa tugmalari **yo'q**. To'liq tavsif:
`docs/JAMOA_TIZIMI.md`.

**Jamoa admini paneli (`👥 Jamoam`):**

| Tugma | Vazifasi |
| ----- | ------- |
| 👥 A'zolar | A'zolar ro'yxati + a'zo kartasi |
| ➕ Do'st qo'shish | Telefon raqam bilan do'st taklif qilish |
| 📋 Do'stlar ro'yxati | Takliflar ro'yxati + 🗑 bekor qilish |
| 📊 Statistika | A'zolar / faol / kutayotgan / bloklangan / guruh / post |
| 📨 Xabar yuborish | Jamoasiga xabar |
| 🔗 Havola | Jamoa va shaxsiy taklif havolalari |

**A'zo kartasi (jamoa admini):** `✅ Tasdiqlash`, `📅 Muddat berish`,
`🚫 Bloklash`, `✅ Blokdan chiqarish`, `🚪 Jamoadan chiqarish`.

**A'zolar ro'yxati indikatorlari:** 🟢 faol | ⚪ to'xtatilgan |
⏳ tasdiq kutilmoqda | ⌛ muddati tugagan | 🚫 bloklangan.

**Super admin panelida jamoa adminlari ro'yxati:** 👑 faol | ⌛ muddati
tugagan | ⏳ tasdiq kutilmoqda | 🚫 bloklangan.

**Jamoa admini kartasi (super admin):** `📅 Muddatni uzaytirish`,
`👥 Sig'imni o'zgartirish`, `🔄 Jamoani topshirish`.

> Eslatma: eski klaviaturalarda qolib ketgan 📊 Status / 📦 Paket tugmalari
> bosilsa ham router ularni to'g'ri ekranga yo'naltiradi (orqaga moslik).

## 🔍 Guruhlarni topish texnik xususiyati

> ⚠️ **Avtomatik qo'shish yo'q.** Skaner faqat **topadi** — hech qanday
> guruh botga avtomatik qo'shilmaydi. Ro'yxat chiqadi, foydalanuvchi
> **✅ belgilaydi**, faqat **belgilanganlar** qo'shiladi.

### Oqim

```
🔍 Guruhlarni topish
   ↓
Telethon iter_dialogs() — barcha dialoglar ko'rib chiqiladi
   ↓
Faqat yozish huquqi bor guruh/megaguruplar topiladi
   ↓
📋 Guruhlar ro'yxati (sahifalash, 15 ta/sahifa)
   ├── ⬜ Guruh A  →  ✅ belgilash
   ├── ⬜ Guruh B
   └── ⬜ Guruh C
   ↓
«✅ Tanlanganlarni qo'shish (N)»  →  faqat belgilanganlar qo'shiladi
```

### Texnik jihatlar

- `bot/groups.py::discover_groups` — Telethon `iter_dialogs()` orqali ishlaydi.
- Topilgan guruhlar **vaqtinchalik sessiyada** saqlanadi
  (`bot/discover_sessions.py`) — bot DB'siga **hali yozilmaydi**.
- `bot/discover_sessions.py::DiscoverSession` — tanlov, sahifalash va muddat
  (30 daqiqa, `DISCOVER_SELECTION_TTL_S`) boshqaruvi.
- Inline tugmalar: `disc:toggle:<indeks>`, `disc:page:<sahifa>`,
  `disc:apply`, `disc:cancel`. `callback_data` hajti cheklanganligi uchun
  guruh o'rniga **sessiya indeksi** ishlatiladi.
- Faqat akkaunt a'zo bo'lgan va **yozish huquqi** bor oddiy guruhlar va
  megaguruplar topiladi (`_posting_rejection` tekshiruvi).
- **Broadcast kanallar siyosat bo'yicha umuman ko'rsatilmaydi** — akkaunt kanal
  egasi yoki admin bo'lsa ham (`_is_broadcast_channel` filtri).
- Username bor guruhlar `@username`, yopiq guruhlar marked ID (`-100…`, `-…`)
  bilan saqlanadi — posting vaqtida mavjud `resolve_group_entity` ishlaydi.
- Takror guruhlar, huquqsiz/chiqib ketilgan dialoglar o'tkazib yuboriladi.
- Paket limiti (`max_groups`) **qo'shish bosqichida** tekshiriladi.
- Foydalanuvchi keraksiz guruhlarni ➖ Guruh o'chirish orqali tozalaydi.

### 🛡 Anti-spam himoyasi (eng muhim qism)

Skaner faqat **o'qish so'rovlari** (`GetDialogs`, `GetParticipant`) ishlatadi —
xabar yubormaydi, guruhga kirmaydi/chiqmaydi. Shunga qaramay Telegramni
inson harakatiga o'xshatish uchun to'rt qavatli himoya bor:

1. **Parallel tekshiruv + pauza** — guruhlar **8 tadan** guruhli
   partiyalarda (`DISCOVER_BATCH_SIZE`) parallel tekshiriladi, partiyalar
   orasida `DISCOVER_BATCH_PAUSE_S` (0.4 s) kutuladi. Har bir guruh
   uchun alohida 1–3 soniya kutish **yo'q** — shuning uchun skaner
   sezilarli tez (16 guruh ≈ 0.9 s).
2. **Cooldown** — bitta foydalanuvchi skanerni 10 daqiqada bir marta bosha
   oladi (`DISCOVER_COOLDOWN_S`); erta bosilsa aniq kutish vaqti ko'rsatiladi.
3. **FloodWait blokirovkasi** — Telegram cheklov bersa, ko'rsatilgan vaqtgacha
   skaner bloklanadi (`_flood_wait_until`), so'rov takrorlanmaydi.
4. **Bitta skaner** — bir vaqtda ikkinchi qidiruv ishga tushmaydi
   (`_discover_running`), sabrsizlanib qayta bosish himoyalangan.

Himoya holati in-memory yuritiladi (restartda tozalanadi); botga zarar bermaydigan
va admin panelini cheklamaydigan yengil yondashuv.

## Eslatma

- Eski inline tugmalar (tahrirlash, sinov, tekshirish) kodda va eski chat
  xabarlarida qoladi, lekin yangi menyuda ko'rinmaydi va yangi foydalanuvchi
  ularga duch kelmaydi.
- Admin paneli va uning guruh/post boshqaruvi **o'zgarishsiz** qoldi.
- Testlar: `python -m unittest discover -s tests -t tests` — **509 test**,
  barchasi yashil.
