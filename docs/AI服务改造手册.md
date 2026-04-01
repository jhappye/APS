# APS AI 助手 · AI 服务改造手册

> 本文档面向：AI 服务开发/运维团队
>
> 目标：当客户接入时，如何将模拟服务替换为客户的真实 APS 系统，包括配置改动、接口适配、AI服务中台对接

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      客户 APS 系统                            │
│  （真实的 ERP/MES/APS，需要接入我们的 AI 服务）                 │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ HTTP REST API
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    AI 网关服务（我方）                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  登录代理 / 会话管理                                   │   │
│  │  插单评估流程：触发 → 轮询 → 拉取结果 → 调 AI服务中台         │   │
│  │  业务问答流程：转发 AI服务中台 /chat-messages               │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│                   AI服务中台                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、快速开始

### 2.1 配置文件位置

所有需要根据客户环境修改的配置集中在 `ai_gateway.py` 顶部：

```python
# ─── 配置 ───────────────────────────────────────────────
APS_BASE_URL        = "http://localhost:8000"   # ← 客户 APS 地址
AI_PLATFORM_BASE_URL = "http://139.224.228.33:8090/v1"  # ← AI服务中台地址
AI_PLATFORM_CHAT_KEY = "app-NMXnjStbZL4uA5ufO7CCjOq7"  # ← 业务问答机器人 Key
AI_PLATFORM_WORKFLOW_KEY = "app-20mcGFNUbrVe8UjiZkttDefU"   # ← 插单评估工作流 Key
```

### 2.2 最小改动清单

| 序号 | 改动项 | 文件 | 说明 |
|------|--------|------|------|
| 1 | APS 地址 | `ai_gateway.py` | 客户真实 APS 后台 URL |
| 2 | AI服务中台地址 | `ai_gateway.py` | AI服务中台地址（客户环境） |
| 3 | AI服务中台聊天 Key | `ai_gateway.py` | 业务问答机器人的 App Key |
| 4 | AI服务工作流 Key | `ai_gateway.py` | 插单评估工作流的 App Key |
| 5 | 登录逻辑 | `ai_gateway.py` | 如果客户有自己的账号体系 |
| 6 | 接口路径 | `ai_gateway.py` | 根据客户 APS 的实际接口路径调整 |
| 7 | 字段映射 | `ai_gateway.py` | APS 返回字段 → AI服务中台输入字段 |

---

## 三、配置详解

### 3.1 APS 地址配置

```python
# 开发测试环境（使用 mock_server）
APS_BASE_URL = "http://localhost:8000"

# 生产环境（客户真实 APS）
APS_BASE_URL = "http://customer-aps-host:8080/api"
```

### 3.2 AI服务中台配置

```python
# AI服务中台地址（包含 /v1 前缀）
AI_PLATFORM_BASE_URL = "http://ai-platform-host:8090/v1"

# 业务问答机器人 App Key
AI_PLATFORM_CHAT_KEY = "app-xxxxxxxxxxxx"

# 插单评估工作流 App Key
AI_PLATFORM_WORKFLOW_KEY = "app-yyyyyyyyyyyy"
```

> **如何获取 AI服务中台 App Key**：登录 AI服务中台 → 进入应用 → API Key

### 3.3 登录代理配置

如果客户 APS 有自己的账号体系，网关的 `/ai/login` 接口需要修改为调用客户登录接口：

```python
@app.post("/ai/login")
async def gateway_login(req: LoginRequest):
    """网关登录：代理客户 APS 登录"""
    async with httpx.AsyncClient(timeout=15) as client:
        # 修改这里：调用客户真实的登录接口
        resp = await client.post(
            f"{APS_BASE_URL}/api/login",    # ← 客户实际路径
            json={
                "userName": req.userName,
                "password": req.password,
                "orgId": req.orgId,
            }
        )
    # ... 后续 token 管理逻辑不变
```

如果客户使用第三方 SSO/OAuth，需要额外适配。

---

## 四、接口路径适配

### 4.1 APS 接口路径映射

AI 网关中硬编码了 mock_server 的接口路径。如果客户 APS 的接口路径不同，需要修改对应位置：

```python
# ai_gateway.py 中需要修改的接口路径：

# 登录
f"{APS_BASE_URL}/api/login"

# 插单评估
f"{APS_BASE_URL}/api/aps/rush-order-evaluate"
f"{APS_BASE_URL}/api/aps/rush-order-evaluate/warning"

# 插单和受影响订单
f"{APS_BASE_URL}/api/aps/rush-order/paging"
f"{APS_BASE_URL}/api/aps/affect-order/paging"
```

