"""
HIVE v4.1 — Dashboard 事件总线

职责:
- 管理 WebSocket 客户端连接
- 广播事件到所有连接的 Dashboard
"""

import asyncio
import json
from fastapi import WebSocket


_ws_clients: set[WebSocket] = set()


async def register_client(ws: WebSocket):
    """注册新的 WebSocket 客户端。"""
    _ws_clients.add(ws)


async def unregister_client(ws: WebSocket):
    """注销断开连接的客户端。"""
    _ws_clients.discard(ws)


async def broadcast_event(event: str, data: dict):
    """向所有 Dashboard WebSocket 客户端广播事件。"""
    payload = json.dumps({"event": event, **data})
    for ws in list(_ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            _ws_clients.discard(ws)


def broadcast_event_sync(event: str, data: dict):
    """同步版广播 — 用于非 async 上下文，创建独立 task。"""
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            asyncio.create_task(broadcast_event(event, data))
            return
    except RuntimeError:
        pass
    # 没有运行中的事件循环时，静默丢弃（避免崩溃）
    # 此时没有 WebSocket 连接可以接收


def get_client_count() -> int:
    """获取当前连接的客户端数。"""
    return len(_ws_clients)
