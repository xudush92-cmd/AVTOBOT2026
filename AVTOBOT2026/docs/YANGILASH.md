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

Barcha yangi funksiya testlangan: **656 test** (`python -m unittest discover -s tests -t tests`).

### 🆕 Guruh nomi **hamma oynalarda** (PR #44)

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| **`db.get_chat_record()`** | 🟢 past | `SELECT` ro'yxatiga `title` qo'shildi — bitta guruhni ko'rsatadigan oynalar endi **nomni** oladi (avval ID chiqardi) |
| **Interval oynasi** | 🟢 past | Tugmalarda **nom**: `КАНГЛИ ЯККА ТУРОНГИЛ МФЙ · Umumiy 6 daq` (avval `-1003119200089 · Umumiy 6 daq`) |
| **O'chirish** | 🟢 past | Xabar va ro'yxatda **nom** — `🗑 O'chirildi: QARNDOSHLAR` |
| **`group_label()`** | 🟢 past | Logika `core/utils.py` ga ko'chirildi — hamma oynada **bir xil** natija |

> 📌 **Baza sxemasi o'zgarmadi** — yangi ustun/jadval yo'q.
> 📌 **Worker / posting / Start / Stop** tegilmadi.
> 📌 **Yopiq guruh ID'si** hech qayerda ko'rsatilmaydi (avvalgi maxfiylik saqlanadi).

### 🆕 Guruh nomi (title) — bazadan tugma matnigacha (PR #41)

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| **Baza sxemasi** | 🟢 past | Faqat **bitta ustun** qo'shiladi: `ALTER TABLE groups ADD COLUMN title TEXT DEFAULT ''`. Eski guruhlar uchun `title` bo'sh bo'ladi — ma'lumot o'chmaydi, ko'chirilmaydi |
| **`🗑` tugmasi** | 🟢 past | Endi guruh **nomi** ko'rinadi (`🗑 1. Taxi Xorazm Toshken`) — foydalanuvchi qaysi guruhni o'chirmoqchi ekanini aniq biladi. Nomi yo'q bo'lsa — username |
| **Ro'yxat** | 🟢 past | `1. Taxi Xorazm Toshken — https://t.me/taxi_x` — nom va havola birga |
| **Yopiq guruhlar** | 🟢 past | Marked ID (`-100123...`) **ko'rsatilmaydi** — avvalgi maxfiylik saqlanadi |
| **Telegram so'rovi** | 🟢 past | Nom olish **fon task**da — foydalanuvchi kutmaydi. Qo'lda kiritish oqimi tez va Telegram'siz ishlaydi (avvalgi kafolat saqlanadi) |
| **Skaner** | 🟢 past | Skanerda topilgan guruh nomi (`group.title`) **darhol** bazaga saqlanadi |

> 📌 **Yangi sozlamalar yo'q** — `.env` ga hech narsa qo'shish shart emas.
> 📌 **Worker / posting / Start / Stop** tegilmadi.

### 🆕 «💬 Guruhlar» oynasi UX tuzatishlari (PR #40)

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| **Qo'shilgan guruhlar ko'rinmaydi** | 🟢 past | Oyna yangilanganda faqat «💬 GURUHLAR» sarlavhasi qolardi — ro'yxat va havolalar yo'qolardi. Endi matn/markup `build_groups_window()` da yig'iladi va `mg:del`, `mg:page`, `disc:apply` — hammasi **bir xil to'liq oynani** ko'rsatadi |
| **«🔍 Guruhlarni topish» ikki joyda** | 🟢 past | Inline oynadagi takror tugma olib tashlandi. Endi skaner **faqat asosiy menyuda**. (`mg:find` handler saqlanadi — eski xabarlardan bosilsa ham ishlasin) |
| **«🚫 Bekor qilish» oynani yopmaydi** | 🟢 past | Xabar endi **o'chiriladi**, «Bekor qilindi» deb qolmaydi. Xuddi shunday `mg:back` ham oynani o'chiradi |
| **Qo'shishdan keyin guruhlar ko'rinmaydi** | 🟢 past | `disc:apply` endi hisobot bilan birga **yangilangan «💬 Guruhlar» oynasini** ko'rsatadi (agar xabar tahrirlab bo'lmasa — yangi xabar yuboriladi) |
| **Skaner takror guruh ko'rsatadi** | 🟢 past | Filtr allaqachon ishlaydi (`existing_keys`); bu PR da o'zgartirilmadi, faqat **regressiya testi** qo'shildi |

