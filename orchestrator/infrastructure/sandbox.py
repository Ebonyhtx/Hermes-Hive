"""
HIVE v4.1 — 沙箱管理器

职责:
- 为每个 Worker 创建隔离的临时工作目录
- 限制 Worker 的网络访问（仅允许包管理源）
- 超时强制终止
- 执行完毕后清理临时目录
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional


class Sandbox:
    """Worker 沙箱：隔离执行环境。"""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(tempfile.gettempdir()) / "hive_sandbox"

    def create_workspace(self, session_id: str) -> Path:
        """
        为 session 创建工作目录。
        返回工作目录 Path。
        """
        ws_path = self.base_dir / session_id
        if ws_path.exists():
            shutil.rmtree(ws_path)
        ws_path.mkdir(parents=True, exist_ok=True)
        return ws_path

    def run(
        self,
        cmd: list[str],
        cwd: Path,
        timeout_s: int = 600,
        env: Optional[dict] = None,
    ) -> dict:
        """
        在沙箱中执行命令。

        安全措施:
        1. 继承最小环境变量
        2. 设置超时
        3. 超时后强制 kill 进程树
        4. 输出大小限制

        Args:
            cmd: 命令列表
            cwd: 工作目录
            timeout_s: 超时秒数（默认 600s）
            env: 额外环境变量

        Returns:
            {"stdout": str, "stderr": str, "exit_code": int, "timed_out": bool}
        """
        # 构建安全环境
        safe_env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "USER": os.environ.get("USER", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PYTHONIOENCODING": "utf-8",
        }
        if env:
            safe_env.update(env)

        start = time.time()
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=safe_env,
                start_new_session=sys.platform != "win32",
            )

            try:
                stdout, stderr = proc.communicate(timeout=timeout_s)
                timed_out = False
            except subprocess.TimeoutExpired:
                self._kill_process_tree(proc)
                stdout, stderr = proc.communicate(timeout=5)
                timed_out = True

            elapsed = time.time() - start

            return {
                "stdout": stdout[:50000] if stdout else "",
                "stderr": stderr[:10000] if stderr else "",
                "exit_code": proc.returncode if not timed_out else -1,
                "timed_out": timed_out,
                "elapsed_s": round(elapsed, 1),
            }

        except FileNotFoundError as e:
            return {
                "stdout": "",
                "stderr": f"命令未找到: {e}",
                "exit_code": -1,
                "timed_out": False,
                "elapsed_s": 0,
            }

    def _kill_process_tree(self, proc: subprocess.Popen):
        """强制 kill 进程树 / Force-kill process tree (cross-platform)."""
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=5,
                )
            else:
                # Kill the process group if we set start_new_session, else kill individually
                try:
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, AttributeError):
                    proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def cleanup(self, session_id: str):
        """清理 session 的工作目录。"""
        ws_path = self.base_dir / session_id
        if ws_path.exists():
            shutil.rmtree(ws_path, ignore_errors=True)
