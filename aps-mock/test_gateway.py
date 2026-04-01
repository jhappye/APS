#!/usr/bin/env python3
"""
AI 网关服务 V2 · 测试脚本
完整流程：登录 → 触发评估 → 轮询 → 获取AI报告 → 业务问答
"""
import requests, time, json

BASE = "http://localhost:8001"
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
r = requests.get(f"{BASE}/health", timeout=5)
check("网关服务可访问", r.status_code == 200)
check("返回接口列表", "endpoints" in r.json())

# ─────────────────────────────────────────────
section("STEP 1 · 登录 POST /ai/login")
# ─────────────────────────────────────────────
r = requests.post(f"{BASE}/ai/login",
    json={"userName": "admin", "password": "admin123"})
check("登录返回200", r.status_code == 200)
data = r.json()
check("code=0", data.get("code") == 0, str(data.get("code")))
check("返回 token", bool(data.get("data", {}).get("token")))
check("返回 userId", bool(data.get("data", {}).get("userId")))
TOKEN = data.get("data", {}).get("token", "")
print(f"  token = {TOKEN[:30]}...")

r2 = requests.post(f"{BASE}/ai/login",
    json={"userName": "admin", "password": "wrong"})
check("错误密码返回错误", r2.json().get("code") != 0 or not r2.json().get("data", {}).get("token"))

# ─────────────────────────────────────────────
section("STEP 2 · 无 Token 访问被拒")
# ─────────────────────────────────────────────
r = requests.post(f"{BASE}/ai/chat",
    headers={"Content-Type": "application/json"},
    json={"message": "测试"})
check("无 Token 返回 401", r.status_code == 401)

# ─────────────────────────────────────────────
section("STEP 3 · 触发评估 POST /ai/rush-order/evaluate/start")
# ─────────────────────────────────────────────
r = requests.post(f"{BASE}/ai/rush-order/evaluate/start", headers=headers())
check("触发评估返回200", r.status_code == 200)
data = r.json()
check("code=0", data.get("code") == 0)
check("返回 taskId", bool(data.get("data", {}).get("taskId")))
TASK_ID = data.get("data", {}).get("taskId", "")
print(f"  taskId = {TASK_ID}")

# ─────────────────────────────────────────────
section("STEP 4 · 轮询评估状态 GET /ai/rush-order/evaluate/status/{taskId}")
# ─────────────────────────────────────────────
print("  轮询中，最多等待 15 秒...")
done = False
for i in range(6):
    time.sleep(3)
    r = requests.get(f"{BASE}/ai/rush-order/evaluate/status/{TASK_ID}", headers=headers())
    data = r.json()
    status = data.get("data", {}).get("status", "")
    msg = data.get("data", {}).get("message", "")
    print(f"  第{i+1}次轮询：status={status}  {msg}")
    if status == "completed":
        done = True
        break

check("评估在15秒内完成", done)
check("完成后状态为 completed", done)

# ─────────────────────────────────────────────
section("STEP 5 · 获取AI分析报告（阻塞）POST /ai/rush-order/evaluate/analyze/{taskId}")
# ─────────────────────────────────────────────
if done:
    r = requests.post(f"{BASE}/ai/rush-order/evaluate/analyze/{TASK_ID}",
        headers=headers(), timeout=120)
    check("获取AI报告返回200", r.status_code == 200, f"HTTP {r.status_code}")
    data = r.json()
    check("code=0", data.get("code") == 0)
    check("返回 answer", bool(data.get("data", {}).get("answer")))
    check("返回 conversationId", bool(data.get("data", {}).get("conversationId")))
    answer = data.get("data", {}).get("answer", "")
    CONV_ID = data.get("data", {}).get("conversationId", "")
    print(f"\n  AI报告前150字：{answer[:150]}...")
    print(f"  conversationId = {CONV_ID}")

# ─────────────────────────────────────────────
section("STEP 6 · 流式业务问答 POST /ai/chat/stream")
# ─────────────────────────────────────────────
print("  发送：最近有哪些缺料预警？（流式接收）")
r = requests.post(f"{BASE}/ai/chat/stream",
    headers=headers(),
    json={"message": "最近有哪些缺料预警？", "userId": "test_user", "conversationId": ""},
    stream=True, timeout=60)

check("流式接口返回200", r.status_code == 200)
check("Content-Type 是 SSE", "text/event-stream" in r.headers.get("Content-Type", ""))

chunks, done_event, error_event = [], None, None
for line in r.iter_lines():
    if not line: continue
    if isinstance(line, bytes): line = line.decode("utf-8")
    if not line.startswith("data: "): continue
    raw = line[6:]
    try:
        event = json.loads(raw)
        t = event.get("type")
        if t == "chunk":
            chunks.append(event.get("content", ""))
            print(event.get("content", ""), end="", flush=True)
        elif t == "done":
            done_event = event; print()
        elif t == "error":
            error_event = event; print(f"\n  错误：{event}")
    except Exception:
        pass

check("收到 chunk 事件", len(chunks) > 0, f"{len(chunks)} 个")
check("收到 done 事件", done_event is not None)
check("返回 conversationId", bool((done_event or {}).get("conversationId")))
check("无 error 事件", error_event is None)

# ─────────────────────────────────────────────
section("STEP 7 · 多轮追问（携带 conversationId）")
# ─────────────────────────────────────────────
if done_event:
    conv_id = done_event.get("conversationId", "")
    print(f"  追问（conversationId={conv_id[:20]}...）：哪个最紧急？")
    r2 = requests.post(f"{BASE}/ai/chat",
        headers=headers(),
        json={"message": "哪个最紧急？", "userId": "test_user", "conversationId": conv_id},
        timeout=60)
    check("追问返回200", r2.status_code == 200)
    data2 = r2.json()
    check("追问有答案", bool(data2.get("data", {}).get("answer")))
    check("conversationId 保持一致", data2.get("data", {}).get("conversationId") == conv_id,
          f"{data2.get('data',{}).get('conversationId', '')[:20]} == {conv_id[:20]}")
    print(f"\n  追问回答前100字：{data2.get('data',{}).get('answer','')[:100]}...")

# ─────────────────────────────────────────────
section("📊 测试报告")
# ─────────────────────────────────────────────
total = len(results)
passed = sum(1 for _, ok in results if ok)
failed = total - passed
print(f"\n  总计：{total} 项  通过：{passed} {PASS}  失败：{failed} {FAIL if failed else ''}")
print(f"\n  {'🎉 全部通过！网关服务 V2 可以交付客户使用。' if failed == 0 else '⚠️ 有失败项，请检查配置或 Dify 连接。'}")
if failed:
    for name, ok in results:
        if not ok: print(f"    {FAIL} {name}")