> 📌 **Yangi sozlamalar yo'q** — `.env` ga hech narsa qo'shish shart emas.
> 📌 **Baza sxemasi o'zgarmadi** — yangi jadval/ustun qo'shilmadi.
> 📌 **Worker / Start / Stop / admin-jamoa izolyatsiyasi** tegilmadi.

### 🆕 Guruhni belgilash (✅) tugmasi tuzatildi (PR #39)

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| **✅ belgi chiqmaydi** | 🟢 past | `disc:` prefiksi `ordinary_prefixes` ro'yxatida bor, lekin uning `elif` branch'i zanjirda **yo'q** edi. Shu sabab `disc:toggle` hech qanday handler'ga yetib bormaydi — tugma umuman ishlamaydi. Endi `"disc:"` ro'yxatdan chiqarilgan |
| **Xatolik belgisi yo'q** | 🟢 past | Sabab topildi: na ✅ belgi, na alert, na logda xato. Sabab — xato emas, kod **yetib borilmagan** |
| Kelinglik uchun himoya | 🟢 past | `tests/test_callback_router_coverage.py` — router'dagi har bir prefix kamida bitta branch'da qamralganini **avtomatik** tekshiradi. Bu tipdagi «o'lik zona» qaytmaydi |

> 📌 **Yangi sozlamalar yo'q** — `.env` ga hech narsa qo'shish shart emas.

### 🆕 Inline tugmalar va markaziy xato logi (PR #38)

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| **«🔍 Guruhlarni topish» ishlamaydi** | 🟢 past | `mg:find` — inline callback, lekin `discover_groups` `update.message.reply_text` ishlatardi. Inline kontekstda `update.message` = `None` → `AttributeError`. VPS logida tasdiqlangan. Endi `reply_text_safe` ishlatiladi |
| **«✏️ Jamoa nomi» / «📨 Xabar yuborish» ishlamaydi** | 🟢 past | `edit_message_text` faqat Inline klaviatura qabul qiladi, lekin Reply klaviatura berilardi → `BadRequest: Inline keyboard expected`. Endi `kb_input_cancel_inline()` ishlatiladi |
| **«⏰ Vaqt» oynasi inline kontekstda** | 🟢 past | `mg:global` → `begin_set_interval` — xuddi shu tipdagi xato. `reply_text_safe` bilan tuzatildi |
| **Xatolar logga to'liq yozilmaydi** | 🟢 past | Yangi `core/errlog.py`: `log_error()` (to'liq traceback), `log_gap()` (kamchilik), `log_event()`. Matnli xabar va PTB handler xatolari ham ushlanadi |
| Log hajmi | 🟢 past | Aylanma 5 MB × 4 = **20 MB chegara**. Xato ~2 KB; 100 xato/kun → ~200 KB/kun (**~0.3%**) |

> 📌 **Yangi sozlamalar yo'q** — `.env` ga hech narsa qo'shish shart emas.
> 📌 **Worker / Start / Stop** logikasi tegilmadi — `running` o'zgarishlari yo'q.

### 🆕 Jamoa statistikasi, navigatsiya va referal tozalash (PR #37)

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| **Statistika «Xatolik yuz berdi»** | 🟢 past | `tadm:stats` da `sum(await db.count_chats(...) for m in members)` ishlatilgan — bu **async generator** yaratadi va `TypeError: 'async_generator' object is not iterable` beradi. Endi aniq `await` sikli bilan ketma-ket hisoblanadi. **Bu live'da kuzatilgan xatoning eng ehtimoliy sababi** |
| Statistika sonlari | 🟢 past | «Foydalanuvchilar» soni endi jamoa asosisiz — panel va ro'yxat bilan mos keladi |
| Ichki oynalardan «Orqaga» | 🟢 past | A'zolar / takliflar / statistika oynalaridagi «Orqaga» endi `tadm:back` (asosiy menyu) emas, **`tadm:panel` → jamoa admini paneli**. Panelning o'zidagi «Orqaga» esa asosiy menyuga qaytadi |
| Eski oyna chatda qolishi | 🟢 past | `reply_text_safe()` ga **`in_place=True`** (keyword-only) parametri qo'shildi — inline kontekstda mavjud xabarni **o'zida tahrirlaydi**. Panel va asosiy menyu eski oynani almashtiradi. Standart `reply` semantikasi saqlanadi |
| Jamoa admini referal oynasi | 🟢 past | Jamoa adminida endi **faqat umumiy jamoa havolasi** ko'rsatiladi — shaxsiy `ref_<uid>` havolasi, «Havolani ochish»/«Do'stlarga yuborish» tugmalari va referal statistikasi olib tashlandi. **Oddiy foydalanuvchilar o'zgarishsiz** |
| Ro'yxatdagi son | 🟢 past | `count_team_members(team_id, *, include_admin=True)` — standart holatda **sig'im** hisobi o'zgarmaydi (admin hisobda), `include_admin=False` esa **ko'rsatiladigan** son uchun |

