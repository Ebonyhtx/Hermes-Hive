"""
单元测试：errors, validator, memory_store
"""
import sys, json, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS, FAIL = 0, 0
def check(name, ok, detail=""):
    global PASS, FAIL
    if ok: PASS += 1; print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else: FAIL += 1; print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

# ── errors ──
print("--- errors.py ---")
from orchestrator.infrastructure.errors import ok, error, is_ok, ERROR_CODES

check("ok() 返回格式", ok("data") == {"status": "ok", "data": "data"})
check("error() 返回格式", error("SESSION_NOT_FOUND")["status"] == "error")
check("error() 含错误码", error("SESSION_NOT_FOUND")["error"]["code"] == "E001")
check("is_ok 判断正确", is_ok(ok()) == True and is_ok(error("UNKNOWN_ERROR")) == False)
check("13 个错误码", len(ERROR_CODES) == 13)
check("E001 存在", "SESSION_NOT_FOUND" in ERROR_CODES)
check("E999 存在", "UNKNOWN_ERROR" in ERROR_CODES)
check("E007 含 confirm 提示", "confirm=True" in ERROR_CODES["DELETE_CONFIRM_REQUIRED"]["message"])

# ── validator ──
print("\n--- validator.py ---")
from orchestrator.infrastructure.validator import validate_brief, validate_dag, validate_review, safe_validate, ValidationError

# brief 验证
brief_ok = {"project_name": "test", "description": "desc", "features": [{"name": "f1", "priority": "P0", "description": "d"}],
            "tech_stack": {"language": "Python", "framework": "tkinter", "os": "windows"}, "deliverable": "exe"}
try:
    w = validate_brief(brief_ok)
    check("brief 合法无警告", len(w) == 0)
except ValidationError:
    check("brief 合法无警告", False)

try:
    validate_brief({})
    check("brief 缺字段抛异常", False, "未抛出")
except ValidationError:
    check("brief 缺字段抛异常", True)

sr = safe_validate(brief=brief_ok)
check("safe_validate 无错误", sr["valid"] == True)

# 无效 deliverable
brief_bad = dict(brief_ok, deliverable="wheel")
w2 = validate_brief(brief_bad)
check("无效 deliverable 警告", any("wheel" in w for w in w2))

# dag 验证
dag_ok = {"tasks": [{"id": "T1", "title": "t1", "layer": 1, "deps": [], "type": "code", "assign_to": "coder"}],
          "tech_stack": "python-tkinter", "delivery_template": {}}
try:
    w3 = validate_dag(dag_ok)
    check("dag 合法无警告", len(w3) == 0)
except ValidationError:
    check("dag 合法无警告", False)

# dag 重复 id
dag_bad = {"tasks": [{"id": "T1", "layer": 1, "type": "code"}, {"id": "T1", "layer": 1, "type": "code"}]}
try:
    validate_dag(dag_bad)
    check("重复 id 抛异常", False)
except ValidationError:
    check("重复 id 抛异常", True)

# review 验证
review_ok = {"layers": {"L1_syntax": {}, "L2_brief_alignment": {}, "L3_security": {}, "L4_consistency": {}},
             "overall": "pass", "summary": "ok"}
w4 = validate_review(review_ok)
check("review 合法无警告", len(w4) == 0)

# ── memory_store ──
print("\n--- memory_store.py ---")
from orchestrator.infrastructure.memory_store import MemoryStore

with tempfile.TemporaryDirectory() as tmp:
    store = MemoryStore(store_path=Path(tmp) / "mem.json")
    check("初始化空", len(store.get_skills()) == 0)

    store.record_build("proj1", {"tech_stack": {"language": "Python"}, "deliverable": "exe", "description": "d1"})
    prefs = store.get_preferences()
    check("偏好含 Python", "Python" in str(prefs))

    skills = store.get_skills()
    check("1 条技能", len(skills) == 1)

    store.record_build("proj2", {"tech_stack": {"language": "Rust"}, "deliverable": "cli", "description": "d2"})
    check("2 条技能", len(store.get_skills()) == 2)

    stats = store.get_stats()
    check("stats 含 projects_count", stats["projects_count"] == 2)

    store.clear()
    check("清空后 0 条", len(store.get_skills()) == 0)

# ── 汇总 ──
print(f"\n{'='*50}")
total = PASS + FAIL
print(f"单元测试结果: 🟢 {PASS}/{total} 通过, ❌ {FAIL}/{total} 失败")
print(f"{'='*50}")
