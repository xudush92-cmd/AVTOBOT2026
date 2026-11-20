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

**Jamoa adminini faqat super admin yaratadi** — telefon raqam orqali
tayyorlaydi. Oddiy foydalanuvchi o'zi jamoa admini bo'la olmaydi
(`👑 Admin bo'lish` tugmasi menyudan olib tashlangan).

```
🖥 Super Admin → 👑 Jamoa adminlari → ➕ Admin qo'shish
                                        ↓
                                    +998901112233
                                        ↓
                              "✅ Admin tayyorlandi"
```

Admin shu raqam bilan ro'yxatdan o'tsa — **darhol jamoa admini** bo'ladi
(tasdiq kutilmaydi). Keyin birinchi marta `👥 Jamoam` tugmasini bosganda
**o'z jamoasini o'zi shakllantiradi**:

```
👥 Jamoam → 🔢 Jamoangizda qancha foydalanuvchi bo'ladi?  → 5
          → 📋 Jamoa nomini kiriting:  → "Avtoelon Toshkent"
          → ✅ Jamoa yaratildi
             🔗 Havola: https://t.me/Bot?start=team_12
```

| Qoida | Qiymat |
| ----- | ------ |
| Minimal jamoa hajmi | 2 ta foydalanuvchi (`TEAM_MIN_MEMBERS`) |
| Jamoa adminining muddati | `TEAM_ADMIN_DEFAULT_DAYS` (standart 30 kun) |
| Jamoa adminining sig'imi | admin o'zi kiritadi, super admin keyin +/- qila oladi |

**Jamoa admini darhol tasdiqlangan bo'ladi** — u super admin tomonidan
tayyorlangan bo'lgani uchun «tasdiq kutilmoqda» holatiga tushmaydi. U:

- ✅ o'z jamoasini darhol boshqaradi (`👥 Jamoam`),
- ✅ oddiy foydalanuvchi kabi **posting qila oladi** (guruh, postlar),
- ✅ a'zolariga tarif/muddat beradi va ularni tasdiqlaydi.

