# APS AI 助手 · 智能排产业务问答系统

## 一、项目简介

APS AI 助手是一个基于 Dify AI 的智能排产（Advanced Planning and Scheduling）业务问答系统，帮助企业用户通过自然语言与 APS 系统交互，完成插单评估和业务问答两大核心场景。

**核心功能：**
- **插单评估**：用户提交插单需求，AI 自动分析对现有订单的影响，生成评估报告
- **业务问答**：通过自然语言查询订单进度、缺料预警、产能负荷、交期风险等业务数据

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                          用户浏览器                                    │
│  ┌──────────────────────┐     ┌──────────────────────┐             │
│  │    聊天窗口（业务问答）    │     │   插单评估窗口          │             │
│  │  ApsAIChatWidget     │     │  ApsAIChatWidget     │             │
│  │  mode: 'chat'         │     │  mode: 'evaluate'    │             │
│  └──────────┬───────────┘     └──────────┬───────────┘             │
│             │                            │                          │
│             │    aps-ai-sdk.js           │                          │
└─────────────┼────────────────────────────┼──────────────────────────┘
              │                            │
              ▼                            ▼
┌───────────────────────────────────────────────────────────────────┐
│                    AI 网关服务  (Port 8001)                         │
│                         ai_gateway.py                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  登录代理 → 会话管理 → 插单评估流程 → 业务问答（转发 Dify）         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│           │                                  │                     │
│           ▼                                  ▼                     │
│  ┌──────────────────┐            ┌───────────────────────┐       │
│  │  APS 模拟服务      │            │  Dify AI 服务           │       │
│  │  mock_server.py  │            │  (139.224.228.33:8090) │       │
│  │  (Port 8000)     │            └───────────────────────┘       │
│  └──────────────────┘                                              │
└───────────────────────────────────────────────────────────────────┘
```

### 服务说明

| 服务 | 文件 | 端口 | 说明 |
|------|------|------|------|
| APS 模拟服务 | `mock_server.py` | 8000 | 模拟企业 APS 后台，提供登录、插单、评估等接口 |
| AI 网关服务 | `ai_gateway.py` | 8001 | 代理 APS 调用 + Dify AI 转发，维护用户会话 |
| 前端演示页面 | `demo.html` | 8002 | 集成 SDK 的双窗口演示页面（聊天 + 评估） |

---

## 三、目录结构

```
/opt/aps/
├── README.md                        # 本文档
├── CLAUDE.md                        # Claude Code 开发指南
│
├── aps-mock/                        # 后端服务（Python + FastAPI）
│   ├── ai_gateway.py               # AI 网关服务（端口 8001）
│   ├── mock_server.py               # APS 模拟服务（端口 8000）
│   ├── test_all.py                  # 网关完整流程测试脚本
│   ├── test_gateway.py              # 模拟服务接口测试脚本
│   ├── gateway.log                   # 网关服务运行日志
│   ├── server.log                    # 模拟服务运行日志
│   ├── gateway.pid                   # 网关进程 PID
│   └── server.pid                    # 模拟服务进程 PID
│
└── aps-client/                      # 前端资源
    ├── aps-ai-sdk.js                # 客户端 SDK（供前端集成）
    ├── demo.html                    # 双窗口演示页面
    ├── demo_server.log               # Demo 服务日志
    └── demo_server.pid               # Demo 服务 PID
```

---

## 四、快速部署

### 4.1 环境要求

- Python 3.10+
- 网络可访问 Dify 服务（`139.224.228.33:8090`）

### 4.2 安装依赖

```bash
# aps-mock 使用的虚拟环境已包含所有依赖，无需额外安装
# 如需全新安装：
pip install fastapi uvicorn httpx
```

### 4.3 启动所有服务

**推荐启动顺序：**

```bash
# 1. 启动 APS 模拟服务（端口 8000）
cd /opt/aps/aps-mock
nohup env http_proxy= https_proxy= no_proxy='*' python3 mock_server.py > server.log 2>&1 &
echo $! > server.pid

# 2. 启动 AI 网关服务（端口 8001）
nohup env http_proxy= https_proxy= no_proxy='*' python3 ai_gateway.py > gateway.log 2>&1 &
echo $! > gateway.pid

# 3. 启动前端演示页面（端口 8002）
nohup env http_proxy= https_proxy= no_proxy='*' python3 -m http.server 8002 \
  --directory /opt/aps/aps-client > /opt/aps/aps-client/demo_server.log 2>&1 &
echo $! > /opt/aps/aps-client/demo_server.pid
```

**验证服务状态：**

```bash
# APS 模拟服务
curl -s http://localhost:8000/