> 📌 **Yangi sozlamalar yo'q** — `.env` ga hech narsa qo'shish shart emas.
> 📌 **Worker / Start / Stop** logikasi tegilmadi — `running` o'zgarishlari yo'q.

### 🆕 Jamoa kontakti, nomlash va havola tuzatishlari (PR #36)

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| Kim tasdiqlaydi | 🟢 past | **O'zgarmadi** — jamoa a'zosini **jamoa admini** tasdiqlaydi, jamoasiz foydalanuvchini **super admin**. Super admin jamoa admini funksiyalariga aralashmaydi |
| A'zoga ko'rsatiladigan telefon | 🟢 past | Avval **har kimga** super adminning raqami ko'rsatilardi (`LOGIN_SUCCESS_PENDING` — bitta matn). Endi uch holat bor: jamoa a'zosiga **jamoa adminining** raqami, jamoasiz foydalanuvchiga super admin raqami, jamoa asosiga **umuman raqam ko'rsatilmaydi** |
| Jamoa asosining xabari | 🟢 past | Jamoa asosi (jamoa admini) allaqachon tasdiqlangan — avval unga «admin tasdiqini kutilmoqda + super admin raqami» xabari bor edi. Endi «👑 Siz jamoa admini bo'ldingiz!» xabari + jamoa havolasi bor. Unga «yangi ariza» xabari ham yuborilmaydi |
| Shaxsiy jamoa havolasi | 🟢 past | `admin_link()` va `adm_<uid>` deep link **olib tashlandi**. Jamoalarda faqat **umumiy** `team_<id>` havolasi qoldi. Jamoa admini boshqa jamoaga a'zo qo'sha olmaydi (`owner_admin_uid` tekshiruvi saqlanadi) |
| Super admin → jamoa yo'naltirish | 🟢 past | Yangi: **«👥 Jamoaga biriktirish»** tugmasi. Super admin faqat **yo'naltiradi**, tasdiqlaydi emas — jamoa admini tasdiqlaydi (shuning uchun a'zo o'sha jamoa adminining raqamiga murojaat qiladi) |
| Jamoa nomini o'zgartirish | 🟢 past | Super admin yaratgan jamoalar avval `Jamoa #<uid>` nomi bilan qolardi va admin uni o'zgartira olmasdi. Endi jamoa admini panelida **«✏️ Jamoa nomi»** tugmasi bor (2–40 belgi, o'z jamoalari orasida band bo'lmasligi tekshiriladi) |
| Jamoa admini o'z ro'yxatida | 🟢 past | Jamoa asosi endi «👥 Foydalanuvchilar» ro'yxatida **ko'rinmaydi**. Statistika va sig'im hisobida jamoa asosi jamoaning a'zosi sifatida hisobga olinadi |
| Jamoa admini «Orqaga» tugmasi | 🟢 past | Avval `tadm:back` → o'z-o'ziga qaytardi (ko'rinish o'zgarmasdi). Endi **asosiy menyuga** qaytaradi |

> 📌 **Yangi sozlamalar yo'q** — `.env` ga hech narsa qo'shish shart emas.