Super admin jamoa adminining muddatini uzaytirganda — uning **o'z tarif
muddati ham** yangilanadi (aks holda muddat uzaytirilgandan keyin ham
«muddati tugagan» bo'lib qolardi).

---

## 4. Foydalanuvchi ro'yxatdan o'tishi

**Oddiy (jamoasiz, taklif yo'q) foydalanuvchi:**

```
/start
   ↓
📱 Ism → Telefon → Telegram kodi
   ↓
⏳ Tasdiq kutilmoqda — super admin'ga xabar boradi
   ↓
✅ Super admin tasdiqladi → bot faollashdi
```

> Jamoasiz foydalanuvchi **faqat super admin** tomonidan tasdiqlanadi.
> U jamoaga o'zi qo'shila olmaydi — jamoa qo'shish faqat jamoa
> administratorining vazifasi.

**Jamoa havolasi / telefon taklifi orqali kelgan foydalanuvchi:**

```
/start (havola bilan)  →  📱 Ism → Telefon → Telegram kodi
   ↓
⏳ Jamoa admini tasdiqlashni kutilmoqda
   ↓
✅ Admin tasdiqladi → muddat berildi → bot faollashdi
```

**Qoidalar:**
- Jamoali foydalanuvchi **faqat jamoa admini** tasdiqlaydi (super admin emas)
- Jamoa tanlash **yo'q** — jamoalar yopiq, foydalanuvchi jamoani
  ko'ra ham olmaydi va o'zi tanlay ham olmaydi
- Limit to'lgan jamoaga a'zo qo'shilmaydi ("Jamoa to'ldi")
- Jamoa adminining muddati tugagan bo'lsa — jamoa qabul qilmaydi
- **Super admin tomonidan taklif qilingan raqam** ro'yxatdan o'tsa — darhol
  jamoa admini bo'ladi (tasdiq kutilmaydi)

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

> ⛔️ **60 kunlik maksimal muddat** — jamoa a'zolariga beriladigan muddat
> hech qachon 60 kundan oshmasligi kafolatlanadi
> (`TEAM_MEMBER_MAX_DAYS = 60`).
> Super admin `TEAM_ADMIN_MAX_DAYS` orqali jamoa admini muddati chegarasini
> o'zgartirishi mumkin (`0` = cheksiz).

### ➕ Do'st qo'shish (telefon raqam bilan)

Jamoa admini o'z jamoasiga do'stlarini **telefon raqam orqali** qo'shadi —
do'st ro'yxatdan o'tishidan **oldin**.

```
👥 Jamoam
   [➕ Do'st qo'shish]
         ↓
➕ Do'st qo'shish

Do'stingizning telefon raqamini yozing.
📱 Format: +998123456789

Shu raqam bilan ro'yxatdan o'tsa — u avtomatik sizning jamoangizga
biriktiriladi va siz tasdiqlaysiz.
         ↓ (telefon kiritiladi)
✅ Do'st qo'shildi!

📱 +998123456789
📋 Jamoa: Mening jamoam

Endi do'stingizga ushbu havolani yuboring:
https://t.me/bot?start=team_1
```

Qoidalar:

1. **Faqat to'g'ri format** — `+998123456789` (7–15 raqam, `+` bilan).
   `998123456789` shakli ham avtomatik `+998...` ga to'g'rilanadi.
2. **Jamoa sig'imi to'lgan bo'lsa** — qo'shilmaydi.
3. **Taklif biriktirilgach** — holat `✅` ga o'zgaradi, qayta ishlatilmaydi.
4. **Muddati tugagan jamoa admini** — yangi do'st qabul qilmaydi.
5. **Boshqa jamoaga biriktirilgan raqam** — rad etiladi (admin o'z jamoasidagini
   qo'shadi).
6. **📋 Do'stlar ro'yxati** — jamoa admini panelidan ochiladi. Ro'yxatda
   `⏳` (ro'yxatdan o'tmagan) va `✅` (biriktirilgan) holatlar ko'rinadi.
   Xato qo'shilgan raqamni **🗑 bekor qilish** tugmasi bilan olib bo'ladi.
7. **Ikkita havola** — do'stga yuborish uchun:
   - 🔗 **Jamoa havolasi** (`/start team_<id>`)
   - 🔗 **Shaxsiy havolа** (`/start adm_<uid>`)
   
   Ikkalasi ham ishlaydi — foydalanuvchi avtomatik shu jamoaga birikadi.

### 👑 Yangi jamoa admini qo'shish (super admin)

Super admin jamoa adminlarini ro'yxatidan **➕ Admin qo'shish** orqali qo'shadi.

```
👑 Jamoa adminlari
   [➕ Admin qo'shish]
         ↓
👑 Yangi jamoa admini qo'shish

Yangi adminning telefon raqamini yozing.
📱 Format: +998123456789

U shu raqam bilan ro'yxatdan o'tsa — avtomatik jamoa admini bo'ladi.
```

| Holat | Natija |
| ----- | ------ |
| Raqam **yangi** (ro'yxatdan o'tmagan) | Taklif saqlanadi — u ro'yxatdan o'tsa **avtomatik jamoa admini** bo'ladi |
| Raqam **allaqachon ro'yxatdan o'tgan** | U **juda hozir jamoa admini** qilib tayinlanadi (super adminning tanlovi bo'yicha) |

> Taklif qilingan admin o'z jamoasini keyin o'zi yaratadi — birinchi marta
> «👥 Jamoam» tugmasini bosganda jamoaning nomi va sig'imi so'raladi.

### 📥 Ro'yxatdan o'tish oqimi

| Kelish usuli | Natija |
| ------------ | ------ |
| **Jamoa havolasi** (`/start team_<id>`) | Jamoa avtomatik tanlanadi, admin tasdiqlaydi |
| **Admin havolasi** (`/start adm_<uid>`) | Adminning jamoasi avtomatik tanlanadi |
| **Referal havola** (`/start ref_<uid>`) | Referrer jamoasiga avtomatik biriktiriladi |
| **Admin qo'shgan telefon** | Adminning jamoasiga avtomatik biriktiriladi (ariza yuboriladi) |
| **Hech narsa** (boshqa yangilar) | Ro'yxatdan o'tadi va **super admin** tasdiqlaydi |

Jamoani qo'lda tanlash **yo'q**: jamoalar yopiq. Jamoasiz foydalanuvchi
menusida jamoa tugmalari ko'rinmaydi va jamoani ko'ra olmaydi.

### 🚪 Jamoadan chiqish

Oddiy jamoa a'zosi «👥 Jamoam» tugmasi orqali jamoasidan chiqishi mumkin.

Oqim:
1. `👥 Jamoam` → jamoa kartasi (nomi, muddati)
2. `🚪 Jamoadan chiqish` → tasdiqlash oynasi (ogohlantirish bilan)
3. `✅ Ha, chiqaman` → jamoadan chiqadi

Chiqish natijasi:

| Narsa | Natija |
| ----- | ------ |
| `team_id` / `owner_admin_uid` | Tozalanadi — foydalanuvchi endi jamoasiz |
| **Jamoa muddati** | **Tugaydi** (jamoa admini bergan muddat) |
| Super admin bergan muddat | **Saqlanadi** |
| Posting | To'xtatiladi (`running = 0`) |
| Jamoa sig'imi | Bo'shaydi — yangi a'zo qabul qilinadi |
| Jamoa admini | Xabardor bo'ladi: «👋 A'zo ketdi» |

> **Jamoa egasi (admin) jamoasidan chiqmaydi** — jamoa unga tegishli.
> Chiqish faqat oddiy a'zolar uchun.

### 🚪 Jamoadan chiqarish (jamoa admini)

Jamoa admini a'zoni uchun **🚪 Jamoadan chiqarish** tugmasi bor (a'zo
kartasida). Bu bloklashdan farqli — a'zo **jamoasidan butunlay chiqadi**.

| Narsa | Natija |
| ----- | ------ |
| `team_id` / `owner_admin_uid` | Tozalanadi |
| Jamoa muddati | Tugaydi |
| Posting | To'xtatiladi |
| A'zo | Xabar oladi: «🚪 Siz ... jamoasidan chiqarildingiz» |

> **Jamoa egasi jamoasidan chiqarilmaydi.**

### 🚫 Bloklash va jamoa ta'siri

Jamoa admini a'zosini bloklasa — uning postingi **darhol** to'xtatiladi
(worker o'chiriladi). Super admin esa jamoa adminini bloklasa, **butun jamoa**
to'xtaydi:

| Kim bloklandi | Natija |
| ------------- | ------ |
| Jamoa a'zosi | Faqat o'sha a'zo to'xtaydi |
| **Jamoa admini** | **Butun jamoa to'xtaydi** + a'zolar xabar oladi |

Blokdan chiqarilganda jamoa adminining a'zolari qayta ishlaydi (ular
o'zlari `▶️ Start` bosadi).

### 📊 A'zolar ro'yxatidagi holatlar

| Belgi | Holat |
| ----- | ----- |
| 🟢 | Ishlamoqda |
| ⚪ | To'xtatilgan |
| ⏳ | Tasdiq kutilmoqda |
| ⌛ | **Muddati tugagan** — muddat berish kerak |
| 🚫 | Bloklangan |

Ro'yxatda muddati tugagan a'zolar soni ko'rsatiladi — admin kimga muddat
berishi kerakligini darhol biladi.

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
