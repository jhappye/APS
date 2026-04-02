"""AI 网关接口模块"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import httpx
import json
import uuid
import time

from .config import config

router = APIRouter(prefix="/ai", tags=["AI网关"])

# 内存存储
sessions = {}
eval_tasks = {}


def verify_gateway_token(authorization: str = ""):
    """验证网关Token"""
    if not authorization:
        raise HTTPException(401, {"code": "UNAUTHORIZED", "message": "缺少 Authorization Header"})
    token = authorization.replace("Bearer ", "").strip()
    if token not in sessions:
        raise HTTPException(401, {"code": "UNAUTHORIZED", "message": "Token 无效，请重新登录"})
    return sessions[token]


def ok(data=None, message="ok"):
    return {"code": 0, "message": message, "data": data}


# ==================== 登录接口 ====================

class LoginRequest(BaseModel):
    userName: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)
    orgId: Optional[int] = None


@router.post("/login")
async def gateway_login(req: LoginRequest):
    """网关登录接口"""
    if config.is_mock_mode():
        # 模拟模式：直接使用模拟token
        aps_token = "mock_token_valid"
        aps_data = {"userId": "1001", "userName": req.userName, "fullName": "管理员", "orgId": req.orgId or 1}
    else:
        # 生产模式：调用真实APS
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{config.APS_BASE_URL}/api/login", json={
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
            raise HTTPException(401, {"code": "AUTH_FAILED", "message": "用户名或密码错误"})

    gw_token = f"gw_{uuid.uuid4().hex}"
    sessions[gw_token] = {
        "aps_token": aps_token,
        "userId": str(aps_data.get("userId", "")),
        "userName": aps_data.get("userName", ""),
        "fullName": aps_data.get("fullName", ""),
        "orgId": aps_data.get("orgId"),
        "login_time": time.time(),
    }
    return ok(data={
        "token": gw_token,
        "userId": str(aps_data.get("userId", "")),
        "userName": aps_data.get("userName", ""),
        "fullName": aps_data.get("fullName", ""),
    })


# ==================== 插单评估接口 ====================

@router.post("/rush-order/evaluate/start")
async def evaluate_start(authorization: str = Header("")):
    """触发插单评估"""
    session = verify_gateway_token(authorization)
    aps_headers = {"Authorization": f"Bearer {session['aps_token']}"}

    if config.is_mock_mode():
        # 模拟模式：调用内部 APS 接口
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{config.APS_BASE_URL}/api/aps/rush-order-evaluate",
                                    headers=aps_headers)
    else:
        # 生产模式：调用客户 APS
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{config.APS_BASE_URL}/api/aps/rush-order-evaluate",
                                    headers=aps_headers)

    if resp.status_code != 200:
        raise HTTPException(502, {"code": "APS_ERROR", "message": f"触发评估失败 {resp.status_code}"})

    task_id = f"eval_{uuid.uuid4().hex[:8]}"
    eval_tasks[task_id] = {
        "status": "running",
        "aps_token": session["aps_token"],
        "aps_base_url": config.APS_BASE_URL,
    }

    return ok(data={"taskId": task_id, "status": "running"})


@router.get("/rush-order/evaluate/status/{task_id}")
async def evaluate_status(task_id: str, authorization: str = Header("")):
    """轮询评估状态"""
    session = verify_gateway_token(authorization)

    if task_id not in eval_tasks:
        raise HTTPException(404, {"code": "TASK_NOT_FOUND", "message": "taskId 不存在"})

    task = eval_tasks[task_id]
    aps_headers = {"Authorization": f"Bearer {task['aps_token']}"}
    aps_base = task["aps_base_url"]

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{aps_base}/api/aps/rush-order-evaluate/warning",
                                headers=aps_headers)

    body = resp.json()
    warning_data = body.get("data")

    if warning_data is None:
        # 评估完成
        async with httpx.AsyncClient(timeout=30) as client:
            rush_resp = await client.post(
                f"{aps_base}/api/aps/rush-order/paging",
                headers=aps_headers,
                json={"current": 1, "pageSize": 100},
            )
            affect_resp = await client.post(
                f"{aps_base}/api/aps/affect-order/paging",
                headers=aps_headers,
                json={"current": 1, "pageSize": 100},
            )

        task["status"] = "completed"
        task["rush_body"] = rush_resp.text
        task["affect_body"] = affect_resp.text
        return ok(data={"taskId": task_id, "status": "completed"})
    else:
        return ok(data={"taskId": task_id, "status": "running", "message": warning_data})


@router.post("/rush-order/evaluate/analyze/{task_id}/stream")
async def evaluate_analyze_stream(task_id: str, authorization: str = Header("")):
    """获取 AI 分析报告（流式模式）"""
    from fastapi.responses import StreamingResponse

    session = verify_gateway_token(authorization)

    if task_id not in eval_tasks:
        raise HTTPException(404, {"code": "TASK_NOT_FOUND", "message": "taskId 不存在"})

    task = eval_tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(400, {"code": "NOT_READY", "message": "评估尚未完成"})

    ai_payload = {
        "inputs": {
            "rush_order_body": task.get("rush_body", "{}"),
            "affect_order_body": task.get("affect_body", "{}"),
        },
        "response_mode": "streaming",
        "user": session["userId"] or "gateway_user",
    }

    async def generate():
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST", f"{config.AI_PLATFORM_BASE_URL}/workflows/run",
                    headers={"Authorization": f"Bearer {config.get_workflow_key()}", "Content-Type": "application/json"},
                    json=ai_payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield f"data: {json.dumps({'type':'error','message':f'AI服务工作流返回{resp.status_code}','detail':body.decode()[:300]}, ensure_ascii=False)}\n\n"
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
                            if t == "text_chunk":
                                chunk = event.get("data", {}).get("text", "")
                                if chunk:
                                    yield f"data: {json.dumps({'type':'chunk','content':chunk}, ensure_ascii=False)}\n\n"
                            elif t == "workflow_finished":
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
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ==================== 业务问答接口 ====================

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    userId: Optional[str] = ""
    conversationId: Optional[str] = ""


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, authorization: str = Header("")):
    """流式业务问答"""
    from fastapi.responses import StreamingResponse

    session = verify_gateway_token(authorization)

    ai_payload = {
        "query": req.message,
        "user": req.userId or session["userId"] or "gateway_user",
        "response_mode": "streaming",
        "inputs": {},
        "conversation_id": req.conversationId or "",
    }

    async def generate():
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST", f"{config.AI_PLATFORM_BASE_URL}/chat-messages",
                    headers={"Authorization": f"Bearer {config.get_chat_key()}", "Content-Type": "application/json"},
                    json=ai_payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield f"data: {json.dumps({'type':'error','message':f'AI服务 {resp.status_code}','detail':body.decode()[:300]}, ensure_ascii=False)}\n\n"
                        return
                    conv_id = ""
                    async for line in resp.aiter_lines():
                        raw_line = line.rstrip('\r')
                        if not raw_line.startswith("data: "):
                            continue
                        raw = raw_line[6:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            event = json.loads(raw)
                            t = event.get("event", "")
                            if event.get("conversation_id"):
                                conv_id = event["conversation_id"]
                            if t in ("message", "agent_message"):
                                content = event.get("answer", "") or event.get("text", "")
                                if content:
                                    yield f"data: {json.dumps({'type':'chunk','content':content}, ensure_ascii=False)}\n\n"
                            elif t == "message_end":
                                yield f"data: {json.dumps({'type':'done','conversationId':conv_id}, ensure_ascii=False)}\n\n"
                            elif t == "error":
                                yield f"data: {json.dumps({'type':'error','message':event.get('message','')}, ensure_ascii=False)}\n\n"
                            elif t == "ping":
                                pass
                        except Exception:
                            continue
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("/conversation/{conv_id}")
async def clear_conversation(conv_id: str, userId: str = "", authorization: str = Header("")):
    """清除对话历史"""
    session = verify_gateway_token(authorization)
    async with httpx.AsyncClient(timeout=15) as client:
        await client.delete(f"{config.AI_PLATFORM_BASE_URL}/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {config.get_chat_key()}"},
            params={"user": userId or session["userId"]})
    return ok(data={"cleared": True})