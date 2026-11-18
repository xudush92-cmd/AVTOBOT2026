# 👑 JAMOA (TEAM) TIZIMI

Bot ishlaydi — endi foydalanuvchilar jamoalarga bo'linadi va har bir jamoani
**jamoa admini** mustaqil boshqaradi. Jamoa adminlari bir-birining jamoasiga
aralashmaydi.

---

## 1. Rollar

| Rol | Kim | Huquqlar |
| ---- | --- | ------- |
| **Super Admin** | `.env` dagi `ADMIN_ID` (1 ta) | Hammasi: jamoa adminlari, muddat, sig'im, broadcast, statistika |
| **Jamoa admini** | `is_team_admin = 1` bo'lgan user | Faqat **o'z jamoasini** boshqaradi |
| **Foydalanuvchi** | Oddiy user | O'z botidan foydalanadi |

### Tasdiqlash kimga boradi?

| Foydalanuvchi | Tasdiqlaydi | Super admin ro'yxatida |
| -------------- | ----------- | ---------------------- |
| **Jamoali** (jamoa tanlangan) | **Jamoa admini** | ❌ chiqmaydi |
| **Jamoasiz** | **Super Admin** | ✅ chiqadi |

Jamoali arizalar super admin'ga yuborilmaydi, avto-tasdiqdan ham chiqariladi.

---

## 2. Rol taqsimoti

```
┌────────────────────────────────────────────┐
│           SUPER ADMIN (siz)                │
│  👑 Jamoa adminlari → muddat va sig'im      │
├────────────────────────────────────────────┤
│  JAMOA ADMIN A        JAMOA ADMIN B         │
│  ├ User1              ├ User4              │
│  ├ User2              └ User5              │
│  └ User3                                   │
└────────────────────────────────────────────┘
```

Har bir jamoa admini **faqat o'z a'zolarini** ko'radi va boshqaradi:

- Tarif (muddat, kun) berish
- Foydalanuvchini tasdiqlash
- Bloklash / blokdan chiqarish
- Jamoasiga xabar yuborish
- Jamoasi bo'yicha statistika

**Boshqa adminlarning jamoalariga ta'sir qilish mumkin emas** — baza darajasida
`owner_admin_uid` filtri qo'llaniladi va callback'lar server tomonda tekshiriladi.

---

## 3. Jamoa admini bo'lish

```
/start → 🔑 Login → 👑 Admin bo'lish
   ↓
🔢 Jamoangizda qancha foydalanuvchi bo'ladi?  → 5
   ↓
📋 Jamoa nomini kiriting:  → "Avtoelon Toshkent"
   ↓
✅ Jamoa yaratildi
   🔗 Havola: https://t.me/Bot?start=team_12
```

| Qoida | Qiymat |
| ----- | ------ |
| Minimal jamoa hajmi | 2 ta foydalanuvchi (`TEAM_MIN_MEMBERS`) |
| Jamoa adminining muddati | `TEAM_ADMIN_DEFAULT_DAYS` (standart 30 kun) |
| Jamoa adminining sig'imi | admin o'zi kiritadi, super admin keyin +/- qila oladi |

---

## 4. Foydalanuvchi ro'yxatdan o'tishi

```
/start
   ↓
🎯 JAMOA TANLANG  →  [Avtoelon Toshkent (3/5)]  [Boshqa jamoa (5/5)]
   ↓
📱 Ism → Telefon → Telegram kodi
   ↓
⏳ Jamoa admini tasdiqlashni kutilmoqda
   ↓
✅ Admin tasdiqladi → muddat berildi → bot faollashdi
```

**Qoidalar:**
- Jamoali foydalanuvchi **faqat jamoa admini** tasdiqlaydi (super admin emas)
- Jamoa tanlash **ixtiyoriy** — «🙋 Jamoasiz davom etish» tugmasi bilan
  jamoasiz ham ro'yxatdan o'tib, to'liq ishlash mumkin
