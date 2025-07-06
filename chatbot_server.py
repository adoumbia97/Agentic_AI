import time
from collections import defaultdict
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select
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


usage_cache = defaultdict(lambda: {
    "conversations": 0,
    "messages": 0,
    "first_request": None,
    "last_request": None,
    "total_user_words": 0,
    "total_bot_words": 0,
})
conversations_cache = defaultdict(list)

engine = create_engine("sqlite:///chat.db")


def init_db():
    SQLModel.metadata.create_all(engine)

    # migrate in-memory data if present and db empty
    with Session(engine) as session:
        has_usage = session.exec(select(Usage)).first() is not None
        if not has_usage and usage_cache:
            for user, data in usage_cache.items():
                session.add(Usage(username=user, **data))
        has_msgs = session.exec(select(Message)).first() is not None
        if not has_msgs and conversations_cache:
            for user, msgs in conversations_cache.items():
                for m in msgs:
                    session.add(
                        Message(
                            username=user,
                            role=m["role"],
                            content=m["content"],
                            timestamp=m["ts"],
                        )
                    )
        session.commit()

# ─── AGENT SETUP ───────────────────────────────────────────────
@function_tool
def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny."

agent = Agent(
    name="Hello world",
    instructions="You are a helpful agent.",
    tools=[get_weather],
)

app = FastAPI()


@app.on_event("startup")
def startup_event():
    init_db()

# ─── SERVE FRONTEND ────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    return HTMLResponse(open("index.html", encoding="utf-8").read())

# ─── USER HISTORY & USAGE ──────────────────────────────────────
@app.get("/history")
async def get_history(user: str = Depends(get_user)):
    """Return chat history for the user."""
    with Session(engine) as session:
        msgs = session.exec(
            select(Message).where(Message.username == user).order_by(Message.timestamp)
        ).all()
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
    with Session(engine) as session:
        u = session.get(Usage, user)
        if not u:
            u = Usage(username=user)
            session.add(u)
            session.commit()
            session.refresh(u)
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
    with Session(engine) as session:
        users_data = {}
        for u in USER_API_KEYS.values():
            record = session.get(Usage, u)
            if not record:
                record = Usage(username=u)
                session.add(record)
                session.commit()
                session.refresh(record)
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

    with Session(engine) as session:
        record = session.get(Usage, user)
        if not record:
            record = Usage(username=user)
            session.add(record)
            session.commit()
            session.refresh(record)
        record.conversations += 1
        session.add(record)
        session.commit()
    await ws.accept()

    while True:
        try:
            data = await ws.receive_json()
        except WebSocketDisconnect:
            break

        msg = data.get("message", "").strip()
        if not msg:
            continue

        ts = int(time.time() * 1000)
        with Session(engine) as session:
            rec = session.get(Usage, user)
            if rec.first_request is None:
                rec.first_request = ts
            rec.messages += 1
            rec.last_request = ts
            rec.total_user_words += len(msg.split())
            session.add(rec)
            session.add(
                Message(
                    username=user,
                    role="user",
                    content=msg,
                    timestamp=ts,
                )
            )
            session.commit()
            chat_msgs = session.exec(
                select(Message)
                .where(Message.username == user)
                .order_by(Message.timestamp)
            ).all()
            chat_hist = [
                {"role": "system", "content": agent.instructions}
            ] + [
                {"role": m.role, "content": m.content}
                for m in chat_msgs
            ]
        result = await Runner.run(agent, input=chat_hist)
        reply = result.final_output
        with Session(engine) as session:
            rec = session.get(Usage, user)
            rec.total_bot_words += len(reply.split())
            session.add(rec)
            session.add(
                Message(
                    username=user,
                    role="assistant",
                    content=reply,
                    timestamp=ts,
                )
            )
            session.commit()

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
    ts = int(time.time() * 1000)
    with Session(engine) as session:
        rec = session.get(Usage, user)
        if not rec:
            rec = Usage(username=user)
            session.add(rec)
            session.commit()
            session.refresh(rec)
        if rec.first_request is None:
            rec.first_request = ts
        rec.messages += 1
        rec.last_request = ts
        rec.total_user_words += len(req.message.split())
        session.add(rec)
        session.add(
            Message(
                username=user,
                role="user",
                content=req.message,
                timestamp=ts,
            )
        )
        session.commit()
        chat_msgs = session.exec(
            select(Message)
            .where(Message.username == user)
            .order_by(Message.timestamp)
        ).all()
        chat_hist = [
            {"role": "system", "content": agent.instructions}
        ] + [
            {"role": m.role, "content": m.content}
            for m in chat_msgs
        ]
    result = await Runner.run(agent, input=chat_hist)
    reply = result.final_output
    with Session(engine) as session:
        rec = session.get(Usage, user)
        rec.total_bot_words += len(reply.split())
        session.add(rec)
        session.add(
            Message(
                username=user,
                role="assistant",
                content=reply,
                timestamp=ts,
            )
        )
        session.commit()

    return ChatResponse(reply=reply)

# ─── RUNNER ───────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