# AI 网关服务
curl -s http://localhost:8001/health

# 前端演示页面
curl -s http://localhost:8002/demo.html | head -3
```

### 4.4 测试账号

| 字段 | 值 |
|------|-----|
| 用户名 | `admin` |
| 密码 | `admin123` |

---

## 五、接口说明

### 5.1 AI 网关接口（`/ai/*`）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/ai/login` | POST | 用户登录，返回网关 Token |
| `/ai/rush-order/evaluate/start` | POST | 触发插单评估 |
| `/ai/rush-order/evaluate/status/{taskId}` | GET | 轮询评估状态 |
| `/ai/rush-order/evaluate/analyze/{taskId}/stream` | POST | 获取 AI 分析报告（流式） |
| `/ai/chat/stream` | POST | 业务问答（流式，支持多轮对话） |
| `/ai/chat` | POST | 业务问答（阻塞式） |
| `/ai/conversation/{convId}` | DELETE | 清除对话历史 |

### 5.2 APS 模拟服务接口（`/api/*`）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/login` | POST | 登录 |
| `/api/aps/rush-order/paging` | POST | 插单分页查询 |
| `/api/aps/rush-order` | POST | 新增插单 |
| `/api/aps/rush-order` | DELETE | 删除插单 |
| `/api/aps/rush-order-evaluate` | GET | 触发评估运算 |
| `/api/aps/rush-order-evaluate/warning` | GET | 轮询评估状态 |
| `/api/aps/affect-order/paging` | POST | 受影响订单查询 |
| `/api/aps/order` | GET | 订单进度查询（无需 Token） |
| `/api/aps/shortage` | GET | 缺料预警查询（无需 Token） |
| `/api/aps/capacity` | GET | 产能负荷查询（无需 Token） |
| `/api/aps/risk` | GET | 交期风险查询（无需 Token） |

---

## 六、业务问答流程

用户发送自然语言问题，Dify AI 自动调用后端查询接口返回结果。

**流程：**

```
用户提问 → SDK → POST /ai/chat/stream → 网关 → Dify chat-messages API
                                            ↓
                                      Dify 内部执行：
                                      1. 解析用户意图
                                      2. 调用 APS 查询接口（/aps/order 等）
                                      3. 整合结果生成回答
                                            ↓
                                      流式返回 AI 回答 → SDK → 前端显示
```

**SDK 调用示例：**

```javascript
// 发送问题（流式接收）
await ApsAI.chat('最近有哪些缺料预警？', {
  onChunk: (text) => { /* 打字机效果 */ },
  onDone:   (answer, conversationId) => { /* 保存 conversationId */ },
  onError:  (err) => { /* 错误处理 */ }
});
```

**支持的业务问题类型：**

| 问题类型 | 调用接口 | 示例问题 |
|----------|----------|----------|
| 订单进度 | `GET /api/aps/order` | "订单 SO20250001 进度如何？" |
| 缺料预警 | `GET /api/aps/shortage` | "最近有哪些缺料预警？" |
| 产能负荷 | `GET /api/aps/capacity` | "本周产能负荷情况如何？" |
| 交期风险 | `GET /api/aps/risk` | "近两周有哪些交期风险？" |

**多轮对话：**

首次调用时 `conversationId` 传空字符串，收到回答后保存 `conversationId`，后续追问时传入以保持上下文。

```javascript
// 首次提问后保存 conversationId
const convId = result.conversationId;

// 追问时传入
await ApsAI.chat('哪个最紧急？', {
  conversationId: convId,
  // ...
});
```

---

## 七、插单评估流程

用户提交插单，系统触发 APS 模拟运算，AI 生成影响分析报告。

**流程：**

```
1. 用户触发评估
   → POST /ai/rush-order/evaluate/start
   → 返回 taskId

2. 前端轮询状态（每3秒）
   → GET /ai/rush-order/evaluate/status/{taskId}
   → status = "running" → 继续轮询
   → status = "completed" → 进入下一步

3. 流式获取 AI 分析报告
   → POST /ai/rush-order/evaluate/analyze/{taskId}/stream
   → Dify 工作流分析两张表（rush_order + affect_order）
   → 流式返回 AI 报告 → 前端展示

4. 用户确认/追问
   → 用户回复"是"或"查看详细" → 展示报表链接
   → 用户其他追问 → 携带 conversationId 调用 /ai/chat/stream