- Limit to'lgan jamoani tanlab bo'lmaydi ("Jamoa to'ldi")
- Jamoa adminining muddati tugagan bo'lsa — jamoa qabul qilmaydi
- Referal yoki jamoa havolasi orqali kelgan user jamoasi avtomatik tanlanadi
- Jamoa tanlash **ixtiyoriy**: tanlamagan foydalanuvchilar eski tartibda ishlaydi

---

## 5. Muddat va sig'im

### Jamoa admini (super admin boshqaradi)

```
Super Admin → 🖥 Super Admin → 👑 Jamoa adminlari → [Admin A]
   ├── 📅 Muddatni uzaytirish  (1 / 7 / 30 / 90 kun)
   └── 👥 Sig'imni o'zgartirish (2 / 5 / 10 / 20 / 50 / 100 ta)
```

- **Muddat tugasa** → jamoa admini va uning **barcha a'zolari to'xtaydi**
- **Muddat uzaytirilsa** → jamoa qayta ishga tushadi (Start tugmasi bilan)
- **Sig'im kamaytirilsa** → mavjud a'zolar saqlanadi, yangi user qo'shilmaydi

### Jamoa a'zolari (jamoa admini boshqaradi)

Jamoa admini a'zoga muddat (1 / 7 / 30 / 90 kun) beradi. Muddat berilganda
foydalanuvchi tasdiqlanadi (agar avval tasdiqlanmagan bo'lsa).

### Tasdiqlashda muddat tanlash

Tasdiqlash **ikki bosqichli** — avval muddat tanlanadi, keyin tasdiqlash
yakunlanadi. Bu **barcha adminlar uchun** bir xil:

| Admin | Tugmalar | Yakun |
| ----- | -------- | ----- |
| **Super Admin** | `1 / 7 / 30 / 90 / 180 / 365 kun` | `app:term:<uid>:<kun>` |
| **Jamoa admini** | `1 / 7 / 30 / 60 kun` | `tadm:approveterm:<uid>:<kun>` |

Super adminning "Foydalanuvchi qo'shish" oqimi esa alohida — u tasdiqlash
emas, to'g'ridan-to'g'ri qo'shish.

### 🚪 Guruhdan chiqarilish / guruhga yetib borolmaslik

Agar bot guruhdan chiqarilsa yoki guruh yopiq bo'lsa, avtomatik ravishda
aniqlanadi va foydalanuvchi ogohlantiriladi:

| Holat | Xabar | Natija |
| ----- | ----- | ------ |
| Bot chiqarilgan / yozish taqiqlangan | Birinchi urinishda | Guruh `MAX_GROUP_FAILS` (3) urinishdan keyin o'chiriladi |
| Guruh yopiq (private) | Birinchi urinishda | Xuddi shunday |
| Guruh mavjud emas | Birinchi urinishda | Xuddi shunday |
| Havola noto'g'ri | Birinchi urinishda | Xuddi shunday |

Xabar matni xato turiga qarab farqlanadi — foydalanuvchi aniq biladi nima
qilish kerak (botni admin qilib qo'yish yoki guruhni qayta qo'shish).

### ⛔️ Muddat chegarasi (anti-fraud)

Jamoa admini (2-daraja) — "ikkinchi darajali admin" — foydalanuvchiga
istalgancha uzun muddat bera olmasligi kerak. Aks holda u foydalanuvchiga
ko'p muddat berib, uddadan olib, botni tark etishi mumkin (firibgar).

Shuning uchun **har bir admin darajasida muddat chegarasi** belgilanadi:

| Kim | Maksimal muddat | Konfiguratsiya |
| --- | --------------- | ------------- |
| 🛡 **Super Admin** | Cheksiz (365+ kun) | `SUPER_ADMIN_MAX_DAYS=0` |
| 👑 **Jamoa admini (2-daraja)** | **60 kun** | `TEAM_MEMBER_MAX_DAYS=60` |

Qoidalar:

1. **Chegara — beriladigan bir marta muddatga qo'yiladi.** Jamoa admini
   a'zosiga 365 kun so'rashi mumkin, lekin tizim uni avtomatik **60 kunga**
   qisqartiradi. Muddat ko'rsatilganida ham chegara oshgan variantlar
   tugmalarda umuman chiqmaydi.
2. **Muddat berish** (`tadm:setterm`) ham chegaraga bo'ysunadi — chegara
   oshsa, rad etiladi va super admin bilan bog'lanishni aytiladi.
3. **Super admin chegarasiz** — jamoa adminlari uchun muddat uzaytirish,
   sig'im o'zgartirish va jamoani boshqarish uning qo'lida.
4. Chegaralar `.env` orqali o'zgartiriladi (serverda to'g'ridan-to'g'ri,
   kod o'zgartirishsiz).

> **Chegara faqat dastlabki berilgan muddatga tegadi.** Super admin
> qaroriga ko'ra, chegara keyin bo'sh qoldirilishi mumkin.

---

## 6. Izolyatsiya qoidalari

| Amal | Kim bajaradi | Chegara |
| ---- | ------------ | ------- |
| Stop/Start | foydalanuvchi o'zi, jamoa admini | faqat o'zining |
| Guruh qo'shish/o'chirish | foydalanuvchi o'zi | faqat o'zining |
| Post qo'shish/o'chirish | foydalanuvchi o'zi | faqat o'zining |
| Tarif berish | jamoa admini | faqat o'z jamoasiga |
| Bloklash | jamoa admini | faqat o'z jamoasiga |
| Broadcast | super admin | barchaga |
| Jamoa admini yaratish | super admin | — |

Baza darajasida `users.owner_admin_uid` va `users.team_id` ustunlari orqali
tekshiriladi — `callback_data` ni tahrirlash ham o'zgartirish huquqini
bermaydi.

---

## 7. Referal bilan bog'liqlik

- Oddiy referal (`?start=ref_<uid>`) — statistika uchun, **bonus kun yo'q**
- Jamoa havolasi (`?start=team_<id>`) — kelgan user jamoaga birikadi
- Admin havolasi (`?start=adm_<uid>`) — kelgan user adminning jamoasiga birikadi
- Referrer jamoa admini bo'lsa, oddiy referal orqali kelgan user ham
  **avtomatik** shu jamoaga biriktiriladi (jamoa to'ldiq bo'lmasa)

---

## 8. Sozlamalar (`.env`)

| Kalit | Standart | Ma'nosi |
| ----- | -------- | ------- |
| `TEAM_ADMIN_DEFAULT_DAYS` | 30 | Jamoa admini uchun standart muddat (kun) |
| `TEAM_MIN_MEMBERS` | 2 | Minimal jamoa hajmi |
| `TEAM_DEFAULT_MAX_USERS` | 0 | Jamoa adminining sig'imi (0 = cheksiz) |
| `TEAM_LIST_PAGE_SIZE` | 10 | Jamoa tanlash sahifasi hajmi |
| `ALLOW_VIDEO_MEDIA` | 0 | Video qo'llab-quvvatlanadimi (0 = faqat surat) |
| `MAX_ALBUM_FILES` | 4 | Bitta postdagi maksimal rasm soni |
| `REFERRAL_BONUS_DAYS` | 0 | Bonus kunlari (0 = berilmaydi) |

---

## 9. Texnik izohlar

- **Jadval:** `teams` (id, name, owner_admin_uid, max_users, expires_at)
- **users ustunlari:** `team_id`, `owner_admin_uid`, `is_team_admin`,
  `admin_expires_at`, `admin_max_users`
- **Migratsiya:** `ALTER TABLE ... ADD COLUMN` va `CREATE TABLE IF NOT EXISTS` —
  eski ma'lumotlar buzilmaydi, mavjud foydalanuvchilar jamoasiz qoladi va
  eski tartibda ishlaydi
- **Modul:** `bot/teams.py` (oqim), `core/database.py` (baza),
  `bot/keyboards.py` (klaviatura), `bot/texts.py` (matnlar),
  `admin/admin_panel.py` (super admin bo'limi)
- **Testlar:** `tests/test_teams.py`