### 🆕 Restartda posting to'xtamaydi — worker avtomatik tiklanadi

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| `running` bayrog'i restartda to'xtardi | 🟢 past | VPS da kod yangilanganda (`systemctl restart`) `posting_loop` ning `finally` bloki `set_running(uid, False)` qilardi. Natijada foydalanuvchining e'lonlari **to'xtab qolardi** va u qaytadan `▶️ Start` bosishi kerak edi. Endi jarayon to'xtayotganda (`SIGTERM`) `running` **saqlanadi** va yangi process'da `restore_running_workers()` worker'ni **avtomatik tiklaydi** |
| `⛔ Stop` bosgan foydalanuvchilar | 🟢 past | Foydalanuvchi **o'zi** `Stop` bosgan bo'lsa, `running` `False` qilinadi — u restartda **avtomatik tiklanmaydi**, to'xtab tursin |
| Jitter paytidagi `Stop` | 🟢 past | `start jitter` kutish paytida `Stop` bosilsa, `finally` bloki ishlamasdi (`return` `try` dan tashqarida edi) va `running` `True` qolardi — ya'ni to'xtagan foydalanuvchi restartda tiklanib ketardi. Endi jitter `try` blokiga ko'chirilgan |
| Holat ko'rinishi | 🟢 past | Asosiy menyu ustida `🟢 Posting ishlamoqda` / `🔴 Posting to'xtatilgan` qatori ko'rsatiladi. `▶️ Start` va `⛔ Stop` tugmalari **doimiy va alohida** qoladi — holat ularning matnini o'zgartirmaydi |

### 🆕 Polling supervisor tuzatildi — bot javob bermay qolmasin

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| `contextlib.suppress` bilan yashirilgan xatolar | 🟢 past | Supervisor polling'ni qayta ishga tushirganda `stop()`, `initialize()`, `start_polling()` xatolari **yashirilardi**. `stop()` xatosi yashirilganda PTB ichki `_running` bayrogi `True` bo'lib qolardi va `start_polling()` "This Updater is already running!" bilan urilardi — supervisor esa har siklda "✅ Polling qayta boshlandi" deb yozib, **polling haqiqatan ishlamasdi** |
| Xato matni logda yo'q | 🟢 past | Logda faqat `RuntimeError` **klassi** ko'rinardi, matni yo'q. Endi `({type}: {exc})` ko'rinadi — sababni darhol aniqlash mumkin |
| `_running` qoldig'i | 🟢 past | `stop()` xatosidan keyin `_running` qoldig'i `True` bo'lsa, u tozalanadi |

**Yangi yordamchi:** `main.py::_restart_polling()` — to'rt qadam (`stop` → `_running` tozalash → `initialize` → `start_polling`) alohida tekshiriladi, xatolar **yashirilmaydi** va logga yoziladi.

### 🆕 Eski ichki menyular tozalandi (minimal UI — yakuniy)

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| `kb_groups_menu()` / `kb_posts_menu()` | 🟢 past | Eski alohida «Guruhlar» va «Postlar» **ichki** menyulari butunlay olib tashlandi. Ularning o'rniga: `💬 Guruhlar` — yangi inline boshqaruv oynasi (havolalar + `🗑 N. guruh`), qolgan joylarda — asosiy menyu |
| `gchk:back` | 🟢 past | Guruhni tekshirish oynasidan orqaga qaytish endi eski menyuga emas, **yangi inline** `💬 Guruhlar` oynasiga qaytadi |
| `/help` matni | 🟢 past | `📈 Hisobot` (olib tashlangan funksiya) va `video` (rad etiladigan format) eslatilishlari olib tashlandi — matn endi haqiqiyga mos |
| Post qo'shish ko'rsatmasi | 🟢 past | «Bitta rasm / **video** / fayl» → «Bitta rasm yoki fayl» (video rad etiladi) |

Eski tugmalar (`➕ Guruh qo'shish`, `🔎 Guruhni tekshirish`, `⏱ Guruh intervali`,
`✏️ Postni tahrirlash`, `👁 Ko'rinishi`, `🧪 Sinov yuborish`) foydalanuvchi
ekranida **ko'rinmaydi**.

### 🆕 Jamoa adminiga haqiqiy jamoa + sekin rejim (slow mode) ishlovi

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| Avtomatik jamoa yaratish | 🟢 past | Super admin jamoa adminini tayyorlaganda uning uchun **haqiqiy jamoa** yaratiladi va admin darhol shu jamoaga bog'lanadi (`team_id` 0 bo'lmaydi). Jamoa nomi avtomatik (`Jamoa #<uid>`) — har bir adminning jamoasi **unikal**. Admin allaqachon jamoaga bog'langan bo'lsa, mavjudi saqlanadi (ikkinchisi yaratilmaydi) |
| `SlowModeWaitError` | 🟢 past | Telegram'dagi guruh "sekin rejimi" endi alohida ushlanadi: `.seconds` dan foydalaniladi, keyingi yuborish **o'z vaqtida rejalashtiriladi** va darhol qayta urinish qilinmaydi. Bu `FloodWaitError` dan farqli — **faqat shu guruhni** bloklaydi, shuning uchun boshqa guruhlarga yuborish davom etadi |

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

### 🆕 Baza nusxasi (backup) — foydalanuvchilarni bloklamaydi

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| `core/database.py` → `backup_to()` | 🟢 past | Avval nusxa ko'chirilayotgan paytda global `_write_lock` **ushlab turilardi**. Katta bazada bu barcha foydalanuvchilarning yozuvlarini (login, interval o'zgarishi, guruh qo'shish) bloklab qoldirardi — bitta super admin eksporti boshqa odamlarni kutishga majbur qilardi. Endi lock **butunlay ushlanmaydi** |
| Alohida manba ulanishi | 🟢 past | `aiosqlite` har bir ulanish uchun bitta worker thread ishlatadi va `backup()` aynan shu thread'da bajarilishi kerak. Asosiy ulanish ustida `backup()` ishlatilsa, parallel yozuv bilan birga **deadlock** yuzaga keladi (yozuv commit'i nusxadan keyingi navbatda turadi, nusxa esa yozuvni kutadi). Endi nusxa uchun **alohida** manba ulanishi ochiladi va yopiladi |

