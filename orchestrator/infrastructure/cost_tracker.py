"""
HIVE v4.1 — 成本跟踪器

职责:
- 记录每次 Hermes CLI 调用的 token/成本
- 统计当前 session 的总成本
- 检查是否超过预算上限
"""

from typing import Optional

from orchestrator.infrastructure.session_manager import SessionManager

# 默认成本估算（每 1000 tokens）
_COST_PER_1K_INPUT_USD = 0.00015    # DeepSeek V4 Flash 输入
_COST_PER_1K_OUTPUT_USD = 0.00060   # DeepSeek V4 Flash 输出

# 默认预算上限
_DEFAULT_MAX_PER_BUILD_USD = 5.00
_DEFAULT_MAX_DAILY_USD = 20.00
_DEFAULT_WARN_AT_USD = 1.00


class CostTracker:
    """成本跟踪与预算管理。"""

    def __init__(
        self,
        max_per_build_usd: float = _DEFAULT_MAX_PER_BUILD_USD,
        max_daily_usd: float = _DEFAULT_MAX_DAILY_USD,
        warn_at_usd: float = _DEFAULT_WARN_AT_USD,
    ):
        self.max_per_build_usd = max_per_build_usd
        self.max_daily_usd = max_daily_usd
        self.warn_at_usd = warn_at_usd

    def estimate(
        self,
        tasks: int,
        avg_tokens_per_task: int = 5000,
    ) -> dict:
        """
        估算构建成本。

        Args:
            tasks: 任务数量
            avg_tokens_per_task: 每个任务平均 token 数

        Returns:
            {"estimated_tokens": int, "estimated_cost_usd": float, "tasks": int}
        """
        total_tokens = tasks * avg_tokens_per_task
        # 粗略估计：70% 输入 / 30% 输出
        input_cost = total_tokens * 0.7 / 1000 * _COST_PER_1K_INPUT_USD
        output_cost = total_tokens * 0.3 / 1000 * _COST_PER_1K_OUTPUT_USD
        return {
            "estimated_tokens": total_tokens,
            "estimated_cost_usd": round(input_cost + output_cost, 4),
            "tasks": tasks,
        }

    def log(
        self,
        session_id: str,
        phase: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: Optional[float] = None,
    ):
        """
        记录一次成本消耗。

        如果 cost_usd 未提供，根据 tokens 自动估算。
        """
        if cost_usd is None:
            cost_usd = (
                tokens_in / 1000 * _COST_PER_1K_INPUT_USD
                + tokens_out / 1000 * _COST_PER_1K_OUTPUT_USD
            )
        SessionManager.log_cost(session_id, phase, tokens_in, tokens_out, cost_usd)

    def check_limits(self, session_id: str) -> dict:
        """
        检查是否超出预算。

        Returns:
            {"within_limit": bool, "current_cost": float, "max_cost": float, "warnings": [str]}
        """
        session = SessionManager.get_session(session_id)
        if not session:
            return {"within_limit": True, "current_cost": 0, "max_cost": self.max_per_build_usd, "warnings": []}

        current = session.get("total_cost_usd", 0.0)
        warnings = []

        if current >= self.max_per_build_usd:
            warnings.append(f"成本已达上限 ${current:.2f}/${self.max_per_build_usd:.2f}")
            return {
                "within_limit": False,
                "current_cost": current,
                "max_cost": self.max_per_build_usd,
                "warnings": warnings,
            }

        if current >= self.warn_at_usd:
            warnings.append(f"成本警告: ${current:.2f}（阈值 ${self.warn_at_usd:.2f}）")

        return {
            "within_limit": current < self.max_per_build_usd,
            "current_cost": round(current, 4),
            "max_cost": self.max_per_build_usd,
            "warnings": warnings,
        }
