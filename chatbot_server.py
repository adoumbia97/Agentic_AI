import time
from pathlib import Path

from typing import Optional

from sqlmodel import Field, SQLModel, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect,
    Depends, HTTPException, status
)
from fastapi.responses import HTMLResponse
from fastapi.security.api_key import APIKeyQuery, APIKeyHeader
from pydantic import BaseModel
from simple_agents import Agent, Runner, function_tool

# ─── CONFIG ───────────────────────────────────────────────────
USER_API_KEYS  = {"user1-token": "user1", "user2-token": "user2"}
ADMIN_API_KEYS = {"admin-token": "admin"}

API_KEY_NAME   = "access_token"
api_key_query  = APIKeyQuery(name=API_KEY_NAME, auto_error=False)
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# track activation state
user_status = {username: True for username in USER_API_KEYS.values()}

def get_user(
    key_q: str = Depends(api_key_query),
    key_h: str = Depends(api_key_header),
):
    token = key_q or key_h
    if token not in USER_API_KEYS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid user API key")
    user = USER_API_KEYS[token]
    if not user_status.get(user, False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is deactivated")
    return user

def get_admin(
    key_q: str = Depends(api_key_query),
    key_h: str = Depends(api_key_header),
):
    token = key_q or key_h
    if token not in ADMIN_API_KEYS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid admin API key")
    return ADMIN_API_KEYS[token]

# ─── METRICS & STORAGE ─────────────────────────────────────────
class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str
    role: str
    content: str
    timestamp: int


class Usage(SQLModel, table=True):
    username: str = Field(primary_key=True)
    conversations: int = 0
    messages: int = 0
    first_request: Optional[int] = None
    last_request: Optional[int] = None
    total_user_words: int = 0
    total_bot_words: int = 0



engine = create_async_engine("sqlite+aiosqlite:///chat.db")
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    await engine.run_sync(SQLModel.metadata.create_all)

# ─── AGENT SETUP ───────────────────────────────────────────────
@function_tool
def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny."

agent = Agent(
    name="Hello world",
    instructions="You are a helpful agent.",
    tools=[get_weather],
)


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)

# ─── SERVE FRONTEND ────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = Path(__file__).parent / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))

# ─── USER HISTORY & USAGE ──────────────────────────────────────
@app.get("/history")
async def get_history(user: str = Depends(get_user)):
    """Return chat history for the user."""
    async with async_session() as session:
        result = await session.exec(
            select(Message).where(Message.username == user).order_by(Message.timestamp)
        )
        msgs = result.all()
        mapped = [
            {
                "who": m.role == "assistant" and "bot" or "user",
                "text": m.content,
                "ts": m.timestamp,
            }
            for m in msgs
        ]
    return {"username": user, "history": mapped}

@app.get("/usage")
async def user_usage(user: str = Depends(get_user)):
    """Return usage metrics for the user."""
    async with async_session() as session:
        u = await session.get(Usage, user)
        if not u:
            u = Usage(username=user)
            session.add(u)
            await session.commit()
            await session.refresh(u)
        return {
            "username": user,
            "conversations": u.conversations,
            "messages": u.messages,
            "first_request": u.first_request,
            "last_request": u.last_request,
            "total_user_words": u.total_user_words,
            "total_bot_words": u.total_bot_words,
        }

# ─── ADMIN: LIST & TOGGLE USERS ───────────────────────────────
@app.get("/admin/users")
async def admin_list_users(admin: str = Depends(get_admin)):
    """
    Return all users with usage + activation status.
    """
    async with async_session() as session:
        users_data = {}
        for u in USER_API_KEYS.values():
            record = await session.get(Usage, u)
            if not record:
                record = Usage(username=u)
                session.add(record)
                await session.commit()
                await session.refresh(record)
            users_data[u] = {
                "conversations": record.conversations,
                "messages": record.messages,
                "first_request": record.first_request,
                "last_request": record.last_request,
                "total_user_words": record.total_user_words,
                "total_bot_words": record.total_bot_words,
                "active": user_status.get(u, False),
            }
        return {"username": admin, "users": users_data}

class UserStatusUpdate(BaseModel):
    active: bool

async def process_message(user: str, text: str) -> str:
    """Handle a single user message and return the assistant reply."""
    ts = int(time.time() * 1000)
    async with async_session() as session:
        rec = await session.get(Usage, user)
        if not rec:
            rec = Usage(username=user)
            session.add(rec)
            await session.commit()
            await session.refresh(rec)
        if rec.first_request is None:
            rec.first_request = ts
        rec.messages += 1
        rec.last_request = ts
        rec.total_user_words += len(text.split())
        session.add(rec)
        session.add(
            Message(
                username=user,
                role="user",
                content=text,
                timestamp=ts,
            )
        )
        await session.commit()
        result = await session.exec(
            select(Message)
            .where(Message.username == user)
            .order_by(Message.timestamp)
        )
        chat_msgs = result.all()
        chat_hist = [
            {"role": "system", "content": agent.instructions}
        ] + [
            {"role": m.role, "content": m.content}
            for m in chat_msgs
        ]
    result = await Runner.run(agent, input=chat_hist)
    reply = result.final_output
    reply_ts = int(time.time() * 1000)
    async with async_session() as session:
        rec = await session.get(Usage, user)
        rec.total_bot_words += len(reply.split())
        session.add(rec)
        session.add(
            Message(
                username=user,
                role="assistant",
                content=reply,
                timestamp=reply_ts,
            )
        )
        await session.commit()
    return reply

@app.patch("/admin/users/{username}")
async def admin_toggle_user(
    username: str,
    upd: UserStatusUpdate,
    admin: str = Depends(get_admin),
):
    if username not in user_status:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown user")
    user_status[username] = upd.active
    return {"username": username, "active": upd.active}

# ─── WEBSOCKET CHAT ───────────────────────────────────────────
@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    token = ws.query_params.get(API_KEY_NAME)
    if token not in USER_API_KEYS:
        await ws.close(code=1008)
        return

    user = USER_API_KEYS[token]
    if not user_status.get(user, False):
        await ws.close(code=1008)
        return

    async with async_session() as session:
        record = await session.get(Usage, user)
        if not record:
            record = Usage(username=user)
            session.add(record)
            await session.commit()
            await session.refresh(record)
        record.conversations += 1
        session.add(record)
        await session.commit()
    await ws.accept()

    while True:
        try:
            data = await ws.receive_json()
        except WebSocketDisconnect:
            break

        msg = data.get("message", "").strip()
        if not msg:
            continue

        reply = await process_message(user, msg)
        
        await ws.send_json({"reply": reply})

# ─── OPTIONAL HTTP CHAT ───────────────────────────────────────
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

@app.post("/chat", response_model=ChatResponse)
async def chat_http(
    req: ChatRequest,
    user: str = Depends(get_user),
):
    reply = await process_message(user, req.message)
    return ChatResponse(reply=reply)

# ─── RUNNER ───────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
