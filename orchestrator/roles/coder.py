"""
HIVE v4.1 — CODER 工人池

职责: 管理多个并发 Worker 执行编码任务。
纯 Hermes CLI，无 reasonix 依赖。
"""

import asyncio
from pathlib import Path
from typing import Callable, Optional, Awaitable

from orchestrator.hermes_bridge import run_agent
from orchestrator.infrastructure.sandbox import Sandbox


class CoderPool:
    """
    Worker 池管理器。
    管理多个并发 Worker 执行编码任务。
    """

    def __init__(
        self,
        max_workers: int = 3,
        task_timeout_s: int = 600,
        max_retries: int = 3,
    ):
        self.max_workers = max_workers
        self.task_timeout_s = task_timeout_s
        self.max_retries = max_retries
        self._semaphore = asyncio.Semaphore(max_workers)
        self.sandbox = Sandbox()

    async def execute_dag(
        self,
        dag: dict,
        workspace_path: Path,
        session_id: str,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """
        执行完整 DAG。

        执行逻辑:
        1. 按 layer 分组任务
        2. 同层无依赖任务全部并行
        3. 有依赖任务等前序完成
        4. 失败自动重试（max_retries 次）

        Returns:
            {"completed": [task_ids], "failed": [task_ids], "results": {...}}
        """
        tasks = dag.get("tasks", [])
        # 根据技术栈获取源文件扩展名
        self._source_ext = (dag.get("delivery_template", {}) or {}).get("source_ext", [".py"])
        if not tasks:
            return {"completed": [], "failed": [], "results": {}}

        # 按 layer 分组
        layers: dict[int, list[dict]] = {}
        for t in tasks:
            layers.setdefault(t["layer"], []).append(t)

        completed: dict[str, dict] = {}
        failed: dict[str, dict] = {}

        for layer_num in sorted(layers.keys()):
            layer_tasks = layers[layer_num]

            # 检查每个任务的依赖是否已满足
            ready_tasks = []
            for t in layer_tasks:
                deps = t.get("deps", [])
                if all(d in completed or d in failed for d in deps):
                    # 如果有关键依赖失败，此任务也标记为失败
                    if any(d in failed for d in deps):
                        failed[t["id"]] = {
                            "task_id": t["id"],
                            "status": "failed",
                            "error": f"依赖 {[d for d in deps if d in failed][0]} 失败",
                        }
                        continue
                    ready_tasks.append(t)

            if not ready_tasks:
                continue

            # 并行执行 ready_tasks
            tasks_coros = [
                self._execute_single_task(t, workspace_path, on_progress, self._source_ext)
                for t in ready_tasks
            ]
            results = await asyncio.gather(*tasks_coros)

            for result in results:
                tid = result["task_id"]
                if result["status"] == "success":
                    completed[tid] = result
                else:
                    failed[tid] = result

        return {
            "completed": list(completed.keys()),
            "failed": list(failed.keys()),
            "results": {**completed, **failed},
        }

    async def _execute_single_task(
        self,
        task: dict,
        workspace_path: Path,
        on_progress: Optional[Callable] = None,
        source_ext: Optional[list] = None,
    ) -> dict:
        """
        执行单个编码任务。
        调 Hermes CLI 完成。

        Returns:
            {"task_id": str, "status": str, "files": [str], "summary": str, "error": str}
        """
        async with self._semaphore:
            if on_progress:
                result = on_progress(task["id"], "start")
                if hasattr(result, '__await__'):
                    asyncio.create_task(result)

            for attempt in range(self.max_retries):
                try:
                    result = await asyncio.wait_for(
                        self._call_hermes(task, workspace_path, source_ext),
                        timeout=self.task_timeout_s,
                    )
                    if result.get("status") == "success":
                        if on_progress:
                            r = on_progress(task["id"], "done")
                            if hasattr(r, '__await__'):
                                asyncio.create_task(r)
                        # 增量交付：报告任务产出的文件
                        files = result.get("files", [])
                        if files and on_progress:
                            r = on_progress(task["id"], "file_ready", files)
                            if hasattr(r, '__await__'):
                                asyncio.create_task(r)
                        return result
                    else:
                        if on_progress:
                            r = on_progress(task["id"], "retry", attempt + 1)
                            if hasattr(r, '__await__'):
                                asyncio.create_task(r)
                except asyncio.TimeoutError:
                    if on_progress:
                        r = on_progress(task["id"], "timeout", attempt + 1)
                        if hasattr(r, '__await__'):
                            asyncio.create_task(r)

            # 所有重试耗尽
            if on_progress:
                r = on_progress(task["id"], "failed")
                if hasattr(r, '__await__'):
                    asyncio.create_task(r)
            return {
                "task_id": task["id"],
                "status": "failed",
                "files": [],
                "summary": f"任务 {task['title']} 失败（{self.max_retries} 次重试后）",
                "error": "超出最大重试次数",
            }

    async def _call_hermes(self, task: dict, workspace_path: Path, source_ext: Optional[list] = None) -> dict:
        """
        调用 Hermes CLI 执行编码任务。
        source_ext: 源文件扩展名列表，如 [".py", ".dart", ".rs"]
        """
        prompt = self._build_coder_prompt(task, workspace_path)
        exts = source_ext or [".py"]

        try:
            # 使用 run_agent 调用 Hermes CLI（在独立线程中执行，避免阻塞事件循环）
            response = await asyncio.to_thread(run_agent, "coder", prompt, timeout=self.task_timeout_s)

            # 根据技术栈查找生成的文件
            src_dir = workspace_path / "src"
            files = []
            if src_dir.exists():
                for ext in exts:
                    files.extend(
                        str(f.relative_to(workspace_path)) for f in src_dir.rglob(f"*{ext}")
                    )

            return {
                "task_id": task["id"],
                "status": "success" if files else "partial",
                "files": files,
                "summary": f"实现 {task['title']}",
                "error": "",
            }
        except Exception as e:
            return {
                "task_id": task["id"],
                "status": "failed",
                "files": [],
                "summary": f"Hermes CLI 调用失败",
                "error": str(e),
            }

    def _build_coder_prompt(self, task: dict, workspace_path: Path) -> str:
        """构建发给 Hermes CLI 的 coder prompt。"""
        desc = task.get('description', '')
        # 从验收标准中提取技术栈信息，通知 CODER 使用何种语言
        ac = task.get('acceptance_criteria', '')
        tech_hint = ''
        if any(kw in (ac + desc).lower() for kw in ['flutter', 'dart']):
            tech_hint = '\n技术栈: Flutter/Dart - 代码写入 src/lib/ 目录'
        elif any(kw in (ac + desc).lower() for kw in ['rust', 'cargo']):
            tech_hint = '\n技术栈: Rust - 代码写入 src/ 目录'
        elif any(kw in (ac + desc).lower() for kw in ['go ', 'golang']):
            tech_hint = '\n技术栈: Go - 代码写入 src/ 目录'
        elif any(kw in (ac + desc).lower() for kw in ['react', 'vue', 'javascript', 'typescript']):
            tech_hint = '\n技术栈: Node.js - 代码写入 src/ 目录'
        else:
            tech_hint = '\n技术栈: Python - 代码写入 src/ 目录'
        return (
            f"## 任务\n"
            f"{task.get('title', 'untitled')}\n\n"
            f"## 描述\n"
            f"{desc}\n\n"
            f"## 验收标准\n"
            f"{ac}\n\n"
            f"## 工作说明\n"
            f"工作目录: {workspace_path}\n"
            f"代码写入: src/{'lib/' if 'flutter' in (desc+ac).lower() or 'dart' in (desc+ac).lower() else ''}\n"
            f"确保代码语法正确。完成后返回文件列表。"
            f"{tech_hint}"
        )
