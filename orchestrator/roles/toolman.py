"""
HIVE v4.1 — TOOLMAN 交付员

职责链: 依赖安装 → 测试执行 → 打包 → 产出成品
技术栈感知，支持 Python/Rust/Go/Node
"""

import json
import os
import shlex
import shutil
import sys
from pathlib import Path
from typing import Callable, Optional

from orchestrator.hermes_bridge import run_agent

from orchestrator.infrastructure.dependency_manager import DependencyManager
from orchestrator.infrastructure.sandbox import Sandbox
from orchestrator.infrastructure.cost_tracker import CostTracker


class Toolman:
    """
    交付员。
    全自动管线：安装依赖 → 运行测试 → 打包 → 产出成品。
    """

    def __init__(
        self,
        cost_tracker: Optional[CostTracker] = None,
    ):
        self.sandbox = Sandbox()
        self.cost_tracker = cost_tracker or CostTracker()
        self._dependency_manager: Optional[DependencyManager] = None

    async def deliver(
        self,
        dag: dict,
        workspace_path: Path,
        project_name: str,
        tech_stack: str,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """
        完整交付管线。

        Args:
            dag: dag.json dict
            workspace_path: workspace 路径
            project_name: 项目名
            tech_stack: 技术栈（如 python-tkinter, flutter, rust-cli）
            on_progress: 进度回调

        Returns:
            {"test_results": dict, "artifacts": list, "cost": dict, "status": str}
        """
        if on_progress:
            on_progress("deliver", "start")

        is_python = tech_stack.startswith("python-")
        self._dependency_manager = DependencyManager(workspace_path) if is_python else None
        template = dag.get("delivery_template", {})

        # 环境预检：检查构建工具链是否存在
        prereq = self._check_prerequisites(tech_stack)
        if prereq["missing"]:
            if on_progress:
                on_progress("deliver", "install_sdk")
            # 自动下载安装缺失的 SDK
            install_result = self._auto_install_sdk(tech_stack, prereq["missing"], on_progress)
            if not install_result["success"]:
                if on_progress:
                    on_progress("deliver", "error")
                return {"test_results": {}, "artifacts": [], "cost": {"tokens": 0, "usd": 0.0},
                        "status": "prerequisites_missing", "error": install_result["error"]}
            # 重新检查
            prereq = self._check_prerequisites(tech_stack)
            if prereq["missing"]:
                msg = f"安装后仍缺少: {', '.join(prereq['missing'])}"
                if on_progress:
                    on_progress("deliver", "error")
                return {"test_results": {}, "artifacts": [], "cost": {"tokens": 0, "usd": 0.0},
                        "status": "prerequisites_missing", "error": msg}

        # 构建环境变量
        venv_env = self._build_venv_env(workspace_path) if is_python else None
        # 如果安装了新 SDK，合并其路径到环境变量
        if "sdk_paths" in prereq and prereq["sdk_paths"]:
            extra_path = os.pathsep.join(prereq["sdk_paths"])
            if venv_env:
                venv_env["PATH"] = extra_path + os.pathsep + venv_env.get("PATH", os.environ.get("PATH", ""))
            else:
                venv_env = {"PATH": extra_path + os.pathsep + os.environ.get("PATH", "")}

        # Flutter 项目初始化：如果项目还没有 android/ 目录，自动 flutter create
        if tech_stack == "flutter" and not (workspace_path / "android").exists():
            self._init_flutter_project(workspace_path, project_name)

        # Step 1: 依赖安装
        if on_progress:
            on_progress("dependencies", "start")
        deps_result = self._install_dependencies(workspace_path, dag.get("requirements", []), is_python)
        if on_progress:
            on_progress("dependencies", "done")

        # Step 2: 运行测试
        if on_progress:
            on_progress("testing", "start")
        test_cmd = template.get("test_cmd", "pytest tests/ -v")
        test_result = self._run_tests(workspace_path, test_cmd, env=venv_env)
        if on_progress:
            on_progress("testing", "done")

        # Step 3: 打包
        if on_progress:
            on_progress("packaging", "start")
        build_cmd = template.get("build_cmd", "")  # 已在 planner.py 中格式化
        artifacts = self._build_artifact(workspace_path, build_cmd, project_name, env=venv_env)
        if on_progress:
            on_progress("packaging", "done")

        # Step 4: 成本
        cost = {
            "tokens": 0,
            "usd": 0.0,
        }

        status = "success"
        if test_result.get("failed", 0) > 0:
            status = "test_failed"
        if not artifacts:
            if status == "success":
                status = "build_failed"
            else:
                status = "partial_failure"

        if on_progress:
            on_progress("deliver", "done")

        return {
            "test_results": test_result,
            "artifacts": artifacts,
            "cost": cost,
            "status": status,
        }

    def _check_prerequisites(self, tech_stack: str) -> dict:
        """检查构建工具链是否可用。返回 {"missing": [str], "found": [str], "sdk_paths": [str]}。"""
        required = []
        if tech_stack == "flutter":
            required = ["flutter", "dart"]
        elif tech_stack == "rust-cli":
            required = ["cargo", "rustc"]
        elif tech_stack == "go-cli":
            required = ["go"]
        elif tech_stack == "node-react":
            required = ["node", "npm"]

        missing = []
        found = []
        sdk_paths = []
        for tool in required:
            path = shutil.which(tool)
            if path:
                found.append(tool)
            else:
                missing.append(tool)

        # 检查托管 SDK 目录
        sdk_dir = Path.home() / ".hermes" / "hive-v4" / "tools"
        if tech_stack == "flutter":
            flutter_bin = sdk_dir / "flutter" / "bin"
            if flutter_bin.exists():
                sdk_paths.append(str(flutter_bin))
                # 重新检查 flutter
                old_path = os.environ.get("PATH", "")
                os.environ["PATH"] = str(flutter_bin) + os.pathsep + old_path
                if shutil.which("flutter"):
                    missing = [t for t in missing if t not in ("flutter", "dart")]
                    sdk_paths.append(str(flutter_bin))

        return {"missing": missing, "found": found, "sdk_paths": sdk_paths}

    def _auto_install_sdk(self, tech_stack: str, missing: list, on_progress=None) -> dict:
        """自动下载安装缺失的 SDK。目前支持 Flutter。"""
        if tech_stack != "flutter":
            return {"success": False, "error": f"暂时不支持自动安装 {tech_stack} SDK，请手动安装"}

        tools_dir = Path.home() / ".hermes" / "hive-v4" / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        flutter_dir = tools_dir / "flutter"
        flutter_bin = flutter_dir / "bin"
        flutter_exe = flutter_bin / "flutter.exe" if sys.platform == "win32" else flutter_bin / "flutter"

        # 如果已经下载过，直接加到 PATH
        if flutter_exe.exists():
            if on_progress:
                on_progress("install_sdk", "found_cached")
            return {"success": True, "path": str(flutter_bin)}

        if on_progress:
            on_progress("install_sdk", "downloading")

        # Flutter Windows stable 下载
        import urllib.request
        import zipfile
        import io

        # 先获取最新稳定版版本号
        try:
            releases_url = "https://storage.googleapis.com/flutter_infra_release/releases/releases_windows.json"
            resp = urllib.request.urlopen(releases_url, timeout=15)
            releases = json.loads(resp.read().decode())
            # 找最新的 stable hash
            stable_hash = None
            for rel in releases.get("releases", []):
                if rel.get("channel") == "stable":
                    stable_hash = rel.get("hash")
                    archive = rel.get("archive")
                    break
            if not archive:
                archive = "stable/windows/flutter_windows_3.29.2-stable.zip"
            download_url = f"https://storage.googleapis.com/flutter_infra_release/releases/{archive}"
        except Exception:
            download_url = "https://storage.googleapis.com/flutter_infra_release/releases/stable/windows/flutter_windows_3.29.2-stable.zip"

        if on_progress:
            on_progress("install_sdk", f"downloading_flutter")

        try:
            # 下载
            resp = urllib.request.urlopen(download_url, timeout=300)
            total = int(resp.headers.get("Content-Length", 0))
            chunk_size = 8192
            data = bytearray()
            downloaded = 0
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                data.extend(chunk)
                downloaded += len(chunk)
                if total and on_progress:
                    pct = int(downloaded / total * 100)
                    if pct % 20 == 0:
                        on_progress("install_sdk", f"下载中 {pct}%")

            if on_progress:
                on_progress("install_sdk", "extracting")

            # 解压
            with zipfile.ZipFile(io.BytesIO(bytes(data))) as zf:
                zf.extractall(str(tools_dir))

            # 解压后是 flutter/ 目录，确认路径
            extracted = tools_dir / "flutter"
            if not extracted.exists():
                # 可能是 flutter_windows_xxx/ 格式
                for d in tools_dir.iterdir():
                    if d.is_dir() and "flutter" in d.name.lower():
                        if (d / "bin" / ("flutter.exe" if sys.platform == "win32" else "flutter")).exists():
                            # 重命名为 flutter
                            d.rename(extracted)
                            break

            if flutter_exe.exists():
                if on_progress:
                    on_progress("install_sdk", "done")
                return {"success": True, "path": str(flutter_bin)}
            else:
                return {"success": False, "error": f"解压后未找到 Flutter SDK: {flutter_exe}"}

        except Exception as e:
            return {"success": False, "error": f"下载 Flutter SDK 失败: {str(e)}"}

    def _init_flutter_project(self, workspace_path: Path, project_name: str):
        """初始化 Flutter 项目目录并复制源码。"""
        import subprocess
        # 用沙箱执行 flutter create
        result = self.sandbox.run(
            cmd=["flutter", "create", "--project-name", project_name.replace("-", "_"), str(workspace_path)],
            cwd=workspace_path.parent,
            timeout_s=120,
        )
        # 复制 src/lib/ 到 lib/
        src_lib = workspace_path / "src" / "lib"
        lib_dir = workspace_path / "lib"
        if src_lib.exists() and lib_dir.exists():
            import shutil as _shutil
            for item in src_lib.iterdir():
                dest = lib_dir / item.name
                if item.is_dir():
                    if dest.exists():
                        _shutil.rmtree(dest)
                    _shutil.copytree(item, dest)
                else:
                    _shutil.copy2(item, dest)
        # flutter pub get
        self.sandbox.run(cmd=["flutter", "pub", "get"], cwd=workspace_path, timeout_s=120)

    def _install_dependencies(self, workspace_path: Path, requirements: list, is_python: bool = True) -> dict:
        """安装依赖。"""
        if not requirements:
            return {"success": True, "installed": [], "failed": []}
        if not is_python or not self._dependency_manager:
            # 非 Python 项目：依赖由对应工具链自行处理（flutter pub get, cargo build 等）
            return {"success": True, "installed": requirements, "failed": []}
        return self._dependency_manager.install(requirements)

    def _build_venv_env(self, workspace_path: Path) -> dict:
        """构建包含 venv 路径的环境变量字典。"""
        scripts_dir = workspace_path / ".venv"
        if sys.platform == "win32":
            scripts_dir = scripts_dir / "Scripts"
        else:
            scripts_dir = scripts_dir / "bin"
        extra_path = str(scripts_dir) if scripts_dir.exists() else ""
        env = {}
        if extra_path:
            env["PATH"] = os.pathsep.join([extra_path, os.environ.get("PATH", "")])
        return env

    def _run_tests(self, workspace_path: Path, test_cmd: str, env: Optional[dict] = None) -> dict:
        """运行测试。"""
        cmd = shlex.split(test_cmd)
        result = self.sandbox.run(
            cmd=cmd,
            cwd=workspace_path,
            timeout_s=120,
            env=env,
        )
        passed = result.get("exit_code", -1) == 0
        return {
            "command": test_cmd,
            "passed": passed,
            "failed": 0 if passed else 1,
            "stdout": result.get("stdout", "")[:2000],
            "stderr": result.get("stderr", "")[:500],
        }

    def _build_artifact(self, workspace_path: Path, build_cmd: str, project_name: str, env: Optional[dict] = None) -> list:
        """打包。返回成品文件列表。"""
        # 使用 pyinstaller 或对应技术栈命令
        result = self.sandbox.run(
            cmd=shlex.split(build_cmd),
            cwd=workspace_path,
            timeout_s=300,
            env=env,
        )

        # 查找生成的成品
        dist_dir = workspace_path / "dist"
        artifacts = []
        if dist_dir.exists():
            for f in dist_dir.iterdir():
                if f.is_file():
                    artifacts.append({
                        "name": f.name,
                        "path": str(f),
                        "size": f.stat().st_size,
                    })

        return artifacts
