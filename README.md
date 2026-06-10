# SayGo Web MVP v2

Tarjima chat MVP: FastAPI + WebSocket + OpenAI + PostgreSQL.

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

## v2 yangiliklari

- Users PostgreSQL bazaga saqlanadi
- Contacts PostgreSQL bazaga saqlanadi
- Chats PostgreSQL bazaga saqlanadi
- Messages PostgreSQL bazaga saqlanadi
- Render restart bo'lsa xabarlar yo'qolmaydi
