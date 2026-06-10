"""
HIVE v4.1 — ARC 需求转述师 / Requirements Translator

核心规则：不提问。用户描述 → 标准 brief.json。
Core rule: no questions. User description → structured brief.json.
"""

import asyncio
import json
import re
from typing import Optional

from orchestrator.hermes_bridge import run_agent
from orchestrator.i18n import pick_prompt
from orchestrator.infrastructure.cost_tracker import CostTracker


# ── Hermes CLI Prompt 模板 / Prompt Templates ──

_TRANSLATE_PROMPT_ZH = """你是一位需求转述师。你的工作是把用户的自然语言描述转译为结构化的项目需求 JSON。

核心规则：
1. **不提问**。用户给什么就用什么，不确定的字段用默认值。
2. **置信度标注**。每个字段标注你有多确定（0-1），低于 0.8 的字段必须写备注说明你做了什么假设。
3. **只输出 JSON**。不要输出任何解释性文字。

输出必须是一个合法的 JSON 对象，包含以下字段：

- project_name: 项目名称（提取或生成，最长 40 字符）
- description: 原样保留用户描述
- features: 数组，每个元素包含 name/priority(P0|P1|P2)/description
- tech_stack: 对象，包含 language/framework/os
- deliverable: exe|app|appimage|docker|lib|cli|apk
- ui_spec: 对象，包含 framework/style
- _confidence: 对象，包含 overall(0-1) 和 items 数组（每个含 field/value/confidence/note）

重要 — 技术栈推断规则：
- 如果提到 Flutter/Dart/Android/移动端/iOS → language: "Dart", framework: "Flutter", os: "Android"
- 如果提到 tkinter/GUI桌面 → language: "Python", framework: "tkinter", os: "windows"
- 如果提到 FastAPI/Web API → language: "Python", framework: "FastAPI", os: "cross-platform"
- 如果提到 React/Vue/前端/网页 → language: "JavaScript", framework: "React", os: "cross-platform"
- 如果提到 Rust → language: "Rust", framework: "", os: "cross-platform"
- 如果提到 Go → language: "Go", framework: "", os: "cross-platform"
- 默认值: language: "Python", framework: "tkinter", os: "windows"

注意：
- features 是数组，每个元素是对象（含 name/priority/description）
- 如果用户描述中未提供足够信息，推断合理默认值并用 _confidence 标注
- project_name 从描述中提取，最多 40 字符
- 不要加多余字段

用户描述：
{description}
"""

_TRANSLATE_PROMPT_EN = """You are a requirements translator. Your job is to convert natural language user descriptions into structured project requirement JSON.

Core rules:
1. **Do not ask questions.** Use what the user provides; fill defaults for missing fields.
2. **Confidence annotation.** Annotate each field with your confidence (0-1). Fields below 0.8 must include a note explaining your assumption.
3. **Output JSON only.** Do not include any explanatory text.

Output must be a valid JSON object with these fields:

- project_name: Project name (extract or generate, max 40 chars)
- description: Preserve the user's description as-is
- features: Array, each element has name/priority(P0|P1|P2)/description
- tech_stack: Object with language/framework/os
- deliverable: exe|app|appimage|docker|lib|cli|apk
- ui_spec: Object with framework/style
- _confidence: Object with overall(0-1) and items array (each with field/value/confidence/note)

Important — Tech stack inference rules:
- Flutter/Dart/Android/mobile/iOS → language: "Dart", framework: "Flutter", os: "Android"
- tkinter/GUI desktop → language: "Python", framework: "tkinter", os: "windows"
- FastAPI/Web API → language: "Python", framework: "FastAPI", os: "cross-platform"
- React/Vue/frontend/web → language: "JavaScript", framework: "React", os: "cross-platform"
- Rust → language: "Rust", framework: "", os: "cross-platform"
- Go → language: "Go", framework: "", os: "cross-platform"
- Default: language: "Python", framework: "tkinter", os: "windows"

Notes:
- features is an array of objects (name/priority/description)
- Infer reasonable defaults when user provides insufficient info, annotate with _confidence
- project_name extracted from description, max 40 chars
- Do not add extra fields

User description:
{description}
"""