**Nima uchun muhim:** `db:backup` va `db:export` super admin panelida
qo'lda ishga tushiriladi. Avval katta bazada bu barcha foydalanuvchilarning
yozuvlarini vaqtincha bloklab qoldirgan bo'lardi.

### 🆕 Foydalanuvchi lock'lari — collision yo'q

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| `core/update_locks.py` | 🟢 past | Lock'lar avval `uid % 256` (striped) uslubida taqsimlanardi. Natijada `uid=1` va `uid=257` **bir xil** lock'ni olardi — bitta foydalanuvchi uzoq amal qilsa, ikkinchisi **kutib qolardi**. Endi lock'lar **aybiga** yaratiladi va `WeakValueDictionary` bilan saqlanadi (faol bo'lmagan lock'lar xotiradan o'chadi) |

### 🆕 Soddalashtirilgan menyu — kamroq, aniqroq tugmalar

Foydalanuvchilar tugmalarni ko'p deb xal qilayotgani uchun menyu
qisqartirildi. Hisobot/Status/Paket **butunlay olib tashlandi**.

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| Asosiy menyu | 🟢 past | Endi: `▶️ Start`, `⛔ Stop`, `🔍 Guruhlarni topish`, `💬 Guruhlar`, `➕ Post qo'shish`, `🗑 Post o'chirish`, `⏱ Interval`, `👥 Referal` (+ jamoa a'zosi/adminida `👥 Jamoam`) |
| Start/Stop ajratildi | 🟢 past | Ikkalasi **doimiy, alohida** tugmalar. Holat yorlig'i olib tashlandi — tugma bosilganda alohida xabar bilan aytiladi |
| `📈 Hisobot` / `📊 Status` / `📦 Paket` | 🟢 past | Butunlay olib tashlandi. `/status` buyrug'i ham olib tashlandi (Telegram buyruqlar ro'yxatidan ham) |
| `⏱ Interval` | 🟢 past | Ikki xil interval **bitta oynada**: `🌐 Barcha guruhlar uchun` va `⏱ Bitta guruh uchun`. Eski `⏱ Guruh intervali` va `⏱ Posting oralig'i` tugmalari o'rniga keldi |
| `💬 Guruhlar` oynasi | 🟢 past | Yuqorida **guruh havolalari** (raqam bilan, `https://t.me/...`), pastda **faqat** `🗑 N. guruh` o'chirish tugmalari. Yopiq guruhlarda havola chiqmaydi |
| Jamoa tugmalari | 🟡 o'rta | Jamoasiz foydalanuvchida `🎯 Jamoani tanlash` va `👑 Admin bo'lish` **yo'q**. Jamoa adminini faqat super admin panelidan qo'shish mumkin. Batafsil — `docs/JAMOA_TIZIMI.md` |
| Eski klaviaturalar | 🟢 past | Eski tugma matnlari (`⏱ Guruh intervali`, `⏱ Posting oralig'i`, `🎯 Jamoani tanlash`) **ishlashda davom etadi** — ular yangi oynalarga yo'naltiriladi |

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
| «👑 Admin bo'lish» tugmasi | 🟡 o'rta | Tugma asosiy menyudan **butunlay olib tashlandi**. Jamoa adminini **faqat super admin** yaratadi (`🖥 Super Admin` → `👑 Jamoa adminlari` → `➕ Admin qo'shish`, telefon raqam orqali). Eski tugma matni eski klaviaturalarda bosilsa — jamoa admini uchun jamoa yaratish oqimi boshlanadi, oddiy user uchun esa rad javobi beriladi |
| Jamoa sig'i | 🟢 past | Jamoa to'lgan bo'lsa yangi a'zo biriktirilmaydi (`assign_team_member` / `set_team_pending` ham tekshiradi) — limit oshishi mumkin emas |
| Super admin paneli | 🟢 past | Bo'sh jamoa adminlari ro'yxatida ham «➕ Admin qo'shish» tugmasi ko'rinadi — birinchi jamoa adminini qo'shish uchun |

