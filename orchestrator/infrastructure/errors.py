"""
HIVE v4.1 — 统一错误码定义

返回格式规范:
  成功: {"status": "ok", "data": {...}}
  错误: {"status": "error", "error": {"code": "E001", "message": "..."}}
"""

from typing import Any


ERROR_CODES = {
    "SESSION_NOT_FOUND":      {"code": "E001", "http": 404, "message": "Session 不存在"},
    "PROJECT_NOT_FOUND":     {"code": "E002", "http": 404, "message": "项目不存在"},
    "VERSION_NOT_FOUND":     {"code": "E003", "http": 404, "message": "版本不存在"},
    "BUILD_IN_PROGRESS":     {"code": "E004", "http": 409, "message": "构建正在进行中"},
    "NO_ACTIVE_BUILD":       {"code": "E005", "http": 400, "message": "无活跃构建"},
    "CANCEL_FAILED":         {"code": "E006", "http": 500, "message": "取消构建失败"},
    "DELETE_CONFIRM_REQUIRED": {"code": "E007", "http": 400, "message": "确认删除请设置 confirm=True"},
    "WORKER_TIMEOUT":        {"code": "E008", "http": 504, "message": "Worker 执行超时"},
    "DEPENDENCY_FAILED":     {"code": "E009", "http": 500, "message": "依赖安装失败"},
    "COST_LIMIT_EXCEEDED":   {"code": "E010", "http": 402, "message": "成本超出预算上限"},
    "INVALID_BRIEF":         {"code": "E011", "http": 400, "message": "无效的 brief 格式"},
    "HERMES_CLI_FAILED":     {"code": "E012", "http": 500, "message": "Hermes CLI 调用失败"},
    "UNKNOWN_ERROR":         {"code": "E999", "http": 500, "message": "未知错误"},
}


def ok(data: Any = None) -> dict:
    """成功响应。"""
    return {"status": "ok", "data": data}


def error(error_key: str, message: str = "", details: dict = None) -> dict:
    """错误响应。"""
    err = ERROR_CODES.get(error_key, ERROR_CODES["UNKNOWN_ERROR"])
    return {
        "status": "error",
        "error": {
            "code": err["code"],
            "message": message or err["message"],
            "details": details or {},
        },
    }


def is_ok(response: dict) -> bool:
    """检查响应是否成功。"""
    return response.get("status") == "ok"
