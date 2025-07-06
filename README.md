# Agentic AI Chatbot

This repository contains a lightweight AI-powered chatbot application built with **FastAPI**. It provides a web-based chat interface with token-based authentication and an admin dashboard for monitoring usage.

## Features

- **FastAPI** backend serving HTTP and WebSocket endpoints
- **Real-time chat** with persistent conversation history in memory
- **Token authentication** for users and admins
- **Admin dashboard** to view usage metrics and activate/deactivate users
- **Single-page UI** built with Bootstrap 5

## Project Layout

```
├── chatbot_server.py   # FastAPI application
├── index.html          # Web UI for chat and admin dashboard
├── my_bot.py           # Minimal example agent
├── description.txt     # Full project overview
└── README.md           # This file
```

## Running the Server

1. Create a Python virtual environment and install dependencies (see `requirements.txt` if present).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Start the development server:

```bash
uvicorn chatbot_server:app --reload --host 0.0.0.0 --port 8000
```

3. Open `index.html` in your browser or navigate to `http://localhost:8000` if served by FastAPI.

## API Keys

The server uses simple in-memory API keys for demonstration:

- `user1-token` → user `user1`
- `user2-token` → user `user2`
- `admin-token` → admin `admin`

Use these tokens in the UI when logging in as a user or admin.

## License

This project is provided as-is for demonstration purposes.
