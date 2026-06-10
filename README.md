# SayGo Web MVP

SayGo — tarjima qiluvchi web chat MVP.

Hozirgi versiya:

- nickname orqali kirish;
- foydalanuvchi tili tanlash;
- nickname orqali chat ochish;
- real-time WebSocket chat;
- OpenAI orqali avtomatik tarjima;
- bitta Render Web Service sifatida ishlaydi.

> Eslatma: bu MVP demo. Ma'lumotlar hozircha RAM xotirada saqlanadi. Render qayta ishga tushsa user/chatlar o'chadi. Keyingi bosqichda PostgreSQL qo'shiladi.

## Local ishga tushirish

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` ichiga OpenAI kalitingizni qo'ying:

```env
OPENAI_API_KEY=sk-your-openai-key
OPENAI_MODEL=gpt-5-mini
```

Ishga tushirish:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Brauzerda oching:

```text
http://localhost:8000
```

## Render deploy

Render rasmiy FastAPI deploy hujjatlarida start command quyidagicha beriladi:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Render sozlamalari:

- Build Command:

```bash
pip install -r requirements.txt
```

- Start Command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

- Environment Variables:

```env
OPENAI_API_KEY=sk-your-openai-key
OPENAI_MODEL=gpt-5-mini
```

## Test qilish

1. Birinchi brauzerda SayGo oching.
2. `@asadulla`, til `uz` bilan kiring.
3. Ikkinchi brauzer yoki incognito oynada SayGo oching.
4. `@ivan`, til `ru` bilan kiring.
5. `@asadulla` oynasida suhbatdosh sifatida `@ivan` yozib chat oching.
6. `@ivan` oynasida suhbatdosh sifatida `@asadulla` yozib chat oching.
7. Uzbekcha xabar yozing, ruscha tarjima ko'rinadi.

## API

- `GET /api/health`
- `POST /api/register`
- `GET /api/users/{nickname}`
- `GET /api/search?q=@nick`
- `POST /api/contacts/add`
- `GET /api/contacts/{nickname}`
- `POST /api/chats/start`
- `GET /api/chats/{nickname}`
- `WS /ws/{nickname}`

## Keyingi bosqich

- PostgreSQL database;
- haqiqiy login / OTP;
- QR code;
- voice message tarjima;
- real-time voice call tarjima.
