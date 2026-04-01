#!/usr/bin/env python3
"""
APS AI 网关服务 V2
==================
基于真实接口重写，核心变化：
1. 新增登录代理：客户端通过网关登录，网关维护 APS token
2. 插单评估流程：触发评估 → 轮询 warning → 查两张表 → 调 Dify
3. 业务问答：直接转发到 Dify
"""

from fastapi import FastAPI, Header, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import httpx, json, uuid, asyncio, time, logging

logger = logging.getLogger("uvicorn.access")
logger.setLevel(logging.INFO)

app = FastAPI(title="APS AI 网关服务 V2", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── 配置 ───────────────────────────────────────────────
APS_BASE_URL        = "http://localhost:8000"            # APS 服务地址（测试用模拟服务）
DIFY_BASE_URL       = "http://139.224.228.33:8090/v1"              # Dify 内部地址
DIFY_API_KEY        = "app-NMXnjStbZL4uA5ufO7CCjOq7"     # ← 聊天机器人 API Key（业务问答用）
DIFY_WORKFLOW_A_KEY = "app-20mcGFNUbrVe8UjiZkttDefU"     # ← 工作流A的 API Key（插单评估专用）
GATEWAY_TOKEN       = "aps-gateway-token-2026"           # ← 客户调用网关时用的 Token

# ─── 内存存储 ────────────────────────────────────────────
# { gateway_token → { aps_token, userId, userName, ... } }
sessions = {}
# { eval_task_id → { status, rush_data, affect_data, conv_id } }
eval_tasks = {}

# ─── 工具函数 ─────────────────────────────────────────────
def verify_gateway_token(authorization: str = ""):
    if not authorization:
        raise HTTPException(401, {"code": "UNAUTHORIZED", "message": "缺少 Authorization Header"})
    token = authorization.replace("Bearer ", "").strip()
    if token not in sessions:
        raise HTTPException(401, {"code": "UNAUTHORIZED", "message": "Token 无效，请重新登录"})
    return sessions[token]

def ok(data=None, message="ok"):
    return {"code": 0, "message": message, "data": data}

def err(message, code="ERROR"):
    return {"code": -1, "message": message, "data": None}

# ════════════════════════════════════════════════════════
#  登录
# ════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    userName: str
    password: str
    orgId: Optional[int] = None

@app.post("/ai/login")
async def gateway_login(req: LoginRequest):
    """
    网关登录接口
    客户端调此接口，网关代为登录 APS，返回网关 token
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{APS_BASE_URL}/api/login", json={
            "userName": req.userName,
            "password": req.password,
            "orgId": req.orgId,
            "loginPort": "Web",
        })

    if resp.status_code != 200:
        raise HTTPException(502, {"code": "APS_ERROR", "message": "APS 登录服务异常"})

    body = resp.json()
    aps_data = body.get("data") or {}
    aps_token = aps_data.get("token", "")

    if not aps_token:
        return err(body.get("message", "用户名或密码错误"))

    # 生成网关 token
    gw_token = f"gw_{uuid.uuid4().hex}"
    sessions[gw_token] = {
        "aps_token":  aps_token,
        "userId":     str(aps_data.get("userId", "")),
        "userName":   aps_data.get("userName", ""),
        "fullName":   aps_data.get("fullName", ""),
        "orgId":      aps_data.get("orgId"),
        "login_time": time.time(),
    }

    return ok(data={
        "token":    gw_token,
        "userId":   str(aps_data.get("userId", "")),
        "userName": aps_data.get("userName", ""),
        "fullName": aps_data.get("fullName", ""),
    })

# ════════════════════════════════════════════════════════
#  插单评估 · 完整流程
# ════════════════════════════════════════════════════════

@app.post("/ai/rush-order/evaluate/start")
async def evaluate_start(authorization: str = Header("")):
    """
    触发插单评估
    调用 APS GET /api/aps/rush-order-evaluate
    返回 taskId，用于后续轮询
    """
    session = verify_gateway_token(authorization)
    aps_headers = {"Authorization": f"Bearer {session['aps_token']}"}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{APS_BASE_URL}/api/aps/rush-order-evaluate",
                                headers=aps_headers)

    if resp.status_code != 200:
        raise HTTPException(502, {"code": "APS_ERROR", "message": f"触发评估失败 {resp.status_code}"})

    task_id = f"eval_{uuid.uuid4().hex[:8]}"
    eval_tasks[task_id] = {
        "status": "running",
        "aps_token": session["aps_token"],
        "rush_data": None,
        "affect_data": None,
    }

    return ok(data={"taskId": task_id, "status": "running"})


@app.get("/ai/rush-order/evaluate/status/{task_id}")
async def evaluate_status(task_id: str, authorization: str = Header("")):
    """
    轮询评估状态
    内部轮询 APS GET /api/aps/rush-order-evaluate/warning
    data=null → 完成；data=文字 → 进行中
    """
    session = verify_gateway_token(authorization)

    if task_id not in eval_tasks:
        raise HTTPException(404, {"code": "TASK_NOT_FOUND", "message": "taskId 不存在"})

    task = eval_tasks[task_id]
    aps_headers = {"Authorization": f"Bearer {task['aps_token']}"}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{APS_BASE_URL}/api/aps/rush-order-evaluate/warning",
                                headers=aps_headers)

    body = resp.json()
    warning_data = body.get("data")   # null = 完成，字符串 = 进行中

    if warning_data is None:
        # 评估完成，拉取两张结果表
        async with httpx.AsyncClient(timeout=30) as client:
            rush_resp = await client.post(
                f"{APS_BASE_URL}/api/aps/rush-order/paging",
                headers=aps_headers,
                json={"current": 1, "pageSize": 100},
            )
            affect_resp = await client.post(
                f"{APS_BASE_URL}/api/aps/affect-order/paging",
                headers=aps_headers,
                json={"current": 1, "pageSize": 100},
            )

        task["status"] = "completed"
        task["rush_body"]   = rush_resp.text
        task["affect_body"] = affect_resp.text
        return ok(data={"taskId": task_id, "status": "completed"})
    else:
        return ok(data={"taskId": task_id, "status": "running", "message": warning_data})


@app.post("/ai/rush-order/evaluate/analyze/{task_id}")
async def evaluate_analyze(task_id: str, authorization: str = Header("")):
    """
    获取 AI 分析报告（阻塞模式）
    直接调用工作流A的 Run API，把两张表数据作为 inputs 传入
    """
    session = verify_gateway_token(authorization)

    if task_id not in eval_tasks:
        raise HTTPException(404, {"code": "TASK_NOT_FOUND", "message": "taskId 不存在"})

    task = eval_tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(400, {"code": "NOT_READY", "message": "评估尚未完成，请先轮询 status 接口"})

    # 调工作流A的 Run API（blocking 模式）
    dify_payload = {
        "inputs": {
            "rush_order_body":   task.get("rush_body", "{}"),
            "affect_order_body": task.get("affect_body", "{}"),
        },
        "response_mode": "blocking",
        "user": session["userId"] or "gateway_user",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{DIFY_BASE_URL}/workflows/run",
            headers={"Authorization": f"Bearer {DIFY_WORKFLOW_A_KEY}", "Content-Type": "application/json"},
            json=dify_payload,
        )

    if resp.status_code != 200:
        raise HTTPException(502, {"code": "DIFY_ERROR", "message": f"Dify 工作流返回 {resp.status_code}: {resp.text[:300]}"})

    dify_data = resp.json()
    # 工作流 Run API 返回结构：data.outputs 里有工作流结束节点的输出变量
    outputs = dify_data.get("data", {}).get("outputs", {})
    answer = outputs.get("answer") or outputs.get("text") or str(outputs)

    return ok(data={
        "answer":  answer,
        "taskId":  task_id,
        "outputs": outputs,
    })


@app.post("/ai/rush-order/evaluate/analyze/{task_id}/stream")
async def evaluate_analyze_stream(task_id: str, authorization: str = Header("")):
    """
    获取 AI 分析报告（流式模式，打字机效果）
    调用工作流A的 Run API（streaming 模式），事件类型：workflow_started / node_finished / workflow_finished
    """
    session = verify_gateway_token(authorization)

    if task_id not in eval_tasks:
        raise HTTPException(404, {"code": "TASK_NOT_FOUND", "message": "taskId 不存在"})

    task = eval_tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(400, {"code": "NOT_READY", "message": "评估尚未完成"})

    dify_payload = {
        "inputs": {
            "rush_order_body":   task.get("rush_body", "{}"),
            "affect_order_body": task.get("affect_body", "{}"),
        },
        "response_mode": "streaming",
        "user": session["userId"] or "gateway_user",
    }

    async def generate():
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST", f"{DIFY_BASE_URL}/workflows/run",
                    headers={"Authorization": f"Bearer {DIFY_WORKFLOW_A_KEY}", "Content-Type": "application/json"},
                    json=dify_payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield f"data: {json.dumps({'type':'error','message':f'Dify工作流返回{resp.status_code}','detail':body.decode()[:300]}, ensure_ascii=False)}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            event = json.loads(raw)
                            t = event.get("event", "")
                            # 工作流流式事件类型和 chat 不同
                            if t == "text_chunk":
                                # LLM 节点流式输出
                                chunk = event.get("data", {}).get("text", "")
                                if chunk:
                                    yield f"data: {json.dumps({'type':'chunk','content':chunk}, ensure_ascii=False)}\n\n"
                            elif t == "workflow_finished":
                                # 工作流完成，取输出变量
                                outputs = event.get("data", {}).get("outputs", {})
                                answer = outputs.get("answer") or outputs.get("text") or str(outputs)
                                yield f"data: {json.dumps({'type':'done','answer':answer,'taskId':task_id}, ensure_ascii=False)}\n\n"
                            elif t == "error":
                                yield f"data: {json.dumps({'type':'error','message':event.get('message','工作流执行错误')}, ensure_ascii=False)}\n\n"
                        except Exception:
                            continue
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

# ════════════════════════════════════════════════════════
#  业务问答（流式 + 多轮对话）
# ════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    userId: Optional[str] = ""
    conversationId: Optional[str] = ""

@app.post("/ai/chat/stream")
async def chat_stream(req: ChatRequest, authorization: str = Header("")):
    """流式业务问答（打字机效果）"""
    verify_gateway_token(authorization)
    session = sessions[authorization.replace("Bearer ", "").strip()]

    dify_payload = {
        "query":           req.message,
        "user":            req.userId or session["userId"] or "gateway_user",
        "response_mode":   "streaming",
        "inputs":          {},
        "conversation_id": req.conversationId or "",
    }

    print(f"[CHAT] 收到请求: message='{req.message}' userId={req.userId} conversationId={req.conversationId}")

    async def generate():
        try:
            print(f"[CHAT] 正在转发到 Dify: {DIFY_BASE_URL}/chat-messages")
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST", f"{DIFY_BASE_URL}/chat-messages",
                    headers={"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"},
                    json=dify_payload,
                ) as resp:
                    print(f"[CHAT] Dify 返回状态: {resp.status_code}")
                    if resp.status_code != 200:
                        body = await resp.aread()
                        print(f"[CHAT] Dify 错误: {body.decode()[:500]}")
                        yield f"data: {json.dumps({'type':'error','message':f'Dify {resp.status_code}','detail':body.decode()[:300]}, ensure_ascii=False)}\n\n"
                        return
                    conv_id = ""
                    event_count = {"chunk": 0, "done": 0, "error": 0, "other": 0}
                    async for line in resp.aiter_lines():
                        # 去掉行尾的\r（Dify可能发送\r\n换行）
                        raw_line = line.rstrip('\r')
                        if not raw_line.startswith("data: "):
                            continue
                        raw = raw_line[6:].strip()
                        if raw == "[DONE]":
                            print(f"[CHAT] 收到 [DONE]，结束")
                            break
                        try:
                            event = json.loads(raw)
                            t = event.get("event", "")
                            if event.get("conversation_id"):
                                conv_id = event["conversation_id"]
                            if t in ("message", "agent_message"):
                                content = event.get("answer", "") or event.get("text", "")
                                if content:
                                    event_count["chunk"] += 1
                                    yield f"data: {json.dumps({'type':'chunk','content':content}, ensure_ascii=False)}\n\n"
                                else:
                                    print(f"[CHAT] 跳过空的 agent_message, answer='{event.get('answer','')}'")
                            elif t == "message_end":
                                event_count["done"] += 1
                                print(f"[CHAT] 收到 message_end, conv_id={conv_id}, event_count={event_count}")
                                yield f"data: {json.dumps({'type':'done','conversationId':conv_id}, ensure_ascii=False)}\n\n"
                            elif t == "error":
                                event_count["error"] += 1
                                print(f"[CHAT] 收到 Dify error 事件: {event.get('message','')}")
                                yield f"data: {json.dumps({'type':'error','message':event.get('message','')}, ensure_ascii=False)}\n\n"
                            elif t == "agent_thought":
                                # 调试：打印 AI 思考过程
                                thought = event.get("thought", "")[:100]
                                tool = event.get("tool", "")
                                print(f"[CHAT] agent_thought: tool={tool} thought={thought}")
                            elif t == "ping":
                                pass  # 忽略 ping
                            else:
                                event_count["other"] += 1
                                print(f"[CHAT] 未处理事件类型: {t}, 已有: {event_count}")
                        except Exception as e:
                            print(f"[CHAT] 解析事件异常: {e}, raw={raw[:100]}")
                            continue
        except Exception as e:
            print(f"[CHAT] generate 异常: {e}")
            yield f"data: {json.dumps({'type':'error','message':str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


@app.post("/ai/chat")
async def chat_blocking(req: ChatRequest, authorization: str = Header("")):
    """阻塞业务问答（备用）"""
    verify_gateway_token(authorization)
    session = sessions[authorization.replace("Bearer ", "").strip()]

    dify_payload = {
        "query":           req.message,
        "user":            req.userId or session["userId"] or "gateway_user",
        "response_mode":   "blocking",
        "inputs":          {},
        "conversation_id": req.conversationId or "",
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{DIFY_BASE_URL}/chat-messages",
            headers={"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"},
            json=dify_payload)

    if resp.status_code != 200:
        raise HTTPException(502, {"code": "DIFY_ERROR", "message": f"Dify 返回 {resp.status_code}"})

    d = resp.json()
    return ok(data={"answer": d.get("answer",""), "conversationId": d.get("conversation_id","")})


@app.delete("/ai/conversation/{conv_id}")
async def clear_conversation(conv_id: str, userId: str = "", authorization: str = Header("")):
    """清除对话历史"""
    verify_gateway_token(authorization)
    session = sessions[authorization.replace("Bearer ", "").strip()]
    async with httpx.AsyncClient(timeout=15) as client:
        await client.delete(f"{DIFY_BASE_URL}/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {DIFY_API_KEY}"},
            params={"user": userId or session["userId"]})
    return ok(data={"cleared": True})

# ════════════════════════════════════════════════════════
#  健康检查
# ════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {
        "status": "ok", "service": "APS AI 网关服务 V2", "version": "2.0.0",
        "endpoints": {
            "登录":          "POST /ai/login",
            "触发评估":      "POST /ai/rush-order/evaluate/start",
            "轮询状态":      "GET  /ai/rush-order/evaluate/status/{taskId}",
            "获取AI报告(流式)": "POST /ai/rush-order/evaluate/analyze/{taskId}/stream",
            "获取AI报告(阻塞)": "POST /ai/rush-order/evaluate/analyze/{taskId}",
            "业务问答(流式)": "POST /ai/chat/stream",
            "业务问答(阻塞)": "POST /ai/chat",
            "清除对话":      "DELETE /ai/conversation/{convId}",
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
