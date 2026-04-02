# AI中台 · 智能排产业务问答系统

## 一、项目简介

AI中台是一个基于 AI服务中台的智能排产（Advanced Planning and Scheduling）业务问答系统，帮助企业用户通过自然语言与 APS 系统交互，完成插单评估和业务问答两大核心场景。

**核心功能：**
- **插单评估**：用户提交插单需求 → APS 模拟运算 → AI 自动分析对现有订单的影响，生成评估报告
- **业务问答**：通过自然语言查询订单进度、缺料预警、产能负荷、交期风险等业务数据，支持多轮对话

---

## 二、系统架构

### 2.1 统一服务架构（推荐）

```
┌──────────────────────────────────────────────────────────────────────┐
│                           用户浏览器                                    │
│   ┌──────────────────────┐       ┌──────────────────────┐         │
│   │   聊天窗口（业务问答）   │       │    插单评估窗口        │         │
│   │  ApsAIChatWidget      │       │  ApsAIChatWidget     │         │
│   │  mode: 'chat'          │       │  mode: 'evaluate'     │         │
│   └──────────┬───────────┘       └──────────┬───────────┘         │
│              │                             │                       │
│              │    aps-ai-sdk.js             │                       │
└──────────────┼─────────────────────────────┼──────────────────────┘
               │                             │
               ▼                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│              统一 FastAPI 服务 (Port 8000)                            │
│                        src/main.py                                   │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  /api/*  → APS 接口（登录、插单、评估、查询）                       │ │
│  │  /ai/*  → AI网关接口（登录、评估、问答）                           │ │
│  │  /health → 健康检查                                            │ │
│  └────────────────────────────────────────────────────────────────┘ │
│          │                              │                            │
│          ▼                              ▼                            │
│  ┌──────────────────┐      ┌────────────────────────────────┐      │
│  │  APS 模拟服务      │      │   AI服务中台                   │      │
│  │  (MOCK_MODE=true) │      │   /v1/chat-messages           │      │
│  │                   │      │   /v1/workflows/run           │      │
│  └──────────────────┘      └────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 部署方式

| 部署方式 | 说明 |
|----------|------|
| **Docker Compose** | 一键部署，适合容器化环境 |
| **systemctl** | 系统服务方式部署，适合生产 Linux 服务器 |
| **手动启动** | 直接运行 Python 服务，适合开发调试 |

### 2.3 服务说明

| 服务 | 文件 | 端口 | 说明 |
|------|------|------|------|
| 统一服务 | `src/main.py` | 8000 | 整合 APS 接口 + AI网关 + 健康检查 |
| 前端演示页面 | `demo.html` | - | 集成 SDK 的双窗口演示页面（可通过任意静态服务器托管） |

---

## 三、目录结构

```
/opt/aps/
├── README.md                        # 本文档
├── CLAUDE.md                        # Claude Code 开发指南
│
├── docs/                            # 接入文档
│   ├── 客户接入指南.md              # 客户方接入指南（供客户阅读）
│   └── AI服务改造手册.md            # AI 服务部署改造手册（供我方运维/开发阅读）
│
├── src/                             # 统一服务源码（Python + FastAPI）
│   ├── main.py                      # 服务入口（端口 8000）
│   ├── config.py                    # 配置管理
│   ├── aps.py                       # APS 接口模块
│   ├── gateway.py                   # AI 网关模块
│   └── utils.py                     # 工具函数
│
├── aps-mock/                        # 旧版分离服务（已废弃）
│   ├── ai_gateway.py               # AI 网关服务（端口 8001，已废弃）
│   ├── mock_server.py               # APS 模拟服务（端口 8000）
│   ├── test_all.py                  # AI 网关完整流程测试脚本
│   ├── test_gateway.py              # APS 模拟服务接口测试脚本
│   ├── gateway.log                   # AI 网关运行日志
│   ├── server.log                    # APS 模拟服务运行日志
│   ├── gateway.pid                   # AI 网关进程 PID
│   └── server.pid                    # APS 模拟服务进程 PID
│
├── aps-client/                      # 前端资源
│   ├── aps-ai-sdk.js               # 客户端 SDK（聊天组件 + API）
│   ├── demo.html                    # 双窗口演示页面
│   └── verify_api.py                # API 验证脚本
│
├── systemd/                          # systemd 服务配置
│   └── ai-platform.service          # systemctl 服务文件
│
├── docker-compose.yml               # Docker Compose 配置
├── Dockerfile                        # Docker 镜像构建文件
├── install.sh                        # systemctl 安装脚本
└── requirements.txt                  # Python 依赖
```

---

## 四、快速部署

### 4.1 环境要求

- Python 3.10+
- Docker & Docker Compose（使用容器部署时）
- 网络可访问 AI服务中台（`139.224.228.33:8090`）

### 4.2 部署方式一：Docker Compose（推荐）

```bash
# 启动服务
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f

