# 💳 To'lov tizimi — yagona oylik obuna (qo'lda tasdiqlash)

Bu hujjat "A reja" to'lov oqimini tasvirlaydi: onlayn provayder (Payme / Click /
Stars) hali ulanmagan, to'lov **karta orqali o'tkaziladi**, mijoz **kvitansiya
rasmini** yuboradi, super admin esa tasdiqlaydi yoki rad etadi.

Tarif yagona: **`OYLIK`** — bir oylik to'lov, cheklovlarsiz (guruh, post,
kunlik yuborish va faol soatlar bo'yicha limit yo'q). Sinov (trial) tarifi yo'q.

---

## 1. Yoqish

To'lov standart holatda **o'chiq** (`PAYMENTS_ENABLED=0`). O'chiq holatda
foydalanuvchi 💳 tugmasini ko'rmaydi va eski xatti-harakat saqlanadi.

```env
PAYMENTS_ENABLED=1
MONTHLY_PRICE=300000          # oylik narx, so'm. 0 yoki bo'sh = to'lov tugmasi ko'rinmaydi
PAY_CARD=8600 0000 0000 0000  # karta raqami
PAY_BANK=                     # bank nomi (ixtiyoriy)
PAY_HOLDER=ISM FAMILIYA       # karta egasi
PAYMENT_DAYS=30               # bitta to'lov necha kunlik muddat beradi
PAYMENT_REQUEST_TTL_MIN=120   # kvitansiyasiz so'rov necha daqiqa yashaydi
PAYMENT_REMIND_DAYS=3         # muddat tugashidan necha kun oldin eslatma
PAYMENT_PROOF_RETENTION_DAYS=14  # qaror qilingan kvitansiya necha kundan keyin o'chadi
PAYMENT_QUEUE_ALERT=10        # navbatda shuncha kvitansiya bo'lsa adminga ogohlantirish
PAY_REF_PREFIX=AVTO           # to'lov izohi prefiksi
```

Yoqilgandan keyin botni qayta ishga tushiring. Migratsiya yangi jadval va
ustunlarni xavfsiz qo'shadi; oldindan ma'lumotlar bazasi zaxirasini oling.

## 2. Mijoz oqimi

1. `💳 Obuna` tugmasi (yoki `/pay`) → narx va `💳 Oylik obuna — <narx> so'm`
   tugmasi.
