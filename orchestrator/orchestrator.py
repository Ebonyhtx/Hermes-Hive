"""
HIVE v4.1 — 编排器主循环

职责:
1. 驱动 7 状态机
2. 编排各角色按阶段执行
3. 处理错误和迭代循环
4. 事件通知
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

# 状态机
from orchestrator.machine import HiveMachine

# Infrastructure
from orchestrator.infrastructure.session_manager import SessionManager
from orchestrator.infrastructure.sandbox import Sandbox
from orchestrator.infrastructure.cost_tracker import CostTracker
from orchestrator.infrastructure.validator import safe_validate, ValidationError
from orchestrator.dashboard.events import broadcast_event

# Roles
from orchestrator.roles.arc import Architect
from orchestrator.roles.planner import Planner
from orchestrator.roles.coder import CoderPool
from orchestrator.roles.tester import Tester
from orchestrator.roles.reviewer import Reviewer
from orchestrator.roles.toolman import Toolman


# ── 事件回调类型 ──

EventHandler = Callable[[str, dict], None]


# ── 默认配置 ──

_HIVE_V4_DIR = Path.home() / ".hermes" / "hive-v4"
_BUILDS_DIR = _HIVE_V4_DIR / "builds"


class HiveOrchestrator:
    """
    编排器主循环。
    每个 session 对应一个 HiveOrchestrator 实例。
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        project_name: Optional[str] = None,
        on_event: Optional[EventHandler] = None,
        max_workers: int = 3,
    ):
        if not session_id:
            raise ValueError("session_id is required — use SessionManager.create_session() first")
        self.session_id = session_id
        self.project_name = project_name or ""
        self.on_event = on_event  # 事件回调（Dashboard 推送用）
        self.max_workers = max_workers

        # 状态机
        self.machine = HiveMachine()

        # 基础设施
        self.sandbox = Sandbox()
        self.cost_tracker = CostTracker()
        self.workspace_path = _BUILDS_DIR / self.session_id

        # Roles
        self.architect = Architect(cost_tracker=self.cost_tracker)
        self.planner = Planner()
        self.coder_pool = CoderPool(max_workers=max_workers)
        self.tester = Tester()
        self.reviewer = Reviewer()
        self.toolman = Toolman(cost_tracker=self.cost_tracker)

        # 构建上下文
        self.brief: Optional[dict] = None
        self.dag: Optional[dict] = None
        self.build_result: Optional[dict] = None
        self.review_result: Optional[dict] = None
        self.version: int = 0
        self._lang: str = "en"

    # ── 错误恢复 ──

    async def _retry_with_backoff(
        self,
        fn,
        max_retries: int = 3,
        base_delay: float = 2.0,
        description: str = "",
    ):
        """带指数退避的重试。"""
        last_error = None
        for attempt in range(max_retries):
            try:
                result = fn()
                if hasattr(result, '__await__'):
                    return await result
                return result
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    await self._emit("retry", {
                        "attempt": attempt + 1,
                        "max": max_retries,
                        "delay": delay,
                        "error": str(e),
                        "description": description,
                    })
                    await asyncio.sleep(delay)
        raise last_error or RuntimeError(f"{description} 失败")

    async def _with_cost_check(self, fn):
        """成本检查包装器。"""
        limits = self.cost_tracker.check_limits(self.session_id)
        if not limits["within_limit"]:
            raise RuntimeError(f"成本超限: {limits['warnings']}")
        result = fn()
        if hasattr(result, '__await__'):
            return await result
        return result

    # ── 公共 API ──

    async def build(self, description: str, lang: str = "en") -> dict:
        """
        执行完整构建管线。

        Args:
            description: 用户需求描述
            lang: 语言

        Returns:
            {"session_id": str, "version": int, "status": str, "message": str}
        """
        await self._emit("build_start", {"session_id": self.session_id, "description": description[:100]})

        self._lang = lang

        try:
            # 成本预检
            await self._with_cost_check(lambda: None)

            # Session 已在 mcp_server 中创建，此处只需确保持久化状态
            SessionManager.update_state(self.session_id, "translating", "translating")

            # Phase 1: ARC 转译（重试 3 次，退避 2s/4s/8s）
            await self._retry_with_backoff(
                lambda: self._phase_translating(description, lang),
                max_retries=3, base_delay=2.0, description="ARC 转译"
            )

            # Phase 2: PLANNER 编排（重试 2 次）
            await self._retry_with_backoff(
                lambda: self._phase_planning(),
                max_retries=2, base_delay=2.0, description="PLANNER 编排"
            )

            # Phase 3: CODER + TESTER 执行（内部自带重试）
            await self._phase_executing()

            # 检查全部任务是否 failed
            build_result = self.build_result or {}
            failed = build_result.get("failed", [])
            if len(failed) >= len(build_result.get("completed", []) + failed):
                raise RuntimeError(f"全部任务失败: {failed}")

            # Phase 4: REVIEWER 审查
            await self._phase_reviewing()

            # Phase 5: TOOLMAN 交付
            await self._retry_with_backoff(
                lambda: self._phase_delivery(),
                max_retries=2, base_delay=3.0, description="交付"
            )

            # 完成
            self.machine.delivery_ready()
            SessionManager.update_state(self.session_id, "done", "done")
            await self._save_version("构建完成")

            result = {
                "session_id": self.session_id,
                "version": self.version,
                "status": "done",
                "message": f"构建完成，版本 {self.version}",
            }

        except Exception as e:
            self.machine.fail_build()
            error_msg = str(e)
            SessionManager.update_state(self.session_id, "failed", "failed")
            SessionManager.update_error(self.session_id, error_msg)
            await self._emit("build_error", {"session_id": self.session_id, "error": error_msg})
            result = {
                "session_id": self.session_id,
                "version": self.version,
                "status": "failed",
                "message": error_msg,
            }

        await self._emit("build_end", result)
        return result

    async def iterate(self, request: str) -> dict:
        """
        迭代修改已有项目。

        Args:
            request: 修改请求描述

        Returns:
            {"session_id": str, "version": int, "status": str, "message": str}
        """
        await self._emit("iterate_start", {"session_id": self.session_id, "request": request})

        if not self.brief:
            # 从持久化恢复
            session = SessionManager.get_session(self.session_id)
            if session and session.get("brief"):
                self.brief = session["brief"]

        try:
            # 迭代流程
            self.machine.start_iteration()
            self.machine.start_build()

            await self._phase_translating(request, "zh", existing_brief=self.brief)
            await self._phase_planning(is_iteration=True)
            await self._phase_executing()
            await self._phase_reviewing()
            await self._phase_delivery()

            self.machine.delivery_ready()
            await self._save_version(f"迭代: {request[:50]}")

            SessionManager.create_version(
                self.session_id, self.version,
                summary=f"迭代: {request[:100]}"
            )

            result = {
                "session_id": self.session_id,
                "version": self.version,
                "status": "done",
                "message": f"迭代完成，版本 {self.version}",
            }
        except Exception as e:
            self.machine.fail_build()
            result = {
                "session_id": self.session_id,
                "version": self.version,
                "status": "failed",
                "message": str(e),
            }

        await self._emit("iterate_end", result)
        return result

    def cancel(self) -> dict:
        """取消当前构建。"""
        self.machine.cancel_build()
        SessionManager.update_state(self.session_id, "cancelled", "cancelled")
        self.sandbox.cleanup(self.session_id)
        return {"session_id": self.session_id, "status": "cancelled"}

    def get_status(self) -> dict:
        """获取当前构建状态。"""
        return {
            "session_id": self.session_id,
            "project_name": self.project_name,
            "state": self.machine.state,
            "version": self.version,
            "has_brief": self.brief is not None,
            "has_dag": self.dag is not None,
            "cost": self.cost_tracker.check_limits(self.session_id),
        }

    # ── 阶段执行（内部） ──

    async def _phase_translating(
        self, description: str, lang: str = "en",
        existing_brief: Optional[dict] = None,
    ):
        """ARC 转译阶段。"""
        self.machine.start_build()
        SessionManager.update_state(self.session_id, "translating", "translating")
        await self._emit("phase", {"phase": "translating", "status": "start"})

        brief = await self.architect.translate(description, lang, existing_brief)
        SessionManager.update_brief(self.session_id, brief)
        self.brief = brief

        # 检查置信度
        low_conf = self.architect.check_confidence(brief)
        if low_conf:
            await self._emit("confidence_warning", {
                "session_id": self.session_id,
                "items": low_conf,
                "message": "有几个选项拿不准，已按默认处理（可在 Dashboard 查看）",
            })

        self.machine.brief_ready()
        await self._emit("phase", {"phase": "translating", "status": "done"})

    async def _phase_planning(self, is_iteration: bool = False):
        """PLANNER 编排阶段。"""
        SessionManager.update_state(self.session_id, "planning", "planning")
        await self._emit("phase", {"phase": "planning", "status": "start"})

        dag = await self.planner.plan(self.brief, is_iteration=is_iteration, lang=self._lang)
        SessionManager.update_dag(self.session_id, dag)
        self.dag = dag

        self.machine.plan_ready()
        await self._emit("phase", {"phase": "planning", "status": "done", "tasks": len(dag.get("tasks", []))})

    async def _phase_executing(self):
        """CODER + TESTER 执行阶段。"""
        SessionManager.update_state(self.session_id, "executing", "executing")
        await self._emit("phase", {"phase": "executing", "status": "start"})

        self.workspace_path.mkdir(parents=True, exist_ok=True)

        # 获取编码和测试任务
        dag = self.dag or {}
        all_tasks = dag.get("tasks", [])
        code_tasks = [t for t in all_tasks if t.get("type") == "code"]
        test_tasks = [t for t in all_tasks if t.get("type") == "test"]

        # 并行执行 CODER + TESTER
        coder_task = None
        tester_task = None

        if code_tasks:
            coder_task = asyncio.create_task(
                asyncio.wait_for(
                    self.coder_pool.execute_dag(
                        {"tasks": code_tasks},
                        self.workspace_path,
                        self.session_id,
                        on_progress=lambda tid, status, *a: (
                            self._emit("task_progress", {"task_id": tid, "status": status, "attempts": a[0] if a else 1})
                            if status != "file_ready"
                            else self._emit("file_ready", {"task_id": tid, "files": a[0] if a else []})
                        ),
                    ),
                    timeout=self.coder_pool.task_timeout_s * 2,  # DAG 总超时 = 单任务超时 × 2
                )
            )

        if test_tasks:
            tester_task = asyncio.create_task(
                asyncio.wait_for(
                    self.tester.write_tests(self.brief, self.workspace_path, test_tasks),
                    timeout=120,
                )
            )

        # 等待全部完成（Coder + Tester 并行）
        all_tasks = []
        if coder_task:
            all_tasks.append(coder_task)
        if tester_task:
            all_tasks.append(tester_task)

        try:
            results = await asyncio.gather(*all_tasks) if all_tasks else []
            if coder_task:
                self.build_result = results[0] if results else {"completed": [], "failed": []}
            if tester_task:
                # tester_task 的索引在 gather 结果中：如果 coder 也在列表中，索引 1
                test_idx = 1 if coder_task else 0
                test_result = results[test_idx] if len(results) > test_idx and tester_task else None
                if test_result and tester_task:
                    await self._emit("test_files_ready", test_result)
        except asyncio.TimeoutError:
            await self._emit("phase", {"phase": "executing", "status": "timeout",
                                        "message": "执行超时"})
            self.build_result = {"completed": [], "failed": [t["id"] for t in code_tasks],
                                 "error": "执行超时"}
        except Exception as e:
            await self._emit("phase", {"phase": "executing", "status": "error",
                                        "message": f"执行失败: {e}"})
            self.build_result = {"completed": [], "failed": [t["id"] for t in code_tasks],
                                 "error": str(e)}

        self.machine.code_ready()
        await self._emit("phase", {"phase": "executing", "status": "done",
                                    "completed": self.build_result.get("completed", []),
                                    "failed": self.build_result.get("failed", [])})

    async def _phase_reviewing(self):
        """REVIEWER 审查阶段。"""
        SessionManager.update_state(self.session_id, "reviewing", "reviewing")
        await self._emit("phase", {"phase": "reviewing", "status": "start"})

        review = await self.reviewer.review(
            self.workspace_path,
            self.brief or {},
            version=self.version,
        )
        self.review_result = review

        await self._emit("phase", {"phase": "reviewing", "status": "done",
                                    "overall": review.get("overall", "?")})
        # 推送审查报告详情
        await self._emit("review_report", {
            "overall": review.get("overall", "?"),
            "summary": review.get("summary", ""),
            "layers": {
                name: {"status": data.get("status")}
                for name, data in review.get("layers", {}).items()
            },
        })

    async def _phase_delivery(self):
        """TOOLMAN 交付阶段。"""
        SessionManager.update_state(self.session_id, "testing", "testing")
        await self._emit("phase", {"phase": "testing", "status": "start"})

        tech_stack = (self.dag or {}).get("tech_stack", "python-tkinter")
        delivery = await self.toolman.deliver(
            dag=self.dag or {},
            workspace_path=self.workspace_path,
            project_name=self.project_name,
            tech_stack=tech_stack,
            on_progress=lambda step, status: self._emit("delivery_progress", {
                "step": step, "status": status,
            }),
        )

        # 检视交付结果
        del_status = delivery.get("status", "unknown")
        artifacts = delivery.get("artifacts", [])

        if del_status == "prerequisites_missing":
            raise RuntimeError(delivery.get("error", f"缺少构建工具: {tech_stack}"))

        if del_status in ("build_failed", "partial_failure") and not artifacts:
            raise RuntimeError(f"打包失败: 未产出成品文件。测试结果: {delivery.get('test_results', {})}")

        await self._emit("phase", {"phase": "testing", "status": "done",
                                    "artifacts": artifacts})

    # ── 辅助方法 ──

    async def _save_version(self, summary: str = ""):
        """记录版本。"""
        self.version += 1
        SessionManager.create_version(self.session_id, self.version, summary=summary)

    async def _emit(self, event: str, data: dict):
        """发出事件（Dashboard 推送用）。"""
        data["event"] = event
        data["session_id"] = self.session_id
        data["timestamp"] = datetime.utcnow().isoformat()
        # 推送到 Dashboard WebSocket
        await broadcast_event(event, data)
        if self.on_event:
            self.on_event(event, data)
