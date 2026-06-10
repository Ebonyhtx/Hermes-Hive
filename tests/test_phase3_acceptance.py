"""
HIVE v4.1 Phase 3 acceptance tests
"""
import shutil
import sys, json, time, asyncio, socket, subprocess, threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_HAS_HERMES = shutil.which("hermes") is not None
if not _HAS_HERMES:
    print("\n⚠ Hermes CLI not found — Phase 3 tests requiring HTTP daemon will be skipped\n")

PASS, FAIL = 0, 0

def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1; print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1; print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

# ══════════════════════════════════════════════════════
# 1. Dashboard 模块
# ══════════════════════════════════════════════════════
print("--- 1. Dashboard 模块 ---")
from orchestrator.dashboard.events import broadcast_event, register_client, unregister_client, get_client_count
check("events.py 导入", True)
check("get_client_count=0", get_client_count() == 0)

from orchestrator.dashboard.server import dashboard_app, set_orchestrators_ref, get_app
check("server.py 导入", True)
check("dashboard_app 是 FastAPI", "FastAPI" in type(dashboard_app).__name__)

html = Path("orchestrator/dashboard/templates/dashboard.html").read_text()
check("dashboard.html 存在", len(html) > 1000)
check("dashboard.html 含 WebSocket", "WebSocket" in html)

# ══════════════════════════════════════════════════════
# 2. Dashboard HTTP 可达性
# ══════════════════════════════════════════════════════
print("\n--- 2. Dashboard HTTP ---")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()

proc = subprocess.Popen(
    [sys.executable, "-c", f"""
import sys; sys.path.insert(0, '.')
from orchestrator.dashboard.server import dashboard_app
import uvicorn
uvicorn.run(dashboard_app, host='127.0.0.1', port={port}, log_level='error')
"""],
    cwd=str(Path(__file__).resolve().parent.parent),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
time.sleep(2)

import urllib.request
try:
    resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/dashboard", timeout=5)
    body = resp.read().decode()
    check("Dashboard 200", resp.status == 200)
    check("含 HIVE 标题", "HIVE" in body)
    check("含 WebSocket JS", "WebSocket" in body)
except Exception as e:
    check("Dashboard 可访问", False, str(e))
finally:
    proc.terminate()
    try: proc.wait(timeout=3)
    except: proc.kill()

# ══════════════════════════════════════════════════════
# 3. memory_store.py
# ══════════════════════════════════════════════════════
print("\n--- 3. memory_store.py ---")
import tempfile
from orchestrator.infrastructure.memory_store import MemoryStore

with tempfile.TemporaryDirectory() as tmp:
    store = MemoryStore(store_path=Path(tmp) / "memory.json")
    check("MemoryStore 实例化", True)

    store.record_build("test_proj", {
        "tech_stack": {"language": "Python", "framework": "tkinter"},
        "deliverable": "exe",
        "description": "测试项目",
    }, success=True)
    check("record_build 成功", True)

    prefs = store.get_preferences()
    check("偏好含 Python", prefs.get("language", {}).get("Python", 0) >= 1)

    skills = store.get_skills()
    check("技能列表非空", len(skills) >= 1)

    stats = store.get_stats()
    check("stats 含 projects_count", "projects_count" in stats)
    check("stats 含 skills_count", "skills_count" in stats)

    store.clear()
    check("清空后 skills=0", len(store.get_skills()) == 0)

# ══════════════════════════════════════════════════════
# 4. hive_client.py
# ══════════════════════════════════════════════════════
print("\n--- 4. hive_client.py ---")
from orchestrator.hive_client import HiveClient, BuildResult
check("HiveClient 导入", True)
check("BuildResult 导入", True)

client = HiveClient(url=f"http://127.0.0.1:{port}")
check("HiveClient 实例化", True)
check("client.build 方法", hasattr(client, 'build'))
check("client.iterate 方法", hasattr(client, 'iterate'))
check("client.cancel 方法", hasattr(client, 'cancel'))
check("client.list_projects 方法", hasattr(client, 'list_projects'))
check("client.versions 方法", hasattr(client, 'versions'))
check("client.rollback 方法", hasattr(client, 'rollback'))
check("client.diff 方法", hasattr(client, 'diff'))
check("client.read_file 方法", hasattr(client, 'read_file'))
check("client.list_files 方法", hasattr(client, 'list_files'))
check("client.artifacts 方法", hasattr(client, 'artifacts'))

result = BuildResult({"session_id": "test", "status": "done", "version": 1})
check("BuildResult 属性", result.session_id == "test")
check("BuildResult 状态", result.status == "done")

# ══════════════════════════════════════════════════════
# 汇总
# ══════════════════════════════════════════════════════
print(f"\n{'='*60}")
total = PASS + FAIL
print(f"Phase 3 验收结果: 🟢 {PASS}/{total} 通过, ❌ {FAIL}/{total} 失败")
print(f"{'='*60}")
