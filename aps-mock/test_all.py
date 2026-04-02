#!/usr/bin/env python3
"""
AI中台 · 真实接口测试脚本 V2
测试顺序：登录 → 查插单 → 触发评估 → 轮询状态 → 查受影响订单
"""
import requests, time, json

BASE = "http://localhost:8000"
PASS, FAIL = "✅", "❌"
results = []
TOKEN = ""

def check(name, ok, detail=""):
    mark = PASS if ok else FAIL
    print(f"  {mark} {name}" + (f"  →  {detail}" if detail else ""))
    results.append((name, ok))

def section(title):
    print(f"\n{'='*55}\n  {title}\n{'='*55}")

def headers():
    return {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}

# ─────────────────────────────────────────────
section("STEP 0 · 健康检查")
# ─────────────────────────────────────────────
r = requests.get(f"{BASE}/", timeout=5)
check("服务可访问", r.status_code == 200)

# ─────────────────────────────────────────────
section("STEP 1 · 登录 POST /api/login")
# ─────────────────────────────────────────────
r = requests.post(f"{BASE}/api/login", json={"userName": "admin", "password": "admin123"})
check("登录返回200", r.status_code == 200)
data = r.json()
check("statusCode=200", data.get("statusCode") == 200)
check("返回 token", bool(data.get("data", {}).get("token")))
TOKEN = data.get("data", {}).get("token", "")
print(f"  token = {TOKEN[:30]}...")

# 错误密码测试
r2 = requests.post(f"{BASE}/api/login", json={"userName": "admin", "password": "wrong"})
check("错误密码不返回token", not (r2.json().get("data") or {}).get("token"))

# ─────────────────────────────────────────────
section("STEP 2 · 查询插单列表 POST /api/aps/rush-order/paging")
# ─────────────────────────────────────────────
r = requests.post(f"{BASE}/api/aps/rush-order/paging",
    headers=headers(), json={"current": 1, "pageSize": 10})
check("分页查询返回200", r.status_code == 200)
data = r.json()
check("statusCode=200", data.get("statusCode") == 200)
paging = data.get("data", {})
check("返回 data.data 列表", isinstance(paging.get("data"), list))
check("返回 total 字段", isinstance(paging.get("total"), int))
check("返回 pageTotal 字段", isinstance(paging.get("pageTotal"), int))

if paging.get("data"):
    o = paging["data"][0]
    # 验证真实字段名
    for field in ["orderCode","rushUserFullName","materialCode","materialName",
                  "customerCode","qty","expectDate","priority","remark",
                  "productScheduleEndDate","lackDay","creationTime"]:
        check(f"  字段 {field} 存在", field in o)

    print(f"\n  插单列表预览（共{paging['total']}条）：")
    for item in paging["data"][:3]:
        print(f"    {item['orderCode']} | {item['materialName']} | 数量:{item['qty']} | 交期:{item['expectDate'][:10]}")

# ─────────────────────────────────────────────
section("STEP 3 · 触发评估 GET /api/aps/rush-order-evaluate")
# ─────────────────────────────────────────────
r = requests.get(f"{BASE}/api/aps/rush-order-evaluate", headers=headers())
check("触发评估返回200", r.status_code == 200)
data = r.json()
check("statusCode=200", data.get("statusCode") == 200)

# ─────────────────────────────────────────────
section("STEP 4 · 轮询评估状态 GET /api/aps/rush-order-evaluate/warning")
# ─────────────────────────────────────────────
print("  轮询中（最多等待15秒）...")
done = False
for i in range(6):
    time.sleep(2)
    r = requests.get(f"{BASE}/api/aps/rush-order-evaluate/warning", headers=headers())
    data = r.json()
    warn_data = data.get("data")
    print(f"  第{i+1}次轮询：data = {repr(warn_data)}")
    if warn_data is None:
        # data=null 表示完成
        done = True
        break

check("评估在15秒内完成（warning.data = null）", done)

# ─────────────────────────────────────────────
section("STEP 5 · 查询插单结果（评估后）")
# ─────────────────────────────────────────────
r = requests.post(f"{BASE}/api/aps/rush-order/paging",
    headers=headers(), json={"current": 1, "pageSize": 10})
data = r.json()
orders = data.get("data", {}).get("data", [])
check("评估后 productScheduleEndDate 已填充",
      any(o.get("productScheduleEndDate") for o in orders),
      "排产结束日期应有值")
check("评估后 lackDay 已填充",
      any(o.get("lackDay") is not None for o in orders),
      "缺口天数应有值")

print(f"\n  插单评估结果：")
for item in orders[:3]:
    lack = item.get("lackDay", 0) or 0
    flag = "⚠️延迟" if lack > 0 else "✅满足"
    print(f"    {item['orderCode']} | 期望:{item['expectDate'][:10]} | 排产:{str(item.get('productScheduleEndDate',''))[:10]} | 缺口:{lack}天 {flag}")

# ─────────────────────────────────────────────
section("STEP 6 · 受影响订单 POST /api/aps/affect-order/paging")
# ─────────────────────────────────────────────
r = requests.post(f"{BASE}/api/aps/affect-order/paging",
    headers=headers(), json={"current": 1, "pageSize": 20})
check("受影响订单返回200", r.status_code == 200)
data = r.json()
check("statusCode=200", data.get("statusCode") == 200)
affect = data.get("data", {})
check("返回 data.data 列表", isinstance(affect.get("data"), list))
check("有受影响订单数据", len(affect.get("data", [])) > 0)

if affect.get("data"):
    o = affect["data"][0]
    for field in ["orderCode","materialCode","materialName","qty","deliveryDate",
                  "originalProductScheduleEndDate","productScheduleEndDate",
                  "affectDay","delayDay","isDelay"]:
        check(f"  字段 {field} 存在", field in o)

    # 验证业务逻辑
    for item in affect["data"]:
        if item.get("isDelay"):
            check(f"  {item['orderCode']} isDelay=true 时 delayDay>0",
                  item.get("delayDay", 0) > 0, f"delayDay={item.get('delayDay')}")
            break

    print(f"\n  受影响订单（共{affect['total']}条）：")
    delayed = [o for o in affect["data"] if o.get("isDelay")]
    not_delayed = [o for o in affect["data"] if not o.get("isDelay")]
    print(f"    延迟：{len(delayed)} 条 | 未延迟：{len(not_delayed)} 条")
    for item in sorted(delayed, key=lambda x: -(x.get("delayDay") or 0))[:3]:
        print(f"    {item['orderCode']} | 延迟{item['delayDay']}天 | {item['materialName']}")

# ─────────────────────────────────────────────
section("STEP 7 · 无 Token 访问测试")
# ─────────────────────────────────────────────
r = requests.post(f"{BASE}/api/aps/rush-order/paging",
    headers={"Content-Type": "application/json"},
    json={"current": 1, "pageSize": 10})
check("无 Token 返回 401", r.status_code == 401)

# ─────────────────────────────────────────────
section("📊 测试报告")
# ─────────────────────────────────────────────
total = len(results)
passed = sum(1 for _, ok in results if ok)
failed = total - passed
print(f"\n  总计：{total} 项  通过：{passed} {PASS}  失败：{failed} {FAIL if failed else ''}")
print(f"\n  {'🎉 全部通过！可以对接 AI服务工作流。' if failed == 0 else '⚠️ 有失败项，请检查服务。'}")
if failed:
    print("\n  失败项：")
    for name, ok in results:
        if not ok:
            print(f"    {FAIL} {name}")