# 停止服务
docker compose down

# 重启服务
docker compose restart
```

**环境变量配置（可选）**：

创建 `.env` 文件或使用环境变量：

```bash
# .env 文件示例
MOCK_MODE=true
APS_BASE_URL=http://localhost:8000
AI_PLATFORM_BASE_URL=http://139.224.228.33:8090/v1
AI_PLATFORM_CHAT_KEY=your_chat_key_here
AI_PLATFORM_WORKFLOW_KEY=your_workflow_key_here
LOG_LEVEL=INFO
```

### 4.3 部署方式二：systemctl（生产 Linux 服务器）

```bash
# 安装服务
sudo ./install.sh

# 启动服务
sudo systemctl start ai-platform

# 停止服务
sudo systemctl stop ai-platform

# 重启服务
sudo systemctl restart ai-platform

# 查看服务状态
sudo systemctl status ai-platform

# 查看日志
tail -f /var/log/ai-platform/stdout.log
tail -f /var/log/ai-platform/stderr.log
```

### 4.4 部署方式三：手动启动（开发调试）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动统一服务（端口 8000）
cd /opt/aps
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000

# 3. 启动前端演示页面（可选）
cd /opt/aps/aps-client
python -m http.server 8002
```

> ⚠️ **注意**：务必使用 `env http_proxy= https_proxy= no_proxy='*'` 取消代理，否则服务无法直连 AI服务中台。

### 4.5 验证服务状态

```bash
# 健康检查
curl http://localhost:8000/health

# 根路径
curl http://localhost:8000/
```

### 4.6 测试账号

| 字段 | 值 |
|------|-----|
| 用户名 | `admin` |
| 密码 | `admin123` |

---

## 五、环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MOCK_MODE` | `true` | 模式切换：`true`=模拟模式，`false`=生产模式 |
| `APS_BASE_URL` | `http://localhost:8000` | APS 服务地址（生产模式使用） |
| `AI_PLATFORM_BASE_URL` | `http://139.224.228.33:8090/v1` | AI服务中台地址 |
| `AI_PLATFORM_CHAT_KEY` | - | 业务问答 Key（必填） |
| `AI_PLATFORM_WORKFLOW_KEY` | - | 插单评估 Key（必填） |
| `LOG_LEVEL` | `INFO` | 日志级别：DEBUG, INFO, WARNING, ERROR |

---

## 六、SDK 集成指南（重点）

### 5.1 快速演示

部署后直接访问：

```
http://192.168.253.128:8002/demo.html
```

页面包含两个并排窗口：
- **左窗口（聊天模式）**：输入自然语言问题，AI 实时回答
- **右窗口（评估模式）**：点击按钮触发插单评估，AI 生成分析报告

### 5.2 运行时配置（必须）

**SDK 地址通过 `window.APS_CONFIG` 运行时配置**，不写死在代码里。

在 `aps-ai-sdk.js` **之前**定义 `window.APS_CONFIG`：

```html
<!-- 1. 配置网关地址（必须写在 aps-ai-sdk.js 之前）-->
<script>
  window.APS_CONFIG = {
    BASE_URL: 'http://192.168.253.128:8000'  // ← 改成你的统一服务地址
  }
</script>

<!-- 2. 引入 SDK -->
<script src="aps-ai-sdk.js"></script>

<!-- 3. 初始化聊天窗口 -->
<script>
  // 聊天模式（业务问答）
  ApsAIChatWidget.mount('#chat-panel', { mode: 'chat' })

  // 评估模式（插单评估）
  ApsAIChatWidget.mount('#eval-panel', { mode: 'evaluate' })
</script>
```

