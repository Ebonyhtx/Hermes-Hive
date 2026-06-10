"""
HIVE v4.1 — 跨项目记忆（JSON 文件存储）

职责:
- 存储用户偏好（语言、风格、平台）
- 记录模式识别（项目中的常见选择）
- 提炼技能（从成功项目中提取的编码模式）
- 仅在被主动查询时使用（被动参考，不干扰构建）

零外部依赖（纯 JSON 文件操作）。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class MemoryStore:
    """
    跨项目记忆。

    存储位置: ~/.hermes/hive-v4/memory.json
    使用规则: 只在 ARC 转译时被动参考。
    """

    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = store_path or Path.home() / ".hermes" / "hive-v4" / "memory.json"
        self._data = self._load()

    # ── 公共 API ──

    def record_build(self, project_name: str, brief: dict, success: bool = True):
        """
        记录一次构建到记忆。

        - 更新偏好（tech_stack, deliverable）
        - 记录新项目
        - 保存成功模式
        """
        ts = brief.get("tech_stack", {})
        if ts:
            self._update_preference("language", ts.get("language", ""))
            self._update_preference("framework", ts.get("framework", ""))
            self._update_preference("os", ts.get("os", ""))

        deliverable = brief.get("deliverable", "")
        if deliverable:
            self._update_preference("deliverable", deliverable)

        # 记录项目
        projects = self._data.setdefault("projects", [])
        existing = [p for p in projects if p["name"] == project_name]
        if existing:
            existing[0]["last_built"] = datetime.now().isoformat()
            existing[0]["success"] = success
        else:
            projects.append({
                "name": project_name,
                "tech_stack": ts,
                "last_built": datetime.now().isoformat(),
                "success": success,
            })

        # 成功项目提炼技能
        if success:
            self._extract_skill(project_name, brief)

        self._save()

    def get_preferences(self) -> dict:
        """获取用户偏好（供 ARC 参考）。"""
        return dict(self._data.get("preferences", {}))

    def get_skills(self) -> list:
        """获取提炼的技能列表。"""
        return list(self._data.get("skills", []))

    def get_stats(self) -> dict:
        """获取记忆统计。"""
        return {
            "projects_count": len(self._data.get("projects", [])),
            "skills_count": len(self._data.get("skills", [])),
            "preferences": self.get_preferences(),
        }

    def clear(self):
        """清空所有记忆。"""
        self._data = {"entries": []}
        self._save()

    # ── 内部方法 ──

    def _load(self) -> dict:
        """从磁盘加载记忆。"""
        if self.store_path.exists():
            try:
                return json.loads(self.store_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"entries": [], "preferences": {}, "projects": [], "skills": []}

    def _save(self):
        """持久化到磁盘。"""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _update_preference(self, key: str, value: str):
        """更新单条偏好（频率统计）。"""
        if not value:
            return
        prefs = self._data.setdefault("preferences", {})
        freq = prefs.setdefault(key, {})
        freq[value] = freq.get(value, 0) + 1

    def _extract_skill(self, project_name: str, brief: dict):
        """从成功项目中提炼技能。"""
        skills = self._data.setdefault("skills", [])
        description = brief.get("description", "")[:200]
        tech_stack = brief.get("tech_stack", {})

        # 去重：相同 tech_stack + 相似描述不重复记录
        for s in skills:
            if s.get("tech_stack") == tech_stack and s.get("project") == project_name:
                return

        skills.append({
            "project": project_name,
            "tech_stack": tech_stack,
            "description": description,
            "recorded_at": datetime.now().isoformat(),
        })

        # 保留最近 20 条技能
        if len(skills) > 20:
            self._data["skills"] = skills[-20:]
