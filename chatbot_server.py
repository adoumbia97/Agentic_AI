from collections import defaultdict
from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect,
    Depends, HTTPException, status
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security.api_key import APIKeyQuery, APIKeyHeader
from pydantic import BaseModel
from agents import Agent, Runner, function_tool

# ─── AUTH SETUP ────────────────────────────────────────────
# In a real app you’d load these from env or a DB
API_KEYS = {
    "user1-secret-token": "user1",
    "user2-secret-token": "user2",
}
API_KEY_NAME = "access_token"
api_key_query  = APIKeyQuery(name=API_KEY_NAME, auto_error=False)
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_current_user(
    key_q: str = Depends(api_key_query),
    key_h: str = Depends(api_key_header),
) -> str:
    token = key_q or key_h
    if token in API_KEYS:
        return API_KEYS[token]
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
        headers={"WWW-Authenticate": "API key"},
    )

# ─── USAGE MONITORING ──────────────────────────────────────
# Simple in-memory counters
usage = defaultdict(lambda: {"conversations": 0, "messages": 0})

# ─── AGENT TOOL ────────────────────────────────────────────
@function_tool
def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny."

agent = Agent(
    name="Hello world",
    instructions="You are a helpful agent.",
    tools=[get_weather],
)

# ─── FASTAPI APP ───────────────────────────────────────────
app = FastAPI()

# 1) Serve chat UI
@app.get("/", response_class=HTMLResponse)
async def get_index():
    return HTMLResponse(open("index.html", encoding="utf-8").read())

# 2) Static assets (if you have CSS/JS in ./static)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 3) WebSocket chat with API-key in query: ?access_token=...
@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    token = ws.query_params.get(API_KEY_NAME)
    if token not in API_KEYS:
        await ws.close(code=1008)           # Policy Violation
        return

    user = API_KEYS[token]
    usage[user]["conversations"] += 1      # new conversation

    await ws.accept()
    history = [{"role": "system", "content": agent.instructions}]

    try:
        while True:
            data = await ws.receive_json()
            msg = data.get("message", "").strip()
            if not msg:
                continue

            usage[user]["messages"] += 1   # count every user message

            history.append({"role": "user", "content": msg})
            result = await Runner.run(agent, input=history)
            bot_reply = result.final_output
            history.append({"role": "assistant", "content": bot_reply})

            await ws.send_json({"reply": bot_reply})
    except WebSocketDisconnect:
        print(f"🔌 {user} disconnected")

# 4) (Optional) HTTP POST /chat for REST clients
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

@app.post("/chat", response_model=ChatResponse)
async def chat_http(
    req: ChatRequest,
    user: str = Depends(get_current_user),
):
    usage[user]["messages"] += 1
    history = [
        {"role": "system", "content": agent.instructions},
        {"role": "user",   "content": req.message},
    ]
    result = await Runner.run(agent, input=history)
    return ChatResponse(reply=result.final_output)

# 5) Protected usage endpoint
@app.get("/usage")
async def get_usage(user: str = Depends(get_current_user)):
    return usage[user]

# ─── LAUNCHER ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "chatbot_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