> ℹ️ **Jamoalar yopiq.** Oddiy foydalanuvchi jamoalarni ko'ra olmaydi va
> o'zi jamoaga qo'shila olmaydi — jamoaga faqat jamoa administratori
> qo'shadi (telefon taklifi yoki jamoa havolasi orqali). Jamoa adminlari
> faqat o'z jamoalariga ta'sir qiladi.

### 🆕 Jamoa tizimi soddalashtirildi — jamoalar yopiq

| Qism | Xavf | Izoh |
| ---- | ---- | ---- |
| `🎯 Jamoani tanlash` | 🟡 o'rta | Tugma **butunlay olib tashlandi** va jamoalar **yopiq** bo'ldi. Oddiy foydalanuvchi jamoalarni ko'ra olmaydi. `show_team_picker` va `handle_team_pick_callback` faqat **super admin** uchun ishlaydi — oddiy user callback yuborsa, rad javobi beriladi |
| Jamoa adminini yaratish | 🟢 past | Faqat **super admin** panelidan (`➕ Admin qo'shish`, telefon raqam). Admin ro'yxatdan o'tgach **birinchi marta** `👥 Jamoam` bosganda jamoaning nomi va sig'imi so'raladi — jamoani o'zi shakllantiradi |
| Oddiy user → jamoa admini | 🟢 past | `begin_team_admin_register` endi rolini tekshiradi: jamoa admini bo'lmagan user uchun rad javobi beriladi |
| Super admin paneli | 🟢 past | Jamoa admini kartasida jamoasi yo'q bo'lsa «⏳ hali yaratilmagan — admin «👥 Jamoam» orqali nomini va sig'imini kiritadi» deb ko'rsatiladi. Bo'sh ro'yxat matni ham yangilandi |
| Tasdiqlash | 🟢 past | O'zgarmadi: jamoasiz user → **super admin**, jamoa a'zosi → **jamoa admini** (maksimal 60 kun) |
| Inline xavfsizligi | 🟢 past | Jamoa oqimlarida `update.message.reply_text` → `reply_text_safe` ga o'tkazildi — inline tugma bosilganda `AttributeError` chiqmasligi uchun |

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
🔁 N ta worker tiklandi                      ← restartda avtomatik tiklanganlar
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

### Jamoa bo'yicha qo'shimcha tekshirish (PR #36)

1. **Jamoa admini** → «👥 Jamoam» → **«✏️ Jamoa nomi»** → nom kiriting →
   yangi nom saqlansin va a'zolar ro'yxatida yangi nom ko'rinsin.
2. **Jamoa admini** → «👥 Jamoam» → «🔗 Havola» — faqat **bitta** havola
   (`start=team_...`) chiqsin, `start=adm_...` **chiqmasin**.
3. **Jamoa admini** → «👥 Jamoam» → «👥 Foydalanuvchilar» — jamoa asosi
   (admin) o'z ro'yxatida **ko'rinmasin**.
4. **Jamoa admini** → panel → «⬅️ Orqaga» — **asosiy menyuga** qaytsin
   (o'z-o'ziga qaytmasin).
5. **Yangi a'zo** (havola orqali) ro'yxatdan o'tsa — «⏳ Endi jamoa
   adminingiz sizni tasdiqlashni kutilmoqda» va **jamoa adminining**
   telefon raqami chiqsin (super adminning emas).
6. **Super admin** → foydalanuvchi kartasi → «👥 Jamoaga biriktirish» →
   jamoa adminini tanlang → a'zo jamoa adminiga **ariza** olsin va a'zoga
   jamoa adminining telefon raqami yuborilsin.
7. **To'g'ridan to'g'ri kelgan** (jamoasiz) foydalanuvchi ro'yxatdan o'tsa —
   **super admin** raqami chiqsin (o'zgarmasligi kerak).

### Jamoa paneli va statistikasi (PR #37)

1. **Jamoa admini** → «👥 Jamoam» → **«📊 Statistika»** — oyna **xatosiz**
   ochilsin (avval «Xatolik yuz berdi» berardi). Guruh/post sonlari
   raqam ko'rinishi kerak.
2. **Statistika** → «⬅️ Orqaga» — **jamoa admini paneliga** qaytsin
   (asosiy menyuga emas).
3. **«👥 Foydalanuvchilar»** → «⬅️ Orqaga» — **jamoa admini paneliga**
   qaytsin; **«📋 Do'stlar ro'yxati»** → «⬅️ Orqaga» — ham panelga.
4. **Panel** → «⬅️ Orqaga» — **asosiy menyuga** qaytsin.
5. **Orqaga bosilganda** eski oyna chatda **qolmasin** — o'rniga yangisi
   yozilsin (inline xabar tahrirlansin).
6. **Jamoa admini** → «👥 Referal» — faqat **bitta** tugma: «🔗 Jamoa
   havolasi». Shaxsiy referal statistikasi va `start=ref_...` havolasi
   **chiqmasin**.
7. **Oddiy foydalanuvchi** → «👥 Referal» — avvalgi ko'rinish **saqlansin**
   (`start=ref_...` + statistika).

### Guruhni belgilash va router qamrovi (PR #39)

1. **«💬 Guruhlar»** → **«🔍 Guruhlarni topish»** → ro'yxatda guruhni
   **✅ belgilang** — yuqorida **«✅ Tanlandi: <guruh nomi>»** ogohlantirishi
   chiqishi va tugmada **✅** belgisi paydo bo'lishi kerak (avval
   hech narsa chiqmasdi).