**典型客户 APS 路径差异**：

| 功能 | mock_server 路径 | 客户可能路径 |
|------|-----------------|-------------|
| 登录 | `/api/login` | `/auth/login` `/user/login` |
| 触发评估 | `/api/aps/rush-order-evaluate` | `/api/v2/rush-order/evaluate` |
| 查询状态 | `/api/aps/rush-order-evaluate/warning` | `/api/v2/rush-order/evaluate/status` |
| 插单列表 | `/api/aps/rush-order/paging` | `/api/rush-orders` |
| 受影响订单 | `/api/aps/affect-order/paging` | `/api/orders/impact` |

**修改方法**：在 `ai_gateway.py` 中全局搜索接口路径，逐个替换为客户实际路径。

### 4.2 响应状态码适配

mock_server 返回 `statusCode`，但有些 APS 返回 `code`：

```python
# 当前代码（兼容 mock_server）
if body.get("statusCode") != 200:
    raise HTTPException(502, {"code": "APS_ERROR", ...})

# 如果客户返回 code 格式：
if body.get("code") != 0:
    raise HTTPException(502, {"code": "APS_ERROR", ...})
```

需要根据客户 APS 的实际响应结构调整判断逻辑。

---

## 五、字段映射

### 5.1 插单评估结果字段映射

客户 APS 返回的字段名可能与我方不一致。关键映射点在 `evaluate_status` 函数中：

```python
# 当前代码从 APS 响应中取数据：
rush_resp = await client.post(
    f"{APS_BASE_URL}/api/aps/rush-order/paging",
    json={"current": 1, "pageSize": 100},
)
# 响应体需要包含这些字段：
# rushOrders[].orderCode, rushOrders[].materialCode,
# rushOrders[].productScheduleEndDate, rushOrders[].lackDay 等
```

**如果客户 APS 字段名不同**（例如 `orderCode` → `rushOrderNo`），需要在这里做映射：

```python
# 示例：将客户字段映射为标准字段
def map_rush_order(raw):
    return {
        "orderCode": raw.get("rushOrderNo"),      # ← 客户字段名
        "materialCode": raw.get("materialCode"),
        "productScheduleEndDate": raw.get("scheduledDate"),  # ← 字段名不同
        "lackDay": raw.get("gapDays"),            # ← 字段名不同
        # ... 其他字段映射
    }
```

### 5.2 AI服务工作流输入数据格式

插单评估结果会被传给 AI服务工作流，inputs 格式为：

```python
ai_payload = {
    "inputs": {
        "rush_order_body":   json.dumps(rush_orders_data),    # 插单列表 JSON
        "affect_order_body": json.dumps(affect_orders_data), # 受影响订单 JSON
    },
    "response_mode": "streaming",
    "user": session["userId"],
}
```

**AI服务工作流中需要配置**：
- `rush_order_body` 输入变量（类型：段落/文本）
- `affect_order_body` 输入变量（类型：段落/文本）

### 5.3 业务问答数据接口

AI服务中台内部会直接调用客户的 APS 查询接口，不需要经过网关。客户需要确保以下接口可被 AI服务中台服务器访问：

| 接口 | 说明 | AI服务中台调用方式 |
|------|------|--------------|
| `GET /aps/order` | 订单进度 | AI服务中台 HTTP 节点 |
| `GET /aps/shortage` | 缺料预警 | AI服务中台 HTTP 节点 |
| `GET /aps/capacity` | 产能负荷 | AI服务中台 HTTP 节点 |
| `GET /aps/risk` | 交期风险 | AI服务中台 HTTP 节点 |

---

## 六、登录与会话管理

### 6.1 Token 管理机制

AI 网关使用内存字典维护会话：

```python
sessions = {}  # { gateway_token → { aps_token, userId, userName, ... } }
eval_tasks = {}  # { task_id → { status, ... } }
```

**生产环境建议**：
- 使用 Redis 替代内存字典，支持多实例部署
- Token 设置过期时间
- 定期清理过期会话

### 6.2 APS Token 透传

当客户 APS 需要身份验证时，AI 网关保存了 `aps_token`：

```python
sessions[gw_token] = {
    "aps_token": aps_token,   # 客户 APS 的登录 Token
    "userId": ...,
    ...
}
```

