# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

APS AI 助手 is an AI-powered Advanced Planning and Scheduling assistant system. It consists of two main components:

- **aps-mock**: Python backend services (FastAPI) - mock APS server + AI gateway
- **aps-client**: JavaScript SDK and demo for frontend integration

## Architecture

```
Client Browser
    │
    ├─→ ai_gateway.py (port 8001) ──→ AI服务中台 (external)
    │         │
    │         └─→ mock_server.py (port 8000) ──→ Mock APS Backend
    │                                              (simulates enterprise APS system)
```

### Services

| Service | File | Port | Purpose |
|---------|------|------|---------|
| Mock APS Server | `aps-mock/mock_server.py` | 8000 | Simulates enterprise APS backend (login, rush orders, evaluation) |
| AI Gateway | `aps-mock/ai_gateway.py` | 8001 | Proxies APS calls + AI服务中台, manages sessions |

### Key API Flows

**Rush Order Evaluation Flow:**
1. Client → `POST /ai/login` (gateway) → APS login
2. Client → `POST /ai/rush-order/evaluate/start` → triggers APS evaluation
3. Client polls `GET /ai/rush-order/evaluate/status/{taskId}` until "completed"
4. Client → `POST /ai/rush-order/evaluate/analyze/{taskId}/stream` → gets AI report via AI服务工作流

**Business Chat Flow:**
1. Client → `POST /ai/chat/stream` → streams AI responses via AI服务中台 chat-messages API

## Commands

### Running Services

```bash
# Start Mock APS Server (port 8000)
cd /opt/aps/aps-mock && ./aps_venv/bin/python mock_server.py

# Start AI Gateway (port 8001) - in another terminal
cd /opt/aps/aps-mock && ./aps_venv/bin/python ai_gateway.py
```

### Testing

```bash
# Test AI Gateway (full flow: login → evaluate → chat)
cd /opt/aps/aps-mock && ./aps_venv/bin/python test_all.py

# Test Mock APS Server directly
cd /opt/aps/aps-mock && ./aps_venv/bin/python test_gateway.py
```

### Client Demo

Open `aps-client/demo.html` in a browser after starting both services.

## Test Credentials

- Username: `admin`
- Password: `admin123`

## Important Data Conventions

From the integration docs (`对接说明文档.md`):

- `remark` field: **must return empty string `""`**, never `null`
- `materialBottlenecks` / `capacityBottlenecks`: **must return empty array `[]`**, never `null`
- `gapDays`: positive = delayed, negative = early
- `delayedTop10`: sorted by `delayDays` descending

## File Structure

```
/opt/aps/
├── CLAUDE.md
├── aps-mock/
│   ├── ai_gateway.py      # AI Gateway service (FastAPI, port 8001)
│   ├── mock_server.py     # Mock APS backend (FastAPI, port 8000)
│   ├── test_all.py        # Gateway integration tests
│   ├── test_gateway.py    # Mock server tests
│   ├── gateway.log        # Gateway service log
│   ├── server.log         # Mock server log
│   └── aps_venv/          # Python virtual environment
│       └── bin/python     # Python interpreter with dependencies
└── aps-client/
    ├── aps-ai-sdk.js      # Client-side JavaScript SDK
    ├── demo.html           # Demo page (chat + evaluate modes)
    └── verify_api.py      # API verification script
```
