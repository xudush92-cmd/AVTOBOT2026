# 🚀 YANGILASH (PROD'A QO'YISH) QO'LLANMASI

Bu hujjat kodni serverga chiqarish tartibi, tekshirish ro'yxati va orqaga
qaytish rejasini beradi.

## 1. Nima o'zgaradi va xavf darajasi

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| Baza sxemasi | 🟢 past | Faqat **ustun/qo'shimcha jadval qo'shiladi** (`ALTER TABLE ... ADD COLUMN`, `CREATE TABLE IF NOT EXISTS`). Eski ustunlar va ma'lumotlar o'chirilmaydi, ko'chirilmaydi. Migratsiya `init_db()` ichida avtomatik ishlaydi — qo'lda SQL kerak emas |
| Limitlar (guruh/post/kunlik) | 🟢 past | Eski foydalanuvchilarda barcha limitlar `0` = **cheksiz**, ya'ni hozirgi xatti-harakat saqlanadi. Cheklov faqat admin paket bersa yoki `.env`da default qo'ysa paydo bo'ladi |
| Referal | 🟢 past | Hisoblash mantig'i o'zgarmadi; qo'shilgan narsa — mukofot (bonus kun) va himoya qoidalari. `REFERRAL_BONUS_DAYS=0` qilsangiz mukofot umuman berilmaydi |
| Tez tasdiqlash | 🟢 past | `AUTO_APPROVE_ENABLED` standart **0** — hech narsa avtomatik tasdiqlanmaydi, faqat admin navbati ishlaydi |
| Worker yuborish | 🟡 o'rta | Endi albom `send_file([...])` orqali, matnli post `link_preview` bayrog'i bilan ketadi. Kunlik limit/faol soat yoqilsa, yuborishlar o'sha oynaga moslashadi |
| Media disk | 🟡 o'rta | Albomlar bilan fayllar soni o'sadi. Har user uchun kvota: `MAX_MEDIA_FILES_PER_USER` (standart 200) |

Barcha yangi funksiya testlangan: **476 test** (`python -m unittest discover -s tests -t tests`).

### 🆕 «🔍 Guruhlarni topish» skaneri — tez, izolyatsiyalangan, havolali

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| Parallel huquq tekshiruvi | 🟢 past | Oldin har bir guruh uchun `get_permissions` **ketma-ket** chaqirilardi (har biriga 1–3 s pauza). Endi `DISCOVER_BATCH_SIZE` (standart **8**) ta guruh **bir vaqtda** tekshiriladi. Skaner bir necha barobar tezlashadi |
| Alohida client | 🟢 past | Skaner endi **alohida** TelegramClient ishlatadi (posting clientidan alohida). Oldin bitta client bo'lgani uchun skaner davomida **shu foydalanuvchining posting'i** sekinlashardi. Endi ikkalasi **parallel** ishlaydi |
| Ochiq havolalar | 🟢 past | Topilgan guruhlar ro'yxatida endi **`https://t.me/username`** ko'rinadi (xabar matnida, sahifa bo'yicha). Tugma matni 64 belgi limiti tufayli qisqa qoldirilgan |
| Qisqartirilgan pauza | 🟡 o'rta | Guruhlar orasidagi pauza `1–3 s` dan **`0.05–0.25 s`** ga tushirildi. Telegram FloodWait xavfi shuning uchun **batch'lar orasida** `DISCOVER_BATCH_PAUSE_S` (standart `0.4 s`) saqlanadi |
| Alohida client limiti | 🟢 past | Bir vaqtda faqat `MAX_ISOLATED_CLIENTS` (standart **10**) ta alohida client ishlaydi. Limit to'lsa foydalanuvchi **kutilmaydi** — darhol xabar oladi |

**Yangi sozlamalar** (`.env` da, ixtiyoriy):

```env
DISCOVER_BATCH_SIZE=8            # bir vaqtda tekshiriladigan guruhlar soni (1–20)
DISCOVER_BATCH_PAUSE_S=0.4       # batch'lar orasidagi pauza (soniya)
DISCOVER_PERMISSION_TIMEOUT_S=20 # bitta guruh tekshiruvining limiti
DISCOVER_PROGRESS_EVERY=10       # progress xabari qancha guruhdan keyin
MAX_ISOLATED_CLIENTS=10          # bir vaqtda alohida client'lar limiti
```

**Nima uchun muhim:** avval bitta foydalanuvchi skaner bosganda, uning
**o'z posting'i** ham sekinlashardi (bir client — ketma-ket RPC) va skaner
**bir necha daqiqa** davom etardi. Endi skaner tez, alohida va boshqa
foydalanuvchilarga **ta'sir qilmaydi**.

### 🆕 Foydalanuvchi lock'lari — collision yo'q

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| `core/update_locks.py` | 🟢 past | Lock'lar avval `uid % 256` (striped) uslubida taqsimlanardi. Natijada `uid=1` va `uid=257` **bir xil** lock'ni olardi — bitta foydalanuvchi uzoq amal qilsa, ikkinchisi **kutib qolardi**. Endi lock'lar **aybiga** yaratiladi va `WeakValueDictionary` bilan saqlanadi (faol bo'lmagan lock'lar xotiradan o'chadi) |

