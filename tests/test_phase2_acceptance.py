"""
HIVE v4.1 Phase 2 acceptance tests — mcp_server + dashboard
"""
import asyncio
import shutil
import sys, tempfile, json, time, threading, socket
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_HAS_HERMES = shutil.which("hermes") is not None
if not _HAS_HERMES:
    print("\n⚠ Hermes CLI not found — Phase 2 tests requiring HTTP daemon will be skipped\n")

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

# ══════════════════════════════════════════════════════
# 1. version_manager.py — async 方法用 asyncio.run
# ══════════════════════════════════════════════════════
print("--- 1. version_manager.py ---")
from orchestrator.versioning.version_manager import VersionManager

vm = VersionManager()
vm.projects_root = Path(tempfile.gettempdir()) / f"hive_test_{int(time.time())}"
vm.projects_root.mkdir(parents=True, exist_ok=True)

async def test_version_symlink():
    import shutil as _shutil
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        src_dir = project_dir / "source"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("v1")
        (src_dir / "dist").mkdir()
        (src_dir / "dist" / "app.exe").write_text("")

        v1 = vm.create_version("symlink_test", src_dir, summary="v1")
        check("v1=1 创建", v1 == 1)

        (src_dir / "main.py").write_text("v2")
        v2 = vm.create_version("symlink_test", src_dir, summary="v2")
        check("v2=2 创建", v2 == 2)

        proj_dir = Path(vm.projects_root) / "symlink_test"
        current = vm._current_version(proj_dir)
        check(f"current 指向 v{v2}", current == 2)

        rb = vm.rollback("symlink_test", 1)
        check("回滚成功", rb.get("status") == "success")
        check("回滚后 current=v1", rb.get("current_version") == 1)

        current2 = vm._current_version(proj_dir)
        check(f"current symlink 指向 v1", current2 == 1)

asyncio.run(test_version_symlink())

# ══════════════════════════════════════════════════════
# 2. mcp_server.py — 工具注册 + 启动 + Dashboard
# ══════════════════════════════════════════════════════
print("\n--- 2. mcp_server.py: 工具注册 ---")
from orchestrator.mcp_server import mcp

tools = mcp._tool_manager.list_tools()
tool_names = [t.name for t in tools]

required_tools = [
    "hive_build", "hive_iterate", "hive_rollback", "hive_versions",
    "hive_diff", "hive_status", "hive_ls", "hive_read", "hive_artifact",
    "hive_cancel", "hive_list_projects", "hive_delete_project",
    "hive_dashboard_url", "hive_memory",
]
for name in required_tools:
    check(f"工具已注册: {name}", name in tool_names)

check("工具总数 >= 13", len(tools) >= 13, f"{len(tools)} 个")

# ══════════════════════════════════════════════════════
# 3. 启动 MCP Server 验证 HTTP 可达
# ══════════════════════════════════════════════════════
print("\n--- 3. mcp_server.py: HTTP daemon ---")

# 找个可用端口
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()

# 用短超时启动 server 并请求 dashboard
import subprocess
server_proc = subprocess.Popen(
    [sys.executable, "-c", f"""
import sys; sys.path.insert(0, '.')
from orchestrator.mcp_server import dashboard_app
import uvicorn
uvicorn.run(dashboard_app, host='127.0.0.1', port={port}, log_level='error')
"""],
    cwd=str(Path(__file__).resolve().parent.parent),
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

# 等它启动
time.sleep(2)

import urllib.request
try:
    resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/dashboard", timeout=5)
    html = resp.read().decode()
    check("Dashboard 返回 200", resp.status == 200)
    check("Dashboard 含 HIVE 标题", "HIVE" in html or "hive" in html.lower())
    check("Dashboard 含 WebSocket 代码", "WebSocket" in html or "websocket" in html.lower())
except Exception as e:
    check("Dashboard 可访问", False, str(e))
finally:
    server_proc.terminate()
    try:
        server_proc.wait(timeout=3)
    except:
        server_proc.kill()

# ══════════════════════════════════════════════════════
# 4. hive.json 配置验证
# ══════════════════════════════════════════════════════
print("\n--- 4. hive.json 配置 ---")
config = json.loads(Path("hive.json").read_text())
check("配置含 version", "version" in config)
check("配置含 mcp_port=8421", config.get("mcp_port") == 8421)
check("配置含 max_workers=3", config.get("max_workers") == 3)

# ══════════════════════════════════════════════════════
# 汇总
# ══════════════════════════════════════════════════════
print(f"\n{'='*60}")
total = PASS + FAIL
print(f"Phase 2 验收结果: 🟢 {PASS}/{total} 通过, ❌ {FAIL}/{total} 失败")
print(f"{'='*60}")
