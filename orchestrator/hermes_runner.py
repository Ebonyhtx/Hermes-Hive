"""Hermes Agent 独立运行器 — 在隔离进程中调 Hermes CLI

设计目的：避免 MCP Server 的 stdio/进程组污染子进程。
调用方式：python hermes_runner.py <role> <prompt_file> <result_file>

工作流程：
1. 读取 prompt 文件
2. 调 hermes chat -q
3. 清理输出
4. 写入 result 文件
5. 退出码 0=成功 1=失败
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 4:
        print("Usage: hermes_runner.py <role> <prompt_file> <result_file> [workdir]", file=sys.stderr)
        sys.exit(1)

    role = sys.argv[1]
    prompt_file = sys.argv[2]
    result_file = sys.argv[3]
    workdir = sys.argv[4] if len(sys.argv) > 4 else ""

    # 读 prompt
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt = f.read()
    except Exception as e:
        _write_result(result_file, {"error": f"读 prompt 失败: {e}"}, fatal=True)
        sys.exit(1)

    # 找 Hermes
    hermes = _find_hermes()
    if not hermes:
        _write_result(result_file, {"error": "Hermes CLI 未找到"})
        sys.exit(1)

    # 构建参数
    toolsets = {
        "architect": "",
        "planner": "file",
        "coder": "terminal,file",
        "reviewer": "file",
        "free_agent": "",
    }.get(role, "")

    # 按角色选择模型（可选 — 默认使用 Hermes config.yaml 的默认模型）
    # 优先级: env var > hermes_runner 兜底 > Hermes 默认
    # 设置方式: export HIVE_MODEL_ARCHITECT="gpt-4" 或 hermes config set ...
    model_env_var = f"HIVE_MODEL_{role.upper()}"
    model_override = os.environ.get(model_env_var, "")

    cmd = [hermes, "chat", "-q", prompt, "-Q", "--source", "tool"]
    if toolsets:
        cmd.extend(["-t", toolsets])
    if model_override:
        cmd.extend(["-m", model_override])
    # 不传 -m → Hermes 使用 config.yaml 的默认模型

    # 执行（完全隔离的子进程）
    try:
        kw = dict(capture_output=True, text=True, timeout=300)
        if workdir:
            kw["cwd"] = workdir
        proc = subprocess.run(cmd, **kw)

        if proc.returncode == 0:
            cleaned = _clean_response(proc.stdout)
            _write_result(result_file, {"ok": True, "response": cleaned})
            sys.exit(0)
        else:
            stderr = (proc.stderr or "")[:500]
            _write_result(result_file, {"error": f"exit {proc.returncode}: {stderr}"})
            sys.exit(1)

    except subprocess.TimeoutExpired:
        _write_result(result_file, {"error": "超时 300s"})
        sys.exit(1)
    except Exception as e:
        _write_result(result_file, {"error": str(e)})
        sys.exit(1)


def _find_hermes() -> str:
    """查找 Hermes CLI / Locate Hermes CLI binary"""
    h = shutil.which("hermes")
    if h:
        return h
    # Search common install locations
    candidates = [
        Path.home() / ".hermes" / "venv" / "Scripts" / "hermes.exe",    # Windows
        Path.home() / ".hermes" / "venv" / "bin" / "hermes",           # Unix
        Path.home() / "AppData" / "Local" / "hermes" / "hermes.exe",   # Windows fallback
        Path("/usr/local/bin/hermes"),
        Path("/opt/hermes/hermes"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return ""


def _clean_response(text: str) -> str:
    """清理输出"""
    if not text:
        return ""
    text = re.sub(r"\x1b\[[0-9;]*[mK]", "", text)
    lines = text.strip().split("\n")
    found = []
    reasoning = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("┌─"):
            reasoning = True
            continue
        if reasoning:
            if s[0].islower() or s.startswith("The") or s.startswith("Let"):
                continue
            if all(c in "─│┌┐└┘├┤┬┴┼ " for c in s):
                continue
            reasoning = False
        if s.startswith("session_id:"):
            continue
        found.append(s)
    return "\n".join(found)


def _write_result(path: str, data: dict, fatal: bool = False):
    """写入结果文件"""
    data["_runner"] = "hermes_runner"
    data["_fatal"] = fatal
    try:
        Path(path).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