> 默认值（未配置时）：`http://localhost:8000`
>
> 报表页面地址从 `BASE_URL` 自动推导，例如 `BASE_URL: 'http://x:8000'` → 报表地址 `http://x:8000/report`

### 5.3 ApsAI 核心 API

登录状态在多个组件间共享，调用任意 API 前需先登录。

```javascript
// ─── 登录 ───────────────────────────────────────
await ApsAI.login(userName, password, orgId?)
// 返回: { token, userId, userName, fullName }

// ─── 业务问答（流式，支持多轮对话）───────────────────
// 推荐使用 ApsAIChatWidget，只需 mount 即可
// 也可直接调用底层 API：
await ApsAI.chat(message, {
  onChunk:  (text) => { /* 打字机效果，逐字显示 */ },
  onDone:   (answer, conversationId) => { /* 回答完成 */ },
  onError:  (err) => { /* 错误：{ code, message } */ }
})

// ─── 插单评估（流式）───────────────────────────────
// 推荐使用 ApsAIChatWidget
// 也可直接调用底层 API：
await ApsAI.evaluateRushOrders({
  onStatus: (msg) => { /* 状态变化，如"正在提交..." */ },
  onChunk:  (text) => { /* 打字机效果 */ },
  onDone:   (answer, conversationId) => { /* 报告完成 */ },
  onError:  (err) => { /* 错误 */ }
})

// ─── 清除对话历史 ─────────────────────────────────
await ApsAI.clearConversation()

// ─── 查询状态 ─────────────────────────────────────
ApsAI.isLoggedIn()          // 是否已登录
ApsAI.getToken()            // 获取当前 token
ApsAI.getConversationId()   // 获取当前对话 ID
ApsAI.getReportUrl()        // 获取报表页面 URL
```

### 5.4 ApsAIChatWidget UI 组件

```javascript
// 挂载一个聊天窗口
// mode: 'chat'     → 业务问答模式（显示快捷问题建议）
// mode: 'evaluate' → 插单评估模式（显示"触发评估"按钮）
ApsAIChatWidget.mount(selector, {
  mode: 'chat'  // 或 'evaluate'
})
```

**chat 模式快捷问题建议**（点击直接发送）：

```javascript
const SUGGESTED = [
  '最近有哪些物料缺料预警？',
  '本周产能负荷情况如何？',
  '近两周有哪些交期风险？',
  '查询订单 SO20250001 进度',
]
```

**evaluate 模式交互流程**：

1. 点击 **"触发插单评估"** → AI 生成分析报告
2. 报告末尾提示"回复'是'或'查看详细'" → 点击后展示报表链接
3. 用户也可直接追问（回复其他内容触发多轮对话）

### 5.5 完整嵌入示例

```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>AI中台</title>
<style>
  body { font-family: "PingFang SC", sans-serif; background: #f0f2f5;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .panel { width: 420px; height: 640px; box-shadow: 0 8px 40px rgba(0,0,0,.12);
           border-radius: 12px; overflow: hidden; }
</style>
</head>
<body>

<!-- SDK 配置（必须在前）-->
<script>
  window.APS_CONFIG = {
    BASE_URL: 'http://192.168.253.128:8001'  // ← 改成实际网关地址
  }
</script>

<div id="chat-panel" class="panel"></div>

<script src="aps-ai-sdk.js"></script>
<script>
  ApsAIChatWidget.mount('#chat-panel', { mode: 'chat' })
</script>

</body>
</html>
```

### 5.6 多窗口共享登录状态

同一页面多个 `ApsAIChatWidget` 实例共享同一个 `ApsAI` 实例，登录一次即可在多个窗口间共享状态：

```javascript
// 两个窗口共享登录状态
ApsAIChatWidget.mount('#chat-panel',  { mode: 'chat' })     // 业务问答
ApsAIChatWidget.mount('#eval-panel',  { mode: 'evaluate' })  // 插单评估
```

---

## 七、统一服务接口（Port 8000）

### 7.1 AI 网关接口（`/ai/*`）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/ai/login` | POST | 用户登录，返回网关 Token |
| `/ai/rush-order/evaluate/start` | POST | 触发插单评估，返回 taskId |
| `/ai/rush-order/evaluate/status/{taskId}` | GET | 轮询评估状态（running → completed） |
| `/ai/rush-order/evaluate/analyze/{taskId}/stream` | POST | 获取 AI 分析报告（流式） |
| `/ai/chat/stream` | POST | 业务问答（流式，支持多轮对话） |
| `/ai/conversation/{convId}` | DELETE | 清除对话历史 |