### 🆕 💬 Foydalanuvchining o'z guruhlarini boshqarish oynasi

Super admin allaqachon foydalanuvchining guruhiga **alohida interval** qo'yish
huquqiga ega (`uc:` prefiksi). Endi **foydalanuvchining o'zi ham** o'z guruhiga
alohida interval qo'yishi mumkin — **bitta sodda oynada**.

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| Asosiy menyu | 🟢 past | Endi `💬 Guruhlar` va `⏱ Guruh intervali` tugmalari bor. Eski `➖ Guruh o'chirish` tugmasi olib tashlandi (ikki xil oyna chalkashuv keltirardi) — u ham `💬 Guruhlar` oynasiga yo'naltiriladi |
| Yangi oyna (`bot/my_groups.py`) | 🟢 past | Bitta inline oyna: har guruh yonida `⏱ X daq` (alohida interval) va `🗑 N. guruh` (o'chirish). Yuqorida `🔍 Guruhlarni topish` va `⏱ Umumiy interval` |
| Super admin o'z guruhlari | 🟢 past | Super admin uchun bu oyna **ishlamaydi** — u allaqachon `uc:` orqali har bir foydalanuvchining guruhini boshqaradi. `mg:` prefiksi super admin'dan **himoyalangan** |
| Izolyatsiya | 🟢 past | Foydalanuvchi **faqat o'z** guruhlarini ko'radi va o'zgartiradi — `mg:` callback'lari `db.get_chat_record(uid, ...)` orqali tekshiriladi |

### 🆕 Tasdiqlash xabarlari — foydalanuvchini kechiktirmasligi

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| `bot/login.py` | 🟢 past | Yangi foydalanuvchi login tugagach, tasdiqlovchiga xabar `await` bilan yuborilardi. Telegram sekin bo'lsa (timeout ~30 s) foydalanuvchi **javobsiz** qolardi. Endi xabar **fon task**'ida yuboriladi |
| `bot/teams.py` | 🟢 past | Yangi jamoa admini o'z jamoasini yaratgach, super admin'ga xabar yuborilardi — xuddi shu muammo. Endi foydalanuvchi **avval** tasdiqlanadi, xabar **keyin** yuboriladi |
| Fon task xatolari | 🟢 past | Task ichidagi xatolar yutiladi va logga yoziladi (unhandled task yo'q) |

**Nima uchun muhim:** bu ikki joy — foydalanuvchining **eng ko'p kutadigan** joylari
(kirish va jamoa yaratish). Telegram javob bermay qolsa, foydalanuvchi bot
"ishlamayapti" deb oylardi. Endi foydalanuvchi **darhol** javob oladi.

### 🆕 Bot bir vaqtda o'lmasligi (startup barqarorligi)

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| `set_my_commands` | 🟢 past | Endi `set_bot_commands()` orqali chaqiriladi — xato bo'lsa **yutiladi**, bot ishlashda davom etadi. Oldin bitta timeout butun botni o'ldirardi |
| `app.initialize()` | 🟢 past | `_with_retry()` — 3 urinish, oralig'ida kutish. Telegram vaqtincha javob bermasa, bot **avtomatik** ulanadi |
| `start_polling()` | 🟢 past | Xuddi shunday retry bilan |

**Nima uchun muhim:** Telegram API vaqtincha javob bermay qolsa (`TimedOut`,
`NetworkError`, `Bad Gateway`), oldingi kodda bot **butunlay to'xtardi** —
foydalanuvchilar javob olmagan holda postlarni ko'rishda davom etardi.
Endi bunday holatda bot **o'z-o'zidan tiklanadi**.

### 🆕 Telegram API ulanishi (bot "javob bermaydi" muammosi)

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| `connection_pool_size` | 🟢 past | PTB standart qiymati **1** edi. Long-polling (`getUpdates`, serverda 10s kutadi) connection'ni band qilib, javob yuborish so'rovlarini "pool timeout" bilan uzardi. Endi **20** (`.env` dan `TELEGRAM_CONNECTION_POOL_SIZE` bilan o'zgartiriladi) |
| `read_timeout` / `get_updates_read_timeout` | 🟢 past | Standart `5s` edi — `getUpdates` 10s kutsa timeout berib, polling to'xtardi. Endi `30s` / `40s` |
| `pool_timeout` | 🟢 past | Standart `1s` edi — javoblar polling paytida uzilib ketardi. Endi `30s` |
| Polling supervisor | 🟢 past | Polling task'i to'xtasa (Telegram `Bad Gateway`, `TimedOut`), supervisor uni avtomatik qayta boshlaydi. Bot bir marta o'chib qolmaydi |

**Qo'shimcha `.env` sozlamalari** (ixtiyoriy — standart qiymatlar yetarli):

```
TELEGRAM_CONNECTION_POOL_SIZE=20
TELEGRAM_READ_TIMEOUT=30
TELEGRAM_WRITE_TIMEOUT=30
TELEGRAM_CONNECT_TIMEOUT=15
TELEGRAM_POOL_TIMEOUT=30
TELEGRAM_GET_UPDATES_READ_TIMEOUT=40
TELEGRAM_GET_UPDATES_POOL_TIMEOUT=30
```

**Tekshirish (serverda):**

```bash
journalctl -u avtobot3.service --since "10 minutes ago" --no-pager | grep -iE "polling|timed out|networkerror"
```

`⚠️ Polling to'xtadi ... qayta boshlanadi` xabari chiqsa — supervisor ishlayapti (bu normal, u tiklaydi).

### 🆕 Jamoa (team) tizimi

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| `teams` jadvali | 🟢 past | `CREATE TABLE IF NOT EXISTS` — mavjud foydalanuvchilar jamoasiz qoladi va eski tartibda ishlaydi |
| `users` ustunlari | 🟢 past | `team_id`, `owner_admin_uid`, `is_team_admin`, `admin_expires_at`, `admin_max_users` — `ALTER TABLE ADD COLUMN`, eski yozuvlarda `NULL`/`0` |
| Referal bonuslari | 🟢 past | `REFERRAL_BONUS_DAYS=0` — **yangi bonus kunlar berilmaydi**. Berilgan kunlar (`referral_bonus_days`) o'chirmaydi, saqlanadi |
| Video media | 🟢 past | `ALLOW_VIDEO_MEDIA=0` — video yuborish rad etiladi, faqat surat. Eski saqlangan video postlar o'z-o'zidan yuborilmaydi (albatta ular `send_video` orqali yuboriladi — kerak bo'lsa `ALLOW_VIDEO_MEDIA=1` qo'ying) |
| Albom limiti | 🟡 o'rta | `MAX_ALBUM_FILES` 10 → **4**. Albomlar kichraydi, xotira va trafik kamayadi |
| `team_invites` jadvali | 🟢 past | `CREATE TABLE IF NOT EXISTS` — do'st qo'shish va yangi admin takliflari uchun. Eski ma'lumotga tegilmaydi |
| Muddat chegarasi | 🟢 past | `TEAM_MEMBER_MAX_DAYS=60` — jamoa admini a'zosiga maksimal 60 kun. `SUPER_ADMIN_MAX_DAYS=0` — super admin chegarasiz |
| Tasdiqlash oqimi | 🟡 o'rta | Endi tasdiqlash **ikki bosqichli**: avval muddat tanlanadi, keyin tasdiqlash. Avvalgi avtomatik 30 kun o'rniga tanlangan muddat beriladi |
| Jamoadan chiqish | 🟢 past | Oddiy jamoa a'zosi jamoasidan chiqishi mumkin — **jamoa muddati ham tugaydi**. Jamoa egasi chiqmaydi |
| Jamoadan chiqarish | 🟢 past | Jamoa admini a'zoni jamoasidan chiqaradi (a'zo kartasidagi `🚪` tugmasi) |
| Jamoani topshirish | 🟢 past | Super admin jamoani boshqa jamoa adminga o'tkazadi — a'zolar, sig'im va muddat yangi admin ostiga o'tadi |
| Guruhlarni topish oqimi | 🟡 o'rta | **O'zgarish:** endi hech qanday guruh avtomatik qo'shilmaydi — topilgan guruhlar ro'yxat qilib ko'rsatiladi (sahifalash, 15 ta/sahifa), foydalanuvchi ✅ belglaydi, faqat belgilanganlar qo'shiladi |
| Do'stlar ro'yxati | 🟢 past | Taklif qilingan raqamlar ro'yxati + bekor qilish (`🗑`) |
| Bloklash ta'siri | 🟢 past | Jamoa admini bloklansa — **butun jamoa** to'xtaydi, a'zolar xabar oladi |
| Muddat indikatorlari | 🟢 past | ⌛ — muddati tugagan (a'zo va jamoa admini ro'yxatlarida) |
| Jamoa admini tasdiqi | 🟢 past | Jamoani yaratgan admin **darhol tasdiqlangan** bo'ladi — tasdiq kutilmaydi, oddiy user kabi posting qiladi |
| «👑 Admin bo'lish» tugmasi | 🟢 past | Tugma asosiy menyuning oxirgi qatoriga qo'shildi (jamoasiz user uchun `🎯 Jamoani tanlash` bilan bir qatorda). Tugma **login'dan oldin ham** ishlaydi — ro'yxatdan o'tmagan, tasdiqlanmagan yoki sessiyasiz user ham jamoasini yaratishi mumkin. Kirish oynasida tugma bosilsa, kiritish oynasi bekor qilinadi va jamoa oqimi boshlanadi (avvalgi xatoda u telefon raqam sifatida qabul qilinardi) |
| Jamoa sig'i | 🟢 past | Jamoa to'lgan bo'lsa yangi a'zo biriktirilmaydi (`assign_team_member` / `set_team_pending` ham tekshiradi) — limit oshishi mumkin emas |
| Super admin paneli | 🟢 past | Bo'sh jamoa adminlari ro'yxatida ham «➕ Admin qo'shish» tugmasi ko'rinadi — birinchi jamoa adminini qo'shish uchun |

> ℹ️ Jamoa tizimi **ixtiyoriy**: foydalanuvchi jamoa tanlamasa, oddiy user
> sifatida ishlaydi. Jamoa adminlari faqat o'z jamoalariga ta'sir qiladi.

### ⚠️ Foydalanuvchi uchun muhim o'zgarish

**🔍 Guruhlarni topish** endi boshqacha ishlaydi:

| Oldin | Endi |
| ----- | ---- |
| Bitta tugma → barcha guruhlar avtomatik qo'shilib, **darhol e'lon yuborish** boshlanardi | Tugma → guruhlar **topiladi va ro'yxat ko'rsatiladi** → foydalanuvchi **✅ belgilaydi** → **faqat belgilanganlar** qo'shiladi |

Foydalanuvchilar uchun bu **xavfsizlik** — keraksiz guruhlarga avtomatik
xabar yuborilmaydi. **Belgilanmagan guruhlar hech qachon qo'shilmaydi.**

Texnik o'zgarish: yangi modul `bot/discover_sessions.py` (vaqtinchalik tanlov
sessiyasi, 30 daqiqa) va yangi inline callback'lar (`disc:toggle`, `disc:page`,
`disc:apply`, `disc:cancel`). **Baza sxemasi o'zgarmadi** — yangi jadval
qo'shilmadi.

