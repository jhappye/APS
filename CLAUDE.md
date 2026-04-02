# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI中台 is an AI-powered Advanced Planning and Scheduling assistant system. It consists of two main components:

- **src/**: Python backend services (FastAPI) - unified service with APS interfaces + AI gateway
- **aps-client/**: JavaScript SDK and demo for frontend integration

## Architecture

```
Client Browser
    │
    └─→ Unified Service (port 8000)
              ├─→ /api/*  APS接口
              └─→ /ai/*  AI网关接口
                        │
                        └─→ AI服务中台 (external)
```

### Unified Service

| Component | File | Description |
|-----------|------|-------------|
| APS Interfaces | `src/aps.py` | APS mock server (login, rush orders, evaluation) |
| AI Gateway | `src/gateway.py` | Proxies APS calls + AI服务中台, manages sessions |
| Entry Point | `src/main.py` | FastAPI application (port 8000) |
| Configuration | `src/config.py` | Environment variable configuration |

### Running Service

**Option 1: Python directly**
```bash
cd /opt/aps
pip install -r requirements.txt
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

**Option 2: Docker Compose**
```bash
docker compose up -d
docker compose down
```

**Option 3: systemctl (after install)**
```bash
sudo ./install.sh
sudo systemctl start ai-platform
```

### Key API Flows

**Rush Order Evaluation Flow:**
1. Client → `POST /ai/login` (gateway) → APS login
2. Client → `POST /ai/rush-order/evaluate/start` → triggers APS evaluation
3. Client polls `GET /ai/rush-order/evaluate/status/{taskId}` until "completed"
4. Client → `POST /ai/rush-order/evaluate/analyze/{taskId}/stream` → gets AI report via AI服务工作流

**Business Chat Flow:**
1. Client → `POST /ai/chat/stream` → streams AI responses via AI服务中台 chat-messages API

## Configuration

The service uses environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| MOCK_MODE | Enable mock mode | `true` |
| APS_BASE_URL | APS backend URL | `http://localhost:8000` |
| AI_PLATFORM_BASE_URL | AI服务中台 URL | `http://139.224.228.33:8090/v1` |
| AI_PLATFORM_CHAT_KEY | Chat API Key | - |
| AI_PLATFORM_WORKFLOW_KEY | Workflow API Key | - |

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
├── README.md
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── main.py          # Unified service entry point
│   ├── aps.py           # APS interfaces
│   ├── gateway.py        # AI gateway interfaces
│   ├── config.py         # Configuration
│   └── utils.py          # Utility functions
├── systemd/
│   └── ai-platform.service  # systemctl service
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── aps-client/
    ├── aps-ai-sdk.js      # Client-side JavaScript SDK
    ├── demo.html           # Demo page
    └── verify_api.py       # API verification script
```