### 7.2 APS 接口（`/api/*`）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/login` | POST | 登录 |
| `/api/aps/rush-order/paging` | POST | 插单分页查询 |
| `/api/aps/rush-order-evaluate` | GET | 触发评估运算（约3秒） |
| `/api/aps/rush-order-evaluate/warning` | GET | 轮询评估状态 |
| `/api/aps/affect-order/paging` | POST | 受影响订单查询 |
| `/api/aps/order` | GET | 订单进度查询（无需 Token） |
| `/api/aps/shortage` | GET | 缺料预警查询（无需 Token） |
| `/api/aps/capacity` | GET | 产能负荷查询（无需 Token） |
| `/api/aps/risk` | GET | 交期风险查询（无需 Token） |
| `/report` | GET | 插单评估报表页面（HTML） |

### 7.3 健康检查接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 根路径，返回服务状态 |
| `/health` | GET | 健康检查，返回可用端点列表 |

---

## 八、业务问答流程

```
用户提问
  ↓
SDK: POST /ai/chat/stream
  ↓
AI 网关：验证 Token，转发 AI服务中台 /chat-messages
  ↓
AI服务中台：解析意图 → 调用 APS 查询接口 → 整合结果生成回答
  ↓
流式返回 agent_message 事件（每个字一块）
  ↓
网关：转换为 { type: 'chunk', content: '字' } SSE 事件
  ↓
SDK：onChunk 回调，打字机效果展示
  ↓
AI服务中台：返回 message_end 事件
  ↓
SDK：onDone 回调，携带 conversationId 供追问
```

**SDK 调用示例（底层 API）**：

```javascript
await ApsAI.chat('最近有哪些缺料预警？', {
  onChunk:  (text) => { bubble.innerHTML += text },        // 打字机效果
  onDone:   (answer, conversationId) => { convId = conversationId },
  onError:  (err)  => { console.error('错误:', err.message) }
})

// 追问（携带 conversationId）
await ApsAI.chat('哪个最紧急？', {
  conversationId: convId,  // 传入上一轮的 ID，保持上下文
  onChunk:  (text) => { /* ... */ },
  onDone:   (answer) => { /* ... */ },
})
```

**支持的业务问题类型**：

| 问题类型 | APS 接口 | 示例问题 |
|----------|----------|----------|
| 订单进度 | `GET /api/aps/order` | "订单 SO20250001 进度如何？" |
| 缺料预警 | `GET /api/aps/shortage` | "最近有哪些缺料预警？" |
| 产能负荷 | `GET /api/aps/capacity` | "本周产能负荷情况如何？" |
| 交期风险 | `GET /api/aps/risk` | "近两周有哪些交期风险？" |

---

## 九、插单评估流程

```
用户点击"触发评估"
  ↓
SDK: POST /ai/rush-order/evaluate/start
  ↓
AI 网关 → APS: GET /api/aps/rush-order-evaluate（触发异步运算）
  ↓
SDK 轮询 GET /ai/rush-order/evaluate/status/{taskId}
  ↓
APS: GET /api/aps/rush-order-evaluate/warning → data=null（运算完成）
  ↓
网关自动拉取：POST /api/aps/rush-order/paging + POST /api/aps/affect-order/paging
  ↓
SDK: POST /ai/rush-order/evaluate/analyze/{taskId}/stream
  ↓
AI服务工作流：分析 rush_order + affect_order 两张表
  ↓
流式返回 AI 分析报告 → SDK 展示
  ↓
用户回复"是"/"查看详细" → 展示报表链接
  ↓
用户也可追问 → 携带 conversationId 触发多轮对话
```

**SDK 调用示例**：

```javascript
await ApsAI.evaluateRushOrders({
  onStatus: (msg) => { statusDiv.textContent = msg },          // "正在提交评估..."
  onChunk:  (text) => { reportDiv.innerHTML += text },       // 打字机效果
  onDone:   (answer, conversationId) => {
    convId = conversationId
    // 评估完成，可追问
  },
  onError:  (err) => { alert('评估失败: ' + err.message) }
})
```

---

## 十、SDK 配置详解

### 10.1 配置项

