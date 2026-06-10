"""
HIVE v4.1 — MCP Server 入口 + HTTP Daemon

注册 14 个 MCP 工具，启动 HTTP 持久化服务器。
Dashboard 看板通过 custom_route 注册在 MCP Server 上。
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# MCP
from mcp.server.fastmcp import FastMCP

# HIVE Core
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.orchestrator import HiveOrchestrator
from orchestrator.infrastructure.session_manager import SessionManager
from orchestrator.infrastructure.cost_tracker import CostTracker
from orchestrator.infrastructure.errors import ok, error, ERROR_CODES
from orchestrator.versioning.version_manager import VersionManager

# Dashboard 模块
from orchestrator.dashboard.events import broadcast_event, register_client, unregister_client, get_client_count
# dashboard_app 在本模块中定义（FastAPI + WebSocket + MCP mount）


# ── HTML 模板缓存 ──

_TEMPLATE_PATH = Path(__file__).parent / "dashboard" / "templates" / "dashboard.html"

def _load_dashboard_html() -> str:
    """读取 dashboard.html 模板。"""
    if _TEMPLATE_PATH.exists():
        return _TEMPLATE_PATH.read_text(encoding="utf-8")
    return "<h1>Dashboard 模板未找到</h1>"

_HTML_CACHE = _load_dashboard_html()

# ── 全局状态 ──

_ACTIVE_ORCHESTRATORS: dict[str, HiveOrchestrator] = {}
_cost_tracker = CostTracker()
_version_manager = VersionManager()


# ── Orchestrator 生命周期管理 ──

async def _run_orch_with_cleanup(orchestrator: HiveOrchestrator, description: str, lang: str):
    """运行 build 并在完成后清理内存。"""
    try:
        await orchestrator.build(description, lang)
    finally:
        _ACTIVE_ORCHESTRATORS.pop(orchestrator.session_id, None)


async def _run_iter_with_cleanup(orchestrator: HiveOrchestrator, request: str):
    """运行 iterate 并在完成后清理内存。"""
    try:
        await orchestrator.iterate(request)
    finally:
        _ACTIVE_ORCHESTRATORS.pop(orchestrator.session_id, None)


# ── MCP Server 配置 ──

mcp = FastMCP("hive-v4")
# 无状态 JSON 模式
mcp.settings.stateless_http = True
mcp.settings.json_response = True

# ── 将所有 Dashboard 路由添加到 MCP 的 Starlette App ──

from starlette.responses import HTMLResponse, JSONResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

# 获取 streamable HTTP app 的引用
_mcp_asgi = mcp.streamable_http_app()

# ── Dashboard 页面 ──
async def dashboard_page(request):
    return HTMLResponse(_HTML_CACHE)

# ── API 状态 ──
async def api_status(request):
    all_sessions = SessionManager.get_all_sessions()
    return JSONResponse({"projects": all_sessions})

# ── API 会话详情 ──
async def api_session_detail(request):
    session_id = request.path_params.get("session_id", "")
    session = SessionManager.get_session(session_id)
    if not session:
        return JSONResponse({"error": "session 未找到"}, status_code=404)
    error_msg = SessionManager.get_error(session_id) or ""
    if error_msg:
        session["error_message"] = error_msg
    return JSONResponse(session)

# ── API 取消 ──
async def api_cancel(request):
    session_id = request.path_params.get("session_id", "")
    if session_id in _ACTIVE_ORCHESTRATORS:
        result = _ACTIVE_ORCHESTRATORS[session_id].cancel()
        result["message"] = f"构建已取消 (session {session_id})"
        return JSONResponse(result)
    return JSONResponse({"status": "error", "message": "session 未找到"})

# ── API 构建 ──
async def api_build(request):
    qs = request.query_params
    description = qs.get("description", "")
    lang = qs.get("lang", "en")
    if not description:
        return JSONResponse({"status": "info", "usage": "/api/build?description=your+requirements&lang=en"})
    project_name = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", description)[:20]
    session = SessionManager.create_session(project_name)
    session_id = session["session_id"]
    orch = HiveOrchestrator(session_id=session_id, project_name=project_name)
    _ACTIVE_ORCHESTRATORS[session_id] = orch
    asyncio.create_task(orch.build(description, lang))
    return JSONResponse({
        "session_id": session_id, "project_name": project_name,
        "status": "started", "dashboard_url": f"http://127.0.0.1:8421/dashboard",
    })

# ── API 项目列表 ──
async def api_projects(request):
    sessions = SessionManager.get_all_sessions()
    projects = {}
    for s in sessions:
        status = s.get("status", "idle")
        # 过滤已删除/已取消的 session
        if status in ("deleted", "cancelled"):
            continue
        name = s["project_name"]
        if not name:
            continue
        # 多个同名 session 只保留最新的
        if name not in projects or s.get("updated_at", "") > projects[name].get("last_activity", ""):
            projects[name] = {
                "name": name,
                "status": status,
                "state": s.get("state", "idle"),
                "version_count": s.get("current_version", 0),
                "last_activity": s.get("updated_at", ""),
                "session_id": s["session_id"],
                "total_cost_usd": s.get("total_cost_usd", 0),
            }
    sorted_projects = sorted(projects.values(), key=lambda p: p["last_activity"], reverse=True)
    return JSONResponse({"projects": sorted_projects})

# ── API 删除项目 — 硬删所有同名 session ──
async def api_delete_project(request):
    project_name = request.path_params.get("project_name", "")
    if not project_name:
        return JSONResponse({"status": "error", "message": "需要 project_name"})
    deleted = SessionManager.delete_project(project_name)
    msg = f"项目 '{project_name}' 已{'删除' if deleted else '未找到'}"
    return JSONResponse({"status": "ok" if deleted else "error", "message": msg})

# ── API 上传需求文档 ──
async def api_upload(request):
    """上传文件作为构建需求。支持 .txt/.md/.pdf 等文本文件。"""
    from starlette.datastructures import UploadFile
    try:
        form = await request.form()
        file_field = form.get("file")
        if not file_field or not isinstance(file_field, UploadFile):
            return JSONResponse({"status": "error", "message": "请上传文件"}, status_code=400)
        content_bytes = await file_field.read()
        # 尝试用 utf-8 解码
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content = content_bytes.decode("utf-8", errors="replace")
        # 取文件名作为项目名参考
        filename = file_field.filename or "未命名文档"
        # 限制大小 1MB
        if len(content) > 1_000_000:
            return JSONResponse({"status": "error", "message": "文件过大，请控制在 1MB 以内"}, status_code=400)
        # 直接启动构建
        description = f"[来自文件: {filename}]\n{content[:5000]}"
        project_name = filename.rsplit(".", 1)[0][:40]
        session = SessionManager.create_session(project_name)
        session_id = session["session_id"]
        orch = HiveOrchestrator(session_id=session_id, project_name=project_name)
        _ACTIVE_ORCHESTRATORS[session_id] = orch
        asyncio.create_task(_run_orch_with_cleanup(orch, description, "zh"))
        return JSONResponse({
            "session_id": session_id, "project_name": project_name,
            "status": "started", "filename": filename,
            "dashboard_url": "http://127.0.0.1:8421/dashboard",
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"上传处理失败: {str(e)}"}, status_code=500)


# ── API 文件树浏览 ──
async def api_tree(request):
    """递归列出 session 的文件树。"""
    session_id = request.query_params.get("session_id", "")
    if not session_id:
        return JSONResponse({"status": "error", "message": "需要 session_id"}, status_code=400)
    base = _resolve_path(session_id=session_id)
    if not base:
        return JSONResponse({"status": "error", "message": "路径不存在"}, status_code=404)
    tree = _build_file_tree(base)
    return JSONResponse({"tree": tree})


def _build_file_tree(dir_path: Path) -> list:
    """递归构建文件树结构。"""
    items = []
    for child in sorted(dir_path.iterdir()):
        entry = {"name": child.name, "type": "dir" if child.is_dir() else "file"}
        if child.is_dir():
            entry["children"] = _build_file_tree(child)
        else:
            entry["size"] = child.stat().st_size
            entry["ext"] = child.suffix
        items.append(entry)
    return items


# ── API 读取文件内容 ──
async def api_read(request):
    """读取 session 工作区的文件内容。"""
    session_id = request.query_params.get("session_id", "")
    path = request.query_params.get("path", "")
    offset = int(request.query_params.get("offset", "1"))
    limit = int(request.query_params.get("limit", "5000"))
    if not session_id or not path:
        return JSONResponse({"status": "error", "message": "需要 session_id 和 path"}, status_code=400)
    base = _resolve_path(session_id=session_id)
    if not base:
        return JSONResponse({"status": "error", "message": "路径不存在"}, status_code=404)
    file_path = base / path
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse({"status": "error", "message": f"文件不存在: {path}"}, status_code=404)
    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)
    sliced = lines[max(0, offset - 1):min(total, offset - 1 + limit)]
    return JSONResponse({
        "data": {"content": "\n".join(sliced), "total_lines": total, "file_size": file_path.stat().st_size}
    })


# ── API 成品列表（增强版：多位置检测） ──
async def api_artifact(request):
    """获取构建成品文件。"""
    session_id = request.query_params.get("session_id", "")
    if not session_id:
        return JSONResponse({"status": "error", "message": "需要 session_id"}, status_code=400)
    base = _resolve_path(session_id=session_id)
    if not base:
        return JSONResponse({"status": "error", "message": "路径不存在"}, status_code=404)

    artifact_dirs = [base / "dist",  base / "build" / "app" / "outputs" / "flutter-apk", base / "target" / "release"]
    seen = set()
    arts = []

    def add_arts(d):
        if d.exists():
            for f in d.iterdir():
                if f.is_file():
                    fp = str(f.resolve())
                    if fp not in seen:
                        seen.add(fp)
                        arts.append({"name": f.name, "path": str(f), "size": f.stat().st_size, "type": f.suffix})

    for d in artifact_dirs:
        add_arts(d)

    # 兜底：找根目录的大文件
    if not arts:
        for f in base.iterdir():
            if f.is_file() and f.stat().st_size > 100 and f.suffix not in (".pyc",):
                fp = str(f.resolve())
                if fp not in seen:
                    seen.add(fp)
                    arts.append({"name": f.name, "path": str(f), "size": f.stat().st_size, "type": f.suffix})

    return JSONResponse({"data": {"artifacts": arts[:50]}})


# ── API 工作区信息（显示真实磁盘路径） ──
async def api_workspace(request):
    """显示 session 工作区的真实磁盘路径和文件统计。"""
    session_id = request.query_params.get("session_id", "")
    if not session_id:
        return JSONResponse({"status": "error", "message": "需要 session_id"}, status_code=400)
    base = _resolve_path(session_id=session_id)
    if not base:
        return JSONResponse({"status": "error", "message": "路径不存在"}, status_code=404)
    total_files = sum(1 for f in base.rglob("*") if f.is_file())
    total_size = sum(f.stat().st_size for f in base.rglob("*") if f.is_file())
    return JSONResponse({
        "path": str(base.resolve()),
        "total_files": total_files,
        "total_size": total_size,
        "total_size_str": f"{total_size/1024:.0f}KB" if total_size < 1048576 else f"{total_size/1048576:.1f}MB",
    })


# ── API 清理工作区 ──
async def api_clean(request):
    """清理 session 工作区中的 __pycache__ 和 .pyc 文件。"""
    session_id = request.query_params.get("session_id", "")
    action = request.query_params.get("action", "dry_run")
    if not session_id:
        return JSONResponse({"status": "error", "message": "需要 session_id"}, status_code=400)
    base = _resolve_path(session_id=session_id)
    if not base:
        return JSONResponse({"status": "error", "message": "路径不存在"}, status_code=404)

    import shutil
    cleaned_dirs, cleaned_files, freed = 0, 0, 0
    delete_it = (action == "execute")

    for root, dirs, files in os.walk(str(base), topdown=True):
        for d in list(dirs):
            if d == "__pycache__":
                full = Path(root) / d
                sz = sum(f.stat().st_size for f in full.rglob("*") if f.is_file())
                if delete_it:
                    shutil.rmtree(full, ignore_errors=True)
                cleaned_dirs += 1; freed += sz
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                full = Path(root) / f
                if delete_it:
                    full.unlink(missing_ok=True)
                cleaned_files += 1; freed += full.stat().st_size if full.exists() else 0

    return JSONResponse({
        "action": action, "dirs_removed": cleaned_dirs, "files_removed": cleaned_files,
        "freed_bytes": freed, "freed_str": f"{freed/1024:.0f}KB" if freed < 1048576 else f"{freed/1048576:.1f}MB",
    })


# ── WebSocket ──
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    await register_client(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        await unregister_client(websocket)
    except Exception:
        await unregister_client(websocket)

# 注册所有路由（使用 Starlette 官方 API）
_mcp_asgi.router.add_route("/dashboard", dashboard_page)
_mcp_asgi.router.add_route("/api/status", api_status)
_mcp_asgi.router.add_route("/api/session/{session_id}", api_session_detail)
_mcp_asgi.router.add_route("/api/cancel/{session_id}", api_cancel)
_mcp_asgi.router.add_route("/api/build", api_build)
_mcp_asgi.router.add_route("/api/projects", api_projects)
_mcp_asgi.router.add_route("/api/delete/{project_name}", api_delete_project)
_mcp_asgi.router.add_route("/api/upload", api_upload, methods=["POST"])
_mcp_asgi.router.add_route("/api/tree", api_tree)
_mcp_asgi.router.add_route("/api/read", api_read)
_mcp_asgi.router.add_route("/api/artifact", api_artifact)
_mcp_asgi.router.add_route("/api/workspace", api_workspace)
_mcp_asgi.router.add_route("/api/clean", api_clean)
_mcp_asgi.router.add_websocket_route("/ws", ws_endpoint)


# ── 工具定义 ──

@mcp.tool()
async def hive_build(
    description: str,
    lang: str = "zh",
) -> dict:
    """启动新构建。一句话触发完整管线。"""
    project_name = _extract_name(description)
    session = SessionManager.create_session(project_name)
    session_id = session["session_id"]

    if not session["created"]:
        return ok({
            "session_id": session_id,
            "project_name": project_name,
            "status": "existing",
            "message": f"项目 '{project_name}' 已有活跃 session，使用现有会话",
            "dashboard_url": f"http://127.0.0.1:8421/dashboard",
        })

    orchestrator = HiveOrchestrator(
        session_id=session_id, project_name=project_name, max_workers=3)
    _ACTIVE_ORCHESTRATORS[session_id] = orchestrator

    asyncio.create_task(_run_orch_with_cleanup(orchestrator, description, lang))

    return ok({
        "session_id": session_id,
        "project_name": project_name,
        "status": "started",
        "message": f"构建 '{project_name}' 已启动",
        "dashboard_url": f"http://127.0.0.1:8421/dashboard",
    })


@mcp.tool()
async def hive_iterate(session_id: str, request: str) -> dict:
    """对已有项目做迭代修改。"""
    if session_id not in _ACTIVE_ORCHESTRATORS:
        return error("SESSION_NOT_FOUND", f"session {session_id} 未找到")
    orch = _ACTIVE_ORCHESTRATORS[session_id]
    asyncio.create_task(_run_iter_with_cleanup(orch, request))
    return ok({"session_id": session_id, "status": "started", "message": "迭代修改已启动"})


@mcp.tool()
async def hive_rollback(session_id: str, version: int) -> dict:
    """回滚到指定版本。"""
    session = SessionManager.get_session(session_id)
    if not session:
        return error("SESSION_NOT_FOUND", f"session {session_id} 不存在")
    result = _version_manager.rollback(session["project_name"], version)
    if result["status"] == "success":
        SessionManager.rollback_version(session_id, version)
    return ok(result) if result.get("status") == "success" else result


@mcp.tool()
async def hive_versions(session_id: str) -> dict:
    """列出所有版本。"""
    session = SessionManager.get_session(session_id)
    if not session:
        return error("SESSION_NOT_FOUND", f"session {session_id} 不存在")
    versions = _version_manager.list_versions(session["project_name"])
    return ok({"versions": versions})


@mcp.tool()
async def hive_diff(session_id: str, v1: int, v2: int) -> dict:
    """对比两个版本间的文件差异。"""
    session = SessionManager.get_session(session_id)
    if not session:
        return error("SESSION_NOT_FOUND", f"session {session_id} 不存在")
    return ok(_version_manager.diff(session["project_name"], v1, v2))


@mcp.tool()
async def hive_status(session_id: str = "") -> dict:
    """查询进度。不传 session_id 则返回全部活跃 session。"""
    if session_id:
        session = SessionManager.get_session(session_id)
        if not session:
            return error("SESSION_NOT_FOUND", f"session {session_id} 不存在")
        return ok({
            "session_id": session_id,
            "project_name": session["project_name"],
            "state": session["state"],
            "status": session["status"],
            "version": session["current_version"],
            "progress_pct": _calc_progress(session.get("state", "idle")),
            "phase_eta_s": _calc_eta(session.get("state", "idle")),
            "error_message": SessionManager.get_error(session_id) or "",
        })

    all_sessions = SessionManager.get_all_sessions()
    active = [s for s in all_sessions if s["status"] not in ("cancelled", "deleted", "done")]
    return ok({"sessions": active})


@mcp.tool()
async def hive_install_sdk(tech_stack: str = "flutter") -> dict:
    """手动安装指定技术栈的 SDK（当前支持 flutter）。安装后可在构建中使用。"""
    from orchestrator.roles.toolman import Toolman
    tm = Toolman()

    prereq = tm._check_prerequisites(tech_stack)
    if not prereq["missing"]:
        return ok({"message": f"{tech_stack} 所需工具已就绪", "found": prereq["found"]})

    result = tm._auto_install_sdk(tech_stack, prereq["missing"])
    if result["success"]:
        return ok({"message": f"{tech_stack} SDK 安装完成", "path": result.get("path", "")})
    return error("SDK_INSTALL_FAILED", result.get("error", f"安装 {tech_stack} SDK 失败"))


def _file_info(f: Path) -> dict:
    """生成文件信息字典。"""
    stat = f.stat()
    return {
        "name": f.name,
        "type": "dir" if f.is_dir() else "file",
        "size": stat.st_size if f.is_file() else 0,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


@mcp.tool()
async def hive_ls(path: str = "", session_id: str = "", project_name: str = "") -> dict:
    """浏览文件。支持按 session_id 或 project_name。"""
    base = _resolve_path(session_id, project_name)
    if not base:
        return error("PROJECT_NOT_FOUND", "请提供 session_id 或 project_name")
    target = base / path if path else base
    if not target.exists():
        return error("PROJECT_NOT_FOUND", f"路径不存在: {target}")
    if target.is_file():
        return ok({"files": [_file_info(target)]})
    files = [_file_info(f) for f in sorted(target.iterdir())]
    return ok({"files": files})


@mcp.tool()
async def hive_read(path: str, session_id: str = "", project_name: str = "",
                    offset: int = 1, limit: int = 500) -> dict:
    """读取文件内容。"""
    base = _resolve_path(session_id, project_name)
    if not base:
        return error("PROJECT_NOT_FOUND", "请提供 session_id 或 project_name")
    file_path = base / path
    if not file_path.exists() or not file_path.is_file():
        return error("PROJECT_NOT_FOUND", f"文件不存在: {path}")
    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)
    sliced = lines[max(0, offset - 1):min(total, offset - 1 + limit)]
    return ok({"content": "\n".join(sliced), "total_lines": total, "file_size": file_path.stat().st_size})


@mcp.tool()
async def hive_artifact(session_id: str = "", project_name: str = "") -> dict:
    """获取所有成品文件列表。"""
    base = _resolve_path(session_id, project_name)
    if not base:
        return error("PROJECT_NOT_FOUND", "请提供 session_id 或 project_name")
    # 多位置检测成品
    artifact_dirs = [
        base / "dist",
        base / "build" / "app" / "outputs" / "flutter-apk",
        base / "target" / "release",
    ]
    seen = set()
    artifacts = []
    for d in artifact_dirs:
        if d.exists():
            for f in d.iterdir():
                if f.is_file() and f.suffix in (".exe", ".apk", ".aab", ".dmg", ".tar", ".zip"):
                    fp = str(f.resolve())
                    if fp not in seen:
                        seen.add(fp)
                        artifacts.append({"name": f.name, "path": str(f), "size": f.stat().st_size, "type": f.suffix})
    if not artifacts:
        for f in base.iterdir():
            if f.is_file() and f.stat().st_size > 100 and f.suffix not in (".pyc",):
                fp = str(f.resolve())
                if fp not in seen:
                    seen.add(fp)
                    artifacts.append({"name": f.name, "path": str(f), "size": f.stat().st_size, "type": f.suffix})
    return ok({"artifacts": artifacts})


@mcp.tool()
async def hive_cancel(session_id: str) -> dict:
    """中止正在进行的构建。"""
    if session_id not in _ACTIVE_ORCHESTRATORS:
        return error("NO_ACTIVE_BUILD", f"session {session_id} 无活跃构建")
    result = _ACTIVE_ORCHESTRATORS[session_id].cancel()
    result["message"] = f"构建已取消 (session {session_id})"
    return ok(result)


@mcp.tool()
async def hive_list_projects() -> dict:
    """列出所有项目。"""
    sessions = SessionManager.get_all_sessions()
    projects = {}
    for s in sessions:
        name = s["project_name"]
        if name not in projects or s["updated_at"] > projects[name]["last_activity"]:
            projects[name] = {"name": name, "status": s["status"],
                              "version_count": s["current_version"],
                              "last_activity": s["updated_at"],
                              "latest_version": s["current_version"]}
    return ok({"projects": list(projects.values())})


@mcp.tool()
async def hive_delete_project(project_name: str, confirm: bool = False) -> dict:
    """删除项目。必须 confirm=True 才会执行。"""
    if not confirm:
        return error("DELETE_CONFIRM_REQUIRED")
    deleted = SessionManager.delete_project(project_name)
    if deleted:
        return ok({"project_name": project_name, "message": f"项目 '{project_name}' 已删除"})
    return error("PROJECT_NOT_FOUND", f"项目 '{project_name}' 未找到")


@mcp.tool()
async def hive_dashboard_url() -> dict:
    """获取 Dashboard 访问地址。"""
    return ok({"url": "http://127.0.0.1:8421/dashboard", "port": 8421})


@mcp.tool()
async def hive_memory(action: str = "stats", dry_run: bool = True) -> dict:
    """跨项目记忆操作。"""
    hive_dir = Path.home() / ".hermes" / "hive-v4"
    memory_file = hive_dir / "memory.json"

    if action == "stats":
        if memory_file.exists():
            data = json.loads(memory_file.read_text(encoding="utf-8"))
            return ok({"memory": data, "total_entries": len(data.get("entries", []))})
        return ok({"memory": {"entries": []}, "total_entries": 0})
    elif action == "skills":
        from orchestrator.infrastructure.memory_store import MemoryStore
        store = MemoryStore()
        return ok({"skills": store.get_skills(), "total_skills": len(store.get_skills())})
    elif action == "clear":
        if not dry_run and memory_file.exists():
            memory_file.write_text(json.dumps({"entries": []}), encoding="utf-8")
            return ok({"memory": {"entries": []}, "total_entries": 0, "cleared": True})
        return ok({"memory": {"entries": []}, "total_entries": 0, "dry_run": True})
    return error("UNKNOWN_ERROR", f"未知 action: {action}")


# ── 辅助函数 ──

def _calc_progress(state: str) -> float:
    """根据 state 估算进度百分比。"""
    progress_map = {
        "idle": 0.0, "translating": 0.1, "planning": 0.25,
        "executing": 0.5, "testing": 0.75, "done": 1.0, "cancelled": 0.0,
    }
    return progress_map.get(state, 0.0)


def _calc_eta(state: str) -> int:
    """根据 state 估算剩余时间（秒）。"""
    eta_map = {
        "idle": 0, "translating": 15, "planning": 30,
        "executing": 300, "testing": 180, "done": 0, "cancelled": 0,
    }
    return eta_map.get(state, 0)


def _extract_name(description: str) -> str:
    """从描述中提取项目名。"""
    m = re.search(r"(?:做|写|创建|构建|开发|给我)(?:一个|个|一款|一套)?(.+?)(?:应用|程序|工具|系统|项目|$)", description)
    if m:
        name = m.group(1).strip()[:40]
        if name:
            return name
    return description[:20].strip()


def _resolve_path(session_id: str = "", project_name: str = "") -> Optional[Path]:
    """根据 session_id 或 project_name 解析工作区路径。"""
    if session_id:
        build_dir = Path.home() / ".hermes" / "hive-v4" / "builds" / session_id
        if build_dir.exists():
            return build_dir
    if project_name:
        version_dir = Path.home() / ".hermes" / "hive-v4" / "projects" / project_name
        if version_dir.exists():
            current_link = version_dir / "current"
            if current_link.exists():
                if current_link.is_symlink():
                    return current_link.resolve()
                try:
                    v = int(current_link.read_text().strip())
                    return version_dir / f"v{v}"
                except (ValueError, OSError):
                    pass
            versions = sorted([d for d in version_dir.iterdir() if d.name.startswith("v")])
            if versions:
                return versions[-1]
    return None


# ── 启动入口 ──

def main():
    """启动入口。使用 Starlette streamable-http app，注册了 Dashboard 路由。"""
    print("HIVE v4.1 MCP Server + Dashboard")
    print(f"   Dashboard: http://127.0.0.1:8421/dashboard")
    print(f"   MCP:       http://127.0.0.1:8421/mcp")
    print(f"   WS:        ws://127.0.0.1:8421/ws")
    print(f"   Sessions:  ~/.hermes/hive-v4/")

    import uvicorn
    uvicorn.run(
        _mcp_asgi,
        host="127.0.0.1",
        port=8421,
        log_level="info",
    )


if __name__ == "__main__":
    main()
