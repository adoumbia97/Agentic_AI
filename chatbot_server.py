import time
from pathlib import Path
from collections import defaultdict
from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect,
    Depends, HTTPException, status, UploadFile, File
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
usage = defaultdict(lambda: {
    "conversations":     0,
    "messages":          0,
    "first_request":     None,
    "last_request":      None,
    "total_user_words":  0,
    "total_bot_words":   0,
})
conversations = defaultdict(list)  # user → list of {role, content, ts}
DOCS_DIR = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)

# ─── AGENT SETUP ───────────────────────────────────────────────
@function_tool
def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny."

@function_tool
def show_time(_: str = "") -> str:
    """Return the current server time."""
    return time.strftime("%Y-%m-%d %H:%M:%S")

@function_tool
def fetch_doc(name: str) -> str:
    """Return the contents of a document stored in docs/."""
    path = DOCS_DIR / name
    if not path.exists():
        return "Document not found."
    return path.read_text()

agent = Agent(
    name="Utility Bot",
    instructions="You are a helpful assistant. You can show the current time, "
                 "fetch documents, or give general guidance.",
    tools=[get_weather, show_time, fetch_doc],
)

app = FastAPI()

# ─── SERVE FRONTEND ────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    return HTMLResponse(open("index.html", encoding="utf-8").read())

# ─── USER HISTORY & USAGE ──────────────────────────────────────
@app.get("/history")
async def get_history(user: str = Depends(get_user)):
    """
    Return [{ who:'user'|'bot', text:str, ts:int }, ...]
    """
    mapped = []
    for m in conversations[user]:
        mapped.append({
            "who": m["role"] == "assistant" and "bot" or "user",
            "text": m["content"],
            "ts": m["ts"],
        })
    return {"username": user, "history": mapped}

@app.get("/usage")
async def user_usage(user: str = Depends(get_user)):
    """
    Return { username, conversations, messages,
             first_request, last_request,
             total_user_words, total_bot_words }
    """
    u = usage[user]
    return {
        "username":            user,
        "conversations":       u["conversations"],
        "messages":            u["messages"],
        "first_request":       u["first_request"],
        "last_request":        u["last_request"],
        "total_user_words":    u["total_user_words"],
        "total_bot_words":     u["total_bot_words"],
    }

# ─── ADMIN: LIST & TOGGLE USERS ───────────────────────────────
@app.get("/admin/users")
async def admin_list_users(admin: str = Depends(get_admin)):
    """
    Return all users with usage + activation status.
    """
    return {
        "username": admin,
        "users": {
            u: {
                **usage[u],
                "active": user_status.get(u, False)
            }
            for u in USER_API_KEYS.values()
        }
    }

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

@app.post("/admin/docs")
async def upload_document(
    file: UploadFile = File(...),
    admin: str = Depends(get_admin),
):
    dest = DOCS_DIR / file.filename
    with dest.open("wb") as f:
        f.write(await file.read())
    return {"filename": file.filename}

@app.get("/admin/history/{username}")
async def admin_history(
    username: str,
    admin: str = Depends(get_admin),
):
    msgs = conversations.get(username, [])
    mapped = [
        {
            "who": m["role"] == "assistant" and "bot" or "user",
            "text": m["content"],
            "ts": m["ts"],
        }
        for m in msgs
    ]
    return {"username": username, "history": mapped}

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

    usage[user]["conversations"] += 1
    await ws.accept()

    while True:
        try:
            data = await ws.receive_json()
        except WebSocketDisconnect:
            break

        msg = data.get("message", "").strip()
        if not msg:
            continue

        if msg.lower() == "clear history":
            conversations[user].clear()
            await ws.send_json({"reply": "History cleared."})
            continue

        ts = int(time.time() * 1000)
        u = usage[user]
        # first request?
        if u["first_request"] is None:
            u["first_request"] = ts
        u["messages"]      += 1
        u["last_request"]  = ts
        u["total_user_words"] += len(msg.split())

        # store and call
        conversations[user].append({"role": "user", "content": msg, "ts": ts})
        # build OpenAI chat history
        chat_hist = (
            [{"role": "system", "content": agent.instructions}]
            + [{"role": m["role"], "content": m["content"]}
               for m in conversations[user]]
        )
        result = await Runner.run(agent, input=chat_hist)
        reply = result.final_output

        u["total_bot_words"] += len(reply.split())
        conversations[user].append({"role": "assistant", "content": reply, "ts": ts})

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
    if req.message.strip().lower() == "clear history":
        conversations[user].clear()
        return ChatResponse(reply="History cleared.")

    u = usage[user]
    if u["first_request"] is None:
        u["first_request"] = ts
    u["messages"]      += 1
    u["last_request"]   = ts
    u["total_user_words"] += len(req.message.split())

    conversations[user].append({"role": "user", "content": req.message, "ts": ts})
    chat_hist = (
        [{"role": "system", "content": agent.instructions}]
        + [{"role": m["role"], "content": m["content"]}
           for m in conversations[user]]
    )
    result = await Runner.run(agent, input=chat_hist)
    reply = result.final_output

    u["total_bot_words"] += len(reply.split())
    conversations[user].append({"role": "assistant", "content": reply, "ts": ts})

    return ChatResponse(reply=reply)

# ─── RUNNER ───────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("chatbot_server:app", host="0.0.0.0", port=8000, reload=True)
