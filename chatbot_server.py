import time
from collections import defaultdict
from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect,
    Depends, HTTPException, status
)
from fastapi.responses import HTMLResponse
from fastapi.security.api_key import APIKeyQuery, APIKeyHeader
from pydantic import BaseModel
from agents import Agent, Runner, function_tool

# ─── CONFIG ─────────────────────────────────────────────────
USER_API_KEYS  = {"user1-token": "user1", "user2-token": "user2"}
ADMIN_API_KEYS = {"admin-token": "admin"}

API_KEY_NAME   = "access_token"
api_key_query  = APIKeyQuery(name=API_KEY_NAME, auto_error=False)
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_user(
    key_q: str = Depends(api_key_query),
    key_h: str = Depends(api_key_header),
):
    token = key_q or key_h
    if token in USER_API_KEYS:
        return USER_API_KEYS[token]
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid user API key",
        headers={"WWW-Authenticate": "API key"},
    )

def get_admin(
    key_q: str = Depends(api_key_query),
    key_h: str = Depends(api_key_header),
):
    token = key_q or key_h
    if token in ADMIN_API_KEYS:
        return ADMIN_API_KEYS[token]
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid admin API key",
        headers={"WWW-Authenticate": "API key"},
    )

# ─── METRICS & STORAGE ───────────────────────────────────────
usage         = defaultdict(lambda: {"conversations": 0, "messages": 0})
conversations = defaultdict(list)  # user -> list of {who,text,ts}

# ─── AGENT SETUP ────────────────────────────────────────────
@function_tool
def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny."

agent = Agent(
    name="Hello world",
    instructions="You are a helpful agent.",
    tools=[get_weather],
)

app = FastAPI()

# ─── SERVE UI ───────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    return HTMLResponse(open("index.html", encoding="utf-8").read())

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin():
    return HTMLResponse(open("admin.html", encoding="utf-8").read())

# ─── USER HISTORY ENDPOINT ──────────────────────────────────
@app.get("/history")
async def get_history(user: str = Depends(get_user)):
    """
    Return the logged-in user’s full conversation so far.
    """
    return {
        "username": user,
        "history": conversations[user]
    }

# ─── USER USAGE ENDPOINT ────────────────────────────────────
@app.get("/usage")
async def user_usage(user: str = Depends(get_user)):
    """
    Return the logged-in user’s usage + their username.
    """
    return {
        "username": user,
        **usage[user]
    }

# ─── ADMIN USAGE ENDPOINT ───────────────────────────────────
@app.get("/admin/usage")
async def admin_usage(admin: str = Depends(get_admin)):
    """
    Return *all* users’ usage plus the admin’s username.
    """
    return {
        "username": admin,
        "usage": usage
    }

# ─── WEBSOCKET CHAT ────────────────────────────────────────
conversations = defaultdict(list)  
usage = defaultdict(lambda: {"conversations": 0, "messages": 0})

@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    token = ws.query_params.get("access_token")
    if token not in USER_API_KEYS:
        await ws.close(code=1008)
        return

    user = USER_API_KEYS[token]
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

        ts = int(time.time() * 1000)
        # 1) store the user message with a valid role
        conversations[user].append({
            "role":    "user",
            "content": msg,
            "ts":      ts
        })
        usage[user]["messages"] += 1

        # 2) build the OpenAI‐compatible history
        chat_messages = [
            {"role": "system",    "content": agent.instructions}
        ] + [
            {"role": m["role"],  "content": m["content"]}
            for m in conversations[user]
        ]

        # 3) call your agent
        result = await Runner.run(agent, input=chat_messages)
        reply = result.final_output

        # 4) store the assistant reply
        conversations[user].append({
            "role":    "assistant",
            "content": reply,
            "ts":      ts
        })

        await ws.send_json({"reply": reply})


        


# ─── History ────────────────────────────────────
@app.get("/history")
async def get_history(user: str = Depends(get_user)):
    """
    Returns each message as { who: "user"|"bot", text: "...", ts }.
    """
    mapped = []
    for m in conversations[user]:
        mapped.append({
            "who": m["role"] == "assistant" and "bot" or "user",
            "text": m["content"],
            "ts": m["ts"]
        })
    return {
        "username": user,
        "history": mapped
    }

# ─── OPTIONAL HTTP CHAT ────────────────────────────────────
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

@app.post("/chat", response_model=ChatResponse)
async def chat_http(
    req: ChatRequest,
    user: str = Depends(get_user),
):
    ts = int(time.time()*1000)
    usage[user]["messages"] += 1
    conversations[user].append({"who": "user", "text": req.message, "ts": ts})

    result = await Runner.run(agent, input=conversations[user])
    conversations[user].append({"who": "bot", "text": result.final_output, "ts": ts})

    return ChatResponse(reply=result.final_output)

# ─── RUNNER ───────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("chatbot_server:app", host="0.0.0.0", port=8000, reload=True)
