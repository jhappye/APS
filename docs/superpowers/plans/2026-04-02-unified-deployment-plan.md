# AI中台统一部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 APS 模拟服务和 AI 网关服务合并为单一服务，支持 Docker Compose 和 systemctl 部署

**Architecture:** 单一 FastAPI 应用，统一端口 8000，通过 MOCK_MODE 环境变量切换模拟/生产模式

**Tech Stack:** Python 3.12, FastAPI, uvicorn, Docker, docker-compose, systemctl

---

## 文件结构

```
/opt/aps/
├── docker-compose.yml          # Docker Compose 配置
├── .env.example               # 环境变量示例
├── Dockerfile                 # 镜像构建
├── src/
│   ├── __init__.py
│   ├── main.py                # 统一入口，路由注册
│   ├── aps.py                 # APS 接口（原 mock_server.py）
│   ├── gateway.py              # AI 网关接口（原 ai_gateway.py）
│   ├── config.py              # 配置加载
│   └── utils.py               # 工具函数
├── systemd/
│   └── ai-platform.service     # systemctl 服务
└── requirements.txt           # 依赖
```

---

### Task 1: 创建项目结构和配置模块

**Files:**
- Create: `src/__init__.py`
- Create: `src/config.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Create src/__init__.py**

```python
"""AI中台统一服务"""
```

- [ ] **Step 2: Create src/config.py**

```python
import os
from typing import Optional

class Config:
    """统一配置管理"""

    # 模式切换
    MOCK_MODE: bool = os.getenv("MOCK_MODE", "true").lower() == "true"

    # APS 配置
    APS_BASE_URL: str = os.getenv("APS_BASE_URL", "http://localhost:8000")

    # AI服务中台配置
    AI_PLATFORM_BASE_URL: str = os.getenv("AI_PLATFORM_BASE_URL", "http://139.224.228.33:8090/v1")
    AI_PLATFORM_CHAT_KEY: str = os.getenv("AI_PLATFORM_CHAT_KEY", "")
    AI_PLATFORM_WORKFLOW_KEY: str = os.getenv("AI_PLATFORM_WORKFLOW_KEY", "")

    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "/var/log/ai-platform/app.log")

    @classmethod
    def is_mock_mode(cls) -> bool:
        return cls.MOCK_MODE


# 全局配置实例
config = Config()
```

- [ ] **Step 3: Create requirements.txt**

```
fastapi==0.109.0
uvicorn==0.27.0
httpx==0.26.0
pydantic==2.5.3
python-multipart==0.0.6
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt src/__init__.py src/config.py
git commit -m "feat: 创建项目结构和配置模块"
```

---

### Task 2: 创建 APS 接口模块

**Files:**
- Create: `src/aps.py`
- Create: `src/utils.py`
- Reference: `aps-mock/mock_server.py` (现有代码参考)

- [ ] **Step 1: Create src/utils.py**

```python
"""工具函数"""
from datetime import datetime, timedelta, date
import random


