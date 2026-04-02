#!/usr/bin/env python3
"""
AI中台 · 模拟服务 V2
基于客户方真实接口文档重写
真实接口对应：
  POST /api/login                          → 登录获取 token
  POST /api/aps/rush-order/paging          → 查询插单列表
  GET  /api/aps/rush-order-evaluate        → 触发插单评估运算
  GET  /api/aps/rush-order-evaluate/warning→ 获取评估提醒（运算状态）
  POST /api/aps/affect-order/paging        → 查询受影响订单列表
"""

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Any
import uvicorn, uuid, random, asyncio
from datetime import datetime, timedelta, date

app = FastAPI(title="AI中台 模拟服务 V2（真实接口）", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── 内存存储 ─────────────────────────────────────────────
tokens = {}
evaluation_status = {}
rush_orders_store = []
affect_orders_store = []

# ─── 工具函数 ──────────────────────────────────────────────
def today_str(offset=0):
    return (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%dT%H:%M:%S")

def date_str(offset=0):
    return (date.today() + timedelta(days=offset)).strftime("%Y-%m-%dT00:00:00")

def rand_order_code():
    return f"SO{random.randint(20250001, 20259999)}"

def verify_token(authorization: str = ""):
    if not authorization:
        raise HTTPException(status_code=401, detail={"statusCode": 401, "message": "未登录"})
    token = authorization.replace("Bearer ", "").strip()
    if token not in tokens:
        raise HTTPException(status_code=401, detail={"statusCode": 401, "message": "token 无效或已过期"})
    return tokens[token]

def ok(data=None, message="success"):
    return {"statusCode": 200, "message": message, "data": data}

def _build_affect_orders():
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

def _init_rush_orders():
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

_init_rush_orders()

# ════════════════════════════════════════════════════════
#  登录
# ════════════════════════════════════════════════════════

class LoginInput(BaseModel):
    userName: str
    password: str
    orgId: Optional[int] = None
    loginPort: Optional[str] = "Web"
    loginVersion: Optional[str] = "1.0"
    loginIp: Optional[str] = None

@app.post("/api/login")
async def login(body: LoginInput):
    """登录。测试账号：admin / admin123"""
    if body.userName == "admin" and body.password == "admin123":
        token = f"mock_token_{uuid.uuid4().hex}"
        info = {
            "userId": 1001, "userName": body.userName,
            "fullName": "管理员", "orgId": body.orgId or 1,
            "orgCode": "ORG001", "token": token,
            "loginTimestamp": int(datetime.now().timestamp()),
        }
        tokens[token] = info
        return ok(data=info)
    return ok(data=None, message="用户名或密码错误")

# ════════════════════════════════════════════════════════
#  公共请求体
# ════════════════════════════════════════════════════════

class BasePagingInput(BaseModel):
    current: int = 1
    pageSize: int = 20
    total: Optional[int] = 0
    filter: Optional[Any] = None
    orders: Optional[Any] = None
    filterPlanId: Optional[int] = None
    timestamps: Optional[str] = None

# ════════════════════════════════════════════════════════
#  插单接口
# ════════════════════════════════════════════════════════

@app.post("/api/aps/rush-order/paging")
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

class RushOrderPostInput(BaseModel):
    orderCode: Optional[str] = None
    materialCode: Optional[str] = None
    materialName: Optional[str] = None
    customerCode: Optional[str] = None
    customerName: Optional[str] = None
    qty: Optional[float] = None
    expectDate: Optional[str] = None
    priority: Optional[int] = 1
    remark: Optional[str] = None

@app.post("/api/aps/rush-order")
async def rush_order_create(body: RushOrderPostInput, authorization: str = Header("")):
    """新增插单"""
    verify_token(authorization)
    new_order = {
        "kid": str(uuid.uuid4()),
        "id": 1000 + len(rush_orders_store) + 1,
        "orderCode": body.orderCode or f"RO{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "rushUserFullName": "操作员",
        "materialCode": body.materialCode or "",
        "materialName": body.materialName or "",
        "customerCode": body.customerCode or "",
        "customerName": body.customerName or "",
        "qty": body.qty or 0,
        "expectDate": body.expectDate or date_str(14),
        "priority": body.priority or 1,
        "remark": body.remark or "",
        "productScheduleEndDate": None,
        "lackDay": None,
        "creationTime": today_str(),
    }
    rush_orders_store.append(new_order)
    return ok(data=new_order)

class BaseIdsEntityInput(BaseModel):
    ids: Optional[List[int]] = []
    timestamps: Optional[str] = None

@app.delete("/api/aps/rush-order")
async def rush_order_delete(body: BaseIdsEntityInput, authorization: str = Header("")):
    """删除插单"""
    verify_token(authorization)
    global rush_orders_store
    ids_to_del = set(body.ids or [])
    rush_orders_store = [o for o in rush_orders_store if o["id"] not in ids_to_del]
    return ok(data=True)

# ════════════════════════════════════════════════════════
#  插单评估
# ════════════════════════════════════════════════════════

@app.get("/api/aps/rush-order-evaluate")
async def rush_order_evaluate(authorization: str = Header("")):
    """
    触发插单评估运算（异步，约3秒完成）
    触发后轮询 /api/aps/rush-order-evaluate/warning 查询进度
    data 为提示文字 = 运算中；data 为 null = 运算完成
    """
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

@app.get("/api/aps/rush-order-evaluate/warning")
async def rush_order_evaluate_warning(authorization: str = Header("")):
    """
    获取评估提醒（轮询运算状态）
    返回 data = 文字提示 → 运算中，继续轮询
    返回 data = null     → 运算完成，可查询结果
    """
    verify_token(authorization)
    state = evaluation_status.get("state")
    if state == "running":
        return ok(data="正在评估中，请稍候...")
    elif state == "done":
        return ok(data=None, message="评估完成")
    else:
        return ok(data=None, message="暂无评估任务")

# ════════════════════════════════════════════════════════
#  受影响订单
# ════════════════════════════════════════════════════════

@app.post("/api/aps/affect-order/paging")
async def affect_order_paging(body: BasePagingInput, authorization: str = Header("")):
    """
    受影响订单分页查询
    评估完成后调用，返回被插单影响的现有订单列表
    """
    verify_token(authorization)
    if evaluation_status.get("state") != "done":
        return ok(data={"data": [], "current": 1, "pageSize": body.pageSize,
                        "total": 0, "pageTotal": 0}, message="暂无评估结果，请先触发评估运算")
    total = len(affect_orders_store)
    start = (body.current - 1) * body.pageSize
    page_data = affect_orders_store[start: start + body.pageSize]
    return ok(data={
        "data": page_data, "current": body.current,
        "pageSize": body.pageSize, "total": total,
        "pageTotal": max(1, (total + body.pageSize - 1) // body.pageSize)
    })

# ════════════════════════════════════════════════════════
#  健康检查
# ════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════
#  工作流 B · 业务问答查询接口（无需 Token，供 AI服务中台 HTTP 节点直接调用）
# ════════════════════════════════════════════════════════

@app.get("/api/aps/order")
async def query_order(orderNo: Optional[str] = None,
                      materialCode: Optional[str] = None,
                      dateFrom: Optional[str] = None,
                      dateTo: Optional[str] = None):
    """订单进度查询（无需Token）"""
    orders = []
    for _ in range(random.randint(1, 3)):
        mc, mn = random.choice([
            ("M20240001","伺服电机"),("M20240023","控制板"),
            ("M20240045","减速箱"),("M20240067","传感器组件")
        ])
        delay = random.randint(-3, 7)
        total = random.randint(50, 500)
        done  = random.randint(0, total)
        plan_end = today_str(random.randint(1, 20))
        due = (datetime.strptime(plan_end, "%Y-%m-%dT%H:%M:%S") + timedelta(days=-delay)).strftime("%Y-%m-%dT%H:%M:%S")
        orders.append({
            "orderNo":          orderNo or f"SO{random.randint(20250001,20259999)}",
            "materialCode":     materialCode or mc,
            "materialName":     mn,
            "planStartDate":    today_str(-random.randint(5,10)),
            "planEndDate":      plan_end,
            "dueDate":          due,
            "completedQty":     done,
            "totalQty":         total,
            "status":           "delayed" if delay > 0 else ("in_progress" if done < total else "completed"),
            "delayDays":        max(0, delay),
            "currentOperation": random.choice(["冲压","焊接","装配","检测","包装"]),
            "bottleneck":       "冲压机产能不足" if delay > 0 else ""
        })
    return {"code": 0, "message": "ok", "data": {"total": len(orders), "orders": orders}}


@app.get("/api/aps/shortage")
async def query_shortage(materialCode: Optional[str] = None,
                         dateFrom: Optional[str] = None,
                         dateTo: Optional[str] = None,
                         limit: int = 20):
    """缺料预警查询（无需Token）"""
    items = []
    for _ in range(random.randint(2, 5)):
        mc, mn = random.choice([
            ("M20240001","伺服电机"),("M20240023","控制板"),
            ("M20240045","减速箱"),("M20240067","传感器组件")
        ])
        shortage = random.randint(10, 200)
        items.append({
            "materialCode":  materialCode or mc,
            "materialName":  mn,
            "shortageQty":   shortage,
            "requiredDate":  today_str(random.randint(3, 14))[:10],
            "currentStock":  random.randint(0, 20),
            "onOrderQty":    random.randint(0, shortage),
            "affectedOrders": [f"SO{random.randint(20250001,20259999)}" for _ in range(random.randint(1,3))],
            "suggestion":    f"建议采购 {shortage+50} 件，最迟 {today_str(random.randint(1,5))[:10]} 到货"
        })
    return {"code": 0, "message": "ok", "data": {"total": len(items), "items": items[:limit]}}


@app.get("/api/aps/capacity")
async def query_capacity(dateFrom: Optional[str] = None,
                         dateTo: Optional[str] = None,
                         resourceCode: Optional[str] = None):
    """产能负荷查询（无需Token）"""
    resources = []
    for code, name in [("WC001","车间A-冲压机"),("WC002","车间A-焊接线"),
                       ("WC003","车间B-装配台"),("WC004","车间B-检测站")]:
        load = random.randint(60, 120)
        available = round(random.uniform(40, 80), 1)
        planned   = round(available * load / 100, 1)
        overload_days = []
        if load > 100:
            overload_days = [today_str(random.randint(1,5))[:10] for _ in range(random.randint(1,3))]
        resources.append({
            "resourceCode":  code,
            "resourceName":  name,
            "loadRate":      load,
            "availableHours": available,
            "plannedHours":  planned,
            "overloadDays":  overload_days,
            "status":        "overload" if load > 100 else ("warning" if load > 85 else "normal")
        })
    return {"code": 0, "message": "ok", "data": {"resources": resources}}


@app.get("/api/aps/risk")
async def query_risk(dateFrom: Optional[str] = None,
                     dateTo: Optional[str] = None,
                     riskLevel: Optional[str] = None,
                     limit: int = 20):
    """交期风险查询（无需Token）"""
    orders = []
    for _ in range(random.randint(3, 8)):
        _, mn = random.choice([
            ("M20240001","伺服电机"),("M20240023","控制板"),
            ("M20240045","减速箱"),("M20240067","传感器组件")
        ])
        delay = random.randint(1, 12)
        due   = today_str(random.randint(3, 14))[:10]
        expected = (datetime.strptime(due, "%Y-%m-%d") + timedelta(days=delay)).strftime("%Y-%m-%d")
        orders.append({
            "orderNo":      f"SO{random.randint(20250001,20259999)}",
            "materialName": mn,
            "dueDate":      due,
            "expectedDate": expected,
            "delayDays":    delay,
            "riskLevel":    "high" if delay > 5 else "medium",
            "riskReason":   random.choice(["关键物料缺货","瓶颈工序积压","设备临时停机","紧急插单影响"]),
            "suggestion":   random.choice(["建议与客户协商延期","建议加班赶产","建议外协加工"])
        })
    if riskLevel and riskLevel != "all":
        orders = [o for o in orders if o["riskLevel"] == riskLevel]
    return {"code": 0, "message": "ok", "data": {"total": len(orders), "orders": orders[:limit]}}


@app.get("/report")
async def report():
    """模拟报表页面"""
    from starlette.responses import HTMLResponse
    html = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>插单评估明细报表</title>
<style>
  body { font-family: "PingFang SC", "Microsoft YaHei", sans-serif; background: #f7f8fa; padding: 20px; }
  h1 { color: #1a56db; font-size: 20px; }
  .summary { background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .summary h2 { font-size: 16px; margin: 0 0 12px; }
  table { width: 100%%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; }
  th { background: #1a56db; color: #fff; padding: 10px 12px; text-align: left; font-size: 13px; }
  td { padding: 9px 12px; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
  tr:last-child td { border-bottom: none; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
  .tag-delay { background: #fee2e2; color: #dc2626; }
  .tag-ok { background: #d1fae5; color: #059669; }
  .tag-warn { background: #fef3c7; color: #d97706; }
  .footer { text-align: center; color: #9ca3af; font-size: 12px; margin-top: 20px; }
</style>
</head>
<body>
<h1>📊 插单评估明细报表</h1>
<div class="summary">
  <h2>评估汇总</h2>
  <p>插单数量：<strong>2</strong> &nbsp;|&nbsp;
     受影响订单：<strong>9</strong> &nbsp;|&nbsp;
     造成延迟：<strong>2</strong> &nbsp;|&nbsp;
     准时：<strong>7</strong></p>
</div>
<h2 style="font-size:15px;margin:16px 0 10px">插单详情</h2>
<table>
  <tr>
    <th>插单编号</th><th>客户</th><th>物料</th><th>数量</th><th>期望交期</th><th>模拟交期</th><th>缺口天数</th><th>物料瓶颈</th><th>产能瓶颈</th>
  </tr>
  <tr>
    <td>RO2026032901</td><td>C001</td><td>伺服电机</td><td>100</td><td>2025-09-01</td><td>2025-09-03</td><td><span class="tag tag-delay">+2天</span></td><td>钢材, 铜线</td><td>车间A-冲压机</td>
  </tr>
  <tr>
    <td>RO2026032902</td><td>C002</td><td>控制板</td><td>50</td><td>2025-09-05</td><td>2025-09-04</td><td><span class="tag tag-ok">-1天</span></td><td></td><td></td>
  </tr>
</table>
<h2 style="font-size:15px;margin:16px 0 10px">受影响订单（延迟 Top10）</h2>
<table>
  <tr>
    <th>订单号</th><th>原承诺交期</th><th>新交期</th><th>延迟天数</th><th>延迟原因</th>
  </tr>
  <tr>
    <td>SO20251234</td><td>2025-09-10</td><td>2025-09-15</td><td><span class="tag tag-delay">+5天</span></td><td>产能冲突</td>
  </tr>
  <tr>
    <td>SO20251235</td><td>2025-09-12</td><td>2025-09-13</td><td><span class="tag tag-warn">+1天</span></td><td>物料短缺</td>
  </tr>
</table>
<div class="footer">本报表由 AI中台自动生成 · 数据仅供参考</div>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/")
async def health():
    return {
        "status": "ok",
        "service": "AI中台 模拟服务 V2（真实接口）",
        "version": "2.0.0",
        "test_account": {"userName": "admin", "password": "admin123"},
        "endpoints": {
            "登录": "POST /api/login",
            "插单查询": "POST /api/aps/rush-order/paging",
            "插单新增": "POST /api/aps/rush-order",
            "插单删除": "DELETE /api/aps/rush-order",
            "触发评估": "GET /api/aps/rush-order-evaluate",
            "查询评估状态": "GET /api/aps/rush-order-evaluate/warning",
            "受影响订单": "POST /api/aps/affect-order/paging",
            "订单进度查询(无Token)": "GET /api/aps/order",
            "缺料预警查询(无Token)": "GET /api/aps/shortage",
            "产能负荷查询(无Token)": "GET /api/aps/capacity",
            "交期风险查询(无Token)": "GET /api/aps/risk",
            "报表页面": "GET /report",
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
