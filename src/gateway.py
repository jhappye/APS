"""AI 网关接口模块"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import httpx
import json
import uuid
import time
import asyncio

from .config import config
from . import aps
from .aps import BasePagingInput

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
        # 模拟模式：直接调用 APS 函数
        resp = await aps.rush_order_evaluate(authorization=f"Bearer {session['aps_token']}")
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
    is_mock = config.is_mock_mode()

    if is_mock:
        # 模拟模式：直接调用 APS 函数
        warning_resp = await aps.rush_order_evaluate_warning(authorization=f"Bearer {task['aps_token']}")
    else:
        # 生产模式：调用客户 APS
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{aps_base}/api/aps/rush-order-evaluate/warning",
                                    headers=aps_headers)
        warning_resp = resp.json()

    warning_data = warning_resp.get("data")

    if warning_data is None:
        # 评估完成
        if is_mock:
            rush_resp = await aps.rush_order_paging(body=BasePagingInput(current=1, pageSize=100), authorization=f"Bearer {task['aps_token']}")
            affect_resp = await aps.affect_order_paging(body=BasePagingInput(current=1, pageSize=100), authorization=f"Bearer {task['aps_token']}")
            task["rush_body"] = json.dumps(rush_resp)
            task["affect_body"] = json.dumps(affect_resp)
        else:
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
            task["rush_body"] = rush_resp.text
            task["affect_body"] = affect_resp.text

        task["status"] = "completed"
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

    async def generate_mock():
        """Mock 模式下的模拟 AI 分析报告"""
        # 从 task 数据中解析实际的 APS 数据
        try:
            rush_data = json.loads(task.get("rush_body", "{}"))
            affect_data = json.loads(task.get("affect_body", "{}"))
            rush_orders = rush_data.get("data", {}).get("data", [])
            affect_orders = affect_data.get("data", {}).get("data", [])
        except Exception:
            rush_orders = []
            affect_orders = []

        # 生成插单列表摘要
        rush_summary = []
        for o in rush_orders[:5]:
            status = "满足" if (o.get("lackDay") or 0) <= 0 else f"不满足，预计延迟{o.get('lackDay')}天"
            rush_summary.append(
                f"插单编号：{o.get('orderCode', 'N/A')}\n"
                f"插单人员：{o.get('rushUserFullName', 'N/A')} | 创建日期：{o.get('creationTime', '')[:10]}\n"
                f"客户：{o.get('customerCode', 'N/A')} | 物料：{o.get('materialCode', 'N/A')} {o.get('materialName', 'N/A')}\n"
                f"需求数量：{o.get('qty', 0)} | 期望交期：{o.get('expectDate', '')[:10]} | 优先级：{o.get('priority', 'N/A')}\n"
                f"备注：{o.get('remark', '无') or '无'}\n"
                f"排产结束日期：{o.get('productScheduleEndDate', 'N/A')[:10] if o.get('productScheduleEndDate') else 'N/A'} | 缺口天数：{o.get('lackDay', 'N/A')}\n"
                f"评估结论：{status}\n"
            )

        # 受影响订单统计
        delayed_orders = [o for o in affect_orders if o.get("isDelay")]
        normal_orders = [o for o in affect_orders if not o.get("isDelay")]

        affect_summary = []
        affect_summary.append(f"受影响订单总数：{len(affect_orders)}\n")
        affect_summary.append(f"未造成延迟：{len(normal_orders)}条\n")
        if normal_orders:
            o = normal_orders[0]
            affect_summary.append(f"举例Top10：订单{o.get('orderCode', 'N/A')} {o.get('materialName', 'N/A')} 交期{o.get('deliveryDate', '')[:10]}\n")
            affect_summary.append(f"原排产{o.get('originalProductScheduleEndDate', '')[:10]}→新排产{o.get('productScheduleEndDate', '')[:10]} 影响{o.get('affectDay', 0)}天\n")
        affect_summary.append(f"造成延迟：{len(delayed_orders)}条（按延迟天数降序）\n")
        for o in delayed_orders[:7]:
            affect_summary.append(
                f"举例Top10：订单{o.get('orderCode', 'N/A')} {o.get('materialName', 'N/A')} "
                f"延迟{o.get('delayDay', 0)}天 交期{o.get('deliveryDate', '')[:10]}\n"
            )

        mock_report = f"""1. 总览

本次评估共 {len(rush_orders)} 个插单，以下是详细结果：

2. 插单逐项分析（按创建时间升序）


{"".join(rush_summary)}

3. 对现有订单的影响


{"".join(affect_summary)}

4. 结尾


如需查看完整明细，请回复'是'或'查看详细'"""
        for char in mock_report:
            yield f"data: {json.dumps({'type':'chunk','content':char}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.02)
        yield f"data: {json.dumps({'type':'done','answer':mock_report,'taskId':task_id}, ensure_ascii=False)}\n\n"

    async def generate():
        if config.is_mock_mode():
            async for chunk in generate_mock():
                yield chunk
            return

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

    async def generate_mock():
        """Mock 模式下的模拟 AI 回答"""
        mock_responses = [
            "根据当前 APS 数据分析，",
            "您好！以下是您的查询结果：\n\n",
            "让我为您查询一下...\n\n根据系统数据，",
        ]
        import random
        response = random.choice(mock_responses)

        if "订单" in req.message or "进度" in req.message:
            response += "当前有 3 个订单处于生产中状态，其中 2 个可能存在交期延迟风险。建议关注冲压车间的产能情况。"
        elif "缺料" in req.message:
            response += "近期有以下物料存在缺料风险：\n1. 伺服电机 - 缺料约 100 件\n2. 控制板 - 缺料约 80 件\n建议尽快安排采购。"
        elif "产能" in req.message:
            response += "当前产能负荷率为 87%，处于正常水平。但冲压车间负荷较高（约 95%），建议适时安排加班。"
        elif "风险" in req.message or "交期" in req.message:
            response += "近期交期风险预警：\n1. 高风险订单 3 个（延迟 7 天以上）\n2. 中风险订单 5 个（延迟 3-7 天）\n建议及时与客户沟通。"
        else:
            response += "您可以查询：订单进度、缺料预警、产能负荷、交期风险等业务数据。请问有什么可以帮助您的？"

        conv_id = f"mock_conv_{uuid.uuid4().hex[:8]}"
        for char in response:
            yield f"data: {json.dumps({'type':'chunk','content':char}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.02)
        yield f"data: {json.dumps({'type':'done','conversationId':conv_id}, ensure_ascii=False)}\n\n"

    async def generate():
        if config.is_mock_mode():
            async for chunk in generate_mock():
                yield chunk
            return

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
    if config.is_mock_mode():
        return ok(data={"cleared": True})
    async with httpx.AsyncClient(timeout=15) as client:
        await client.delete(f"{config.AI_PLATFORM_BASE_URL}/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {config.get_chat_key()}"},
            params={"user": userId or session["userId"]})
    return ok(data={"cleared": True})