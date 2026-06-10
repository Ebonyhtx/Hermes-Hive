"""
HIVE v4.1 — Schema 验证器

验证 brief.json / dag.json / review.json 的字段完整性和类型正确性。
纯 Python 实现，零外部依赖。
"""

from typing import Any, Optional


class ValidationError(Exception):
    """Schema 验证错误。"""
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"[{field}] {message}")


def validate_brief(brief: dict) -> list[str]:
    """
    验证 brief.json 结构。
    返回警告列表（空列表 = 完全合法）。
    抛出 ValidationError = 致命错误。
    """
    warnings = []

    # 必填字段
    required = ["project_name", "description", "features", "tech_stack", "deliverable"]
    for field in required:
        if field not in brief:
            raise ValidationError(field, f"缺少必填字段")

    # project_name
    if len(brief.get("project_name", "")) > 100:
        warnings.append("project_name 超过 100 字符")

    # features
    features = brief.get("features", [])
    if not isinstance(features, list):
        raise ValidationError("features", "必须是数组")
    for i, feat in enumerate(features):
        if isinstance(feat, dict):
            if "name" not in feat:
                warnings.append(f"features[{i}] 缺少 name")
            priority = feat.get("priority", "")
            if priority and priority not in ("P0", "P1", "P2"):
                warnings.append(f"features[{i}].priority 应为 P0|P1|P2，实际为 '{priority}'")
        else:
            warnings.append(f"features[{i}] 应为对象，实际为 {type(feat).__name__}")

    # tech_stack
    ts = brief.get("tech_stack", {})
    if isinstance(ts, dict):
        for sub in ("language", "framework"):
            if sub not in ts:
                warnings.append(f"tech_stack 缺少 '{sub}'")
        lang = ts.get("language", "")
        valid_langs = ("Python", "Rust", "Go", "Node.js", "Other")
        if lang and lang not in valid_langs:
            warnings.append(f"tech_stack.language='{lang}' 不在 {valid_langs}")
        os_val = ts.get("os", "")
        valid_os = ("windows", "macos", "linux", "cross-platform")
        if os_val and os_val not in valid_os:
            warnings.append(f"tech_stack.os='{os_val}' 不在 {valid_os}")
    else:
        warnings.append("tech_stack 应为对象")

    # deliverable
    deliverable = brief.get("deliverable", "")
    valid_deliverables = ("exe", "app", "appimage", "docker", "lib", "cli")
    if deliverable and deliverable not in valid_deliverables:
        warnings.append(f"deliverable='{deliverable}' 不在 {valid_deliverables}")

    # _confidence
    conf = brief.get("_confidence", {})
    if conf:
        if not isinstance(conf, dict):
            warnings.append("_confidence 应为对象")
        else:
            overall = conf.get("overall", 0.5)
            if not (0 <= overall <= 1):
                warnings.append(f"_confidence.overall={overall} 不在 0-1 范围")

    return warnings


def validate_dag(dag: dict) -> list[str]:
    """
    验证 dag.json 结构。
    返回警告列表。
    """
    warnings = []

    if "tasks" not in dag:
        raise ValidationError("tasks", "缺少必填字段")
    if not isinstance(dag["tasks"], list):
        raise ValidationError("tasks", "必须是数组")
    if len(dag["tasks"]) < 1:
        raise ValidationError("tasks", "至少需要 1 个任务")

    task_ids = set()
    for i, task in enumerate(dag["tasks"]):
        if not isinstance(task, dict):
            warnings.append(f"tasks[{i}] 应为对象")
            continue

        tid = task.get("id", "")
        if not tid:
            warnings.append(f"tasks[{i}] 缺少 id")
        else:
            if tid in task_ids:
                raise ValidationError(f"tasks.{tid}", "重复的 task_id")
            task_ids.add(tid)

        layer = task.get("layer", 0)
        if not (1 <= layer <= 4):
            warnings.append(f"tasks.{tid} layer={layer} 不在 1-4 范围")

        ttype = task.get("type", "")
        if ttype not in ("code", "test", "build", "deploy"):
            warnings.append(f"tasks.{tid} type='{ttype}' 应为 code|test|build|deploy")

        assign_to = task.get("assign_to", "")
        if assign_to and assign_to not in ("coder", "tester", "toolman"):
            warnings.append(f"tasks.{tid} assign_to='{assign_to}' 应为 coder|tester|toolman")

        # 验证 deps
        for dep in task.get("deps", []):
            if dep not in task_ids and dep not in [t.get("id") for t in dag["tasks"][:i]]:
                warnings.append(f"tasks.{tid} 依赖 '{dep}' 不存在于 tasks 中")

    if "tech_stack" not in dag:
        warnings.append("缺少 tech_stack")

    return warnings


def validate_review(review: dict) -> list[str]:
    """
    验证 review.json 结构。
    """
    warnings = []

    for layer_name in ("L1_syntax", "L2_brief_alignment", "L3_security", "L4_consistency"):
        if layer_name not in review.get("layers", {}):
            warnings.append(f"缺少层 {layer_name}")

    overall = review.get("overall", "")
    if overall and overall not in ("pass", "warn", "fail"):
        warnings.append(f"overall='{overall}' 应为 pass|warn|fail")

    if not review.get("summary", ""):
        warnings.append("summary 为空")

    return warnings


def safe_validate(brief: Optional[dict] = None, dag: Optional[dict] = None,
                  review: Optional[dict] = None) -> dict:
    """
    安全验证：返回结构化结果而非抛异常。

    Returns:
        {"valid": bool, "warnings": [str], "errors": [str]}
    """
    warnings = []
    errors = []

    if brief is not None:
        try:
            warnings.extend(validate_brief(brief))
        except ValidationError as e:
            errors.append(str(e))

    if dag is not None:
        try:
            warnings.extend(validate_dag(dag))
        except ValidationError as e:
            errors.append(str(e))

    if review is not None:
        try:
            warnings.extend(validate_review(review))
        except ValidationError as e:
            errors.append(str(e))

    return {
        "valid": len(errors) == 0,
        "warnings": warnings,
        "errors": errors,
    }
