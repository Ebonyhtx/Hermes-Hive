"""
HIVE v4.1 — 国际化 / i18n

用法:
    from orchestrator.i18n import TXT, tt
    print(tt(TXT.DAEMON_STARTED, lang, pid=1234))
"""

# ── 帮助函数 ──

def tt(table: dict, lang: str = "en", **kwargs) -> str:
    """从翻译表取文本，支持格式化。fallback 到 zh -> en -> key。"""
    entry = table.get(lang)
    if entry is None:
        entry = table.get("zh", table.get("en", str(table)))
    if kwargs:
        return entry.format(**kwargs)
    return entry


def pick_prompt(zh: str, en: str, lang: str) -> str:
    """中英文 prompt 模板选择。默认英文。"""
    return en if lang != "zh" else zh


# ── CLI / 用户可见消息 ──

TXT = {}

TXT["DAEMON_STARTING"] = {
    "zh": "HIVE daemon 已启动 (PID {pid})",
    "en": "HIVE daemon started (PID {pid})",
}
TXT["DAEMON_RUNNING"] = {
    "zh": "HIVE daemon 已在运行 (PID {pid})",
    "en": "HIVE daemon already running (PID {pid})",
}
TXT["DAEMON_STOPPED"] = {
    "zh": "HIVE daemon 已停止 (PID {pid})",
    "en": "HIVE daemon stopped (PID {pid})",
}
TXT["DAEMON_NOT_RUNNING"] = {
    "zh": "HIVE daemon 未运行",
    "en": "HIVE daemon is not running",
}
TXT["DAEMON_DASHBOARD"] = {
    "zh": "Dashboard: http://127.0.0.1:8421/dashboard",
    "en": "Dashboard: http://127.0.0.1:8421/dashboard",
}
TXT["DAEMON_MCP"] = {
    "zh": "MCP Server: http://127.0.0.1:8421/mcp",
    "en": "MCP Server: http://127.0.0.1:8421/mcp",
}
TXT["DAEMON_WS"] = {
    "zh": "WS: ws://127.0.0.1:8421/ws",
    "en": "WS: ws://127.0.0.1:8421/ws",
}
TXT["DAEMON_SESSIONS_DIR"] = {
    "zh": "Sessions: ~/.hermes/hive-v4/",
    "en": "Sessions: ~/.hermes/hive-v4/",
}
TXT["DAEMON_WAITING"] = {
    "zh": "等待就绪中... 稍后访问 http://127.0.0.1:8421/dashboard",
    "en": "Waiting for ready... visit http://127.0.0.1:8421/dashboard shortly",
}
TXT["DAEMON_STOP_FAILED"] = {
    "zh": "停止失败: {error}",
    "en": "Stop failed: {error}",
}
TXT["DAEMON_STATUS_OK"] = {
    "zh": "HIVE daemon: OK 运行中",
    "en": "HIVE daemon: OK running",
}
TXT["DAEMON_STATUS_DEAD"] = {
    "zh": "HIVE daemon: X 未运行",
    "en": "HIVE daemon: X not running",
}
TXT["DAEMON_UNKNOWN_CMD"] = {
    "zh": "未知命令: {cmd}",
    "en": "Unknown command: {cmd}",
}

TXT["AGENT_UNAVAILABLE"] = {
    "zh": "[Agent:{role} 不可用] {reason}\n请确认: 1) Hermes 已安装 2) API Key 已配置 3) 网络可达",
    "en": "[Agent:{role} unavailable] {reason}\nPlease verify: 1) Hermes installed 2) API Key configured 3) Network reachable",
}

# ── 构建阶段名称 ──

PHASE_NAMES = {
    "idle":        {"zh": "空闲",     "en": "Idle"},
    "translating": {"zh": "转译",     "en": "Translating"},
    "planning":    {"zh": "编排",     "en": "Planning"},
    "executing":   {"zh": "编码",     "en": "Executing"},
    "testing":     {"zh": "测试",     "en": "Testing"},
    "done":        {"zh": "完成",     "en": "Done"},
    "cancelled":   {"zh": "已取消",   "en": "Cancelled"},
    "failed":      {"zh": "失败",     "en": "Failed"},
    "reviewing":   {"zh": "审查中",   "en": "Reviewing"},
}

STATUS_LABELS = {
    "running": {"zh": "运行中", "en": "Running"},
    "done":    {"zh": "完成",   "en": "Done"},
    "failed":  {"zh": "失败",   "en": "Failed"},
    "cancelled": {"zh": "已取消", "en": "Cancelled"},
    "deleted":   {"zh": "已删除", "en": "Deleted"},
    "idle":      {"zh": "空闲",   "en": "Idle"},
}

# ── Dashboard 标签（备用 — 前端有自己的中英文映射） ──

DASHBOARD = {
    "title":            {"zh": "HIVE v4 控制台",   "en": "HIVE v4 Console"},
    "subtitle":         {"zh": "Multi-Agent Build", "en": "Multi-Agent Build"},
    "project_panel":    {"zh": "项目", "en": "Projects"},
    "file_panel":       {"zh": "文件", "en": "Files"},
    "console_tab":      {"zh": "控制台", "en": "Console"},
    "files_tab":        {"zh": "文件", "en": "Files"},
    "artifacts_tab":    {"zh": "成品", "en": "Artifacts"},
    "new_build":        {"zh": "+ 新构建", "en": "+ New Build"},
    "search_projects":  {"zh": "搜索项目...", "en": "Search projects..."},
    "describe_req":     {"zh": "描述你的需求...", "en": "Describe your requirements..."},
    "upload":           {"zh": "上传", "en": "Upload"},
    "clean":            {"zh": "清理", "en": "Clean"},
    "delete":           {"zh": "删除", "en": "Delete"},
    "build":            {"zh": "构建", "en": "Build"},
    "cancel":           {"zh": "取消", "en": "Cancel"},
    "log":              {"zh": "日志", "en": "Log"},
    "clear":            {"zh": "清除", "en": "Clear"},
}
