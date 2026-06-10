"""
HIVE v4.1 — PLANNER 调度员

职责: brief.json → dag.json（零用户确认，直接派发）
调 Hermes CLI 做智能任务拆解。
"""

import asyncio
import json
from typing import Optional

from orchestrator.hermes_bridge import run_agent
from orchestrator.i18n import pick_prompt


# ── Hermes CLI Prompt 模板 ──

_PLAN_PROMPT_ZH = """你是一位软件项目调度员。你的工作是把需求 brief 拆解为具体的开发任务。

当前项目:
- 名称: {project_name}
- 技术栈: {tech_stack_json}
- 交付类型: {deliverable}
- 功能:
{features_text}

任务拆解规则:
1. 每个任务有唯一的 ID (T1, T2, T3...)
2. 按 layer 分层：
   - Layer 1: 无依赖的并行任务（UI / 逻辑 / 数据模型 / 测试用例）
   - Layer 2: 依赖 Layer 1 的集成任务
   - Layer 3: 测试运行
   - Layer 4: 打包交付
3. 每个任务标注 type: code | test | build
4. 每个任务标注 assign_to: coder | tester | toolman
5. 标注依赖关系 deps: ["T1", "T2"]
6. 根据技术栈输出对应语言的文件：Python→.py, Flutter/Dart→.dart, Rust→.rs, Go→.go, Node→.js/.ts

只输出 JSON，格式如下：
{{
  "tasks": [
    {{"id": "T1", "title": "任务名", "layer": 1, "deps": [], "type": "code", "assign_to": "coder", "acceptance_criteria": "验收标准描述"}}
  ],
  "requirements": ["依赖包名"]
}}
"""

_PLAN_PROMPT_EN = """You are a software project scheduler. Your job is to break down requirement briefs into concrete development tasks.

Current project:
- Name: {project_name}
- Tech stack: {tech_stack_json}
- Deliverable type: {deliverable}
- Features:
{features_text}

Task breakdown rules:
1. Each task has a unique ID (T1, T2, T3...)
2. Layer structure:
   - Layer 1: Parallel tasks with no dependencies (UI / logic / data model / tests)
   - Layer 2: Integration tasks depending on Layer 1
   - Layer 3: Test execution
   - Layer 4: Packaging & delivery
3. Each task has type: code | test | build
4. Each task has assign_to: coder | tester | toolman
5. Specify dependencies: deps: ["T1", "T2"]
6. Use correct file extensions per tech stack: Python→.py, Flutter/Dart→.dart, Rust→.rs, Go→.go, Node→.js/.ts

Output JSON only, format:
{{
  "tasks": [
    {{"id": "T1", "title": "Task name", "layer": 1, "deps": [], "type": "code", "assign_to": "coder", "acceptance_criteria": "Acceptance criteria description"}}
  ],
  "requirements": ["dependency package names"]
}}
"""


# ── 技术栈交付模板 ──

DELIVERY_TEMPLATES = {
    "python-tkinter": {
        "test_cmd": "pytest tests/ -v",
        "build_cmd": "pyinstaller --onefile src/main.py -n {project_name}",
        "artifact_ext": ".exe",
        "requirements_auto": ["pyinstaller"],
        "source_ext": [".py"],
    },
    "python-fastapi": {
        "test_cmd": "pytest tests/ -v",
        "build_cmd": "docker build -t {project_name} .",
        "artifact_ext": ".tar",
        "requirements_auto": ["uvicorn", "fastapi", "pytest"],
        "source_ext": [".py"],
    },
    "flutter": {
        "test_cmd": "flutter test",
        "build_cmd": "flutter build apk --release",
        "artifact_ext": ".apk",
        "requirements_auto": [],
        "source_ext": [".dart", ".yaml", ".yml"],
    },
    "rust-cli": {
        "test_cmd": "cargo test",
        "build_cmd": "cargo build --release",
        "artifact_ext": "",
        "requirements_auto": [],
        "source_ext": [".rs"],
    },
    "go-cli": {
        "test_cmd": "go test ./...",
        "build_cmd": "go build -o dist/{project_name} .",
        "artifact_ext": "",
        "requirements_auto": [],
        "source_ext": [".go"],
    },
    "node-react": {
        "test_cmd": "npx vitest run",
        "build_cmd": "npx vite build",
        "artifact_ext": "",
        "requirements_auto": [],
        "source_ext": [".js", ".jsx", ".ts", ".tsx"],
    },
}


