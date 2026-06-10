"""
HIVE v4.1 — Python SDK

为 Hermes Agent 提供一站式 HIVE 交互接口。
无需手写 asyncio 轮询或 session 管理。

用法:
    from hive_client import HiveClient

    client = HiveClient(url="http://127.0.0.1:8421")
    build = client.build("做一个极简计算器，Python tkinter")
    result = build.wait()
    print(result.artifacts)
    print(result.summary)

    # 迭代
    v2 = build.iterate("按钮改大一点")
    v2.wait()
    print(v2.diff)
"""

import time
from typing import Optional

import httpx


class BuildResult:
    """构建结果。"""

    def __init__(self, data: dict):
        self.session_id = data.get("session_id", "")
        self.project_name = data.get("project_name", "")
        self.status = data.get("status", "")
        self.version = data.get("version", 0)
        self.message = data.get("message", "")
        self.artifacts = data.get("artifacts", [])
        self.summary = data.get("summary", "")
        self.diff = data.get("diff", "")
        self._raw = data

    def __repr__(self):
        return f"<BuildResult {self.project_name} v{self.version} [{self.status}]>"


class HiveClient:
    """
    HIVE 客户端 — 封装 MCP 工具调用。

    Args:
        url: HIVE MCP Server 地址（默认 http://127.0.0.1:8421）
        poll_interval: 轮询间隔（秒）
        timeout: 总超时（秒）
    """

    def __init__(
        self,
        url: str = "http://127.0.0.1:8421",
        poll_interval: float = 2.0,
        timeout: int = 600,
    ):
        self.url = url.rstrip("/")
        self.poll_interval = poll_interval
        self.timeout = timeout

        # 通过 HTTP 调用 MCP 工具
        self._tool_url = f"{self.url}/mcp"

    def build(self, description: str, lang: str = "zh") -> BuildResult:
        """
        一句话启动构建。

        Args:
            description: 用户需求描述
            lang: 语言

        Returns:
            BuildResult（等待构建完成）
        """
        session = self._call_tool("hive_build", {
            "description": description,
            "lang": lang,
        })

        session_id = session.get("session_id", "")
        if not session_id:
            return BuildResult({"status": "error", "message": "构建启动失败"})

        # 轮询等待完成
        return self._poll_until_done(session_id)

    def iterate(self, session_id: str, request: str) -> BuildResult:
        """
        迭代修改已有项目。

        Args:
            session_id: 已有 session
            request: 修改请求描述

        Returns:
            BuildResult
        """
        self._call_tool("hive_iterate", {
            "session_id": session_id,
            "request": request,
        })
        return self._poll_until_done(session_id)

    def status(self, session_id: str = "") -> dict:
        """查询构建状态。"""
        return self._call_tool("hive_status", {"session_id": session_id})

    def cancel(self, session_id: str) -> dict:
        """中止构建。"""
        return self._call_tool("hive_cancel", {"session_id": session_id})

    def list_projects(self) -> list:
        """列出所有项目。"""
        result = self._call_tool("hive_list_projects", {})
        return result.get("projects", [])

    def versions(self, session_id: str) -> list:
        """获取版本列表。"""
        result = self._call_tool("hive_versions", {"session_id": session_id})
        return result.get("versions", [])

    def rollback(self, session_id: str, version: int) -> dict:
        """回滚到指定版本。"""
        return self._call_tool("hive_rollback", {
            "session_id": session_id,
            "version": version,
        })

    def diff(self, session_id: str, v1: int, v2: int) -> dict:
        """对比两个版本的差异。"""
        return self._call_tool("hive_diff", {
            "session_id": session_id,
            "v1": v1,
            "v2": v2,
        })

    def read_file(self, path: str, session_id: str = "", project_name: str = "",
                  offset: int = 1, limit: int = 500) -> dict:
        """读取文件。"""
        return self._call_tool("hive_read", {
            "path": path, "session_id": session_id,
            "project_name": project_name, "offset": offset, "limit": limit,
        })

    def list_files(self, path: str = "", session_id: str = "", project_name: str = "") -> list:
        """列出文件。"""
        result = self._call_tool("hive_ls", {
            "path": path, "session_id": session_id, "project_name": project_name,
        })
        return result.get("files", [])

    def artifacts(self, session_id: str = "", project_name: str = "") -> list:
        """获取成品列表。"""
        result = self._call_tool("hive_artifact", {
            "session_id": session_id, "project_name": project_name,
        })
        return result.get("artifacts", [])

    # ── 内部方法 ──

    def _call_tool(self, tool_name: str, params: dict) -> dict:
        """通过 HTTP 调用 MCP 工具（使用 httpx）。"""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": params,
            },
            "id": int(time.time() * 1000),
        }

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(self._tool_url, json=payload)
                result = resp.json()
                if "error" in result:
                    return {"status": "error", "message": result["error"].get("message", str(result["error"]))}
                return result.get("result", result)
        except httpx.RequestError as e:
            return {"status": "error", "message": f"连接 HIVE 失败: {e}"}

    def _poll_until_done(self, session_id: str) -> BuildResult:
        """轮询等待构建完成。"""
        start = time.time()
        terminal_states = {"done", "cancelled", "failed", "error"}

        while time.time() - start < self.timeout:
            raw = self._call_tool("hive_status", {"session_id": session_id})
            
            # 检查错误响应
            if raw.get("status") == "error":
                return BuildResult({
                    "session_id": session_id,
                    "status": "error",
                    "message": raw.get("error", {}).get("message", str(raw)),
                })
            
            # hive_status 返回 ok({"session_id": ..., "state": "done", ...}) 格式
            data = raw.get("data", raw)
            state = data.get("state", "")

            # 检查完成
            if state in terminal_states:
                # 获取成品
                arts = self.artifacts(session_id=session_id)
                return BuildResult({
                    "session_id": session_id,
                    "project_name": data.get("project_name", ""),
                    "status": state,
                    "version": data.get("version", 0),
                    "artifacts": arts,
                    "summary": f"构建完成，状态: {state}",
                })

            time.sleep(self.poll_interval)

        # 超时
        return BuildResult({
            "session_id": session_id,
            "status": "timeout",
            "message": f"等待超过 {self.timeout}s",
        })
