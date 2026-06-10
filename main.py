import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"

client: Optional[AsyncOpenAI] = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

app = FastAPI(title="SayGo Web MVP", version="0.1.0")

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

users: Dict[str, dict] = {}
contacts: Dict[str, set] = {}
chats: Dict[str, List[dict]] = {}
connections: Dict[str, WebSocket] = {}


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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_nickname(nickname: str) -> str:
    nickname = nickname.strip().lower().replace(" ", "")
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


def public_user(nickname: str) -> Optional[dict]:
    user = users.get(nickname)
    if not user:
        return None
    return {
        "nickname": user["nickname"],
        "display_name": user["display_name"],
        "language": user["language"],
        "created_at": user["created_at"],
    }


async def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    text = text.strip()
    if not text:
        return ""
    if source_lang == target_lang:
        return text
    if client is None:
        return f"[OPENAI_API_KEY yo'q: {target_lang}] {text}"

    source = LANG_NAMES.get(source_lang, source_lang)
    target = LANG_NAMES.get(target_lang, target_lang)

    response = await client.responses.create(
        model=OPENAI_MODEL,
        instructions=(
            "You are SayGo's translation engine. Translate only the user's message. "
            "Keep the meaning natural for chat. Do not explain. Do not add quotes. "
            "If the message is already in the target language, return it unchanged."
        ),
        input=f"Translate from {source} to {target}:\n{text}",
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
        "openai_key_configured": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL,
    }


@app.post("/api/register")
async def register(payload: RegisterPayload):
    nickname = normalize_nickname(payload.nickname)
    language = payload.language if payload.language in LANG_NAMES else "uz"
    display_name = payload.display_name.strip() or nickname

    if nickname in users:
        users[nickname]["display_name"] = display_name
        users[nickname]["language"] = language
    else:
        users[nickname] = {
            "nickname": nickname,
            "display_name": display_name,
            "language": language,
            "created_at": now_iso(),
        }
        contacts.setdefault(nickname, set())

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
    result = [public_user(nick) for nick in users if nick.startswith(q)]
    return [u for u in result if u][:20]


@app.post("/api/contacts/add")
async def add_contact(payload: AddContactPayload):
    owner = normalize_nickname(payload.owner)
    contact = normalize_nickname(payload.contact)
    if owner not in users:
        raise HTTPException(status_code=404, detail="Owner not found")
    if contact not in users:
        raise HTTPException(status_code=404, detail="Contact not found")
    if owner == contact:
        raise HTTPException(status_code=400, detail="You cannot add yourself")

    contacts.setdefault(owner, set()).add(contact)
    contacts.setdefault(contact, set()).add(owner)
    return {"ok": True, "owner": owner, "contact": public_user(contact)}


@app.get("/api/contacts/{nickname}")
async def list_contacts(nickname: str):
    nickname = normalize_nickname(nickname)
    if nickname not in users:
        raise HTTPException(status_code=404, detail="User not found")
    return [public_user(n) for n in sorted(contacts.get(nickname, set())) if public_user(n)]


@app.post("/api/chats/start")
async def start_chat(payload: StartChatPayload):
    user_a = normalize_nickname(payload.user_a)
    user_b = normalize_nickname(payload.user_b)

    if user_a not in users:
        raise HTTPException(status_code=404, detail="First user not found")
    if user_b not in users:
        raise HTTPException(status_code=404, detail="Second user not found")
    if user_a == user_b:
        raise HTTPException(status_code=400, detail="Cannot chat with yourself")

    cid = chat_id_for(user_a, user_b)
    chats.setdefault(cid, [])
    contacts.setdefault(user_a, set()).add(user_b)
    contacts.setdefault(user_b, set()).add(user_a)

    return {
        "chat_id": cid,
        "user_a": public_user(user_a),
        "user_b": public_user(user_b),
        "messages": chats[cid],
    }


@app.get("/api/chats/{nickname}")
async def user_chats(nickname: str):
    nickname = normalize_nickname(nickname)
    if nickname not in users:
        raise HTTPException(status_code=404, detail="User not found")
    result = []
    for cid, messages in chats.items():
        members = cid.split("__")
        if nickname in members:
            other = members[0] if members[1] == nickname else members[1]
            result.append({
                "chat_id": cid,
                "other": public_user(other),
                "last_message": messages[-1] if messages else None,
            })
    return result


@app.websocket("/ws/{nickname}")
async def websocket_endpoint(websocket: WebSocket, nickname: str):
    nickname = normalize_nickname(nickname)
    await websocket.accept()
    connections[nickname] = websocket

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            cid = data.get("chat_id")
            sender = normalize_nickname(data.get("sender", ""))
            receiver = normalize_nickname(data.get("receiver", ""))
            text = data.get("text", "").strip()
            client_message_id = data.get("client_message_id")

            if sender not in users or receiver not in users:
                await websocket.send_text(json.dumps({"type": "error", "detail": "User not found"}))
                continue
            if not text:
                continue

            expected_cid = chat_id_for(sender, receiver)
            if cid != expected_cid:
                cid = expected_cid

            sender_lang = users[sender]["language"]
            receiver_lang = users[receiver]["language"]

            try:
                translated = await translate_text(text, sender_lang, receiver_lang)
            except Exception as exc:
                translated = f"[Translation error] {text}"
                print("Translation error:", repr(exc))

            message = {
                "type": "message",
                "id": f"msg_{len(chats.get(cid, [])) + 1}",
                "chat_id": cid,
                "sender": sender,
                "receiver": receiver,
                "original_text": text,
                "translated_text": translated,
                "source_lang": sender_lang,
                "target_lang": receiver_lang,
                "created_at": now_iso(),
                "client_message_id": client_message_id,
                "status": "translated",
            }

            chats.setdefault(cid, []).append(message)

            if receiver in connections:
                await connections[receiver].send_text(json.dumps(message, ensure_ascii=False))

            if sender in connections:
                await connections[sender].send_text(json.dumps(message, ensure_ascii=False))

    except WebSocketDisconnect:
        if connections.get(nickname) is websocket:
            connections.pop(nickname, None)
