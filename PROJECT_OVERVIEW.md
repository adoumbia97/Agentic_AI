# Project Overview

This document captures the full context of your AI-powered chatbot application, including its purpose, architecture, directory layout, and file responsibilities. You can refer back to this when asking any AI assistant for help or onboarding new developers.

---

## 🚀 Purpose

Build a lightweight, production-grade AI chatbot with:

- **FastAPI** backend serving both HTTP and WebSocket endpoints  
- **WebSocket** chat for real-time, stateful conversations  
- **Token-based auth** for “user” vs “admin” roles  
- **Persistent** in-memory conversation history per user  
- **Admin dashboard** to view usage metrics and (de)activate users  
- **Single-page** Bootstrap UI with Chat + Admin tabs  

---

## 📁 Directory Structure

├── chatbot_server.py # FastAPI application (API + WebSocket + auth + usage)
├── index.html # Single-page frontend (Chat + Admin UI)
├── static/ # (optional) put CSS/JS/assets here if needed
│ └── ...
├── requirements.txt # Python deps (FastAPI, Uvicorn, pydantic, agents, etc.)
└── PROJECT_OVERVIEW.md # (this file) project description & structure
---

## 🗂️ File Descriptions

### 1. `chatbot_server.py`

- **Imports & Config**  
  - `FastAPI`, `WebSocket`, `Depends`, `HTTPException`, etc.  
  - `APIKeyQuery` / `APIKeyHeader` for extracting `access_token`  
  - In-memory stores:  
    - `USER_API_KEYS` / `ADMIN_API_KEYS` → token→username maps  
    - `user_status` → activation flags  
    - `usage` dict → per-user metrics (conversations, messages, first/last timestamps, word counts)  
    - `conversations` dict → per-user message history with `{ role, content, ts }`  

- **Auth Dependencies**  
  - `get_user` → validates user token & activation  
  - `get_admin` → validates admin token  

- **Endpoints**  
  - `GET /` → serves `index.html`  
  - `GET /history` → returns `{ username, history: [ { who, text, ts }, … ] }`  
  - `GET /usage` → returns per-user usage + username  
  - `GET /admin/users` → returns `{ username: admin, users: { user1: {…}, user2: {…} } }`  
  - `PATCH /admin/users/{username}` → toggles a user’s active flag  
  - `WebSocket /ws/chat` → real-time chat stream (requires valid user token)  
  - `POST /chat` → optional HTTP fallback for chat  

- **Chat Logic**  
  1. On each user message:  
     - Validate & update metrics (`first_request`, `last_request`, word counts)  
     - Append to `conversations[user]` with `role="user"`  
     - Build OpenAI-compatible history (`system` + previous `role, content`)  
     - Call `Runner.run(agent, input=history)`  
     - Append assistant reply to store with `role="assistant"`  
     - Send reply over WS or HTTP  

### 2. `index.html`

- **Libraries**  
  - Bootswatch “Flatly” / Bootstrap 5 CDN  
  - Vanilla JS for DOM, fetch & WebSocket  

- **Layout**  
  - **Navbar** with tabs: Chat & Admin  
  - **Login row**:  
    - Role selector (User/Admin)  
    - Token input + Login/Logout buttons  
    - “New Conversation” & “My Usage” (User only)  
    - Logged-in username label  
    - Alert area for errors or info  

  - **Chat tab**:  
    - Centered **Card** (700×400) with scrollable chat pane  
    - Input + Send button (Enter key sends)  

  - **Admin tab**:  
    - Card with **table** showing per-user:  
      - Active status, conversations, messages  
      - first_request, last_request (human-readable)  
      - total_user_words, total_bot_words  
      - Action button to Activate/Deactivate  

- **UX Details**  
  - Persist token/role/username in `localStorage` to survive reloads  
  - On User login → fetch `/history`, replay bubbles, open WS  
  - On Admin login → fetch `/admin/users`, render table & action buttons  
  - Mistyped tokens → dismissible Bootstrap alerts, form remains active  
  - “New Conversation” closes WS and resets local chat only (server sees new convo)  
  - “My Usage” & table show up-to-date metrics  

---

## 📦 Dependencies

Track in `requirements.txt`:



Install with:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn chatbot_server:app --reload --host 0.0.0.0 --port 8000


Test API Keys:

User1: user1-token → user1

User2: user2-token → user2

Admin: admin-token → admin



