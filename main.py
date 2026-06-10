import json
import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano").strip() or "gpt-5-nano"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./saygo.db").strip() or "sqlite:///./saygo.db"

client: Optional[AsyncOpenAI] = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

app = FastAPI(title="SayGo Web MVP", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

LANG_NAMES = {
    "uz": "Uzbek",
    "ru": "Russian",
    "en": "English",
}

connections: dict[str, WebSocket] = {}
online_users: set[str] = set()


def make_engine() -> Engine:
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


engine = make_engine()


def is_postgres() -> bool:
    return engine.dialect.name.startswith("postgres")


def is_sqlite() -> bool:
    return engine.dialect.name == "sqlite"


class RegisterPayload(BaseModel):
    nickname: str = Field(min_length=2, max_length=32)
    display_name: str = Field(default="", max_length=60)
    language: str = Field(default="uz")


class StartChatPayload(BaseModel):
    user_a: str
    user_b: str


class AddContactPayload(BaseModel):
    owner: str
    contact: str


class QRResolvePayload(BaseModel):
    code: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_nickname(nickname: str) -> str:
    nickname = (nickname or "").strip().lower().replace(" ", "")
    if not nickname:
        raise HTTPException(status_code=400, detail="Nickname is required")
    if not nickname.startswith("@"):
        nickname = "@" + nickname
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_@.")
    if any(ch not in allowed for ch in nickname):
        raise HTTPException(status_code=400, detail="Nickname may contain only latin letters, numbers, underscore and dot")
    return nickname


def chat_id_for(a: str, b: str) -> str:
    return "__".join(sorted([a, b]))


def row_to_public_user(row) -> Optional[dict]:
    if not row:
        return None
    m = row._mapping if hasattr(row, "_mapping") else row
    return {
        "nickname": m["nickname"],
        "display_name": m["display_name"],
        "language": m["language"],
        "created_at": str(m["created_at"]),
    }


def message_to_dict(row) -> dict:
    m = row._mapping if hasattr(row, "_mapping") else row
    return {
        "type": "message",
        "id": str(m["id"]),
        "chat_id": m["chat_id"],
        "sender": m["sender"],
        "receiver": m["receiver"],
        "original_text": m["original_text"],
        "translated_text": m["translated_text"],
        "source_lang": m["source_lang"],
        "target_lang": m["target_lang"],
        "created_at": str(m["created_at"]),
        "client_message_id": m.get("client_message_id") if hasattr(m, "get") else m["client_message_id"],
        "status": m["status"],
    }


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                nickname VARCHAR(64) PRIMARY KEY,
                display_name VARCHAR(100) NOT NULL,
                language VARCHAR(10) NOT NULL DEFAULT 'uz',
                created_at VARCHAR(64) NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS contacts (
                owner VARCHAR(64) NOT NULL,
                contact VARCHAR(64) NOT NULL,
                created_at VARCHAR(64) NOT NULL,
                PRIMARY KEY (owner, contact)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id VARCHAR(160) PRIMARY KEY,
                user_a VARCHAR(64) NOT NULL,
                user_b VARCHAR(64) NOT NULL,
                created_at VARCHAR(64) NOT NULL
            )
        """))
        if is_postgres():
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    chat_id VARCHAR(160) NOT NULL,
                    sender VARCHAR(64) NOT NULL,
                    receiver VARCHAR(64) NOT NULL,
                    original_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    source_lang VARCHAR(10) NOT NULL,
                    target_lang VARCHAR(10) NOT NULL,
                    client_message_id VARCHAR(120),
                    status VARCHAR(30) NOT NULL DEFAULT 'translated',
                    created_at VARCHAR(64) NOT NULL
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id VARCHAR(160) NOT NULL,
                    sender VARCHAR(64) NOT NULL,
                    receiver VARCHAR(64) NOT NULL,
                    original_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    source_lang VARCHAR(10) NOT NULL,
                    target_lang VARCHAR(10) NOT NULL,
                    client_message_id VARCHAR(120),
                    status VARCHAR(30) NOT NULL DEFAULT 'translated',
                    created_at VARCHAR(64) NOT NULL
                )
            """))


@app.on_event("startup")
async def on_startup():
    init_db()


