"""
⚠️ DEPRECATED — This module is kept for backward compatibility.

The main build pipeline uses:
  - orchestrator/hermes_bridge.py  (run_agent)
  - orchestrator/hermes_runner.py  (subprocess execution)
  - orchestrator/infrastructure/   (session, workspace management)

Workspace creation is now managed by HiveOrchestrator via ~/.hermes/hive-v4/builds/.
This file will be removed in v4.2.
"""
import subprocess
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import warnings
warnings.warn(
    "hermes_wrapper.py is deprecated. Use hermes_bridge.py and HiveOrchestrator instead.",
    DeprecationWarning,
    stacklevel=2,
)
import subprocess
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── 路径常量 ──────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
PROFILES_DIR = PROJECT_ROOT / "profiles"

def hive_data_dir() -> Path:
    """HIVE 数据目录 — 统一入口。~/.hermes/hive/ > HERMES_HOME/hive/ > PROJECT_ROOT"""
    from pathlib import Path as _P
    # 1) 默认 ~/.hermes/hive/
    new_home = _P.home() / ".hermes" / "hive"
    if new_home.exists():
        return new_home
    # 2) 用户设置的 HERMES_HOME/hive/
    hermes_home = os.environ.get("HERMES_HOME", "")
    if hermes_home:
        alt = _P(hermes_home) / "hive"
        if alt.exists():
            return alt
    # 3) 源码目录兜底
    return PROJECT_ROOT

WORKSPACES_DIR = hive_data_dir() / "workspaces"
TEMPLATE_DIR = WORKSPACES_DIR / "_template"


# ═══════════════════════════════════════════════════════
#  WORKSPACE 管理
# ═══════════════════════════════════════════════════════

def generate_session_id(mode: str = "dev") -> str:
    """生成 session ID：{mode}_{YYYYMMDD}_{HHMMSS}_{6位随机}"""
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    rand = os.urandom(3).hex()
    return f"{mode}_{stamp}_{rand}"


def create_workspace(session_id: str, project_name: str = "") -> str:
    """从模板创建 workspace"""
    ws_path = WORKSPACES_DIR / session_id
    if ws_path.exists():
        raise FileExistsError(f"Workspace {session_id} 已存在")

    # 复制模板（模板不存在时直接创建目录结构）
    if TEMPLATE_DIR.exists():
        shutil.copytree(TEMPLATE_DIR, ws_path)
    else:
        ws_path.mkdir(parents=True, exist_ok=True)

    # 确保必要目录存在
    for subdir in ["tasks", "results/toolman",
                   "results/reviewer", "results/final"]:
        (ws_path / subdir).mkdir(parents=True, exist_ok=True)

    # 初始化 _meta.json
    now = datetime.now().isoformat()
    meta = {
        "session_id": session_id,
        "mode": "development",
        "created_at": now,
        "status": "active",
        "project_name": project_name,
        "project_type": "",
        "agents_involved": ["architect", "planner", "toolman", "reviewer"],
        "files_created": 0,
        "last_activity": now,
    }
    write_json(ws_path / "_meta.json", meta)

    # 初始化 state/current.json
    state = {
        "session_id": session_id,
        "mode": "development",
        "user_request": "",
        "dag": [],
        "edges": [],
        "current_phase": "idle",
        "updated_at": now,
    }
    write_json(ws_path / "state" / "current.json", state)

    # 初始化 project_memory/_init.json
    write_json(ws_path / "project_memory" / "_init.json", {
        "initialized_at": now,
        "template_version": "1.0",
    })

    # Git init src/（git 不可用时静默跳过）
    try:
        subprocess.run(["git", "init"], cwd=str(ws_path / "src"),
                       capture_output=True, timeout=5)
    except Exception:
        pass

    # 审计日志首行
    append_audit(ws_path, {
        "timestamp": now,
        "event": "workspace_created",
        "actor": "orchestrator",
        "detail": f"项目: {project_name}",
    })

    return str(ws_path)


def workspace_path(session_id: str) -> Path:
    return WORKSPACES_DIR / session_id


def read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict):
    """写 JSON 文件（自动创建目录）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_audit(ws_path: Path, entry: dict):
    """追加审计日志条目到 workspace 的 audit log。"""
    audit_dir = ws_path / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    log_file = audit_dir / "audit.log"
    line = json.dumps(entry, ensure_ascii=False)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ═══════════════════════════════════════════════════════
#  HERMES AGENT 管理
# ═══════════════════════════════════════════════════════

def _find_hermes_python() -> str:
    """Find Hermes venv Python interpreter (cross-platform)"""
    import sys as _sys
    # 1) If already inside a Hermes venv, use current Python
    if hasattr(_sys, 'real_prefix') or (hasattr(_sys, 'base_prefix') and _sys.base_prefix != _sys.prefix):
        return _sys.executable
    # 2) Search common Hermes install locations
    from pathlib import Path as _P
    hermes_home = _P(os.environ.get("HERMES_HOME", "."))
    search_dirs = [_P.home() / ".hermes"]
    if hermes_home != _P("."):
        search_dirs.append(hermes_home)
    for base in search_dirs:
        for venv_py in [
            base / "venv" / "Scripts" / "python.exe",  # Windows
            base / "venv" / "bin" / "python",           # Unix
            base / "hermes-agent" / "venv" / "Scripts" / "python.exe",
            base / "hermes-agent" / "venv" / "bin" / "python",
        ]:
            if venv_py.exists():
                return str(venv_py)
    # 3) Fallback: system Python
    return _sys.executable

def run_agent_and_get_response(profile: str, prompt: str, timeout: int = 120, max_retries: int = 3, workdir: str = "") -> str:
    """启动 Hermes Agent 并获取回复文本（含重试）

    全部 LLM 调用通过 hermes_bridge → hermes_runner → hermes chat -q。
    """
    from orchestrator.hermes_bridge import run_agent as _bridge

    last_error = ""
    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait = 2 ** attempt
            print(f"  🔄 重试 {attempt}/{max_retries}（{wait}s 后）...", flush=True)
            time.sleep(wait)

        try:
            result = _bridge(profile, prompt, timeout=timeout, workdir=workdir)
            if result.startswith("[Agent 错误]") or result.startswith("[超时]"):
                last_error = result
                if attempt < max_retries:
                    continue
                return result
            return result
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                continue
            return f"[Agent 错误] {e}"

    return last_error or "[Agent 失败] 未知错误"