2. **«✅ Tanlanganlarni qo'shish (N)»** tugmasi paydo bo'lishi kerak —
   u faqat belgilangan guruhlar soni **> 0** bo'lganda chiqadi.
3. **«✅ Tanlanganlarni qo'shish»** ni bosing — guruhlar bazaga qo'shiladi
   va hisobot chiqadi: `✅ 2 ta guruh qo'shildi`.
4. **«💬 Guruhlar»** oynasida tanlangan guruhlar ko'rinishi kerak.

### «💬 Guruhlar» oynasi UX (PR #40)

1. **«💬 Guruhlar»** — oynada **faqat** o'chirish tugmalari va
   «⬅️ Asosiy menyu» bo'lishi kerak. **«🔍 Guruhlarni topish» tugmasi
   bu yerde BO'LMASLIGI kerak** — u faqat asosiy menyuda.
2. Oynada guruh soni va **`https://t.me/...` havolalari** ko'rinishi kerak
   (avval faqat sarlavha ko'rinardi).
3. Biror guruhni **🗑** bilan o'chiring — oyna **to'liq yangilanishi** kerak:
   qolgan guruhlar va havolalar ko'rinib tursin (avval oyna bo'sh qolardi).
4. Sahifalash tugmalari (**📄 1/2**) bosilsa — oyna ham to'liq yangilansin
   (ro'yxat va havolalar saqlansin).
5. **«⬅️ Asosiy menyu»** — eskirgan oyna xabari **o'chirilsin**,
   «💬 Guruhlar yopildi» deb qolmasin.
6. Asosiy menyudagi **«🔍 Guruhlarni topish»** → skaner ro'yxatida
   **allaqachon qo'shilgan guruhlar chiqmasligi** kerak.
7. Skaner ro'yxatida **«🚫 Bekor qilish»** — skaner xabari **to'liq
   o'chirilsin**, «Bekor qilindi» deb qolmasin.
8. Skanerda guruhni **✅ belgilang** → **«✅ Tanlanganlarni qo'shish (N)»** —
   qo'shishdan keyin **«💬 Guruhlar» oynasi** (soni + havolalar + o'chirish
   tugmalari) ko'rinsin, faqat hisobot emas.

### Guruh nomi (title) — PR #41

1. **«💬 Guruhlar»** — ro'yxatda guruh **nomi** va `https://t.me/...`
   havolasi birga ko'rinishi kerak:
   `1. Taxi Xorazm Toshken — https://t.me/taxi_x`.
2. **🗑** tugmasi — guruh **nomini** ko'rsatishi kerak
   (`🗑 1. Taxi Xorazm Toshken`), username emas.
3. **Asosiy menyudagi «🔍 Guruhlarni topish»** → skaner → ✅ belgilang →
   **«✅ Tanlanganlarni qo'shish»** — qo'shishdan keyin oynada **nom**
   ko'rinishi kerak (skaner nomi saqlanadi).
4. **Yopiq guruh** (marked ID) — ID ro'yxatda ham, tugmada ham
   **ko'rinmasligi** kerak (maxfiylik).
5. Eski guruhlar (bazasida nomi yo'q) — «💬 Guruhlar» oynasini bir marta
   ochgandan keyin nomi **avtomatik to'ldiriladi** (fon task, Telegram'dan).

### «Guruhlar yo'q» tuzatishi (PR #42)

Production'da `6169018469` foydalanuvchisida aniqlangan muammo: guruhlar
`+3` deb qo'shilgan deb ko'rsatilgan, lekin «💬 Guruhlar» oynasi bo'sh
chiqqan.