def get_user_row(nickname: str):
    with engine.begin() as conn:
        return conn.execute(text("SELECT * FROM users WHERE nickname = :nickname"), {"nickname": nickname}).fetchone()


def public_user(nickname: str) -> Optional[dict]:
    return row_to_public_user(get_user_row(nickname))


def ensure_user_exists(nickname: str, label: str = "User"):
    user = public_user(nickname)
    if not user:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return user


async def translate_text(text_value: str, source_lang: str, target_lang: str) -> str:
    text_value = text_value.strip()
    if not text_value:
        return ""
    if source_lang == target_lang:
        return text_value
    if client is None:
        return f"[OPENAI_API_KEY yo'q: {target_lang}] {text_value}"

    source = LANG_NAMES.get(source_lang, source_lang)
    target = LANG_NAMES.get(target_lang, target_lang)

    response = await client.responses.create(
        model=OPENAI_MODEL,
        instructions=(
            "You are SayGo's translation engine. Translate only the user's message. "
            "Keep the meaning natural for chat. Do not explain. Do not add quotes. "
            "If the message is already in the target language, return it unchanged."
        ),
        input=f"Translate from {source} to {target}:\n{text_value}",
    )
    return response.output_text.strip()


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "app": "SayGo Web MVP",
        "version": "0.3.1-chat-polish",
        "database_configured": bool(os.getenv("DATABASE_URL", "").strip()),
        "database_dialect": engine.dialect.name,
        "openai_key_configured": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL,
    }


@app.post("/api/register")
async def register(payload: RegisterPayload):
    nickname = normalize_nickname(payload.nickname)
    language = payload.language if payload.language in LANG_NAMES else "uz"
    display_name = payload.display_name.strip() or nickname

    with engine.begin() as conn:
        exists = conn.execute(text("SELECT nickname FROM users WHERE nickname = :nickname"), {"nickname": nickname}).fetchone()
        if exists:
            conn.execute(text("""
                UPDATE users SET display_name = :display_name, language = :language
                WHERE nickname = :nickname
            """), {"nickname": nickname, "display_name": display_name, "language": language})
        else:
            conn.execute(text("""
                INSERT INTO users (nickname, display_name, language, created_at)
                VALUES (:nickname, :display_name, :language, :created_at)
            """), {"nickname": nickname, "display_name": display_name, "language": language, "created_at": now_iso()})

    return public_user(nickname)


@app.get("/api/users/{nickname}")
async def get_user(nickname: str):
    nickname = normalize_nickname(nickname)
    user = public_user(nickname)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/api/search")
async def search_user(q: str):
    q = q.strip().lower()
    if not q:
        return []
    if not q.startswith("@"):
        q = "@" + q
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT * FROM users
            WHERE nickname LIKE :q
            ORDER BY nickname
            LIMIT 20
        """), {"q": q + "%"}).fetchall()
    return [row_to_public_user(r) for r in rows]




@app.post("/api/qr/resolve")
async def resolve_qr(payload: QRResolvePayload):
    raw = (payload.code or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="QR code is empty")

    nickname = raw
    prefixes = ["saygo://user/", "saygo://u/", "https://saygo.app/u/", "http://saygo.app/u/"]
    for prefix in prefixes:
        if nickname.lower().startswith(prefix):
            nickname = nickname[len(prefix):]
            break

    if "?add=" in nickname:
        nickname = nickname.split("?add=", 1)[1]
    if "/u/" in nickname:
        nickname = nickname.rsplit("/u/", 1)[1]

    nickname = normalize_nickname(nickname)
    user = public_user(nickname)
    if not user:
        raise HTTPException(status_code=404, detail="QR foydalanuvchisi topilmadi")
    return {"ok": True, "user": user, "qr": f"saygo://user/{nickname}"}


@app.post("/api/contacts/add")
async def add_contact(payload: AddContactPayload):
    owner = normalize_nickname(payload.owner)
    contact = normalize_nickname(payload.contact)
    ensure_user_exists(owner, "Owner")
    contact_user = ensure_user_exists(contact, "Contact")
    if owner == contact:
        raise HTTPException(status_code=400, detail="You cannot add yourself")

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO contacts (owner, contact, created_at)
            VALUES (:owner, :contact, :created_at)
            ON CONFLICT (owner, contact) DO NOTHING
        """), {"owner": owner, "contact": contact, "created_at": now_iso()})
        conn.execute(text("""
            INSERT INTO contacts (owner, contact, created_at)
            VALUES (:owner, :contact, :created_at)
            ON CONFLICT (owner, contact) DO NOTHING
        """), {"owner": contact, "contact": owner, "created_at": now_iso()})
    return {"ok": True, "owner": owner, "contact": contact_user}


