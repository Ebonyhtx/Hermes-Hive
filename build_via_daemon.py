"""
HIVE v4.1 — 通过 Daemon API 构建（Dashboard 可见进度）
用法: python build_via_daemon.py
"""
import json, time, urllib.request

MCP_URL = "http://127.0.0.1:8421/mcp"

def call_tool(name, args):
    """调 daemon 的 MCP 工具。"""
    payload = json.dumps({
        "jsonrpc": "2.0", "method": "tools/call",
        "params": {"name": name, "arguments": args},
        "id": int(time.time() * 1000),
    }).encode()
    req = urllib.request.Request(
        MCP_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=600)
    return json.loads(resp.read())

# 1. 启动构建
print("启动构建...")
result = call_tool("hive_build", {
    "description": "做一个 Windows 文件批量重命名工具，Python tkinter 带 GUI，支持正则表达式匹配和替换，打包成 exe",
})
print(f'构建结果: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}')
