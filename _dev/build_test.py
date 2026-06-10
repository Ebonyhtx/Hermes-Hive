"""HIVE v4.1 — 一句话构建脚本
运行方式: python build_test.py
"""
import asyncio, sys
sys.path.insert(0, '.')
from orchestrator.orchestrator import HiveOrchestrator
from orchestrator.infrastructure.session_manager import SessionManager

async def main():
    session = SessionManager.create_session("批量重命名工具")
    session_id = session["session_id"]
    orch = HiveOrchestrator(session_id=session_id, project_name="批量重命名工具")
    print(f'Session: {orch.session_id}')
    print('开始构建（约需 1-5 分钟，取决于 LLM 响应速度）...')
    result = await orch.build(
        '做一个 Windows 文件批量重命名工具，Python tkinter 带 GUI，'
        '支持正则表达式匹配和替换，打包成 exe'
    )
    print('结果:', result)

asyncio.run(main())