@app.get("/api/contacts/{nickname}")
async def list_contacts(nickname: str):
    nickname = normalize_nickname(nickname)
    ensure_user_exists(nickname)
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT u.* FROM contacts c
            JOIN users u ON u.nickname = c.contact
            WHERE c.owner = :owner
            ORDER BY u.display_name, u.nickname
        """), {"owner": nickname}).fetchall()
    return [row_to_public_user(r) for r in rows]


@app.post("/api/chats/start")
async def start_chat(payload: StartChatPayload):
    user_a = normalize_nickname(payload.user_a)
    user_b = normalize_nickname(payload.user_b)
    user_a_profile = ensure_user_exists(user_a, "First user")
    user_b_profile = ensure_user_exists(user_b, "Second user")
    if user_a == user_b:
        raise HTTPException(status_code=400, detail="Cannot chat with yourself")

    cid = chat_id_for(user_a, user_b)
    a, b = sorted([user_a, user_b])

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO chats (chat_id, user_a, user_b, created_at)
            VALUES (:chat_id, :user_a, :user_b, :created_at)
            ON CONFLICT (chat_id) DO NOTHING
        """), {"chat_id": cid, "user_a": a, "user_b": b, "created_at": now_iso()})
        for owner, contact in [(user_a, user_b), (user_b, user_a)]:
            conn.execute(text("""
                INSERT INTO contacts (owner, contact, created_at)
                VALUES (:owner, :contact, :created_at)
                ON CONFLICT (owner, contact) DO NOTHING
            """), {"owner": owner, "contact": contact, "created_at": now_iso()})
        rows = conn.execute(text("""
            SELECT * FROM messages
            WHERE chat_id = :chat_id
            ORDER BY id ASC
            LIMIT 200
        """), {"chat_id": cid}).fetchall()

    return {
        "chat_id": cid,
        "user_a": user_a_profile,
        "user_b": user_b_profile,
        "messages": [message_to_dict(r) for r in rows],
    }


@app.get("/api/chats/{nickname}")
async def user_chats(nickname: str):
    nickname = normalize_nickname(nickname)
    ensure_user_exists(nickname)
    with engine.begin() as conn:
        if is_postgres():
            rows = conn.execute(text("""
                SELECT c.chat_id,
                       c.user_a,
                       c.user_b,
                       m.id AS last_id,
                       m.sender AS last_sender,
                       m.original_text AS last_original_text,
                       m.translated_text AS last_translated_text,
                       m.created_at AS last_created_at
                FROM chats c
                LEFT JOIN LATERAL (
                    SELECT * FROM messages
                    WHERE messages.chat_id = c.chat_id
                    ORDER BY id DESC
                    LIMIT 1
                ) m ON true
                WHERE c.user_a = :nick OR c.user_b = :nick
                ORDER BY COALESCE(m.id, 0) DESC, c.created_at DESC
            """), {"nick": nickname}).fetchall()
        else:
            rows = conn.execute(text("""
                SELECT c.chat_id,
                       c.user_a,
                       c.user_b,
                       (SELECT id FROM messages WHERE messages.chat_id = c.chat_id ORDER BY id DESC LIMIT 1) AS last_id,
                       (SELECT sender FROM messages WHERE messages.chat_id = c.chat_id ORDER BY id DESC LIMIT 1) AS last_sender,
                       (SELECT original_text FROM messages WHERE messages.chat_id = c.chat_id ORDER BY id DESC LIMIT 1) AS last_original_text,
                       (SELECT translated_text FROM messages WHERE messages.chat_id = c.chat_id ORDER BY id DESC LIMIT 1) AS last_translated_text,
                       (SELECT created_at FROM messages WHERE messages.chat_id = c.chat_id ORDER BY id DESC LIMIT 1) AS last_created_at
                FROM chats c
                WHERE c.user_a = :nick OR c.user_b = :nick
                ORDER BY COALESCE((SELECT id FROM messages WHERE messages.chat_id = c.chat_id ORDER BY id DESC LIMIT 1), 0) DESC, c.created_at DESC
            """), {"nick": nickname}).fetchall()

    result = []
    for row in rows:
        m = row._mapping
        other = m["user_a"] if m["user_b"] == nickname else m["user_b"]
        result.append({
            "chat_id": m["chat_id"],
            "other": public_user(other),
            "last_message": {
                "id": m["last_id"],
                "sender": m["last_sender"],
                "original_text": m["last_original_text"],
                "translated_text": m["last_translated_text"],
                "created_at": m["last_created_at"],
            } if m["last_id"] else None,
        })
    return result