后续调用 APS 接口时通过 `Bearer {session['aps_token']}` 透传认证信息。

---

## 七、AI服务中台应用配置

### 7.1 业务问答机器人

**基本信息**：
- 应用类型：聊天助手
- API Key：在 AI服务中台中生成，填入 `AI_PLATFORM_CHAT_KEY`

**提示词配置**（在 AI服务中台中编辑）：

```
你是一个 APS 业务问答助手，可以回答关于订单进度、缺料预警、产能负荷、交期风险等问题。
你可以通过工具查询实时数据，请根据用户问题选择合适的工具。
```

**工具配置**（在 AI服务中台中添加 HTTP 节点）：

| 工具名 | 调用接口 | 说明 |
|--------|----------|------|
| 查询订单 | `GET {APS_BASE_URL}/aps/order` | 订单进度查询 |
| 缺料预警 | `GET {APS_BASE_URL}/aps/shortage` | 缺料预警查询 |
| 产能负荷 | `GET {APS_BASE_URL}/aps/capacity` | 产能负荷查询 |
| 交期风险 | `GET {APS_BASE_URL}/aps/risk` | 交期风险查询 |

### 7.2 插单评估工作流

**基本信息**：
- 应用类型：工作流
- API Key：在 AI服务中台中生成，填入 `AI_PLATFORM_WORKFLOW_KEY`

**工作流结构**：

```
开始
  ↓
LLM 节点（分析 rush_order_body 和 affect_order_body）
  ↓
输出节点（生成分析报告）
  ↓
结束
```

**工作流输入变量**：
- `rush_order_body`（文本）：插单结果 JSON 字符串
- `affect_order_body`（文本）：受影响订单 JSON 字符串

**工作流输出变量**：
- `answer`（文本）：分析报告内容

### 7.3 AI服务中台 API 调用格式

**聊天消息接口**：

```
POST {AI_PLATFORM_BASE_URL}/chat-messages
Authorization: Bearer {AI_PLATFORM_CHAT_KEY}
Content-Type: application/json

{
  "query": "用户问题",
  "user": "user_id",
  "response_mode": "streaming",
  "conversation_id": ""  // 多轮对话时传入
}
```

**工作流接口**：

```
POST {AI_PLATFORM_BASE_URL}/workflows/run
Authorization: Bearer {AI_PLATFORM_WORKFLOW_KEY}
Content-Type: application/json

{
  "inputs": {
    "rush_order_body": "...",
    "affect_order_body": "..."
  },
  "response_mode": "blocking",
  "user": "user_id"
}
```

---

## 八、网络要求

### 8.1 端口需求

| 源 | 目标 | 端口 | 说明 |
|----|------|------|------|
| AI 网关 | 客户 APS | 443/8080 等 | 调用客户接口获取数据 |
| AI 网关 | AI服务中台 | 8090 | 调用 AI服务中台 API |
| 客户 APS | AI 网关 | 8001 | 客户提供给前端的网关地址 |
| AI服务中台 | 客户 APS | 443/8080 等 | AI服务中台工具调用客户接口 |

### 8.2 防火墙配置

确保以下流量可通：

```
AI 网关服务器 → 客户 APS 服务器：允许 HTTP/HTTPS
AI 网关服务器 → AI服务中台服务器：允许 HTTP/HTTPS
AI服务中台服务器 → 客户 APS 服务器：允许 HTTP/HTTPS（用于 AI服务中台工具调用）
```

### 8.3 代理设置

如果 AI 网关服务器需要通过代理访问外网：

```bash
# 启动网关时设置代理
nohup env http_proxy=http://your-proxy:7890 \
        https_proxy=http://your-proxy:7890 \
        no_proxy='localhost,127.0.0.1,customer-aps-host' \
        python3 ai_gateway.py &
```

> **重要**：`no_proxy` 必须包含客户 APS 地址，否则代理会干扰内网调用。

---

## 九、部署清单

### 9.1 部署前检查

```bash
# 1. 确认 APS 地址可达
curl --noproxy '*' http://customer-aps-host:8080/api/health

# 2. 确认 AI服务中台可达
curl --noproxy '*' http://ai-platform-host:8090/v1/healthy

# 3. 确认 AI服务中台 API Key 有效
curl --noproxy '*' -H "Authorization: Bearer {AI_PLATFORM_CHAT_KEY}" \
     http://ai-platform-host:8090/v1/chat-messages \
     -X POST -H "Content-Type: application/json" \
     -d '{"query":"hi","user":"test","response_mode":"streaming","inputs":{}}'
```