```javascript
window.APS_CONFIG = {
  BASE_URL: 'http://192.168.253.128:8000'  // 统一服务地址（端口 8000）
}
```

### 10.2 地址自动推导规则

| BASE_URL | 报表地址 | 说明 |
|----------|----------|------|
| `http://x:8000` | `http://x:8000/report` | 统一服务 |
| `https://x.com:8443` | `https://x.com:8443/report` | 端口不变 |
| `http://x.com` | `http://x.com/report` | 默认端口 80 |

### 10.3 CORS 跨域

如果网关和前端不在同源下，需要在网关或 nginx 配置 CORS。网关已默认配置 `allow_origins=["*"]`，可直接使用。

---

## 十一、常见问题

### Q1: 登录返回"APS 登录服务异常"

**原因**：APS 服务未启动，或使用了代理导致无法连接。

**解决**：
```bash
# 确认服务运行中
curl http://localhost:8000/health

# 重启时取消代理
env http_proxy= https_proxy= no_proxy='*' python -m uvicorn src.main:app
```

### Q2: 聊天窗口发送问题后无回复，但 curl 测试正常

**原因**：浏览器代理缓冲了 SSE 流式响应，导致浏览器无法逐块接收。

**解决**：
1. 浏览器代理设置中将 `139.224.228.33` 加入**绕过列表**
2. 或使用 VPN/直连网络

**排查方法**：打开浏览器 F12 Console，查看 SDK 日志：
- `[ApsAI] chat 请求发送` → 请求已发出
- `[ApsAI] 收到响应: 200 OK` → 网关响应正常
- `[ApsAI] 开始读取流...` → 开始接收流
- `[ApsAI] chunk 事件` → 收到数据（有 chunk 才正常）
- `[ApsAI] error 事件` → 有错误（看 message）
- `[ApsAI] done 事件` → 回答完成

### Q3: 流式响应出现乱码或 JSON 解析失败

**原因**：AI服务中台返回的 SSE 行结束符为 `\r\n`，未正确处理。

**解决**：已修复，参考 `src/gateway.py` 中的 `raw_line = line.rstrip('\r')`。

### Q4: 插单评估正常但 AI 报告为空

**原因**：`evaluate_analyze_stream` 未正确处理 AI服务工作流的 `text_chunk` 和 `workflow_finished` 事件。

**解决**：确认 `src/gateway.py` 中同时处理了：
- `t == "text_chunk"` → yield chunk
- `t == "workflow_finished"` → yield done

### Q5: 报表链接 404

**原因**：报表链接地址配置错误，或服务未启动。

**解决**：
1. 确认 `BASE_URL` 配置正确
2. 确认统一服务运行在端口 8000

### Q6: 多标签页登录状态不共享

**原因**：每个浏览器标签页的 `localStorage` 和内存状态是独立的。

**解决**：`ApsAI` 的登录 Token 保存在 JS 内存中，不跨标签页共享。如需跨标签页，可将 Token 存入 `localStorage`，并在页面加载时读取。

---

## 十二、数据规范

集成 APS 接口时需注意以下字段的格式要求：

| 字段 | 要求 | 说明 |
|------|------|------|
| `remark` | 返回 `""` 而非 `null` | 无备注时必须为空字符串 |
| `materialBottlenecks` | 返回 `[]` 而非 `null` | 无瓶颈时返回空数组 |
| `capacityBottlenecks` | 返回 `[]` 而非 `null` | 无瓶颈时返回空数组 |
| `gapDays` | 正数=延迟，负数=提前 | scheduledDate - dueDate |
| `delayedTop10` | 按 `delayDays` 降序排列 | 延迟最多的排在最前 |

---

## 十三、服务日志

运行时各服务的日志文件：

| 部署方式 | 日志文件 |
|----------|----------|
| Docker | `docker compose logs -f ai-platform` |
| systemctl | `/var/log/ai-platform/stdout.log` |
| 手动启动 | 输出到控制台 |

查看实时日志：
```bash
# Docker
docker compose logs -f

# systemctl
tail -f /var/log/ai-platform/stdout.log
```

网关 `chat_stream` 函数内置了详细的调试日志，包含：
- 收到请求的完整信息
- AI服务中台返回状态码
- 每种事件的处理计数
- `agent_thought` 事件（AI 思考过程）
- 异常栈信息