def today_str(offset: int = 0) -> str:
    """返回当前日期时间字符串"""
    return (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%dT%H:%M:%S")


def date_str(offset: int = 0) -> str:
    """返回当前日期字符串"""
    return (date.today() + timedelta(days=offset)).strftime("%Y-%m-%dT00:00:00")


def rand_order_code() -> str:
    """生成随机订单号"""
    return f"SO{random.randint(20250001, 20259999)}"
```

- [ ] **Step 2: Create src/aps.py (APS 接口模块)**

```python
"""APS 接口模块 - 包含 APS 模拟数据和接口"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Any
import uuid
import random
import asyncio
from datetime import datetime, timedelta

from .utils import today_str, date_str, rand_order_code

router = APIRouter(prefix="/api", tags=["APS"])

# 内存存储
evaluation_status = {"state": "idle"}
rush_orders_store = []
affect_orders_store = []


def _init_rush_orders():
    """初始化模拟插单数据"""
    global rush_orders_store
    materials = [
        ("M20240001", "伺服电机"), ("M20240023", "控制板"),
        ("M20240045", "减速箱"), ("M20240067", "传感器组件"),
        ("M20240089", "电源模块")
    ]
    rush_orders_store = []
    for i in range(5):
        mc, mn = materials[i]
        rush_orders_store.append({
            "kid": str(uuid.uuid4()),
            "id": 1000 + i,
            "orderCode": f"RO2026032900{i+1}",
            "rushUserFullName": random.choice(["张三", "李四", "王五"]),
            "materialCode": mc,
            "materialName": mn,
            "customerCode": f"C00{i+1}",
            "customerName": f"客户{i+1}",
            "qty": random.choice([50, 100, 200, 300]),
            "expectDate": date_str(random.randint(10, 30)),
            "priority": random.randint(1, 3),
            "remark": random.choice(["", "加急", "优先处理", ""]),
            "productScheduleEndDate": None,
            "lackDay": None,
            "creationTime": today_str(-random.randint(0, 2)),
        })


def _build_affect_orders():
    """构建受影响订单数据"""
    global affect_orders_store
    affect_orders_store = []
    materials = [
        ("M20240001", "伺服电机"), ("M20240023", "控制板"),
        ("M20240045", "减速箱"), ("M20240067", "传感器组件"),
    ]
    for i in range(random.randint(5, 12)):
        mc, mn = materials[i % len(materials)]
        affect_day = random.randint(0, 10)
        delay_day = random.randint(0, affect_day)
        delivery = date_str(random.randint(5, 30))
        delivery_dt = datetime.strptime(delivery[:19], "%Y-%m-%dT%H:%M:%S")
        affect_orders_store.append({
            "kid": str(uuid.uuid4()),
            "id": 2000 + i,
            "orderCode": rand_order_code(),
            "orderLine": random.randint(1, 5),
            "priority": random.randint(1, 3),
            "materialCode": mc,
            "materialName": mn,
            "qty": random.choice([50, 100, 200]),
            "deliveryDate": delivery,
            "originalProductScheduleEndDate": (delivery_dt + timedelta(days=-affect_day)).strftime("%Y-%m-%dT%H:%M:%S"),
            "productScheduleEndDate": (delivery_dt + timedelta(days=delay_day)).strftime("%Y-%m-%dT%H:%M:%S"),
            "affectDay": affect_day,
            "delayDay": delay_day,
            "isDelay": delay_day > 0,
            "customField1": None,
        })


# 初始化数据
_init_rush_orders()


def verify_token(authorization: str = ""):
    """验证Token"""
    if not authorization:
        raise HTTPException(status_code=401, detail={"statusCode": 401, "message": "未登录"})
    token = authorization.replace("Bearer ", "").strip()
    if token not in ["mock_token_valid"]:
        raise HTTPException(status_code=401, detail={"statusCode": 401, "message": "token 无效或已过期"})
    return {"token": token}


def ok(data=None, message="success"):
    return {"statusCode": 200, "message": message, "data": data}


# ==================== 登录接口 ====================

class LoginInput(BaseModel):
    userName: str
    password: str
    orgId: Optional[int] = None
    loginPort: Optional[str] = "Web"


@router.post("/login")
async def login(body: LoginInput):
    """登录"""
    if body.userName == "admin" and body.password == "admin123":
        token = "mock_token_valid"
        return ok(data={
            "userId": 1001, "userName": body.userName,
            "fullName": "管理员", "orgId": body.orgId or 1,
            "orgCode": "ORG001", "token": token,
            "loginTimestamp": int(datetime.now().timestamp()),
        })
    return ok(data=None, message="用户名或密码错误")


# ==================== 插单接口 ====================

class BasePagingInput(BaseModel):
    current: int = 1
    pageSize: int = 20
    total: Optional[int] = 0
    filter: Optional[Any] = None
    orders: Optional[Any] = None


@router.post("/aps/rush-order/paging")
async def rush_order_paging(body: BasePagingInput, authorization: str = Header("")):
    """插单分页查询"""
    verify_token(authorization)
    total = len(rush_orders_store)
    start = (body.current - 1) * body.pageSize
    page_data = rush_orders_store[start: start + body.pageSize]
    return ok(data={
        "data": page_data, "current": body.current,
        "pageSize": body.pageSize, "total": total,
        "pageTotal": max(1, (total + body.pageSize - 1) // body.pageSize)
    })


@router.get("/aps/rush-order-evaluate")
async def rush_order_evaluate(authorization: str = Header("")):
    """触发插单评估运算（异步，约3秒完成）"""
    verify_token(authorization)
    evaluation_status["state"] = "running"

    async def run():
        await asyncio.sleep(3)
        for o in rush_orders_store:
            gap = random.randint(-3, 8)
            try:
                expect_dt = datetime.strptime(o["expectDate"][:19], "%Y-%m-%dT%H:%M:%S")
            except Exception:
                expect_dt = datetime.now() + timedelta(days=14)
            o["productScheduleEndDate"] = (expect_dt + timedelta(days=gap)).strftime("%Y-%m-%dT%H:%M:%S")
            o["lackDay"] = gap
        _build_affect_orders()
        evaluation_status["state"] = "done"

    asyncio.create_task(run())
    return ok(data=None, message="评估运算已触发，请通过 /warning 接口轮询进度")


@router.get("/aps/rush-order-evaluate/warning")
async def rush_order_evaluate_warning(authorization: str = Header("")):
    """获取评估提醒（轮询运算状态）"""
    verify_token(authorization)
    state = evaluation_status.get("state")
    if state == "running":
        return ok(data="正在评估中，请稍候...")
    elif state == "done":
        return ok(data=None, message="评估完成")
    else:
        return ok(data=None, message="暂无评估任务")


@router.post("/aps/affect-order/paging")
async def affect_order_paging(body: BasePagingInput, authorization: str = Header("")):
    """受影响订单分页查询"""
    verify_token(authorization)
    if evaluation_status.get("state") != "done":
        return ok(data={"data": [], "current": 1, "pageSize": body.pageSize,
                        "total": 0, "pageTotal": 0}, message="暂无评估结果")
    total = len(affect_orders_store)
    start = (body.current - 1) * body.pageSize
    page_data = affect_orders_store[start: start + body.pageSize]
    return ok(data={
        "data": page_data, "current": body.current,
        "pageSize": body.pageSize, "total": total,
        "pageTotal": max(1, (total + body.pageSize - 1) // body.pageSize)
    })


# ==================== 业务查询接口（无需Token） ====================

@router.get("/aps/order")
async def query_order(orderNo: Optional[str] = None,
                      materialCode: Optional[str] = None,
                      dateFrom: Optional[str] = None,
                      dateTo: Optional[str] = None):
    """订单进度查询"""
    orders = []
    for _ in range(random.randint(1, 3)):
        mc, mn = random.choice([
            ("M20240001","伺服电机"),("M20240023","控制板"),
            ("M20240045","减速箱"),("M20240067","传感器组件")
        ])
        delay = random.randint(-3, 7)
        total = random.randint(50, 500)
        done = random.randint(0, total)
        plan_end = today_str(random.randint(1, 20))
        due = (datetime.strptime(plan_end, "%Y-%m-%dT%H:%M:%S") + timedelta(days=-delay)).strftime("%Y-%m-%dT%H:%M:%S")
        orders.append({
            "orderNo": orderNo or f"SO{random.randint(20250001,20259999)}",
            "materialCode": materialCode or mc,
            "materialName": mn,
            "planStartDate": today_str(-random.randint(5,10)),
            "planEndDate": plan_end,
            "dueDate": due,
            "completedQty": done,
            "totalQty": total,
            "status": "delayed" if delay > 0 else ("in_progress" if done < total else "completed"),
            "delayDays": max(0, delay),
            "currentOperation": random.choice(["冲压","焊接","装配","检测","包装"]),
            "bottleneck": "冲压机产能不足" if delay > 0 else ""
        })
    return {"code": 0, "message": "ok", "data": {"total": len(orders), "orders": orders}}


@router.get("/aps/shortage")
async def query_shortage(materialCode: Optional[str] = None,
                         dateFrom: Optional[str] = None,
                         dateTo: Optional[str] = None,
                         limit: int = 20):
    """缺料预警查询"""
    items = []
    for _ in range(random.randint(2, 5)):
        mc, mn = random.choice([
            ("M20240001","伺服电机"),("M20240023","控制板"),
            ("M20240045","减速箱"),("M20240067","传感器组件")
        ])
        shortage = random.randint(10, 200)
        items.append({
            "materialCode": materialCode or mc,
            "materialName": mn,
            "shortageQty": shortage,
            "requiredDate": today_str(random.randint(3, 14))[:10],
            "currentStock": random.randint(0, 20),
            "onOrderQty": random.randint(0, shortage),
            "affectedOrders": [f"SO{random.randint(20250001,20259999)}" for _ in range(random.randint(1,3))],
            "suggestion": f"建议采购 {shortage+50} 件，最迟 {today_str(random.randint(1,5))[:10]} 到货"
        })
    return {"code": 0, "message": "ok", "data": {"total": len(items), "items": items[:limit]}}


@router.get("/aps/capacity")
async def query_capacity(dateFrom: Optional[str] = None,
                         dateTo: Optional[str] = None,
                         resourceCode: Optional[str] = None):
    """产能负荷查询"""
    resources = []
    for code, name in [("WC001","车间A-冲压机"),("WC002","车间A-焊接线"),
                       ("WC003","车间B-装配台"),("WC004","车间B-检测站")]:
        load = random.randint(60, 120)
        available = round(random.uniform(40, 80), 1)
        planned = round(available * load / 100, 1)
        overload_days = []
        if load > 100:
            overload_days = [today_str(random.randint(1,5))[:10] for _ in range(random.randint(1,3))]
        resources.append({
            "resourceCode": code,
            "resourceName": name,
            "loadRate": load,
            "availableHours": available,
            "plannedHours": planned,
            "overloadDays": overload_days,
            "status": "overload" if load > 100 else ("warning" if load > 85 else "normal")
        })
    return {"code": 0, "message": "ok", "data": {"resources": resources}}


@router.get("/aps/risk")
async def query_risk(dateFrom: Optional[str] = None,
                     dateTo: Optional[str] = None,
                     riskLevel: Optional[str] = None,
                     limit: int = 20):
    """交期风险查询"""
    orders = []
    for _ in range(random.randint(3, 8)):
        _, mn = random.choice([
            ("M20240001","伺服电机"),("M20240023","控制板"),
            ("M20240045","减速箱"),("M20240067","传感器组件")
        ])
        delay = random.randint(1, 12)
        due = today_str(random.randint(3, 14))[:10]
        expected = (datetime.strptime(due, "%Y-%m-%d") + timedelta(days=delay)).strftime("%Y-%m-%d")
        orders.append({
            "orderNo": f"SO{random.randint(20250001,20259999)}",
            "materialName": mn,
            "dueDate": due,
            "expectedDate": expected,
            "delayDays": delay,
            "riskLevel": "high" if delay > 5 else "medium",
            "riskReason": random.choice(["关键物料缺货","瓶颈工序积压","设备临时停机","紧急插单影响"]),
            "suggestion": random.choice(["建议与客户协商延期","建议加班赶产","建议外协加工"])
        })
    if riskLevel and riskLevel != "all":
        orders = [o for o in orders if o["riskLevel"] == riskLevel]
    return {"code": 0, "message": "ok", "data": {"total": len(orders), "orders": orders[:limit]}}


@router.get("/report")
async def report():
    """模拟报表页面"""
    from starlette.responses import HTMLResponse
    html = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>插单评估明细报表</title>
</head>
<body>
<h1>📊 插单评估明细报表</h1>
<p>本报表由 AI中台自动生成</p>
</body>
</html>"""
    return HTMLResponse(content=html)
```

- [ ] **Step 3: Commit**

```bash
git add src/aps.py src/utils.py
git commit -m "feat: 创建APS接口模块"
```

---

### Task 3: 创建 AI 网关模块

**Files:**
- Create: `src/gateway.py`
- Reference: `aps-mock/ai_gateway.py` (现有代码参考)

- [ ] **Step 1: Create src/gateway.py**

```python
"""AI 网关接口模块"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx
import json
import uuid
import asyncio
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
    userName: str
    password: str
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
            return {"code": -1, "message": "用户名或密码错误", "data": None}

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
            resp = await client.get(f"http://127.0.0.1:8000/api/aps/rush-order-evaluate",
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
        "aps_base_url": "http://127.0.0.1:8000" if config.is_mock_mode() else config.APS_BASE_URL,
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
                    headers={"Authorization": f"Bearer {config.AI_PLATFORM_WORKFLOW_KEY}", "Content-Type": "application/json"},
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
    message: str
    userId: Optional[str] = ""
    conversationId: Optional[str] = ""


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, authorization: str = Header("")):
    """流式业务问答"""
    from fastapi.responses import StreamingResponse

    verify_gateway_token(authorization)
    session = sessions[authorization.replace("Bearer ", "").strip()]

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
                    headers={"Authorization": f"Bearer {config.AI_PLATFORM_CHAT_KEY}", "Content-Type": "application/json"},
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
    verify_gateway_token(authorization)
    session = sessions[authorization.replace("Bearer ", "").strip()]
    async with httpx.AsyncClient(timeout=15) as client:
        await client.delete(f"{config.AI_PLATFORM_BASE_URL}/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {config.AI_PLATFORM_CHAT_KEY}"},
            params={"user": userId or session["userId"]})
    return ok(data={"cleared": True})
```

- [ ] **Step 2: Commit**

```bash
git add src/gateway.py
git commit -m "feat: 创建AI网关模块"
```

---

### Task 4: 创建统一入口

**Files:**
- Create: `src/main.py`

- [ ] **Step 1: Create src/main.py**

```python
"""AI中台统一服务入口"""
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import config
from .aps import router as aps_router
from .gateway import router as gateway_router

# 配置日志
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("uvicorn.access")

# 创建应用
app = FastAPI(
    title="AI中台统一服务",
    version="2.0.0",
    description="APS AI中台 - 统一网关服务"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# 注册路由
app.include_router(aps_router)
app.include_router(gateway_router)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "AI中台统一服务",
        "version": "2.0.0",
        "mode": "mock" if config.is_mock_mode() else "production",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "AI中台统一服务",
        "version": "2.0.0",
        "mode": "mock" if config.is_mock_mode() else "production",
        "endpoints": {
            "登录": "POST /ai/login",
            "触发评估": "POST /ai/rush-order/evaluate/start",
            "轮询状态": "GET /ai/rush-order/evaluate/status/{taskId}",
            "获取AI报告(流式)": "POST /ai/rush-order/evaluate/analyze/{taskId}/stream",
            "业务问答(流式)": "POST /ai/chat/stream",
            "清除对话": "DELETE /ai/conversation/{convId}",
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] **Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat: 创建统一服务入口"
```

---

### Task 5: 创建 Docker 支持

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /opt/ai-platform

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY src/ ./src/

# 创建日志目录
RUN mkdir -p /var/log/ai-platform

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create .env.example**

```bash
# 模式切换
MOCK_MODE=true

# APS 配置（生产模式需要）
APS_BASE_URL=http://customer-aps:8080/api

# AI服务中台配置
AI_PLATFORM_BASE_URL=http://139.224.228.33:8090/v1
AI_PLATFORM_CHAT_KEY=app-NMXnjStbZL4uA5ufO7CCjOq7
AI_PLATFORM_WORKFLOW_KEY=app-20mcGFNUbrVe8UjiZkttDefU

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=/var/log/ai-platform/app.log
```

- [ ] **Step 3: Create docker-compose.yml**

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
      - AI_PLATFORM_BASE_URL=${AI_PLATFORM_BASE_URL:-http://139.224.228.33:8090/v1}
      - AI_PLATFORM_CHAT_KEY=${AI_PLATFORM_CHAT_KEY:-}
      - AI_PLATFORM_WORKFLOW_KEY=${AI_PLATFORM_WORKFLOW_KEY:-}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    volumes:
      - ./logs:/var/log/ai-platform
    restart: unless-stopped
    networks:
      - ai-platform-network

networks:
  ai-platform-network:
    driver: bridge
```

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml .env.example
git commit -m "feat: 添加Docker支持"
```

---

### Task 6: 创建 systemctl 服务

**Files:**
- Create: `systemd/ai-platform.service`
- Create: `install.sh` (安装脚本)

- [ ] **Step 1: Create systemd/ai-platform.service**

```ini
[Unit]
Description=AI中台统一服务
Documentation=
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ai-platform
EnvironmentFile=/opt/ai-platform/.env
ExecStart=/opt/ai-platform/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=append:/var/log/ai-platform/stdout.log
StandardError=append:/var/log/ai-platform/stderr.log

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create install.sh**

```bash
#!/bin/bash
set -e

echo "Installing AI中台服务..."

# 创建目录
sudo mkdir -p /opt/ai-platform
sudo mkdir -p /var/log/ai-platform

# 复制文件
sudo cp -r . /opt/ai-platform/

# 创建虚拟环境
cd /opt/ai-platform
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 安装 systemd 服务
sudo cp systemd/ai-platform.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-platform

echo "Installation complete!"
echo ""
echo "To start the service:"
echo "  sudo systemctl start ai-platform"
echo ""
echo "To check status:"
echo "  sudo systemctl status ai-platform"
```

- [ ] **Step 3: Commit**

```bash
git add systemd/ai-platform.service install.sh
git commit -m "feat: 添加systemctl服务支持"
```

---

### Task 7: 文档更新

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README.md**

更新部署架构说明：
- 新增 Docker Compose 部署说明
- 新增 systemctl 部署说明
- 更新架构图
- 更新接口文档

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: 更新部署文档"
```

---

### Task 8: 清理旧文件

**Files:**
- Delete: `aps-mock/ai_gateway.py`
- Delete: `aps-mock/mock_server.py` (功能已迁移到 src/)
- Delete: `aps-mock/test_all.py`
- Delete: `aps-mock/test_gateway.py`

- [ ] **Step 1: 清理旧文件**

```bash
git rm aps-mock/ai_gateway.py aps-mock/mock_server.py aps-mock/test_all.py aps-mock/test_gateway.py
```

- [ ] **Step 2: Commit**

```bash
git commit -m "refactor: 移除旧服务文件，统一到src/目录"
```

---

## 实施检查清单

- [ ] Task 1: 项目结构和配置模块
- [ ] Task 2: APS 接口模块
- [ ] Task 3: AI 网关模块
- [ ] Task 4: 统一服务入口
- [ ] Task 5: Docker 支持
- [ ] Task 6: systemctl 服务
- [ ] Task 7: 文档更新
- [ ] Task 8: 清理旧文件
