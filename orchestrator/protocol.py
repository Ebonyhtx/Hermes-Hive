"""HIVE 数据模型 — Pydantic 模型"""
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional
from datetime import datetime


# ── 枚举 ──

class TaskStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"

class ResultStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"

class VerdictEnum(str, Enum):
    PASS = "pass"
    MINOR_FAIL = "minor_fail"
    FATAL_FAIL = "fatal_fail"

class SessionMode(str, Enum):
    DEVELOPMENT = "development"
    FREE = "free"
    SYSTEM = "system"
    QUICK_TASK = "quick_task"


# ── 任务 ──

class Task(BaseModel):
    task_id: str
    title: str
    description: str
    type: str                      # code | test | deploy | merge | review
    assigned_role: str             # coder | tester | toolman | reviewer
    depends_on: list[str] = []
    max_retries: int = 3
    retry_count: int = 0
    depth: int = 0
    acceptance_criteria: str
    created_at: datetime = Field(default_factory=datetime.now)
    status: TaskStatus = TaskStatus.PENDING


# ── 结果 ──

class Result(BaseModel):
    task_id: str
    producer: str                  # coder | tester | toolman | reviewer
    status: ResultStatus
    summary: str
    artifacts: list[str] = []
    stdout: Optional[str] = None
    errors: list[str] = []
    duration_ms: int = 0
    completed_at: datetime = Field(default_factory=datetime.now)


# ── 裁决 ──

class Issue(BaseModel):
    severity: str                  # minor | major | fatal
    file: Optional[str] = None
    line: Optional[int] = None
    message: str
    suggestion: str

class Verdict(BaseModel):
    task_id: str
    verdict: VerdictEnum
    score: float = 0.0
    issues: list[Issue] = []
    artifacts_reviewed: list[str] = []
    next_action: str = "continue"
    reviewer_notes: str = ""
    issued_at: datetime = Field(default_factory=datetime.now)


# ── DAG ──

class DAGNode(BaseModel):
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    claimed_by: Optional[str] = None


# ── 项目文档 ──

class ProjectBrief(BaseModel):
    project_name: str
    type: str = ""
    description: str = ""
    tech_stack: dict = {}
    architecture: dict = {}
    features: list = []
    acceptance_criteria: str = ""
    user_notes: str = ""
    generated_at: datetime = Field(default_factory=datetime.now)
    confirmed_by_user: bool = False


# ── V4.1 新增数据模型 ──

class VersionInfo(BaseModel):
    """版本信息"""
    version: int
    project_name: str
    summary: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    status: str = "active"       # active | rolled_back | broken
    file_count: int = 0
    artifact_count: int = 0

class Artifact(BaseModel):
    """构建成品"""
    name: str
    path: str
    size: int = 0
    file_type: str = ""           # .exe, .dmg, .tar, .py
    created_at: datetime = Field(default_factory=datetime.now)
    checksum: Optional[str] = None

class ReviewReport(BaseModel):
    """审查报告"""
    session_id: str
    version: int = 0
    layers: dict = {}              # {"L1_syntax": {...}, ...}
    overall: str = "pass"         # pass | warn | fail
    summary: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
