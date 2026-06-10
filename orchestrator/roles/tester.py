"""
HIVE v4.1 — TESTER 独立测试写手

职责: 基于 brief 中的验收标准写测试用例。
只读 brief，调用 Hermes CLI 生成有意义的测试断言。
与 CODER 并行执行（Layer 1），互不读取对方产出。
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

from orchestrator.hermes_bridge import run_agent


_TESTER_PROMPT = """你是一位测试工程师。你的工作是基于需求描述编写 pytest 测试用例。

核心规则：
1. **不要假设实现细节** — 只基于需求编写测试
2. **不要读取已有代码** — 你的测试应当能验证任意实现
3. **每个测试文件独立可运行** — 不依赖其他测试文件
4. **覆盖场景**：基本功能、边界条件、错误处理

需求描述：
{description}

功能名称：{feature_name}
功能介绍：{feature_description}
验收标准：{acceptance_criteria}

请输出完整的 pytest 测试文件内容，包含 import 语句、测试类和测试方法。
只输出 Python 代码，不要输出解释。代码必须语法正确。
"""


class Tester:
    """
    独立测试写手。
    与 CODER 并行执行（Layer 1），互不读取对方产出。
    """

    async def write_tests(
        self,
        brief: dict,
        workspace_path: Path,
        tasks: Optional[list] = None,
    ) -> dict:
        """
        根据 brief 写测试用例。

        Args:
            brief: brief.json dict
            workspace_path: workspace 路径
            tasks: 需要写测试的任务列表

        Returns:
            {"test_files": [str], "test_count": int, "coverage_areas": [str]}
        """
        test_dir = workspace_path / "tests"
        test_dir.mkdir(parents=True, exist_ok=True)

        features = brief.get("features", [])
        test_files = []
        coverage_areas = []
        seen_names: set[str] = set()

        for feat in features:
            name = feat.get("name", "unknown") if isinstance(feat, dict) else feat
            description = feat.get("description", "") if isinstance(feat, dict) else ""
            criteria = feat.get("acceptance_criteria", description) if isinstance(feat, dict) else description
            # 使用安全的英文文件名（中文名转化为拼音前缀）
            safe_name = self._safe_filename(name)
            # 去重
            if safe_name in seen_names:
                safe_name = f"{safe_name}_{len(seen_names)}"
            seen_names.add(safe_name)
            test_file = test_dir / f"test_{safe_name}.py"

            # 尝试通过 Hermes CLI 生成有意义的测试
            if not test_file.exists():
                content = await self._generate_test_via_llm(
                    brief.get("description", ""),
                    name, description, criteria,
                )
                if content:
                    test_file.write_text(content, encoding="utf-8")
                else:
                    # Hermes CLI 不可用时的 fallback 模板
                    test_file.write_text(
                        self._build_test_template(name, feat if isinstance(feat, dict) else {})
                    )

            test_files.append(str(test_file.relative_to(workspace_path)))
            coverage_areas.append(name)

        return {
            "test_files": test_files,
            "test_count": len(test_files),
            "coverage_areas": coverage_areas,
        }

    async def _generate_test_via_llm(
        self,
        description: str,
        feature_name: str,
        feature_description: str,
        acceptance_criteria: str,
    ) -> Optional[str]:
        """通过 Hermes CLI 生成有意义的测试代码。"""
        prompt = _TESTER_PROMPT.format(
            description=description[:500],
            feature_name=feature_name,
            feature_description=feature_description[:500],
            acceptance_criteria=acceptance_criteria[:500],
        )
        try:
            response = await asyncio.to_thread(run_agent, "tester", prompt, 60)
            code = self._extract_code(response)
            if code and len(code) > 50:
                return code
        except Exception:
            pass
        return None

    @staticmethod
    def _safe_filename(name: str) -> str:
        """将中文/特殊字符名转为安全的 ASCII 文件名。"""
        # 保留已有英文字母、数字、下划线、连字符
        safe = "".join(c for c in name if c.isascii() and (c.isalnum() or c in "_-"))
        # 如果没有 ASCII 字符，用 feature 加哈希前缀
        if not safe:
            safe = f"feature_{abs(hash(name)) % 10000}"
        return safe[:40].strip("_-")

    def _extract_code(self, text: str) -> Optional[str]:
        """从 LLM 响应中提取 Python 代码块。"""
        text = text.strip()
        # 尝试提取 ```python ... ``` 代码块
        if "```python" in text:
            start = text.find("```python") + 10
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()
        # 尝试提取 ``` ... ``` 代码块
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()
        # 没有代码块标记，直接返回（假设整个输出就是 Python 代码）
        if text and not text.startswith("```"):
            return text
        return None

    def _build_test_template(self, feature_name: str, feat: dict) -> str:
        """
        构建测试文件模板（Hermes CLI 不可用时的 fallback）。
        """
        description = feat.get("description", "") if isinstance(feat, dict) else ""
        return f'''"""
测试: {feature_name}
{description}

注意: 基于需求描述编写，不假设实现细节。
"""

import pytest


class Test{feature_name.replace(" ", "").replace("_", "").capitalize()}:
    """测试 {feature_name}"""

    def test_basic_functionality(self):
        """基本功能测试"""
        # TODO: 根据验收标准编写测试
        pass

    def test_edge_cases(self):
        """边界情况测试"""
        # TODO: 测试边界条件和异常输入
        pass

    def test_error_handling(self):
        """错误处理测试"""
        # TODO: 测试错误输入的处理
        pass
'''

    def _build_tester_prompt(self, brief: dict, task: dict) -> str:
        """
        构建发给 Hermes CLI 的 tester prompt。
        注意: 不得包含 src/ 目录中已有代码的细节。
        """
        return (
            f"## 需求\n"
            f"{brief.get('description', '')}\n\n"
            f"## 验收标准\n"
            f"{task.get('acceptance_criteria', '')}\n\n"
            f"## 工作说明\n"
            f"在 tests/ 目录下编写 pytest 测试用例。\n"
            f"测试应覆盖: 基本功能、边界条件、错误处理。\n"
            f"只基于需求编写，不假设实现细节。"
        )