> ℹ️ Tanlov sessiyasi **jarayon ichida** saqlanadi (xotira). Server
> qayta ishga tushsa, foydalanuvchi «🔍 Guruhlarni topish» ni qayta bosadi —
> ma'lumotlar yo'qolmaydi, chunki hech narsa saqlanmagan edi.

## 2. Chiqarish tartibi

> ℹ️ Repozitoriyada systemd unit yoki Dockerfile yo'q — bot odatda
> `python main.py` (screen/tmux orqali) yoki siz qo'ygan servis bilan yuriladi.
> Quyidagi buyruqlarda servis nomini o'zingizniki bilan almashtiring.

```bash
cd /opt/avtobot/AVTOBOT2026        # loyiha papkangiz

# 0) Python 3.10+ va joy borligini tekshirish
python3 -V; df -h . | tail -1

# 1) ZAXIRA — majburiy (baza + konfiguratsiya; media hajmini qayd eting)
systemctl stop avtobot              # yoki: pkill -TERM -f "python.*main.py"
cp data/avtobot.db data/avtobot.db.$(date +%F-%H%M)
tar czf backup-files.$(date +%F).tar.gz data config/.env
du -sh media data logs

# 2) KODNI YANGILASH
git fetch origin
git checkout main && git pull       # PR#9 merj qilingan bo'lsa
# yoki merj hali bo'lmasa:
#   git checkout arena/d719d88b-avtobot2026 && git pull

# 3) BOGLIQLIKLAR (yangi paket yo'q, lekin baribir)
source venv/bin/activate
pip install -r requirements.txt

# 4) KONFIGURATSIYA — .envga yangi kalitlarni qo'shish (ixtiyoriy)
#    1-bosqichda HECH QANDAY limit yoqmagan ham yaxshi: eski xatti-harakat qoladi.
nano .env
#
#    Jamoa tizimi uchun (standart qiymatlar bilan ham ishlaydi):
#      TEAM_ADMIN_DEFAULT_DAYS=30     # jamoa admini muddati (kun)
#      TEAM_MIN_MEMBERS=2             # minimal jamoa hajmi
#      ALLOW_VIDEO_MEDIA=0            # 0 = video rad etiladi (faqat surat)
#      MAX_ALBUM_FILES=4              # bitta postga maksimal rasm soni
#      REFERRAL_BONUS_DAYS=0          # bonus kunlari berilmaydi
#
#    Muddat chegarasi (anti-fraud) — jamoa admini a'zosiga maksimal kun:
#      TEAM_MEMBER_MAX_DAYS=60        # jamoa admini uchun chegara (0 = cheksiz)
#      SUPER_ADMIN_MAX_DAYS=0         # super admin uchun chegara (0 = cheksiz)

# 5) START
systemctl start avtobot && journalctl -u avtobot -f
# servis bo'lmasa:
#   screen -S avtobot -d -m python main.py
#   tail -f logs/avtobot.log
```

