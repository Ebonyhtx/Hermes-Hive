"""
HIVE v4.1 — Dashboard 服务器（已迁移到 mcp_server.py）

保留此文件仅为向后兼容。
dashboard_app 和 get_app 通过延迟导入避免循环依赖。
"""

def __getattr__(name):
    """延迟导入 dashboard_app / get_app 避免循环依赖。"""
    if name in ("dashboard_app", "get_app"):
        from orchestrator.mcp_server import dashboard_app as _app
        if name == "dashboard_app":
            return _app
        return lambda: _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