class Planner:
    """
    PLANNER 角色：brief → DAG。
    调 Hermes CLI 智能拆解任务。
    零用户确认，直接派发。
    """

    def __init__(self, session_manager=None):
        self.session_manager = session_manager

    async def plan(
        self,
        brief: dict,
        is_iteration: bool = False,
        lang: str = "en",
    ) -> dict:
        """
        brief.json → dag.json。
        """
        tech_stack = self._resolve_tech_stack(brief)
        template = self._get_delivery_template(tech_stack)
        project_name = brief.get("project_name", "project")
        features = brief.get("features", [])

        # 构造 features 文本
        features_text = "\n".join(
            f"  - {f.get('name', '?')} [{f.get('priority', 'P2')}]: {f.get('description', '')}"
            if isinstance(f, dict) else f"  - {f}"
            for f in features
        ) or "  (no specific features)"

        prompt = pick_prompt(_PLAN_PROMPT_ZH, _PLAN_PROMPT_EN, lang).format(
            project_name=project_name,
            tech_stack_json=json.dumps(brief.get("tech_stack", {}), ensure_ascii=False),
            deliverable=brief.get("deliverable", "exe"),
            features_text=features_text,
        )

        prompt_tpl = prompt

        for attempt in range(2):
            try:
                response = await asyncio.to_thread(run_agent, "planner", prompt_tpl, 120)
                dag = self._parse_json(response)
                if dag and "tasks" in dag and len(dag["tasks"]) >= 2:
                    build_cmd = template["build_cmd"].format(project_name=project_name)
                    dag["requirements"] = list(set(
                        template["requirements_auto"] + dag.get("requirements", [])
                    ))
                    dag["tech_stack"] = tech_stack
                    dag["delivery_template"] = {
                        "test_cmd": template["test_cmd"],
                        "build_cmd": build_cmd,
                        "artifact_ext": template["artifact_ext"],
                        "source_ext": template.get("source_ext", [".py"]),
                    }
                    dag["is_iteration"] = is_iteration
                    return dag
                # 解析失败 → 追加修复指令
                prompt_tpl = prompt + "\n\n注意：刚才的 JSON 格式有误，请只输出一个合法的 JSON 对象。"
            except Exception:
                if attempt == 0:
                    prompt_tpl = prompt + "\n\n注意：刚才调用出错，请只输出一个合法的 JSON 对象。"
                else:
                    break

        # LLM 调用失败：返回模板化兜底 DAG
        return self._fallback_dag(brief, tech_stack, template, project_name, is_iteration)

    def _resolve_tech_stack(self, brief: dict) -> str:
        """从 brief 推断技术栈。"""
        ts = brief.get("tech_stack", {})
        lang = ts.get("language", "Python")
        fw = (ts.get("framework", "") or "").lower()
        plat = (ts.get("os", "") or "").lower()

        # Flutter / Dart 检测
        if lang == "Dart" or "flutter" in fw or "dart" in lang.lower():
            return "flutter"
        if "flutter" in plat or "android" in plat or "ios" in plat:
            return "flutter"

        # Python 检测
        if lang == "Python" and "tkinter" in fw:
            return "python-tkinter"
        if lang == "Python" and ("fastapi" in fw or "api" in fw):
            return "python-fastapi"
        if lang == "Python":
            return "python-tkinter"

        # 其他语言
        if lang == "Rust":
            return "rust-cli"
        if lang == "Go":
            return "go-cli"
        if lang in ("Node.js", "JavaScript", "TypeScript", "React", "Vue"):
            return "node-react"

        return "python-tkinter"

    def _get_delivery_template(self, tech_stack: str) -> dict:
        return DELIVERY_TEMPLATES.get(tech_stack, DELIVERY_TEMPLATES["python-tkinter"])

    def _filter_iteration_tasks(self, tasks: list) -> list:
        """迭代时：只保留 code 类型的任务。"""
        return [t for t in tasks if t.get("type") == "code"]

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

    def _fallback_dag(self, brief, tech_stack, template, project_name, is_iteration):
        """Hermes CLI 调用失败时的兜底 DAG。"""
        build_cmd = template["build_cmd"].format(project_name=project_name)
        dag = {
            "tasks": [
                {"id": "T1", "title": "核心逻辑", "layer": 1, "deps": [], "type": "code", "assign_to": "coder",
                 "acceptance_criteria": brief.get("description", "")},
                {"id": "T2", "title": "UI/接口层", "layer": 1, "deps": [], "type": "code", "assign_to": "coder",
                 "acceptance_criteria": "界面完成"},
                {"id": "T3", "title": "写测试用例", "layer": 1, "deps": [], "type": "test", "assign_to": "tester",
                 "acceptance_criteria": "覆盖主要功能"},
                {"id": "T4", "title": "集成接线", "layer": 2, "deps": ["T1", "T2"], "type": "code", "assign_to": "coder",
                 "acceptance_criteria": "UI 与逻辑对接"},
                {"id": "T5", "title": "运行测试", "layer": 3, "deps": ["T3", "T4"], "type": "test", "assign_to": "toolman"},
                {"id": "T6", "title": "打包交付", "layer": 4, "deps": ["T5"], "type": "build", "assign_to": "toolman"},
            ],
            "requirements": template["requirements_auto"],
            "tech_stack": tech_stack,
            "delivery_template": {
                "test_cmd": template["test_cmd"],
                "build_cmd": build_cmd,
                "artifact_ext": template["artifact_ext"],
                "source_ext": template.get("source_ext", [".py"]),
            },
            "is_iteration": is_iteration,
        }
        if is_iteration:
            dag["tasks"] = self._filter_iteration_tasks(dag["tasks"])
        return dag


def get_template(tech_stack: str) -> dict:
    return DELIVERY_TEMPLATES.get(tech_stack, DELIVERY_TEMPLATES["python-tkinter"])
