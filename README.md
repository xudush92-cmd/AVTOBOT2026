# AVTOBOT2026 — AVTO_2_BOT

Telegram guruhlariga reklama postlarini avtomatik joylashtiruvchi bot.
Kod `AVTOBOT2026/` papkasida; to'liq hujjat: [`AVTOBOT2026/README.md`](AVTOBOT2026/README.md).

## Oddiy foydalanuvchi registratsiyasi (qisqacha)

1. `/start` yoki **🔑 Login** — ism va familiya bitta xabarda so'raladi.
2. Telefon raqami kiritiladi.
3. Telefon tasdiqlanishi bilan Telegram kodi **darhol** so'raladi (admin
   tasdig'i kutilmaydi); kod faqat botdagi raqamli tugmalar orqali kiritiladi.
   QR Login va 2FA fallback saqlanadi.
4. Login tugagach sessiya aktiv `session` emas, Fernet bilan shifrlangan
   `pending_session` sifatida saqlanadi va `awaiting_approval=1` qilinadi;
   super adminga 30 kunlik tarif va 60 daqiqalik interval haqida xabar boradi.
5. Admin tasdiqlaganda pending sessiya Telegramda qayta tekshiriladi va aynan
   o'sha UID'ga tegishli bo'lsa atomik ravishda aktiv sessiyaga ko'chiriladi —
   sessiya revoke qilinmaydi, foydalanuvchi kodni qayta kiritmaydi va darhol
   asosiy menuni oladi.
6. Sessiya boshqa akkauntga tegishli bo'lsa authorization revoke qilinadi va
   pending holat tozalanadi; vaqtinchalik Telegram/tarmoq xatosida pending
   sessiya saqlab qolinadi.

Tarif muddati: admin **⏰ Tarif muddati** orqali yangi muddat bersa, u
**hozirdan boshlab** hisoblanadi va oldingi muddatni **bekor qiladi** (ustiga
qo'shilmaydi) — 30 kunlik userga yana 30 kun berilsa, u 60 emas, 30 kun oladi.
Tasdiqlash va qayta Login muddat ustiga kun qo'shmaydi.

Limitlar: UID bo'yicha login **3 ta/soat** (yangi va tasdiqlanmagan userlar
ham, `/start` orqali aylanib o'tilmaydi) va telefon raqami bo'yicha kod
so'rovi **3 ta/soat** (`send_code_request()`dan oldin tekshiriladi).

Testlar: `cd AVTOBOT2026 && python -m unittest discover -s tests -v`
