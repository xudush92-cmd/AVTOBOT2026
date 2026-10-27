# 🧭 Foydalanuvchi menyusini soddalashtirish (2026-10)

Foydalanuvchi tugmalari ko'pligidan chalg'imasligi uchun menyu **yassi**
(ichki menyusiz) ko'rinishga keltirildi. Barcha asosiy amallar bitta ekranda.

## Yangi asosiy menyu

```text
[                ▶️ Start (🔴 OFF) / ⛔ Stop (🟢 ON)   ]
[ 📈 Hisobot                        ] [ 👥 Referal     ]
[ 🔍 Guruhlarni topish              ] [ ➖ Guruh o'chirish ]
[ ➕ Post qo'shish                  ] [ 🗑 Post o'chirish  ]
[ ⏱ Posting oralig'i                                   ]
```

- **Holat (ON/OFF) alohida Status tugmasisiz** — Start/Stop tugmasining o'zida:
  to'xtagan bo'lsa `▶️ Start (🔴 OFF)`, ishlayotgan bo'lsa `⛔ Stop (🟢 ON)`.
- **Hisobot va Paket bitta tugmada** — 📈 Hisobot ekrani yuborish statistikasi,
  guruh salomatligi, keyingi navbat **hamda** paket/limitlar (guruh/post limiti,
  kunlik limit, ish vaqti, tarif muddati) ni bitta ekranda ko'rsatadi.

## Asosiy o'zgarishlar

| Eski holat | Yangi holat |
| ---------- | ----------- |
| ➕ Guruh qo'shish (qo'lda havola yuborish) | **🔍 Guruhlarni topish** — bot ulangan akkauntning barcha dialoglarini ko'rib, yozish huquqi bor guruh/kanallarni avtomatik qo'shadi |
| 💬 Guruhlar ichki menyusi | Olib tashlandi — ➖ Guruh o'chirish to'g'ridan-to'g'ri ro'yxatni inline tugma qilib ko'rsatadi |
| ⏱ Guruh intervali (har guruhga alohida) | Foydalanuvchidan olib tashlandi — faqat **admin** o'z panelidan (`uc:gint`) sozlaydi |
| 🔎 Guruhni tekshirish | Olib tashlandi — topish paytida yozish huquqi avtomatik tekshiriladi |
| 📝 Postlar ichki menyusi | Olib tashlandi — ➕ Post qo'shish / 🗑 Post o'chirish asosiy ekranda |
| ✏️ Tahrirlash / 👁 Ko'rinish / 🧪 Sinov | Foydalanuvchi tugmalaridan olib tashlandi (dvigatel kodi saqlanadi) |
| ⚙️ Hisob (sessiyani uzish) | Olib tashlandi — sessiya muammosida qayta Login yoki admin |
| ⏱ Posting oralig'i | Tugma qoldi; bosilganda darhol daqiqa kiritish so'raladi (5, 30, …), ichki menyu yo'q |
| 📊 Status (alohida tugma) | Olib tashlandi — ON/OFF holati Start/Stop tugmasining yorlig'iga ko'chirildi; `/status` buyrug'i ishlaydi |
| 📦 Paket va limitlar (alohida tugma) | Olib tashlandi — 📈 Hisobot ekrani ichiga qo'shildi |

Saqlanib qolgan tugmalar: ▶️ Start/⛔ Stop (holat yorlig'i bilan), 📈 Hisobot
(statistika + paket/limitlar), 👥 Referal, 🔍 Guruhlarni topish,
➖ Guruh o'chirish, ➕ Post qo'shish, 🗑 Post o'chirish, ⏱ Posting oralig'i.

> Eslatma: eski klaviaturalarda qolib ketgan 📊 Status / 📦 Paket tugmalari
> bosilsa ham router ularni to'g'ri ekranga yo'naltiradi (orqaga moslik).

## 🔍 Guruhlarni topish texnik xususiyati

- `bot/groups.py::discover_groups` — Telethon `iter_dialogs()` orqali ishlaydi.
- Faqat akkaunt a'zo bo'lgan va **yozish huquqi** bor oddiy guruhlar va
  megaguruplar qo'shiladi (`_posting_rejection` tekshiruvi).
- **Broadcast kanallar siyosat bo'yicha umuman qo'shilmaydi** — akkaunt kanal
  egasi yoki admin bo'lsa ham (`_is_broadcast_channel` filtri); hisobotda
  alohida «kanallar qo'shilmadi» qatorida sanaladi.
- Username bor guruhlar `@username`, yopiq guruhlar marked ID (`-100…`, `-…`)
  bilan saqlanadi — posting vaqtida mavjud `resolve_group_entity` ishlaydi.
- Takror guruhlar, huquqsiz/chiqib ketilgan dialoglar o'tkazib yuboriladi.
- Paket limiti (`max_groups`) hurmat qilinadi; bitta skanerlash 500 dialog
  bilan chegaralangan, har 20 dialogda progress ko'rsatiladi.
- Foydalanuvchi keraksiz guruhlarni ➖ Guruh o'chirish orqali tozalaydi.

### 🛡 Anti-spam himoyasi (eng muhim qism)

Skaner faqat **o'qish so'rovlari** (`GetDialogs`, `GetParticipant`) ishlatadi —
xabar yubormaydi, guruhga kirmaydi/chiqmaydi. Shunga qaramay Telegramni
inson harakatiga o'xshatish uchun to'rt qavatli himoya bor:

1. **Tasodifiy pauza** — har bir tekshirilgan guruh orasida 1–3 soniya kutish
   (`DISCOVER_PAUSE_MIN_S/MAX_S`); 100 ta guruh taxminan 2–4 daqiqa oladi.
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
- Testlar: `python -m unittest discover -s tests` — 245 test, barchasi yashil.
