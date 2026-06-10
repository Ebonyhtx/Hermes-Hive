"""
HIVE v4.1 Phase 1 acceptance tests — 8-state spec validation
"""
import asyncio
import shutil
import sys
import tempfile
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_HAS_HERMES = shutil.which("hermes") is not None
if not _HAS_HERMES:
    print("\n⚠ Hermes CLI not found — LLM-dependent tests skipped\n")

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1

# ═══ 1. machine.py ═══
print("\n--- 1. machine.py ---")
from orchestrator.machine import HiveMachine

m = HiveMachine()
check("initial idle", m.state == "idle")
transitions = [
    ("start_build", "translating"),
    ("brief_ready", "planning"),
    ("plan_ready", "executing"),
    ("code_ready", "testing"),
    ("delivery_ready", "done"),
]
for trigger, expected in transitions:
    getattr(m, trigger)()
    check(f"{trigger} -> {expected}", m.state == expected)

m.start_iteration()
check("iteration done->idle", m.state == "idle")
m.start_iteration()
check("iteration idle->translating", m.state == "translating")
m.cancel_build()
check("cancel", m.state == "cancelled")
m.reset()
m.start_build()
m.fail_build()
check("fail", m.state == "idle")
m2 = HiveMachine()
check("initial is_active=False", not m2.is_active)
m2.start_build()
check("building is_active=True", m2.is_active)

# ═══ 2. session_manager.py ═══
print("\n--- 2. session_manager.py ---")
from orchestrator.infrastructure.session_manager import SessionManager

for s in SessionManager.get_all_sessions():
    if "验收测试" in s["project_name"]:
        SessionManager.delete_project(s["project_name"])

s1 = SessionManager.create_session("验收测试")
check("create session", s1["created"])
SessionManager.update_state(s1["session_id"], "running", "executing")
got2 = SessionManager.get_session(s1["session_id"])
check("state update", got2["state"] == "executing")
s2 = SessionManager.create_session("验收测试")
check("dedup: no new session", not s2["created"])
check("dedup: same id", s2["session_id"] == s1["session_id"])
SessionManager.update_brief(s1["session_id"], {"test": True})
SessionManager.update_dag(s1["session_id"], {"tasks": []})
got3 = SessionManager.get_session(s1["session_id"])
check("brief update", got3.get("brief") is not None)
check("dag update", got3.get("dag") is not None)
SessionManager.create_version(s1["session_id"], 1, "v1")
SessionManager.create_version(s1["session_id"], 2, "v2")
check("versions count", len(SessionManager.get_versions(s1["session_id"])) == 2)
SessionManager.log_cost(s1["session_id"], "translating", tokens_in=100, cost_usd=0.02)
check("cost recorded", SessionManager.get_session(s1["session_id"])["total_cost_usd"] > 0)
SessionManager.delete_project("验收测试")
check("delete", SessionManager.get_session(s1["session_id"])["status"] == "deleted")

# ═══ async tests (version_manager doesn't need Hermes) ═══
async def run_async_tests():
    global PASS, FAIL
    from orchestrator.versioning.version_manager import VersionManager

    print("\n--- 9. version_manager.py ---")
    vm = VersionManager()
    with tempfile.TemporaryDirectory() as tmp:
        vm.projects_root = Path(tmp)
        src_dir = vm.projects_root / "source"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("print('hello')")
        (src_dir / "dist").mkdir()
        (src_dir / "dist" / "app.exe").write_text("")
        v1 = vm.create_version("test_proj", src_dir, brief={"name": "test"}, summary="v1")
        check("v1 created", v1 == 1)
        (src_dir / "main.py").write_text("print('hello v2')")
        v2 = vm.create_version("test_proj", src_dir, summary="v2")
        check("v2 created", v2 == 2)
        check("list 2 versions", len(vm.list_versions("test_proj")) == 2)
        rb = vm.rollback("test_proj", 1)
        check("rollback to v1", rb.get("status") == "success")

    if not _HAS_HERMES:
        print("⏭ LLM-dependent tests skipped (no Hermes CLI)")
        return

    from orchestrator.roles.arc import Architect
    from orchestrator.roles.planner import Planner, get_template
    from orchestrator.roles.coder import CoderPool
    from orchestrator.roles.tester import Tester
    from orchestrator.roles.reviewer import Reviewer
    from orchestrator.roles.toolman import Toolman

    print("\n--- 3. arc.py ---")
    arc = Architect()
    brief = await arc.translate("做一个极简计算器，Python tkinter")
    check("brief has project_name", "project_name" in brief)
    check("brief has features", "features" in brief)
    check("brief has tech_stack", "tech_stack" in brief)

    print("\n--- 4. planner.py ---")
    planner = Planner()
    dag = await planner.plan(brief)
    check("dag has tasks", "tasks" in dag and len(dag["tasks"]) >= 2)
    check("dag has tech_stack", "tech_stack" in dag)
    check("dag has delivery_template", "delivery_template" in dag)

    print("\n--- 5. coder.py ---")
    pool = CoderPool(max_workers=3)
    check("pool max_workers=3", pool.max_workers == 3)

    print("\n--- 6. tester.py ---")
    tester = Tester()
    with tempfile.TemporaryDirectory() as tmp:
        result = await tester.write_tests(
            {"features": [{"name": "calculation", "description": "add/subtract"}]},
            Path(tmp),
        )
        check("test files generated", result["test_count"] >= 1)

    print("\n--- 7. reviewer.py ---")
    reviewer = Reviewer()
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        src = ws / "src"
        src.mkdir()
        (src / "bad.py").write_text("def foo(:")
        report = await reviewer.review(ws, {"features": []}, version=0)
        check("L1 syntax error detected", report["layers"]["L1_syntax"]["status"] == "fail")

    print("\n--- 8. toolman.py ---")
    tm = Toolman()
    check("Toolman instantiated", tm is not None)
    dag_simple = {"tech_stack": "python-tkinter", "requirements": [],
                  "delivery_template": {"test_cmd": "echo ok", "build_cmd": "echo test",
                                        "artifact_ext": ".exe", "source_ext": [".py"]},
                  "tasks": []}
    with tempfile.TemporaryDirectory() as tmp:
        result = await tm.deliver(dag_simple, Path(tmp), "test", "python-tkinter")
        check("deliver returns dict", isinstance(result, dict))

asyncio.run(run_async_tests())

print(f"\n{'='*60}")
total = PASS + FAIL
print(f"Phase 1: {PASS}/{total} passed, {FAIL}/{total} failed")
print(f"{'='*60}")
