#!/usr/bin/env python3
"""
APS AI 助手 · 客户方接口验证脚本
=====================================
用途：帮助客户方在完成接口开发后，快速验证所有接口是否符合对接规范
用法：
  1. 修改下方 CONFIG 中的配置
  2. 运行：python3 verify_api.py
  3. 查看报告，修复 ❌ 项后重新运行直到全部通过
"""

import requests
import json
import time

# ============================================================
# ⚙️  修改这里：填入客户方实际接口地址
# ============================================================
CONFIG = {
    "BASE_URL": "http://localhost:8000",   # ← 改成客户方 APS 地址（AI网关会调用此地址）
    "USERNAME": "admin",                   # ← 测试账号
    "PASSWORD": "admin123",                # ← 测试密码
    "TEST_ORDER_NO": "SO20250001",         # ← 改成一个真实存在的订单号
    "TEST_MATERIAL_CODE": "M20240001",     # ← 改成一个真实存在的物料编码
}
# ============================================================

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"
results = []
token = None

def get_headers(need_auth=True):
    headers = {"Content-Type": "application/json"}
    if need_auth and token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def check(name, ok, detail="", warn=False):
    mark = WARN if warn else (PASS if ok else FAIL)
    msg = f"  {mark} {name}"
    if detail:
        msg += f"  →  {detail}"
    print(msg)
    if not warn:
        results.append((name, ok))

def section(title):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")

def req_get(path, params=None, need_auth=True):
    url = CONFIG["BASE_URL"] + path
    try:
        r = requests.get(url, params=params, headers=get_headers(need_auth), timeout=30)
        return r
    except Exception as e:
        print(f"  ❌ 请求异常: {e}")
        return None

def req_post(path, body=None, need_auth=True):
    url = CONFIG["BASE_URL"] + path
    try:
        r = requests.post(url, json=body, headers=get_headers(need_auth), timeout=30)
        return r
    except Exception as e:
        print(f"  ❌ 请求异常: {e}")
        return None

# ────────────────────────────────────────────
section("STEP 0 · 前置检查")
# ────────────────────────────────────────────
print(f"  目标地址：{CONFIG['BASE_URL']}")
r = req_get("/", need_auth=False)
if r is None:
    print("\n  ❌ 无法连接到目标地址，请检查 BASE_URL 配置和网络连通性")
    exit(1)
check("服务可连接", r is not None, f"HTTP {r.status_code if r else 'N/A'}")

# ────────────────────────────────────────────
section("STEP 1 · 登录（A1）")
# ────────────────────────────────────────────
r = req_post("/api/login", body={
    "userName": CONFIG["USERNAME"],
    "password": CONFIG["PASSWORD"],
    "loginPort": "Web"
}, need_auth=False)
check("POST /api/login 可访问", r is not None and r.status_code == 200,
      f"HTTP {r.status_code if r else 'N/A'}")

global token
if r and r.status_code == 200:
    try:
        data = r.json()
        check("响应 code=0", data.get("code") == 0 or data.get("statusCode") == 200,
              str(data.get("code") or data.get("statusCode")))
        token = data.get("data", {}).get("token")
        check("返回 token", bool(token), token or "缺失")
        if token:
            print(f"\n  登录成功，token = {token[:20]}...")
    except Exception as e:
        check("响应为合法 JSON", False, str(e))
else:
    check("登录成功", False, "请检查用户名密码")
    token = None

# ────────────────────────────────────────────
section("STEP 2 · 触发插单评估（A2）")
# ────────────────────────────────────────────
r = req_get("/api/aps/rush-order-evaluate")
check("GET /api/aps/rush-order-evaluate 可访问", r is not None and r.status_code == 200,
      f"HTTP {r.status_code if r else 'N/A'}")
if r and r.status_code == 200:
    try:
        data = r.json()
        check("响应状态码正常", data.get("statusCode") == 200 or data.get("code") == 0)
        print(f"\n  评估已触发，等待 3 秒后轮询状态...")
        time.sleep(3)
    except Exception as e:
        check("响应为合法 JSON", False, str(e))

