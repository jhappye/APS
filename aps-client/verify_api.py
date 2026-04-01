#!/usr/bin/env python3
"""
APS AI 助手 · 客户方接口验证脚本
=====================================
用途：帮助客户方在完成接口开发后，快速验证所有接口是否符合对接规范
用法：
  1. 修改下方 CONFIG 中的 BASE_URL 为客户方实际地址
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
    "BASE_URL": "http://your-aps-host/api",   # ← 改成客户方地址
    "TOKEN": "your-bearer-token",              # ← 改成对接 Token
    "TEST_ORDER_NO": "SO20250001",             # ← 改成一个真实存在的订单号
    "TEST_MATERIAL_CODE": "M20240001",         # ← 改成一个真实存在的物料编码
    "TEST_CUSTOMER_CODE": "C001",              # ← 改成真实客户编码
    "TEST_DUE_DATE": "2025-12-01",             # ← 测试用期望交期
}
# ============================================================

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"
results = []

def get_headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CONFIG['TOKEN']}"
    }

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

def req_get(path, params=None):
    url = CONFIG["BASE_URL"] + path
    try:
        r = requests.get(url, params=params, headers=get_headers(), timeout=30)
        return r
    except Exception as e:
        return None

def req_post(path, body):
    url = CONFIG["BASE_URL"] + path
    try:
        r = requests.post(url, json=body, headers=get_headers(), timeout=30)
        return r
    except Exception as e:
        return None

# ────────────────────────────────────────────
section("STEP 0 · 前置检查")
# ────────────────────────────────────────────
print(f"  目标地址：{CONFIG['BASE_URL']}")
r = req_get("/rush-order/simulate/ping_test/status")
if r is None:
    print("\n  ❌ 无法连接到目标地址，请检查 BASE_URL 配置和网络连通性")
    exit(1)
check("服务可连接", r.status_code in [200, 404, 400],
      f"HTTP {r.status_code}（404/400 是正常的，说明服务在运行）")

# ────────────────────────────────────────────
section("STEP 1 · 触发插单运算（A1）")
# ────────────────────────────────────────────
body = {
    "rushOrders": [
        {
            "customerCode": CONFIG["TEST_CUSTOMER_CODE"],
            "materialCode": CONFIG["TEST_MATERIAL_CODE"],
            "quantity": 10,
            "dueDate": CONFIG["TEST_DUE_DATE"],
            "priority": "Normal",
            "remark": "验证测试"
        }
    ]
}
r = req_post("/rush-order/simulate", body)
check("POST /rush-order/simulate 可访问", r is not None and r.status_code == 200,
      f"HTTP {r.status_code if r else 'N/A'}")

sim_id = None
if r and r.status_code == 200:
    try:
        data = r.json()
        check("响应 code=0", data.get("code") == 0, str(data.get("code")))
        check("返回 data.simulationId", bool(data.get("data", {}).get("simulationId")),
              data.get("data", {}).get("simulationId", "缺失"))
        check("返回 data.status", data.get("data", {}).get("status") in ["queued", "running"],
              data.get("data", {}).get("status", "缺失"))
        sim_id = data.get("data", {}).get("simulationId")
        print(f"\n  simulationId = {sim_id}")
    except Exception as e:
        check("响应为合法 JSON", False, str(e))

# ────────────────────────────────────────────
section("STEP 2 · 轮询运算状态（A2）")
# ────────────────────────────────────────────
if sim_id:
    print("  轮询中，最多等待 60 秒...")
    completed = False
    for i in range(20):
        time.sleep(3)
        r = req_get(f"/rush-order/simulate/{sim_id}/status")
        if r and r.status_code == 200:
            data = r.json().get("data", {})
            status = data.get("status", "")
            print(f"  第{i+1}次：status = {status}")
            if status == "completed":
                completed = True
                break
            if status == "failed":
                check("运算未失败", False, data.get("failReason", "未知原因"))
                break
        else:
            check("轮询接口可访问", False, f"HTTP {r.status_code if r else 'N/A'}")
            break

    check("运算在60秒内完成", completed)
else:
    check("跳过（simulationId 未获取到）", False, "A1 接口未通过")

# ────────────────────────────────────────────
section("STEP 3 · 查询运算结果（A3）⭐ 最关键")
# ────────────────────────────────────────────
if sim_id and completed:
    r = req_get(f"/rush-order/simulate/{sim_id}/result")
    check("GET /result 返回200", r is not None and r.status_code == 200)

    if r and r.status_code == 200:
        try:
            body = r.json()
            check("响应 code=0", body.get("code") == 0)
            check("status=completed", body.get("status") == "completed", body.get("status"))
            check("data 字段存在", body.get("data") is not None)
            check("reportUrl 字段存在", bool(body.get("reportUrl")), body.get("reportUrl", "缺失"))

            d = body.get("data", {})
            check("rushOrderCount 是数字", isinstance(d.get("rushOrderCount"), int))
            check("rushOrders 是数组", isinstance(d.get("rushOrders"), list))
            check("impact 字段存在", "impact" in d)

            if d.get("rushOrders"):
                o = d["rushOrders"][0]
                required = ["rushOrderNo","creator","createDate","customerCode",
                            "materialCode","materialName","quantity","dueDate",
                            "priority","remark","scheduledDate","gapDays",
                            "materialBottlenecks","capacityBottlenecks"]
                for f in required:
                    check(f"  字段 {f} 存在", f in o)

                # 重点检查：空值规范
                check("  remark 不为 null（必须为空字符串）",
                      o.get("remark") is not None,
                      f"当前值：{repr(o.get('remark'))}")
                check("  materialBottlenecks 是数组（不能为null）",
                      isinstance(o.get("materialBottlenecks"), list),
                      f"当前类型：{type(o.get('materialBottlenecks')).__name__}")
                check("  capacityBottlenecks 是数组（不能为null）",
                      isinstance(o.get("capacityBottlenecks"), list),
                      f"当前类型：{type(o.get('capacityBottlenecks')).__name__}")

                # 检查 gapDays 是数字
                check("  gapDays 是数字", isinstance(o.get("gapDays"), (int, float)),
                      f"当前类型：{type(o.get('gapDays')).__name__}")

            imp = d.get("impact", {})
            check("impact.delayedTop10 是数组", isinstance(imp.get("delayedTop10"), list))
            check("impact.notDelayedTop10 是数组", isinstance(imp.get("notDelayedTop10"), list))

            # 检查 delayedTop10 降序排列
            top10 = imp.get("delayedTop10", [])
            if len(top10) > 1:
                days = [x.get("delayDays", 0) for x in top10]
                check("  delayedTop10 按 delayDays 降序排列",
                      days == sorted(days, reverse=True), str(days))
            else:
                check("  delayedTop10 排序（条数不足跳过）", True, "skip", warn=True)

        except Exception as e:
            check("响应为合法 JSON", False, str(e))
else:
    check("跳过（前序步骤未通过）", False, "")

# ────────────────────────────────────────────
section("STEP 4 · 订单进度查询（A4）")
# ────────────────────────────────────────────
r = req_get("/aps/order", params={"orderNo": CONFIG["TEST_ORDER_NO"]})
check("GET /aps/order 返回200", r is not None and r.status_code == 200,
      f"HTTP {r.status_code if r else 'N/A'}")
if r and r.status_code == 200:
    try:
        d = r.json().get("data", {})
        check("返回 orders 数组", isinstance(d.get("orders"), list))
        if d.get("orders"):
            o = d["orders"][0]
            for f in ["orderNo","materialCode","materialName","planEndDate",
                      "dueDate","completedQty","totalQty","status","delayDays","currentOperation"]:
                check(f"  字段 {f} 存在", f in o)
            # 检查 status 合法值
            check("  status 取值合法", o.get("status") in
                  ["pending","in_progress","completed","delayed"],
                  f"当前值：{o.get('status')}")
    except Exception as e:
        check("响应为合法 JSON", False, str(e))

# ────────────────────────────────────────────
section("STEP 5 · 缺料预警查询（A5）")
# ────────────────────────────────────────────
r = req_get("/aps/shortage", params={"limit": 5})
check("GET /aps/shortage 返回200", r is not None and r.status_code == 200)
if r and r.status_code == 200:
    try:
        d = r.json().get("data", {})
        check("返回 items 数组", isinstance(d.get("items"), list))
        check("返回 total 字段", isinstance(d.get("total"), int))
        if d.get("items"):
            item = d["items"][0]
            for f in ["materialCode","materialName","shortageQty","requiredDate",
                      "currentStock","onOrderQty","affectedOrders","suggestion"]:
                check(f"  字段 {f} 存在", f in item)
            check("  affectedOrders 是数组", isinstance(item.get("affectedOrders"), list))
    except Exception as e:
        check("响应为合法 JSON", False, str(e))

# ────────────────────────────────────────────
section("STEP 6 · 产能负荷查询（A6）")
# ────────────────────────────────────────────
r = req_get("/aps/capacity")
check("GET /aps/capacity 返回200", r is not None and r.status_code == 200)
if r and r.status_code == 200:
    try:
        d = r.json().get("data", {})
        check("返回 resources 数组", isinstance(d.get("resources"), list))
        if d.get("resources"):
            res = d["resources"][0]
            for f in ["resourceCode","resourceName","loadRate",
                      "availableHours","plannedHours","overloadDays","status"]:
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
section("STEP 7 · 交期风险查询（A7）")
# ────────────────────────────────────────────
r = req_get("/aps/risk", params={"limit": 5})
check("GET /aps/risk 返回200", r is not None and r.status_code == 200)
if r and r.status_code == 200:
    try:
        d = r.json().get("data", {})
        check("返回 orders 数组", isinstance(d.get("orders"), list))
        check("limit 参数生效（≤5条）", len(d.get("orders", [])) <= 5)
        if d.get("orders"):
            o = d["orders"][0]
            for f in ["orderNo","materialName","dueDate","expectedDate",
                      "delayDays","riskLevel","riskReason","suggestion"]:
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
    print(f"\n  🎉 所有接口验证通过！可以开始与 AI 助手服务联调。")
else:
    print(f"\n  ⚠️  请修复以下 {failed} 个问题后重新运行验证：\n")
    for name, ok in results:
        if not ok:
            print(f"    {FAIL} {name}")
    print(f"\n  修复完成后重新运行：python3 verify_api.py")