async def send_to_user(nickname: str, payload: dict) -> None:
    ws = connections.get(nickname)
    if ws:
        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass


async def notify_presence(nickname: str, is_online: bool) -> None:
    payload = {"type": "presence", "nickname": nickname, "online": is_online}
    for user, ws in list(connections.items()):
        if user != nickname:
            try:
                await ws.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception:
                pass


@app.websocket("/ws/{nickname}")
async def websocket_endpoint(websocket: WebSocket, nickname: str):
    nickname = normalize_nickname(nickname)
    await websocket.accept()
    connections[nickname] = websocket
    online_users.add(nickname)
    await websocket.send_text(json.dumps({"type": "presence", "nickname": nickname, "online": True}, ensure_ascii=False))
    await notify_presence(nickname, True)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            event_type = data.get("type", "message")
            if event_type == "typing":
                sender = normalize_nickname(data.get("sender", ""))
                receiver = normalize_nickname(data.get("receiver", ""))
                await send_to_user(receiver, {
                    "type": "typing",
                    "chat_id": data.get("chat_id"),
                    "sender": sender,
                    "receiver": receiver,
                    "is_typing": bool(data.get("is_typing", False)),
                })
                continue

            cid = data.get("chat_id")
            sender = normalize_nickname(data.get("sender", ""))
            receiver = normalize_nickname(data.get("receiver", ""))
            text_value = data.get("text", "").strip()
            client_message_id = data.get("client_message_id")

            sender_user = public_user(sender)
            receiver_user = public_user(receiver)
            if not sender_user or not receiver_user:
                await websocket.send_text(json.dumps({"type": "error", "detail": "User not found"}))
                continue
            if not text_value:
                continue

            expected_cid = chat_id_for(sender, receiver)
            if cid != expected_cid:
                cid = expected_cid

            sender_lang = sender_user["language"]
            receiver_lang = receiver_user["language"]

            try:
                translated = await translate_text(text_value, sender_lang, receiver_lang)
            except Exception as exc:
                translated = f"[Translation error] {text_value}"
                print("Translation error:", repr(exc))

            with engine.begin() as conn:
                a, b = sorted([sender, receiver])
                conn.execute(text("""
                    INSERT INTO chats (chat_id, user_a, user_b, created_at)
                    VALUES (:chat_id, :user_a, :user_b, :created_at)
                    ON CONFLICT (chat_id) DO NOTHING
                """), {"chat_id": cid, "user_a": a, "user_b": b, "created_at": now_iso()})
                result = conn.execute(text("""
                    INSERT INTO messages (
                        chat_id, sender, receiver, original_text, translated_text,
                        source_lang, target_lang, client_message_id, status, created_at
                    ) VALUES (
                        :chat_id, :sender, :receiver, :original_text, :translated_text,
                        :source_lang, :target_lang, :client_message_id, :status, :created_at
                    ) RETURNING *
                """), {
                    "chat_id": cid,
                    "sender": sender,
                    "receiver": receiver,
                    "original_text": text_value,
                    "translated_text": translated,
                    "source_lang": sender_lang,
                    "target_lang": receiver_lang,
                    "client_message_id": client_message_id,
                    "status": "translated",
                    "created_at": now_iso(),
                })
                row = result.fetchone()

            message = message_to_dict(row)

            await send_to_user(receiver, message)
            await send_to_user(sender, message)

    except WebSocketDisconnect:
        pass
    finally:
        if connections.get(nickname) is websocket:
            connections.pop(nickname, None)
        online_users.discard(nickname)
        await notify_presence(nickname, False)
