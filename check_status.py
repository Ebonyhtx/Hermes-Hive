"""
HIVE v4.1 — 查看构建进度
运行方式: python check_status.py
"""
import sys
sys.path.insert(0, '.')
from orchestrator.infrastructure.session_manager import SessionManager
from pathlib import Path

sessions = SessionManager.get_all_sessions()
if not sessions:
    print('暂无 session')
    sys.exit(0)

for s in sessions:
    print(f'项目:  {s["project_name"]}')
    print(f'Session: {s["session_id"]}')
    print(f'状态:  {s["status"]}')
    print(f'阶段:  {s["state"]}')
    print(f'版本:  {s.get("current_version", 0)}')

# 检查工作目录是否有产出
builds_dir = Path.home() / ".hermes" / "hive-v4" / "builds"
if builds_dir.exists():
    for d in builds_dir.iterdir():
        if d.is_dir():
            src = d / "src"
            if src.exists():
                files = list(src.rglob("*.py"))
                print(f'  代码文件: {len(files)} 个')
                for f in files:
                    print(f'    {f.relative_to(d)}')
            dist = d / "dist"
            if dist.exists():
                arts = list(dist.iterdir())
                print(f'  成品: {len(arts)} 个')
                for a in arts:
                    print(f'    {a.name} ({a.stat().st_size} bytes)')
