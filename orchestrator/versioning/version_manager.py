"""
HIVE v4.1 — 版本管理器

职责:
- 创建版本（复制工作区文件到版本目录）
- 回滚到指定版本
- 对比两个版本的差异
"""

import difflib
import filecmp
import json
import shutil
from pathlib import Path
from typing import Optional


class VersionManager:
    """
    版本管理。

    文件结构:
    ~/.hermes/hive-v4/projects/{project_name}/
        current -> v3 (symlink)
        v1/
            brief.json
            src/...
            dist/...
            review.json
        v2/...
        current -> v3 (symlink)
    """

    MAX_VERSIONS = 10

    def __init__(self, projects_root: Optional[Path] = None):
        self.projects_root = projects_root or Path.home() / ".hermes" / "hive-v4" / "projects"

    def create_version(
        self,
        project_name: str,
        source_dir: Path,
        brief: Optional[dict] = None,
        review: Optional[dict] = None,
        summary: str = "",
    ) -> int:
        """
        创建新版本。

        Args:
            project_name: 项目名
            source_dir: 工作区源代码目录
            brief: brief.json dict
            review: review.json dict
            summary: 版本摘要

        Returns:
            版本号（从 1 递增）
        """
        project_dir = self.projects_root / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        # 确定版本号
        version = self._next_version(project_dir)

        # 创建版本目录
        version_dir = project_dir / f"v{version}"
        version_dir.mkdir(parents=True, exist_ok=True)

        # 从 source_dir 复制所有文件到版本目录
        src_dest = version_dir / "src"
        if source_dir.exists():
            if source_dir.is_dir():
                shutil.copytree(source_dir, src_dest, dirs_exist_ok=True)
            else:
                src_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_dir, src_dest)

        # 复制 dist（成品文件）
        dist_src = source_dir / "dist" if source_dir.exists() else None
        if dist_src and dist_src.exists():
            shutil.copytree(dist_src, version_dir / "dist", dirs_exist_ok=True)

        # 保存元数据
        if brief:
            (version_dir / "brief.json").write_text(
                json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        if review:
            (version_dir / "review.json").write_text(
                json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        # 保存元信息
        meta = {
            "version": version,
            "summary": summary,
            "files_count": len(list(version_dir.rglob("*"))) if version_dir.exists() else 0,
        }
        (version_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 更新 current symlink
        self._update_current_symlink(project_dir, version)

        return version

    def rollback(self, project_name: str, target_version: int) -> dict:
        """
        回滚到指定版本。

        Args:
            project_name: 项目名
            target_version: 目标版本号（从 1 开始）

        Returns:
            {"status": str, "previous_version": int, "current_version": int}
        """
        project_dir = self.projects_root / project_name
        if not project_dir.exists():
            return {"status": "error", "message": f"项目 {project_name} 不存在"}

        current_version = self._current_version(project_dir)
        if not current_version:
            return {"status": "error", "message": "无版本记录"}

        target_dir = project_dir / f"v{target_version}"
        if not target_dir.exists():
            return {"status": "error", "message": f"版本 v{target_version} 不存在"}

        self._update_current_symlink(project_dir, target_version)

        return {
            "status": "success",
            "previous_version": current_version,
            "current_version": target_version,
        }

    def diff(self, project_name: str, v1: int, v2: int) -> dict:
        """
        对比两个版本的文件差异。

        Args:
            project_name: 项目名
            v1: 旧版本
            v2: 新版本

        Returns:
            {"files": [{"path": str, "added": int, "removed": int}],
             "diff_text": str, "total_changes": int}
        """
        project_dir = self.projects_root / project_name
        v1_dir = project_dir / f"v{v1}" / "src"
        v2_dir = project_dir / f"v{v2}" / "src"

        if not v1_dir.exists() or not v2_dir.exists():
            return {"files": [], "diff_text": "", "total_changes": 0, "error": "版本目录不存在"}

        # 收集所有文件
        all_files = set()
        for d in [v1_dir, v2_dir]:
            if d.exists():
                for f in d.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(d)
                        all_files.add(str(rel))

        files_diff = []
        total_changes = 0
        diff_parts = []

        for rel_path in sorted(all_files):
            f1 = v1_dir / rel_path
            f2 = v2_dir / rel_path

            if f1.exists() and f2.exists():
                # 两个版本都有
                if not filecmp.cmp(f1, f2, shallow=False):
                    text1 = f1.read_text(encoding="utf-8", errors="replace")
                    text2 = f2.read_text(encoding="utf-8", errors="replace")
                    diff = list(difflib.unified_diff(
                        text1.splitlines(keepends=True),
                        text2.splitlines(keepends=True),
                        fromfile=f"v{v1}/{rel_path}",
                        tofile=f"v{v2}/{rel_path}",
                    ))
                    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
                    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
                    files_diff.append({"path": rel_path, "added": added, "removed": removed})
                    total_changes += added + removed
                    diff_parts.extend(diff)
            elif f1.exists():
                # 只在 v1 中存在（已删除）
                with f1.open() as f:
                    lines = f.readlines()
                files_diff.append({"path": rel_path, "added": 0, "removed": len(lines)})
                total_changes += len(lines)
                diff_parts.extend([
                    f"--- v{v1}/{rel_path}",
                    f"+++ v{v2}/{rel_path} (deleted)",
                ] + [f"-{l.rstrip()}" for l in lines])
            else:
                # 只在 v2 中存在（新增）
                with f2.open() as f:
                    lines = f.readlines()
                files_diff.append({"path": rel_path, "added": len(lines), "removed": 0})
                total_changes += len(lines)
                diff_parts.extend([
                    f"--- v{v1}/{rel_path} (new)",
                    f"+++ v{v2}/{rel_path}",
                ] + [f"+{l.rstrip()}" for l in lines])

        return {
            "files": files_diff,
            "diff_text": "\n".join(diff_parts[:500]),  # 限制长度
            "total_changes": total_changes,
        }

    def list_versions(self, project_name: str) -> list[dict]:
        """列出项目的所有版本。"""
        project_dir = self.projects_root / project_name
        if not project_dir.exists():
            return []

        versions = []
        current = self._current_version(project_dir)

        for d in sorted(project_dir.iterdir()):
            if d.name.startswith("v") and d.name[1:].isdigit():
                v = int(d.name[1:])
                meta_file = d / "meta.json"
                meta = {}
                if meta_file.exists():
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                versions.append({
                    "version": v,
                    "is_current": v == current,
                    "summary": meta.get("summary", ""),
                    "files_count": meta.get("files_count", 0),
                })

        return sorted(versions, key=lambda x: x["version"])

    # ── 内部方法 ──

    def _cleanup_old_versions(self, project_name: str):
        """清理超出 MAX_VERSIONS 的旧版本。"""
        project_dir = self.projects_root / project_name
        if not project_dir.exists():
            return
        versions = sorted(
            [int(d.name[1:]) for d in project_dir.iterdir() if d.is_dir() and d.name.startswith("v")],
        )
        while len(versions) > self.MAX_VERSIONS:
            oldest = versions.pop(0)
            import shutil
            shutil.rmtree(project_dir / f"v{oldest}", ignore_errors=True)

    def _next_version(self, project_dir: Path) -> int:
        """计算下一个版本号。"""
        max_v = 0
        for d in project_dir.iterdir():
            if d.name.startswith("v") and d.name[1:].isdigit():
                v = int(d.name[1:])
                max_v = max(max_v, v)
        return max_v + 1

    def _current_version(self, project_dir: Path) -> Optional[int]:
        """获取当前版本号（从 symlink 或 current 文件读取）。"""
        current_link = project_dir / "current"
        if current_link.exists():
            if current_link.is_symlink():
                target = current_link.resolve()
                name = target.name
                if name.startswith("v") and name[1:].isdigit():
                    return int(name[1:])
            elif current_link.is_file():
                # symlink 创建失败时的回退：current 是文本文件
                try:
                    text = current_link.read_text().strip()
                    if text:
                        v = int(text)
                        return v
                except (ValueError, OSError):
                    pass
        return None

    def _update_current_symlink(self, project_dir: Path, version: int):
        """更新 current symlink。"""
        current_link = project_dir / "current"
        target = project_dir / f"v{version}"

        # Windows 上 symlink 需要管理员权限，用 junction 替代
        if current_link.exists():
            if current_link.is_symlink():
                current_link.unlink()
            elif current_link.is_dir():
                shutil.rmtree(current_link)

        try:
            current_link.symlink_to(target, target_is_directory=True)
        except (OSError, PermissionError):
            # Windows 回退：创建 current 文件记录版本
            current_link.write_text(str(version), encoding="utf-8")
