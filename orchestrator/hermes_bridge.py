"""Hermes Agent 桥接层 — 完全隔离的子进程调用

所有 Agent LLM 调用通过 hermes_runner.py 在独立进程中执行。
不共享 MCP Server 的 stdio、进程组、环境变量。
"""

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from orchestrator.i18n import TXT, tt


def run_agent(
    profile: str,
    prompt: str,
    timeout: int = 300,
    workdir: str = "",
) -> str:
    """运行 Hermes Agent 并返回响应文本

    通过 hermes_runner.py 在独立进程中执行，完全隔离。

    Args:
        profile: architect | planner | coder | reviewer | free_agent
        prompt: 发给 Agent 的指令
        timeout: 超时秒数
        workdir: 子进程工作目录（让 terminal/pytest 在正确路径执行）

    Returns:
        Agent 响应文本
    """
    # 找 runner 脚本
    runner = _find_runner()
    if not runner:
        return _fallback(profile, "runner not found")

    try:
        # 写 prompt 到临时文件
        prompt_id = uuid.uuid4().hex[:8]
        tmp_dir = Path(tempfile.gettempdir()) / "hive_runner"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        prompt_file = tmp_dir / f"prompt_{prompt_id}.txt"
        result_file = tmp_dir / f"result_{prompt_id}.json"

        prompt_file.write_text(prompt, encoding="utf-8")

        # 调用独立运行器
        args = [sys.executable, runner, profile, str(prompt_file), str(result_file)]
        if workdir:
            args.append(workdir)
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout + 10,  # 多给点余量
        )

        # 读结果
        if result_file.exists():
            data = json.loads(result_file.read_text(encoding="utf-8"))
            if data.get("ok"):
                return data["response"]
            else:
                return _fallback(profile, data.get("error", "unknown error"))
        else:
            return _fallback(profile, f"no result (exit {proc.returncode})")

    except subprocess.TimeoutExpired:
        return _fallback(profile, f"timeout {timeout}s")
    except Exception as e:
        return _fallback(profile, str(e))

    finally:
        # 清理临时文件
        try:
            if prompt_file.exists():
                prompt_file.unlink()
            if result_file.exists():
                result_file.unlink()
        except Exception:
            pass


def _find_runner() -> Optional[str]:
    """查找 hermes_runner.py"""
    # 优先同目录
    runner = Path(__file__).parent / "hermes_runner.py"
    if runner.exists():
        return str(runner)
    # 备选
    runner2 = Path(__file__).parent.parent / "orchestrator" / "hermes_runner.py"
    if runner2.exists():
        return str(runner2)
    return None


def _fallback(agent_role: str, reason: str) -> str:
    lang = os.environ.get("HIVE_LANG", "zh")
    return tt(TXT["AGENT_UNAVAILABLE"], lang, role=agent_role, reason=reason)