Baza fayli yozish uchun yoziladigan holatda bo'lishi kerak (`data/` va
`logs/` papkalari bot ishlaydigan foydalanuvchiga tegishli bo'lsin):
`ls -ld data logs media`.

## 3. Logda ko'rish kerak bo'lgan birinchi qatorlar

```
Baza tayyor                                  ← migratsiya muvaffaqiyatli
🟢 Worker:<uid> ishga tushdi                 ← workerlar qayta tiklandi
⚡ Avto-tasdiq o'chirilgan (admin navbati)    ← AUTO_APPROVE_ENABLED=0 (standart)
```

Agar `Baza tayyor` chiqmasa yoki `no such column` xatosi bo'lsa — servisini
to'xtatib, zaxiradan `.db` faylini qaytaring (kod eski bazani buzmaydi,
shuning uchun xato bo'lsa sabov izlang, o'chirmang).

## 4. Qo'lda tekshirish (5 daqiqa)

1. `/start` → menyu ochiladi, tugmalar soni eski holat bilan bir xil.
2. **📝 Postlar → ➕ Post qo'shish** → 3 ta rasmni **birga** (albom qilib)
   yuboring → «🖼 3 ta media yig'ildi» va **✅ Tayyor** tugmasi; tugmani
   bosmasangiz ham ~2 soniyadan keyin post saqlanadi.