1. **Qo'shish tekshiruvi** — guruh qo'shishdan keyin bazada **haqiqatan**
   turgani tekshiriladi. Yo'q bo'lsa foydalanuvchiga
   **«❌ Guruhlar qo'shilmadi»** xabari chiqadi (avval yolg'on
   «✅ 3 ta guruh qo'shildi» deyardi).
2. **Sabab logda ko'rinadi** — FK xatosi va boshqa xatolar alohida
   yoziladi:
   ```
   add_chat xatolik (FK): FOREIGN KEY constraint failed
   add_chat: yozuv commitdan keyin topilmadi (uid=..., value=...)
   ```
3. **O'chirish izi** — guruh o'chirilganda logga yoziladi:
   ```
   🗑 6169018469 guruh o'chirildi (foydalanuvchi): @taxi_x
   ```
   (avval faqat Telegram'da xabar chiqardi, logda iz qolmasdi).
4. **Bo'sh oyna eslatmasi** — skanerda topilgan guruhlar bo'lsa,
   «💬 Guruhlar» oynasi «Tanlanganlarni qo'shish» eslatmasini beradi.
5. **Foydalanuvchi o'chirilganda** — guruhlar FK CASCADE ga tayanib
   yo'qolmasligi uchun **aniq** o'chiriladi (natija o'zgarmaydi, lekin
   nazorat ostida bo'ladi).

**Tekshirish (deploydan keyin):**

```bash
journalctl -u avtobot3.service --since "10 minutes ago" | grep -E "add_chat|guruh o'chirildi|bazada 0 ta"
```

### Tanlangan guruhlar yo'qolmasligi (PR #43)

1. **Skanerda guruhlarni ✅ belgilab**, «Tanlanganlarni saqlash» tugmasini
   bosmasdan **«💬 Guruhlar»** oynasiga o'tsangiz — tanlanish **ko'rinadi**
   va oynada **«💾 Tanlanganlarni saqlash (N)»** tugmasi chiqadi.
2. **Skaner oynasida** «⬅️ Guruhlar» tugmasi qo'shildi — u skanerdan
   chiqaradi va **tanlanishni saqlab qoldiradi** («🚫 Bekor qilish» esa
   tanlanishni tozalaydi — o'z xatti-harakaticha).
3. **Tugma matni aniqroq**: «✅ Tanlanganlarni qo'shish» →
   **«💾 Tanlanganlarni saqlash»** — nima qilishini aniq bildiradi.
4. **Tasdiqlash bosqichi** — saqlash tugmasi bosilganda avval tasdiqlash
   oynasi ochiladi («✅ Ha, saqla» / «❌ Yo'q, bekor qil») va qaysi
   guruhlar saqlanayotgani ko'rsatiladi.
5. Skanerdagi va «Guruhlar» oynasidagi saqlash tugmalari **bir xil**
   natijani beradi.

**Tekshirish (deploydan keyin):**

```bash
# 1) «🔍 Guruhlarni topish» → biror guruhni ✅ belgilang
# 2) «💾 Tanlanganlarni saqlash (1)» ni bosing → tasdiqlash oynasi ochiladi
# 3) «✅ Ha, saqla» ni bosing → «✅ 1 ta guruh saqlandi» chiqishi kerak
journalctl -u avtobot3.service --since "5 minutes ago" | grep -E "Tanlangan guruhlar|bazada"
```

### Inline tugmalar va xato logi (PR #38)

1. **«💬 Guruhlar»** → **«🔍 Guruhlarni topish»** — skaner ishlaydi va
   ro'yxat chiqadi (avval «Xatolik yuz berdi» berardi).
2. **Skaner natijasi** → guruhni **✅ belgilang** → **«✅ Tanlanganlarni
   qo'shish (N)»** — guruhlar qo'shiladi.
3. **«💬 Guruhlar»** → **«⏰ Vaqt»** — interval oynasi ochiladi (avval
   inline kontekstda buzilgan).
4. **Jamoa admini** → panel → **«✏️ Jamoa nomi»** — nom kiritish oynasi
   ochiladi (avval `Inline keyboard expected` berardi).
5. **Jamoa admini** → panel → **«📨 Xabar yuborish»** — xabar yuborish
   oynasi ochiladi (avval `Inline keyboard expected` berardi).
6. **Log tekshiruvi** — xato yuzsa, logda shunday yoziladi:
   ```
   💥 XATO: Inline tugma │ uid=6169018469 │ action=mg:find │ TypeError: ...
   ```
   va kamchilik shunday:
   ```
   ⚠️ KAMCHILIK: Guruh topilmadi yoki o'chirilgan │ uid=6169018469 │ action=tadm:member:123
   ```

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
