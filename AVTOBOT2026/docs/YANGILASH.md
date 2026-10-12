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

Barcha yangi funksiya testlangan: **233 test** (`python -m unittest discover -s tests -t tests`).

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