# ────────────────────────────────────────────
section("STEP 3 · 查询评估状态（A3）")
# ────────────────────────────────────────────
print("  轮询中，最多等待 60 秒...")
completed = False
for i in range(20):
    time.sleep(3)
    r = req_get("/api/aps/rush-order-evaluate/warning")
    if r and r.status_code == 200:
        try:
            data = r.json()
            warn_data = data.get("data")
            status = "running" if isinstance(warn_data, str) else "completed"
            print(f"  第{i+1}次：data = {warn_data}")
            if warn_data is None:
                completed = True
                break
        except Exception as e:
            print(f"  第{i+1}次：解析响应失败 {e}")
    else:
        check("轮询接口可访问", False, f"HTTP {r.status_code if r else 'N/A'}")
        break

check("评估在60秒内完成", completed)

# ────────────────────────────────────────────
section("STEP 4 · 查询插单列表（A4）⭐ 最关键")
# ────────────────────────────────────────────
if completed:
    r = req_post("/api/aps/rush-order/paging", body={"current": 1, "pageSize": 100})
    check("POST /api/aps/rush-order/paging 返回200", r is not None and r.status_code == 200)

    if r and r.status_code == 200:
        try:
            data = r.json()
            check("响应结构正确", "data" in data or "statusCode" in data)

            # 兼容两种响应格式
            page_data = data.get("data", {})
            if isinstance(page_data, dict):
                orders = page_data.get("data", [])
            elif isinstance(page_data, list):
                orders = page_data
            else:
                orders = []

            check("返回 data.data 数组（插单列表）", isinstance(orders, list))
            check("插单数量 > 0", len(orders) > 0, f"共 {len(orders)} 条")

            if orders:
                o = orders[0]
                required = ["orderCode", "materialCode", "expectDate", "qty"]
                for f in required:
                    check(f"  字段 {f} 存在", f in o, f"当前值: {o.get(f)}")

                # 评估后应该有值
                check("  productScheduleEndDate 有值（评估已完成）",
                      bool(o.get("productScheduleEndDate")),
                      f"值: {o.get('productScheduleEndDate')}")
                check("  lackDay 是数字",
                      isinstance(o.get("lackDay"), (int, float)),
                      f"类型: {type(o.get('lackDay')).__name__}")
                check("  remark 不为 null（必须为空字符串）",
                      o.get("remark") is not None,
                      f"当前值: {repr(o.get('remark'))}")
        except Exception as e:
            check("响应为合法 JSON", False, str(e))
else:
    check("跳过（前序步骤未通过）", False, "评估未完成")

# ────────────────────────────────────────────
section("STEP 5 · 查询受影响订单（A5）")
# ────────────────────────────────────────────
if completed:
    r = req_post("/api/aps/affect-order/paging", body={"current": 1, "pageSize": 100})
    check("POST /api/aps/affect-order/paging 返回200", r is not None and r.status_code == 200)

    if r and r.status_code == 200:
        try:
            data = r.json()
            page_data = data.get("data", {})
            if isinstance(page_data, dict):
                affect_orders = page_data.get("data", [])
            elif isinstance(page_data, list):
                affect_orders = page_data
            else:
                affect_orders = []

            check("返回受影响订单列表", isinstance(affect_orders, list))
            check("受影响订单数量 > 0", len(affect_orders) > 0, f"共 {len(affect_orders)} 条")

            if affect_orders:
                o = affect_orders[0]
                required = ["orderCode", "materialCode", "deliveryDate",
                           "originalProductScheduleEndDate", "productScheduleEndDate", "delayDay"]
                for f in required:
                    check(f"  字段 {f} 存在", f in o, f"当前值: {o.get(f)}")
                check("  delayDay 是数字", isinstance(o.get("delayDay"), (int, float)))
        except Exception as e:
            check("响应为合法 JSON", False, str(e))
else:
    check("跳过（前序步骤未通过）", False, "评估未完成")

# ────────────────────────────────────────────
section("STEP 6 · 订单进度查询（A6）")
# ────────────────────────────────────────────
r = req_get("/api/aps/order", params={"orderNo": CONFIG["TEST_ORDER_NO"]}, need_auth=False)
check("GET /api/aps/order 返回200", r is not None and r.status_code == 200,
      f"HTTP {r.status_code if r else 'N/A'}")
if r and r.status_code == 200:
    try:
        d = r.json().get("data", {})
        check("返回 orders 数组", isinstance(d.get("orders"), list))
        if d.get("orders"):
            o = d["orders"][0]
            for f in ["orderNo", "materialCode", "materialName", "planEndDate",
                      "dueDate", "completedQty", "totalQty", "status", "delayDays"]:
                check(f"  字段 {f} 存在", f in o)
            check("  status 取值合法", o.get("status") in
                  ["pending", "in_progress", "completed", "delayed"],
                  f"当前值: {o.get('status')}")
    except Exception as e:
        check("响应为合法 JSON", False, str(e))

