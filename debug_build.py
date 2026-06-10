"""HIVE v4.1 — 调试构建脚本"""
import asyncio, sys, time, traceback, tempfile
from pathlib import Path
sys.path.insert(0, '.')
from orchestrator.orchestrator import HiveOrchestrator
from orchestrator.infrastructure.session_manager import SessionManager

async def main():
    session = SessionManager.create_session("批量重命名工具-调试")
    session_id = session["session_id"]
    orch = HiveOrchestrator(session_id=session_id, project_name="批量重命名工具-调试")
    print(f'Session: {orch.session_id}')
    
    # 逐阶段调试
    print('\n=== Phase 1: ARC 转译 ===')
    t0 = time.time()
    try:
        # 直接调 ARC，不经过 retry wrapper
        orch.machine.start_build()
        brief = await orch.architect.translate(
            '做一个 Windows 文件批量重命名工具，Python tkinter 带 GUI，'
            '支持正则表达式匹配和替换，打包成 exe'
        )
        print(f'  OK ({time.time()-t0:.1f}s)')
        print(f'  项目: {brief.get("project_name")}')
        print(f'  Features: {len(brief.get("features", []))}')
    except Exception as e:
        print(f'  FAIL: {e}')
        traceback.print_exc()
        return

    print('\n=== Phase 2: PLANNER ===')
    t0 = time.time()
    try:
        dag = await orch.planner.plan(brief)
        print(f'  OK ({time.time()-t0:.1f}s)')
        print(f'  Tasks: {len(dag.get("tasks", []))}')
    except Exception as e:
        print(f'  FAIL: {e}')
        return

    print('\n=== Phase 3: CODER ===')
    t0 = time.time()
    try:
        ws = Path(tempfile.mkdtemp())
        result = await orch.coder_pool.execute_dag(
            {"tasks": [t for t in dag.get("tasks", []) if t.get("type") == "code"]},
            ws, orch.session_id,
            on_progress=lambda tid, status, *a: print(f'    [{status}] {tid}'),
        )
        print(f'  OK ({time.time()-t0:.1f}s)')
        print(f'  Files: {result.get("completed", [])}')
    except Exception as e:
        print(f'  FAIL: {e}')
        return

    print('\n=== DONE ===')

asyncio.run(main())