### 9.2 启动命令

```bash
# 1. 启动 APS 模拟服务（可选，仅开发测试用）
nohup env http_proxy= https_proxy= no_proxy='*' \
  python3 mock_server.py > server.log 2>&1 &

# 2. 启动 AI 网关
nohup env http_proxy= https_proxy= no_proxy='*' \
  python3 ai_gateway.py > gateway.log 2>&1 &

# 3. 验证网关
curl --noproxy '*' http://localhost:8001/health
```

### 9.3 进程管理（systemd 示例）

```ini
# /etc/systemd/system/ai-gateway.service
[Unit]
Description=APS AI Gateway Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aps/aps-mock
Environment="http_proxy="
Environment="https_proxy="
Environment="no_proxy=*"
ExecStart=/usr/bin/python3 /opt/aps/aps-mock/ai_gateway.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable ai-gateway
sudo systemctl start ai-gateway
sudo systemctl status ai-gateway
```

---

## 十、调试与日志

### 10.1 日志文件

| 文件 | 内容 |
|------|------|
| `gateway.log` | AI 网关所有请求日志 |
| `server.log` | mock_server 请求日志（仅开发测试） |

### 10.2 实时调试日志

`ai_gateway.py` 的 `chat_stream` 函数内置了详细调试日志，会打印：

```
[CHAT] 收到请求: message='...' userId=... conversationId=...
[CHAT] 正在转发到 AI服务中台: http://ai-platform-host:8090/v1/chat-messages
[CHAT] AI服务中台返回状态: 200
[CHAT] agent_thought: tool=business_res thought=...
[CHAT] 收到 message_end, conv_id=..., event_count={'chunk': 50, 'done': 1, ...}
```

### 10.3 常见错误排查

| 错误现象 | 可能原因 | 解决方式 |
|----------|----------|----------|
| 登录返回 "APS 登录服务异常" | APS 地址不可达 / 代理干扰 | `curl --noproxy '*'` 测试 APS |
| AI服务中台返回 400 | App Key 无效 / 参数格式错误 | 检查 AI_PLATFORM_CHAT_KEY 和请求体 |
| AI服务中台返回 500 | AI服务中台内部错误 | 检查 AI服务中台日志 |
| 流式无 chunk 到达 | 代理缓冲了 SSE | 配置 no_proxy / 浏览器绕过代理 |
| 评估状态一直 running | APS 运算未完成 / 接口路径错误 | 检查 APS 的 warning 接口 |
| AI服务中台工具调用失败 | AI服务中台无法访问客户 APS | 检查 AI服务中台 → APS 网络通断 |

---

## 十一、生产环境注意事项

### 11.1 高可用

当前 `sessions` 和 `eval_tasks` 使用内存字典：
- **问题**：重启网关后会话丢失，无法多实例部署
- **解决**：改用 Redis 存储会话和评估任务状态

### 11.2 安全

- `GATEWAY_TOKEN` 建议改为客户专属 Token
- 客户 APS Token 加密存储
- 对外暴露的网关地址建议配置 HTTPS
- 考虑在网关层加接口调用频率限制

### 11.3 监控

建议接入监控：
- 请求成功率
- 平均响应时间
- AI服务中台 API 调用失败率
- 评估任务队列长度

### 11.4 配置分离

建议将配置项移至环境变量或配置文件：

```python
import os

APS_BASE_URL     = os.getenv("APS_BASE_URL",     "http://localhost:8000")
DIFY_BASE_URL    = os.getenv("DIFY_BASE_URL",    "http://localhost:8090/v1")
DIFY_API_KEY     = os.getenv("DIFY_API_KEY",     "")
DIFY_WORKFLOW_A_KEY = os.getenv("DIFY_WORKFLOW_A_KEY", "")
```

```bash
# .env 文件
APS_BASE_URL=http://customer-aps:8080/api
AI_PLATFORM_BASE_URL=http://ai-platform:8090/v1
AI_PLATFORM_CHAT_KEY=app-xxxxxxxxxxxx
AI_PLATFORM_WORKFLOW_KEY=app-yyyyyyyyyyyy
```

启动时加载：
```bash
export $(cat /opt/aps/.env | xargs)
python3 ai_gateway.py
```
