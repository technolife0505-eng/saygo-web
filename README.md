# SayGo Web MVP v6

v6: Voice-to-Voice tarjima.

## Funksiyalar
- Real-time chat
- Avtomatik tarjima
- PostgreSQL saqlash
- Kontaktlar va chatlar ro'yxati
- QR orqali qo'shish
- Voice message: audio saqlash + transcription + tarjima
- Voice-to-Voice: tarjima qilingan matnni MP3 ovozga aylantirish

## Render Environment Variables

```env
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-5-nano
OPENAI_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=alloy
DATABASE_URL=postgresql://...
```

## Render commands

Build:
```bash
pip install -r requirements.txt
```

Start:
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```