3. **👁 Ko'rinish** — post o'z shaxsiy chatingizga chiqadi (guruhga chiqmaydi).
4. **🧪 Sinov yuborish** → bitta guruh + «✅ Ha» tasdig'i → bir marta yuboriladi.
5. **💬 Guruhlar → 🔎 Guruhni tekshirish** → aniq javob: ✅ tayyor yoki
   ⚠️ «bot chiqarilgan / yozish taqiqlangan / guruh topilmadi».
6. **📈 Hisobot** va **📊 Status** — «Bugun ✅/❌» sonlari `logs`dagi
   `📊 <uid> ✅N ❌M` qatori bilan mos kelishi kerak.
7. **⚙️ Hisob → 🔑 sessiya** — eski sessiyalar ishlamoqda (login talab qilinmaydi).

## 5. Limitlarni bosqichma-bosqich yoqish (tavsiya)

Foydalanuvchi akkauntini Telegram cheklamasin uchun eng foydali sozlamalar,
lekin ularni **birdan emas**, tartib bilan yoqing:

```bash
# 1-hafta: faqat himoya (eski userlarga tegmaydi, yangi userlar uchun)
USER_DAILY_LIMIT_DEFAULT=150
ACTIVE_HOURS_DEFAULT=08:00-23:00

# 2-hafta: paketchilar (admin panel → ⚙️ Tarif va limitlar orqali ham qo'yiladi)
DEFAULT_PLAN=SINOV          # 5 guruh / 2 post / 30 yuborish-kuniga

# 3-qadam: navbatni kamaytirish
AUTO_APPROVE_ENABLED=1
AUTO_APPROVE_MAX_RISK=2     # faqat past riskli arizalar
```