```

**SDK 调用示例：**

```javascript
await ApsAI.evaluateRushOrders({
  onStatus: (msg) => { /* 更新状态提示 */ },
  onChunk:  (text) => { /* 打字机效果展示报告 */ },
  onDone:   (answer, convId) => { /* 评估完成，保存 convId 供追问 */ },
  onError:  (err) => { /* 错误处理 */ }
});
```

---

## 八、前端集成

### 8.1 快速演示

部署后直接访问演示页面：

```
http://localhost:8002/demo.html
```

页面包含两个窗口：
- **左窗口（聊天模式）**：输入自然语言问题，AI 实时回答
- **右窗口（评估模式）**：点击按钮触发插单评估，AI 生成分析报告

### 8.2 嵌入式集成

将 SDK 嵌入已有项目：

**1. 引入 SDK**

```html
<script src="aps-ai-sdk.js"></script>
```

**2. 初始化聊天窗口**

```html
<div id="chat-panel"></div>

<script>
  // 聊天模式
  ApsAIChatWidget.mount('#chat-panel', { mode: 'chat' });

  // 评估模式（同一页面可同时使用）
  // ApsAIChatWidget.mount('#eval-panel', { mode: 'evaluate' });
</script>
```

**3. 配置网关地址**

修改 `aps-ai-sdk.js` 中的 `CONFIG.BASE_URL`：

```javascript
const CONFIG = {
  BASE_URL: 'http://你的网关地址:8001',  // 默认 http://139.224.228.33:8001
};
```

**4. 自定义登录后操作**

SDK 会自动处理登录流程，登录成功后可获取用户信息：

```javascript
await ApsAI.login('admin', 'admin123');
console.log(ApsAI.getToken());      // 获取 Token
console.log(ApsAI.getConversationId()); // 获取对话 ID
```

### 8.3 直接使用 SDK（不依赖 UI 组件）

```javascript
// 登录
await ApsAI.login('admin', 'admin123');

// 业务问答
await ApsAI.chat('最近有哪些缺料预警？', {
  onChunk: (c) => { /* 打字机效果 */ },
  onDone:  (a) => { console.log('完整回答:', a); }
});

// 插单评估
await ApsAI.evaluateRushOrders({
  onStatus: (s) => { /* 更新状态 */ },
  onChunk:  (c) => { /* 打字机效果 */ },
  onDone:   (a) => { /* 评估完成 */ }
});

// 清除对话历史
await ApsAI.clearConversation();
```

---

## 九、运行测试

### 9.1 测试 AI 网关（完整流程）

```bash
cd /opt/aps/aps-mock
python3 test_all.py
```

测试项目：
1. 健康检查
2. 登录
3. 无 Token 访问被拒
4. 触发评估 + 轮询状态
5. 获取 AI 分析报告（阻塞）
6. 流式业务问答
7. 多轮追问

### 9.2 测试 APS 模拟服务

```bash
cd /opt/aps/aps-mock
python3 test_gateway.py
```

---

## 十、常见问题

### Q1: 登录返回"APS 登录服务异常"

**原因**：APS 模拟服务（端口 8000）未启动，或网关进程使用了代理导致无法连接 localhost。

**解决**：
```bash
# 确认模拟服务在运行
curl -s http://localhost:8000/

# 重启网关时取消代理
nohup env http_proxy= https_proxy= no_proxy='*' python3 ai_gateway.py &
```

### Q2: 聊天窗口发送问题后无回复

**原因**：`ai_gateway.py` 的 `chat_stream` 函数未正确处理 Dify 返回的 `agent_message` 事件类型（仅处理了 `message`）。

**解决**：确认 `ai_gateway.py` 第 336 行为：
```python
if t in ("message", "agent_message"):
```

### Q3: 流式响应出现打字跳动/乱序

**原因**：网络延迟导致 chunk 乱序到达。

**解决**：SDK 会在 `onDone` 时传入拼接完成的完整回答，可用于最终渲染。

### Q4: 评估流程正常但 AI 报告为空

**原因**：`evaluate_analyze_stream` 未正确处理 Dify workflow 的 `text_chunk` 事件。

**解决**：确认代码中处理了 `text_chunk` 和 `workflow_finished` 两种事件。

### Q5: 跨域问题（CORS）

**解决**：建议通过后端代理转发 AI 服务，避免前端直接调用。

---

## 十一、数据规范

集成时需注意以下字段的格式要求：

| 字段 | 要求 | 说明 |
|------|------|------|
| `remark` | 返回 `""` 而非 `null` | 无备注时必须为空字符串 |
| `materialBottlenecks` | 返回 `[]` 而非 `null` | 无瓶颈时返回空数组 |
| `capacityBottlenecks` | 返回 `[]` 而非 `null` | 无瓶颈时返回空数组 |
| `gapDays` | 正数=延迟，负数=提前 | scheduledDate - dueDate |
| `delayedTop10` | 按 `delayDays` 降序排列 | 延迟最多的排在最前 |