_DELTA_PROMPT_ZH = """你是一位需求转述师。用户希望对已有项目做修改。

已有项目名称: {project_name}
当前需求描述: {current_description}

用户的修改请求:
{request}

请输出 delta brief JSON，包含 _delta=true, _base_brief, description, features 数组。

只输出 JSON，不输出解释。
"""

_DELTA_PROMPT_EN = """You are a requirements translator. The user wants to make changes to an existing project.

Existing project: {project_name}
Current description: {current_description}

User's modification request:
{request}

Output a delta brief JSON with _delta=true, _base_brief, description, features array.

Output JSON only, no explanation.
"""




class Architect:
    """
    ARC 角色：用户描述 → brief.json（零轮问询）。
    通过 Hermes CLI 真实调用 LLM 完成转译。
    """

    def __init__(self, session_manager=None, cost_tracker: Optional[CostTracker] = None):
        self.cost_tracker = cost_tracker or CostTracker()
        self.session_manager = session_manager

    async def translate(
        self,
        description: str,
        lang: str = "en",
        existing_brief: Optional[dict] = None,
    ) -> dict:
        """
        用户描述 → brief.json（调 Hermes CLI 完成转译）。
        """
        prompt = pick_prompt(_TRANSLATE_PROMPT_ZH, _TRANSLATE_PROMPT_EN, lang).format(description=description)

        for attempt in range(2):
            try:
                response = await asyncio.to_thread(run_agent, "architect", prompt, 120)
                brief = self._parse_json(response)
                if brief and "project_name" in brief:
                    brief.setdefault("description", description)
                    brief.setdefault("features", [])
                    # 智能推断默认技术栈（LLM 可能没返回 tech_stack 字段时）
                    if "tech_stack" not in brief:
                        desc_lower = description.lower()
                        if any(kw in desc_lower for kw in ['flutter', 'dart', 'android', '移动端', 'app', 'apk']):
                            brief["tech_stack"] = {"language": "Dart", "framework": "Flutter", "os": "Android"}
                            brief["deliverable"] = "apk"
                        elif any(kw in desc_lower for kw in ['rust', 'cargo']):
                            brief["tech_stack"] = {"language": "Rust", "framework": "", "os": "cross-platform"}
                        elif any(kw in desc_lower for kw in ['go ', 'golang', 'go语言']):
                            brief["tech_stack"] = {"language": "Go", "framework": "", "os": "cross-platform"}
                        elif any(kw in desc_lower for kw in ['react', 'vue', '前端', 'web', '网页']):
                            brief["tech_stack"] = {"language": "JavaScript", "framework": "React", "os": "cross-platform"}
                        elif any(kw in desc_lower for kw in ['api', 'fastapi', '后端']):
                            brief["tech_stack"] = {"language": "Python", "framework": "FastAPI", "os": "cross-platform"}
                        else:
                            brief["tech_stack"] = {"language": "Python", "framework": "tkinter", "os": "windows"}
                    brief.setdefault("deliverable", "apk" if brief.get("tech_stack", {}).get("language") == "Dart" else "exe")
                    brief.setdefault("_confidence", {"overall": 0.5, "items": []})
                    brief["_cost_estimate"] = self.cost_tracker.estimate(tasks=max(len(brief.get("features", [])), 3))
                    return brief
                # JSON 解析失败 → 追加修复指令重试
                retry_note = "\n\n注意：刚才的 JSON 格式有误，请只输出一个合法的 JSON 对象，不要包含任何解释文字。" if lang == 'zh' else "\n\nNote: The previous JSON format was invalid. Output only a valid JSON object with no explanation."
                prompt = prompt + retry_note
            except Exception:
                if attempt == 0:
                    retry_note = "\n\n注意：刚才调用出错，请只输出一个合法的 JSON 对象。" if lang == 'zh' else "\n\nNote: The previous call failed. Output only a valid JSON object."
                    prompt = prompt + retry_note
                else:
                    break

        return self._fallback_brief(description)

    async def translate_delta(
        self,
        request: str,
        current_brief: dict,
        lang: str = "en",
    ) -> dict:
        """迭代修改：调 Hermes CLI 转译 delta brief。"""
        prompt = pick_prompt(_DELTA_PROMPT_ZH, _DELTA_PROMPT_EN, lang).format(
            project_name=current_brief.get("project_name", ""),
            current_description=current_brief.get("description", ""),
            request=request,
        )

        try:
            response = await asyncio.to_thread(run_agent, "architect", prompt, 60)
            delta = self._parse_json(response)
            if delta and delta.get("_delta"):
                return delta
        except Exception:
            pass

        return {
            "_delta": True,
            "_base_brief": current_brief.get("project_name", ""),
            "description": request,
        }

    def check_confidence(self, brief: dict) -> list[dict]:
        """检查 brief 中置信度 < 0.8 的项。"""
        items = brief.get("_confidence", {}).get("items", [])
        return [item for item in items if item.get("confidence", 1.0) < 0.8]

    # ── 内部方法 ──

    def _parse_json(self, text: str) -> Optional[dict]:
        """从 Agent 响应中解析 JSON。"""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0]
        text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _fallback_brief(self, description: str) -> dict:
        """Hermes CLI 调用失败时的兜底 brief。
        从描述中智能推断技术栈，而非固定使用 Python/tkinter。
        """
        desc_lower = description.lower()
        # 智能推断技术栈
        if any(kw in desc_lower for kw in ['flutter', 'dart', 'android', '移动端', 'app', 'apk']):
            ts = {"language": "Dart", "framework": "Flutter", "os": "Android"}
            deliverable = "apk"
        elif any(kw in desc_lower for kw in ['rust', 'cargo']):
            ts = {"language": "Rust", "framework": "", "os": "cross-platform"}
            deliverable = "exe"
        elif any(kw in desc_lower for kw in ['go ', 'golang', 'go语言']):
            ts = {"language": "Go", "framework": "", "os": "cross-platform"}
            deliverable = "exe"
        elif any(kw in desc_lower for kw in ['react', 'vue', '前端', 'web', '网页']):
            ts = {"language": "JavaScript", "framework": "React", "os": "cross-platform"}
            deliverable = "app"
        elif any(kw in desc_lower for kw in ['api', 'fastapi', '后端']):
            ts = {"language": "Python", "framework": "FastAPI", "os": "cross-platform"}
            deliverable = "docker"
        else:
            ts = {"language": "Python", "framework": "tkinter", "os": "windows"}
            deliverable = "exe"

        return {
            "project_name": self._extract_name(description),
            "description": description,
            "features": [
                {"name": "核心功能", "priority": "P0", "description": description}
            ],
            "tech_stack": ts,
            "deliverable": deliverable,
            "_confidence": {
                "overall": 0.3,
                "items": [
                    {"field": "tech_stack", "value": f"{ts['language']}/{ts['framework']}", "confidence": 0.3,
                     "note": "LLM 调用失败，使用启发式推断"}
                ],
            },
            "_cost_estimate": self.cost_tracker.estimate(tasks=3),
            "_raw_description": description,
        }

    def _extract_name(self, description: str) -> str:
        """从描述中提取项目名。"""
        m = re.search(r"(?:做|写|创建|构建|开发|给我)(?:一个|个|一款|一套)?(.+?)(?:应用|程序|工具|系统|项目|$)", description)
        if m:
            name = m.group(1).strip()[:40]
            if name:
                return name
        return description[:20].strip()
