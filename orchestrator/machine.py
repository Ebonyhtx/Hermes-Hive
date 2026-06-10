"""
HIVE v4.1 — 7 状态机

状态: idle → translating → planning → executing → testing → done
                                              ↓ (迭代循环)
                                         idle ← done

对比 v3（12 状态 / 22 转换 / 4 个用户确认点）：
- v4: 7 状态 / 6 转换 / 0 个用户确认点
"""

from transitions import Machine


class HiveMachine:
    """
    7 状态，6 转换。

    用法:
        machine = HiveMachine()
        machine.start_build()      # idle → translating
        machine.brief_ready()      # translating → planning
        machine.plan_ready()       # planning → executing
        machine.code_ready()       # executing → testing
        machine.delivery_ready()   # testing → done
        machine.start_iteration()  # done → idle (迭代)
        machine.cancel_build()     # * → cancelled
        machine.fail_build()       # * → idle (错误回退)
    """

    states = [
        "idle",          # 初始 / 空闲
        "translating",   # ARC 转译中
        "planning",      # PLANNER 编排中
        "executing",     # CODER + TESTER 执行中
        "testing",       # TOOLMAN 测试 + 打包中
        "done",          # 完成
        "cancelled",     # 用户取消
    ]

    transitions = [
        # 正常流程
        {"trigger": "start_build",     "source": "idle",        "dest": "translating"},
        {"trigger": "brief_ready",     "source": "translating", "dest": "planning"},
        {"trigger": "plan_ready",      "source": "planning",    "dest": "executing"},
        {"trigger": "code_ready",      "source": "executing",   "dest": "testing"},
        {"trigger": "delivery_ready",  "source": "testing",     "dest": "done"},
        # 迭代循环: done → idle → translating（两步转换）
        {"trigger": "start_iteration", "source": "done",        "dest": "idle"},
        {"trigger": "start_iteration", "source": "idle",        "dest": "translating"},
        # 取消: 任意状态 → cancelled
        {"trigger": "cancel_build",    "source": "*",           "dest": "cancelled"},
        # 错误回退: 任意状态 → idle（保留上下文）
        {"trigger": "fail_build",       "source": "*",           "dest": "idle"},
    ]

    def __init__(self):
        self.machine = Machine(
            model=self,
            states=HiveMachine.states,
            transitions=HiveMachine.transitions,
            initial="idle",
            auto_transitions=False,
            ignore_invalid_triggers=True,  # 不会因为无效转换抛异常
        )

        # 保存状态转换历史
        self._history: list[dict] = []

        # 为每个状态注册进入/退出回调
        for state in self.states:
            self.machine.add_state(
                state,
                on_enter=[lambda s=state: self._on_enter(s)],
                on_exit=[lambda s=state: self._on_exit(s)],
            )

    def _on_enter(self, state: str):
        self._history.append({"event": "enter", "state": state})
        # 这里可以触发 Dashboard 事件推送

    def _on_exit(self, state: str):
        self._history.append({"event": "exit", "state": state})

    @property
    def current(self) -> str:
        """当前状态名。"""
        return self.state

    @property
    def is_active(self) -> bool:
        """是否在活跃构建中（非 idle / done / cancelled）。"""
        return self.state not in ("idle", "done", "cancelled")

    @property
    def history(self) -> list[dict]:
        """状态转换历史。"""
        return self._history

    def reset(self):
        """重置到 idle（不触发事件）。"""
        self._history = []
        # 直接设置状态，不经过转换
        object.__setattr__(self, "state", "idle")
