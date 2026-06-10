# SayGo Web MVP v4

Tarjima chat MVP: FastAPI + WebSocket + OpenAI + PostgreSQL.

## v4 yangiliklari

- Chatlar ro'yxati va kontaktlar saqlanadi
- Nickname orqali qidirish
- Xabarlar PostgreSQL bazaga saqlanadi
- Xabar yuborilganda darhol ekranga chiqadi
- Tarjima kelgach xabar avtomatik yangilanadi
- Online / offline holati
- “yozmoqda...” typing indicator
- Xabar vaqti va tarjima statuslari

- Profil bo‘limida “Mening QR”
- QR ichida `saygo://user/@nickname`
- QR skanerlash yoki QR matn orqali kontaktga qo‘shish
- QR orqali kontaktga qo‘shilgach chat avtomatik ochiladi

## Render Web Service

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Environment Variables:

```env
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-5-nano
DATABASE_URL=postgresql://...
```

Agar `DATABASE_URL` qo'yilmasa, lokal test uchun `sqlite:///./saygo.db` ishlaydi.