2. Tugma bosilganda so'rov yaratiladi (`status = pending`, `proof_path` bo'sh —
   ya'ni kvitansiya kutilmoqda):
   - summa, karta raqami, karta egasi;
   - izoh kodi: `AVTO-<uid>-OYLIK` (to'lovni aniq ajratish uchun **shu kodni
     o'tkazma izohiga yozish shart**);
   - kvitansiya rasmini shu chatga yuborish so'raladi.
3. Rasm yuborilganda `proof_path` va `proof_hash` yoziladi — so'rov admin
   navbatiga tushadi (`pending` + kvitansiya bor). Rasm faqat **shaxsiy
   chatda** va faqat ochiq (kvitansiya kutilayotgan) so'rov bo'lsa qabul
   qilinadi. Boshqa jarayon (masalan, post yoki login) ochiq bo'lsa, rasm o'sha
   jarayonga boradi.
4. Bir foydalanuvchida bir vaqtning o'zida faqat **bitta** ochiq so'rov bo'ladi.
   Takroran tugma bosilsa, yangi so'rov emas, mavjud so'rov ko'rsatiladi.

Mijoz tugmalari:

- `🧾 To'lov holatim` — joriy so'rov va oxirgi 5 ta to'lov.
- `❌ Bekor` — so'rovni bekor qiladi va kvitansiya faylini o'chiradi.

Kvitansiya fayli: `MEDIA_DIR/payments/<uid>/<pid>.jpg`.

## 3. Admin oqimi

- Admin panelida `💰 To'lovlar navbati` (`adm:pay`) va kutayotgan so'rovlar
  soni ko'rinadi. Tugma faqat `PAYMENTS_ENABLED=1` bo'lganda chiqadi.
- Har bir kvitansiyali `pending` so'rov adminga rasm bilan keladi:
  - takroriy kvitansiya (bir xil sha256 xesh) bo'lsa, ogohlantirish yoziladi;
  - tugmalar: `✅ Tasdiqlash`, `❌ Rad etish`, `👤 Karta`.
- **✅ Tasdiqlash** (`fulfill_payment` / `approve_payment`):
  - muddat tugagan bo'lsa — hozirdan `PAYMENT_DAYS` kun;
  - aks holda — joriy muddat oxiriga `PAYMENT_DAYS` kun qo'shiladi;
  - `paid_total` 1 ga oshadi, `paid_last_at` yangilanadi;
  - foydalanuvchiga xabar yuboriladi; posting to'xtab qolgan bo'lsa avtomatik
    tiklanadi;
  - **idempotent**: qayta bosish muddatni ikki marta uzaytirmaydi
    (`ok=False`, `status` allaqachon qaror qilingan).
- **❌ Rad etish** — so'rov `rejected` bo'ladi, foydalanuvchiga sabab bilan
  xabar boriladi, muddat o'zgarmaydi.

Tasdiqlash natijasi qisqacha:

```python
approve_payment(pid, admin_uid, now=None)
# -> {"ok": bool, "status": str, "payment": dict, "expires": str, "was_paused": bool}
```

## 4. Avtomatika (janitor)

Har bir tsikl (`payments_janitor_loop`) quyidagilarni bajaradi:

| Qoida | Sozlama | Natija |
| ----- | ------- | ------ |
| Kvitansiyasiz so'rov eskirdi | `PAYMENT_REQUEST_TTL_MIN` (120) | `expired` (faqat kvitansiyasizlari) |
| Muddat tugashiga yaqin | `PAYMENT_REMIND_DAYS` (3) | bir marta eslatma (`pay_reminded_at`) |
| Eski kvitansiya | `PAYMENT_PROOF_RETENTION_DAYS` (14) | qaror qilingan so'rovning fayli o'chadi, `proof_path` bo'shatiladi, yozuv saqlanadi |
| Navbat to'lib qoldi | `PAYMENT_QUEUE_ALERT` (10) | adminga ogohlantirish |

Muddati tugagan foydalanuvchida posting `pay_paused` bilan to'xtatiladi;
to'lov tasdiqlangach tiklanadi.

## 5. Ma'lumotlar bazasi

Jadval `payment_requests`:

| Ustun | Ma'nosi |
| ----- | ------- |
| `id`, `uid`, `plan`, `amount`, `days` | so'rov asosiy ma'lumotlari |
| `reference` | izoh kodi (`AVTO-<uid>-OYLIK`) |
| `status` | `pending` → `approved` / `rejected` / `expired` / `cancelled` |
| | `pending` + `proof_path` bo'sh = kvitansiya kutilmoqda; `pending` + `proof_path` bor = admin tekshiruvini kutmoqda |
| `provider`, `provider_txn` | kelajakdagi onlayn provayder uchun (hozir bo'sh) |
| `proof_path`, `proof_hash` | kvitansiya fayli va sha256 xeshi |
| `decided_at`, `decided_by` | qaror vaqti va admin UID |
| `created_at` | so'rov yaratilgan vaqt |

`users` jadvaliga qo'shilgan ustunlar (faqat migratsiya orqali):
`paid_total`, `paid_last_at`, `pay_reminded_at`, `pay_paused`.

**Yagona tarif migratsiyasi:** `app_meta` jadvalida `single_plan_v1` bayrog'i
bor-yo'qligi tekshiriladi. Yo'q bo'lsa, barcha foydalanuvchilar `OYLIK` tarifiga
o'tkaziladi va `max_groups`, `max_posts`, `daily_limit` 0 (cheksiz) qilinadi.
Bayroq qo'yilgandan keyin migratsiya qayta ishlamaydi — admin qo'lda qo'ygan
limitlar o'chmaydi.

Tekshirish so'rovlari:

```sql
-- So'nggi so'rovlar
SELECT id, uid, plan, amount, status, reference, created_at, decided_at
FROM payment_requests ORDER BY id DESC LIMIT 20;

-- Foydalanuvchi bo'yicha jami to'lovlar
SELECT uid, name, paid_total, paid_last_at FROM users WHERE paid_total > 0;
```

## 6. Ma'lum cheklovlar

- To'lov **qo'lda** tasdiqlanadi: onlayn to'lov (Payme / Click / Stars) yo'q.
- Kvitansiya rasmi tekshiruvi qo'lda: OCR yoki avtomatik summa tekshiruvi yo'q.
- Admin paneldagi foydalanuvchiga individual tarif/limit berish vositalari
  (`⚙️ Tarif va limitlar`) saqlangan — ular individual limit qo'yishi mumkin.
- Muddatsiz (`tariff_expires_at` NULL) foydalanuvchiga to'lov muddatni
  o'zgartirmaydi, faqat tarifni yangilaydi.

## 7. Testlar

```bash
python -m unittest discover -s tests -p "test_*.py"                    # PAYMENTS_ENABLED=0
PAYMENTS_ENABLED=1 MONTHLY_PRICE=300000 python -m unittest discover -s tests -p "test_*.py"
```

To'lov testlari: `tests/test_payments_manual.py`. Ikkala rejimda ham o'tishi
shart.
