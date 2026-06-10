"""
HIVE v4.1 — 依赖管理器

职责:
- 为每个 session 创建独立虚拟环境（venv）
- 安装/更新依赖
- 隔离，不污染全局环境
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional


class DependencyManager:
    """依赖管理：venv 创建 + 依赖安装。"""

    def __init__(self, workspace_root: Path):
        """
        Args:
            workspace_root: 项目工作区根目录
        """
        self.workspace_root = workspace_root
        self.venv_path = workspace_root / ".venv"

    def ensure_venv(self) -> bool:
        """
        确保 venv 存在。不存在则创建。
        返回 True 表示已存在，False 表示新建。
        """
        if self.venv_path.exists():
            return True

        # 使用 uv 创建 venv（更快），回退到内置 venv
        try:
            subprocess.run(
                [sys.executable, "-m", "uv", "venv", str(self.venv_path)],
                capture_output=True,
                timeout=30,
            )
        except Exception:
            subprocess.run(
                [sys.executable, "-m", "venv", str(self.venv_path)],
                capture_output=True,
                timeout=30,
            )

        return self.venv_path.exists()

    def install(self, requirements: list[str]) -> dict:
        """
        安装依赖包。

        Args:
            requirements: 包名列表，如 ["requests", "pyinstaller"]

        Returns:
            {"success": bool, "installed": [str], "failed": [str], "error": str}
        """
        if not requirements:
            return {"success": True, "installed": [], "failed": [], "error": ""}

        self.ensure_venv()

        # 找 venv 的 pip
        pip_path = self._pip_path()
        if not pip_path:
            return {"success": False, "installed": [], "failed": requirements, "error": "venv pip not found"}

        results = {"success": True, "installed": [], "failed": [], "error": ""}
        for pkg in requirements:
            try:
                proc = subprocess.run(
                    [pip_path, "install", pkg],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=str(self.workspace_root),
                )
                if proc.returncode == 0:
                    results["installed"].append(pkg)
                else:
                    results["failed"].append(pkg)
                    results["error"] = proc.stderr[:500]
                    results["success"] = False
            except subprocess.TimeoutExpired:
                results["failed"].append(pkg)
                results["error"] = f"安装 {pkg} 超时"
                results["success"] = False

        return results

    def _pip_path(self) -> Optional[str]:
        """找 venv 中的 pip 路径。"""
        if sys.platform == "win32":
            candidates = [
                self.venv_path / "Scripts" / "pip.exe",
                self.venv_path / "Scripts" / "pip3.exe",
            ]
        else:
            candidates = [
                self.venv_path / "bin" / "pip",
                self.venv_path / "bin" / "pip3",
            ]
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    def python_path(self) -> Optional[str]:
        """获取 venv 中的 Python 路径。"""
        if sys.platform == "win32":
            py = self.venv_path / "Scripts" / "python.exe"
        else:
            py = self.venv_path / "bin" / "python"
        return str(py) if py.exists() else None