# ────────────────────────────────────────────
section("STEP 7 · 缺料预警查询（A7）")
# ────────────────────────────────────────────
r = req_get("/api/aps/shortage", params={"limit": 5}, need_auth=False)
check("GET /api/aps/shortage 返回200", r is not None and r.status_code == 200)
if r and r.status_code == 200:
    try:
        d = r.json().get("data", {})
        check("返回 items 数组", isinstance(d.get("items"), list))
        check("返回 total 字段", isinstance(d.get("total"), int))
        if d.get("items"):
            item = d["items"][0]
            for f in ["materialCode", "materialName", "shortageQty", "requiredDate",
                      "currentStock", "onOrderQty", "affectedOrders", "suggestion"]:
                check(f"  字段 {f} 存在", f in item)
            check("  affectedOrders 是数组", isinstance(item.get("affectedOrders"), list))
    except Exception as e:
        check("响应为合法 JSON", False, str(e))

# ────────────────────────────────────────────
section("STEP 8 · 产能负荷查询（A8）")
# ────────────────────────────────────────────
r = req_get("/api/aps/capacity", need_auth=False)
check("GET /api/aps/capacity 返回200", r is not None and r.status_code == 200)
if r and r.status_code == 200:
    try:
        d = r.json().get("data", {})
        check("返回 resources 数组", isinstance(d.get("resources"), list))
        if d.get("resources"):
            res = d["resources"][0]
            for f in ["resourceCode", "resourceName", "loadRate",
                      "availableHours", "plannedHours", "overloadDays", "status"]:
                check(f"  字段 {f} 存在", f in res)
            # 检查 status 逻辑
            for res in d["resources"]:
                load = res.get("loadRate", 0)
                status = res.get("status", "")
                if load > 100:
                    check(f"  {res.get('resourceName')} 过载逻辑正确",
                          status == "overload", f"loadRate={load} status={status}")
                elif load > 85:
                    check(f"  {res.get('resourceName')} 预警逻辑正确",
                          status == "warning", f"loadRate={load} status={status}")
                else:
                    check(f"  {res.get('resourceName')} 正常逻辑正确",
                          status == "normal", f"loadRate={load} status={status}")
            check("  overloadDays 是数组", isinstance(res.get("overloadDays"), list))
    except Exception as e:
        check("响应为合法 JSON", False, str(e))

# ────────────────────────────────────────────
section("STEP 9 · 交期风险查询（A9）")
# ────────────────────────────────────────────
r = req_get("/api/aps/risk", params={"limit": 5}, need_auth=False)
check("GET /api/aps/risk 返回200", r is not None and r.status_code == 200)
if r and r.status_code == 200:
    try:
        d = r.json().get("data", {})
        check("返回 orders 数组", isinstance(d.get("orders"), list))
        check("limit 参数生效（≤5条）", len(d.get("orders", [])) <= 5)
        if d.get("orders"):
            o = d["orders"][0]
            for f in ["orderNo", "materialName", "dueDate", "expectedDate",
                      "delayDays", "riskLevel", "riskReason", "suggestion"]:
                check(f"  字段 {f} 存在", f in o)
            # 检查 riskLevel 逻辑
            for o in d["orders"]:
                delay = o.get("delayDays", 0)
                level = o.get("riskLevel", "")
                expected = "high" if delay > 5 else "medium"
                check(f"  订单 {o.get('orderNo')} 风险等级逻辑正确",
                      level == expected, f"delayDays={delay} → {level}（期望{expected}）")
    except Exception as e:
        check("响应为合法 JSON", False, str(e))

# ────────────────────────────────────────────
section("📊 验证报告")
# ────────────────────────────────────────────
total = len(results)
passed = sum(1 for _, ok in results if ok)
failed = total - passed

print(f"\n  总计：{total} 项")
print(f"  通过：{passed} 项 {PASS}")
print(f"  失败：{failed} 项 {FAIL if failed else ''}")

if failed == 0:
    print(f"\n  🎉 所有接口验证通过！可以开始与 AI 网关服务联调。")
else:
    print(f"\n  ⚠️  请修复以下 {failed} 个问题后重新运行验证：\n")
    for name, ok in results:
        if not ok:
            print(f"    {FAIL} {name}")
    print(f"\n  修复完成后重新运行：python3 verify_api.py")
