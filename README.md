# SayGo Web MVP v5.2

SayGo v5.2: translated messenger MVP with QR contacts, PostgreSQL persistence, text translation, voice transcription, and replayable voice messages.

## Render

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Environment variables:

```text
DATABASE_URL=postgresql://...
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-5-nano
OPENAI_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe
```

## v5.2 changes

- Voice messages are saved in the database.
- Voice messages can be replayed in chat.
- Voice duration is shown.
- Voice upload has size/duration checks.
- Existing v5.1 chat, QR, contacts, typing and presence features remain.

Note: storing audio in PostgreSQL is acceptable for MVP testing. For production, move audio to object storage such as S3/MinIO.
