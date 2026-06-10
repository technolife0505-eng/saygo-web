# SayGo Web MVP v5

v5 funksiyalar:
- Tarjima chat
- PostgreSQL saqlash
- Kontaktlar va chatlar ro'yxati
- Online/offline va typing
- QR qo'shish: HTTPS kamera linki va saygo:// fallback
- Voice message: brauzerda ovoz yozish, OpenAI orqali transcribe, tarjima qilib chatga chiqarish

Render:
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

Environment:
- `DATABASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL=gpt-5-nano`
- `OPENAI_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe`

Eslatma: v5 voice message hozir audio faylni saqlamaydi. Ovoz matnga aylantiriladi va tarjima qilingan xabar sifatida chatga qo'shiladi. v5.1 da tarjima qilingan audio javob qo'shiladi.
