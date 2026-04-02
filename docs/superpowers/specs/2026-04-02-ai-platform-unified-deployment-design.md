# AI中台统一部署架构设计

## 1. 概述

**目标**：将现有的 APS 模拟服务（mock_server.py）和 AI 网关服务（ai_gateway.py）合并为单一服务，统一部署架构。

**核心变更**：
- 两个独立服务 → 单一 FastAPI 应用
- 两个 systemctl 服务 → 一个服务
- 支持模拟/生产模式切换

## 2. 架构设计

### 2.1 统一服务架构

```
                         ┌────────────────────────────────┐
客户端请求 (端口 8000)     │  统一 FastAPI 服务               │
                         │  ┌──────────────────────────┐  │
                         │  │  /api/*  APS接口        │  │
                         │  │  /ai/*  AI网关接口      │  │
                         │  │  /health 健康检查       │  │
                         │  └──────────────────────────┘  │
                         │              ↓                 │
                         │   MOCK_MODE=true:              │
                         │     内部调用模拟数据            │
                         │   MOCK_MODE=false:             │
                         │     外部调用 APS_BASE_URL      │
                         └────────────────────────────────┘
```

### 2.2 路由分组

| 路径 | 说明 | 来源 |
|------|------|------|
| `/api/*` | APS 接口（原 mock_server.py） | 模拟服务 |
| `/ai/*` | AI 网关接口（原 ai_gateway.py） | AI 网关 |
| `/health` | 健康检查 | 统一 |
| `/report` | 报表页面 | 模拟服务 |

### 2.3 模式切换

通过环境变量 `MOCK_MODE` 控制：

| 模式 | MOCK_MODE | APS 数据来源 |
|------|-----------|-------------|
| 模拟模式（开发测试） | `true` | 内置模拟数据 |
| 生产模式（客户部署） | `false` | 外部 APS 系统 |

## 3. 环境变量配置

### 3.1 必填配置

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| `MOCK_MODE` | 模式切换 | `true` / `false` |
| `AI_PLATFORM_BASE_URL` | AI服务中台地址 | `http://139.224.228.33:8090/v1` |
| `AI_PLATFORM_CHAT_KEY` | 业务问答 API Key | `app-xxx` |
| `AI_PLATFORM_WORKFLOW_KEY` | 插单评估 API Key | `app-xxx` |

### 3.2 生产模式额外配置

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| `APS_BASE_URL` | 客户 APS 服务地址 | `http://customer-aps:8080/api` |

### 3.3 可选配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `LOG_FILE` | 日志文件路径 | `/var/log/ai-platform/app.log` |

## 4. 文件结构

```
/opt/aps/
├── docker-compose.yml          # Docker Compose 配置
├── .env.example               # 环境变量示例
├── src/
│   ├── __init__.py
│   ├── main.py                # 统一入口，路由注册
│   ├── aps.py                 # APS 接口（原 mock_server.py）
│   ├── gateway.py             # AI 网关接口（原 ai_gateway.py）
│   ├── config.py             # 配置加载
│   └── utils.py              # 工具函数
├── Dockerfile                 # 镜像构建
└── requirements.txt           # 依赖
```

## 5. 服务管理

### 5.1 systemctl 服务

服务名：`ai-platform`

```ini
[Unit]
Description=AI中台统一服务
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ai-platform
EnvironmentFile=/opt/ai-platform/.env
ExecStart=/opt/ai-platform/venv/bin/python /opt/ai-platform/src/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 5.2 启停命令

```bash
# systemctl
sudo systemctl start ai-platform   # 启动
sudo systemctl stop ai-platform    # 停止
sudo systemctl restart ai-platform # 重启
sudo systemctl status ai-platform  # 状态

# Docker Compose
docker compose up -d      # 启动
docker compose down      # 停止
docker compose restart   # 重启
```

## 6. Docker Compose 配置

```yaml
version: '3.8'
services:
  ai-platform:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ai-platform
    ports:
      - "8000:8000"
    environment:
      - MOCK_MODE=${MOCK_MODE:-true}
      - APS_BASE_URL=${APS_BASE_URL:-}
      - AI_PLATFORM_BASE_URL=${AI_PLATFORM_BASE_URL}
      - AI_PLATFORM_CHAT_KEY=${AI_PLATFORM_CHAT_KEY}
      - AI_PLATFORM_WORKFLOW_KEY=${AI_PLATFORM_WORKFLOW_KEY}
    volumes:
      - ./logs:/var/log/ai-platform
    restart: unless-stopped
```

## 7. 实现步骤

### Step 1: 重构代码结构
- 创建 `src/` 目录
- 分离 APS 接口到 `aps.py`
- 分离 AI 网关到 `gateway.py`
- 提取配置到 `config.py`

### Step 2: 合并路由
- 创建 `main.py` 统一入口
- 注册 `/api/*` 和 `/ai/*` 路由
- 实现模式切换逻辑

### Step 3: Docker 支持
- 创建 `Dockerfile`
- 创建 `docker-compose.yml`
- 创建 `.env.example`

### Step 4: systemd 支持
- 创建 `ai-platform.service`
- 安装脚本

### Step 5: 文档更新
- 更新 README.md
- 更新部署文档
- 清理旧文件

## 8. 向后兼容

- 原有 SDK 调用方式不变（`/ai/*` 接口保持）
- 原有 APS 接口路径不变（`/api/*` 接口保持）
- 仅修改部署架构，不影响业务逻辑