⚠️ Xavfsizlik formulasi: **guruhlar × (15 soat × 60 ÷ interval_daqiqa) ≤ kunlik limit**.
Masalan 60 guruh va 30 daqiqa interval = 60 × 30 = 1800 kunlik urinish — bu
juda ko'p; intervalni kamida 60–90 daqiqaga qo'ying yoki kunlik limitni
150–200 atrofida ushlang (bot tungi tanaffus bilan himoya qiladi).

## 6. Kuzatish (birinchi 48 soat)

```bash
journalctl -u avtobot --since "2 hours ago" | grep -E "FloodWait|cheklov|❌|💥" | tail -30
du -sh media                                # albomlar tufayli o'sish sur'ati
sqlite3 data/avtobot.db "SELECT COUNT(*) FROM send_logs;"           # hisob o'sishi
sqlite3 data/avtobot.db "SELECT uid, SUM(ok), COUNT(*) FROM send_logs GROUP BY uid ORDER BY 3 DESC LIMIT 5;"
```

* `send_logs` avtomatik tozalanadi (`SEND_LOG_RETENTION_DAYS`, standart 30 kun);
  xohlasangiz `SEND_LOGS_ENABLED=0` bilan butunlay o'chiring.
* Xato ulushi (`❌`) 10% dan oshsa — foydalanuvchilarga intervalni oshirish
  yoki guruhlar sonini kamaytirish bo'yicha xabar chiqarish vaqti yetdi.

## 7. Orqaga qaytish

```bash
systemctl stop avtobot
git checkout c0ff414            # yangi bosqichdan oldingi commit (yoki main)
cp data/avtobot.db.$(date +%F-%H%M) data/avtobot.db   # zarur bo'lsagina
systemctl start avtobot
```

Qo'shilgan ustunlar eski kodga xalaqit bermaydi (u ularni o'qimaydi),
shuning uchun `.db` faylini tiklash **shart emas**. Bitta eslatma: yangi
kodda yaratilgan **albom postlar** eski kodda faqat birinchi rasm bilan
ko'rinadi (media ro'yxati `posts.photo`ga moslab saqlanganligi uchun buzilmaydi).

## 8. Ma'lumki "yo'q" narsalar (keyingi bosqich)

* Onlayn to'lov (Payme/Click) va avto-uzaytirish — hozircha admin orqali;
* Bir Telegram hisobiga bir nechta akkaunt;
* Kampaniya havolalari (`?start=src_kod`) va admin grafiklari.

Batafsil: [`TAKLIFLAR_ROADMAP.md`](TAKLIFLAR_ROADMAP.md) (0.1-bo'lim).
