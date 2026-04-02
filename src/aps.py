"""APS 接口模块 - 包含 APS 模拟数据和接口"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
import uuid
import random
import asyncio
from datetime import datetime, timedelta

from .utils import today_str, date_str, rand_order_code

router = APIRouter(prefix="/api", tags=["APS"])

# 内存存储
evaluation_status = {"state": "idle"}
evaluation_task = None
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
    return {"code": 0, "message": message, "data": data}


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
            except (ValueError, IndexError, KeyError):
                expect_dt = datetime.now() + timedelta(days=14)
            o["productScheduleEndDate"] = (expect_dt + timedelta(days=gap)).strftime("%Y-%m-%dT%H:%M:%S")
            o["lackDay"] = gap
        _build_affect_orders()
        evaluation_status["state"] = "done"

    global evaluation_task
    evaluation_task = asyncio.create_task(run())
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
