"""
边界测试：machine 边缘情况 + validator 边界
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS, FAIL = 0, 0
def check(name, ok, detail=""):
    global PASS, FAIL
    if ok: PASS += 1; print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else: FAIL += 1; print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

# ── machine: 边缘情况 ──
print("--- machine.py 边缘测试 ---")
from orchestrator.machine import HiveMachine

m = HiveMachine()
check("初始 idle", m.state == "idle")
check("初始 is_active=False", not m.is_active)

# 无效转换不抛异常
m.cancel_build()  # idle → cancelled (valid via *)
check("取消从 idle 可用", m.state == "cancelled")

m.reset()
check("reset 回到 idle", m.state == "idle")

# 完整路径两次
for _ in range(2):
    m.start_build()
    m.brief_ready()
    m.plan_ready()
    m.code_ready()
    m.delivery_ready()
    m.start_iteration()
check("完整路径循环 2 次", m.state == "idle")
check("历史记录 > 0", len(m.history) > 0)

# 直接从 idle 取消 → 再从 cancelled reset → 正常构建
m.reset()
m.start_build()
m.cancel_build()
m.reset()
m.start_build()
check("cancelled→reset→构建", m.state == "translating")

# ── validator: 边界 ──
print("\n--- validator.py 边界测试 ---")
from orchestrator.infrastructure.validator import validate_brief, validate_dag, safe_validate, ValidationError

# 空 brief
try:
    validate_brief({})
    check("空 brief 抛异常", False)
except ValidationError:
    check("空 brief 抛异常", True)

# features 是字符串而非数组
try:
    validate_brief({"project_name":"t","description":"d","features":"bad","tech_stack":{"language":"Python"},"deliverable":"exe"})
    check("非数组 features 抛异常", False)
except ValidationError:
    check("非数组 features 抛异常", True)

# 空 dag
try:
    validate_dag({})
    check("空 dag 抛异常", False)
except ValidationError:
    check("空 dag 抛异常", True)

# 完整验证通过的场景
w = safe_validate(
    brief={"project_name":"t","description":"d","features":[],"tech_stack":{"language":"Python","framework":"tkinter","os":"windows"},"deliverable":"exe"},
)
check("最小合法 brief", w["valid"] and len(w["warnings"]) == 0)

# brief 缺 tech_stack.os
w2 = safe_validate(
    brief={"project_name":"t","description":"d","features":[],"tech_stack":{"language":"Python"},"deliverable":"exe"},
)
check("缺 framework 有警告", any("framework" in x for x in w2["warnings"]))

# review 缺层
from orchestrator.infrastructure.validator import validate_review
w3 = validate_review({"layers": {}, "overall": "pass"})
check("review 缺 L1 有警告", any("L1" in x for x in w3))

# ── errors: 边界 ──
print("\n--- errors.py 边界测试 ---")
from orchestrator.infrastructure.errors import ok, error, is_ok, ERROR_CODES

check("ok(None) 格式正确", ok(None) == {"status": "ok", "data": None})
check("error 未知 key", error("NONEXISTENT")["error"]["code"] == "E999")
check("error 带自定义 message", "custom" in error("E001", "custom")["error"]["message"])

# 所有错误码都有唯一 code
codes = [v["code"] for v in ERROR_CODES.values()]
check("错误码唯一", len(codes) == len(set(codes)))
check("所有错误码 E001-E999 格式", all(c.startswith("E") and c[1:].isdigit() for c in codes))

print(f"\n{'='*50}")
total = PASS + FAIL
print(f"边界测试: 🟢 {PASS}/{total} 通过, ❌ {FAIL}/{total} 失败")
print(f"{'='*50}")
