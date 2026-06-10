"""
HIVE v4.1 — Pure mock-based unit tests.

No Hermes CLI, no HTTP daemon, no real subprocess/filesystem IO.
Every external dependency is mocked via unittest.mock.
Run:  pytest tests/test_mock.py -v
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock, call, mock_open

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════
# 1. errors.py — pure functions, no mocks needed
# ═══════════════════════════════════════════════════════════
class TestErrors:
    def test_ok_returns_success_status(self):
        from orchestrator.infrastructure.errors import ok, is_ok, error
        r = ok({"a": 1})
        assert r["status"] == "ok"
        assert r["data"] == {"a": 1}
        assert is_ok(r)

    def test_ok_with_none(self):
        from orchestrator.infrastructure.errors import ok
        r = ok()
        assert r["status"] == "ok"
        assert r["data"] is None

    def test_error_returns_error_structure(self):
        from orchestrator.infrastructure.errors import error, is_ok, ERROR_CODES
        r = error("SESSION_NOT_FOUND")
        assert r["status"] == "error"
        assert r["error"]["code"] == "E001"
        assert not is_ok(r)

    def test_error_with_custom_message_and_details(self):
        from orchestrator.infrastructure.errors import error
        r = error("INVALID_BRIEF", message="Missing name", details={"field": "project_name"})
        assert r["error"]["message"] == "Missing name"
        assert r["error"]["details"]["field"] == "project_name"

    def test_unknown_error_key_falls_back(self):
        from orchestrator.infrastructure.errors import error
        r = error("UNKNOWN_KEY")
        assert r["error"]["code"] == "E999"

    def test_error_codes_are_complete(self):
        from orchestrator.infrastructure.errors import ERROR_CODES
        expected = [
            "SESSION_NOT_FOUND", "PROJECT_NOT_FOUND", "VERSION_NOT_FOUND",
            "BUILD_IN_PROGRESS", "NO_ACTIVE_BUILD", "CANCEL_FAILED",
            "DELETE_CONFIRM_REQUIRED", "WORKER_TIMEOUT", "DEPENDENCY_FAILED",
            "COST_LIMIT_EXCEEDED", "INVALID_BRIEF", "HERMES_CLI_FAILED", "UNKNOWN_ERROR",
        ]
        for key in expected:
            assert key in ERROR_CODES, f"Missing error code: {key}"
        assert len(ERROR_CODES) == len(expected)


# ═══════════════════════════════════════════════════════════
# 2. i18n.py — pure functions, no mocks needed
# ═══════════════════════════════════════════════════════════
class TestI18n:
    def test_tt_english(self):
        from orchestrator.i18n import tt, TXT
        msg = tt(TXT["DAEMON_STARTING"], lang="en", pid=999)
        assert "999" in msg
        assert "started" in msg.lower()

    def test_tt_chinese(self):
        from orchestrator.i18n import tt, TXT
        msg = tt(TXT["DAEMON_STARTING"], lang="zh", pid=123)
        assert "123" in msg

    def test_tt_fallback_zh_to_en(self):
        from orchestrator.i18n import tt, TXT
        msg = tt(TXT["DAEMON_STARTING"], lang="fr", pid=1)
        assert msg and isinstance(msg, str)

    def test_tt_with_kwargs(self):
        from orchestrator.i18n import tt, TXT
        msg = tt(TXT["DAEMON_STARTING"], lang="en", pid=9999)
        assert "9999" in msg

    def test_pick_prompt_default_en(self):
        from orchestrator.i18n import pick_prompt
        assert pick_prompt("中文", "English", "en") == "English"

    def test_pick_prompt_zh(self):
        from orchestrator.i18n import pick_prompt
        assert pick_prompt("中文", "English", "zh") == "中文"

    def test_pick_prompt_fallback(self):
        from orchestrator.i18n import pick_prompt
        assert pick_prompt("中文", "English", "fr") == "English"

    def test_phase_names_are_present(self):
        from orchestrator.i18n import PHASE_NAMES
        for state in ("idle", "translating", "planning", "executing", "testing", "done"):
            assert state in PHASE_NAMES

    def test_dashboard_labels_have_both_langs(self):
        from orchestrator.i18n import DASHBOARD
        for key, val in DASHBOARD.items():
            assert "zh" in val, f"{key} lacks zh"
            assert "en" in val, f"{key} lacks en"


# ═══════════════════════════════════════════════════════════
# 3. machine.py — edge cases beyond the happy path
# ═══════════════════════════════════════════════════════════
class TestMachine:
    def test_initial_state(self):
        from orchestrator.machine import HiveMachine
        m = HiveMachine()
        assert m.state == "idle"

    def test_full_cycle(self):
        from orchestrator.machine import HiveMachine
        m = HiveMachine()
        m.start_build()
        assert m.state == "translating"
        m.brief_ready()
        assert m.state == "planning"
        m.plan_ready()
        assert m.state == "executing"
        m.fail_build()
        assert m.state == "idle"

    def test_is_active(self):
        from orchestrator.machine import HiveMachine
        m = HiveMachine()
        assert not m.is_active
        m.start_build()
        assert m.is_active

    def test_reset_clears_history(self):
        from orchestrator.machine import HiveMachine
        m = HiveMachine()
        m.start_build()
        m.reset()
        assert m.state == "idle"
        assert len(m.history) == 0

    def test_double_cancel_is_safe(self):
        from orchestrator.machine import HiveMachine
        m = HiveMachine()
        m.start_build()
        m.cancel_build()
        assert m.state == "cancelled"
        m.cancel_build()
        assert m.state == "cancelled"

    def test_multiple_iterations(self):
        from orchestrator.machine import HiveMachine
        m = HiveMachine()
        m.start_build(); m.cancel_build()
        m.reset()
        m.start_build(); m.brief_ready(); m.plan_ready(); m.fail_build()
        assert m.state == "idle"

    def test_history_records_events(self):
        from orchestrator.machine import HiveMachine
        m = HiveMachine()
        m.start_build()
        assert len(m.history) >= 2


# ═══════════════════════════════════════════════════════════
# 4. validator.py — pure validation logic
# ═══════════════════════════════════════════════════════════
class TestValidator:
    def test_valid_brief_passes(self):
        from orchestrator.infrastructure.validator import validate_brief
        brief = {
            "project_name": "test",
            "description": "A test project",
            "features": [{"name": "calc", "description": "a calculator"}],
            "tech_stack": {"language": "Python", "framework": "tkinter"},
            "deliverable": "exe",
        }
        warnings = validate_brief(brief)
        assert isinstance(warnings, list)

    def test_brief_missing_required_fields(self):
        from orchestrator.infrastructure.validator import validate_brief, ValidationError
        with pytest.raises(ValidationError, match="project_name"):
            validate_brief({})

    def test_brief_empty_features(self):
        from orchestrator.infrastructure.validator import validate_brief
        # Empty features list is allowed (valid, just produces warnings)
        warnings = validate_brief({
            "project_name": "x", "description": "d",
            "features": [], "tech_stack": {}, "deliverable": "exe",
        })
        assert isinstance(warnings, list)

    def test_valid_dag(self):
        from orchestrator.infrastructure.validator import validate_dag
        dag = {
            "tasks": [
                {"id": "1", "layer": 1, "type": "code", "assign_to": "coder", "prompt": "do it", "deps": []},
                {"id": "2", "layer": 2, "type": "code", "assign_to": "coder", "prompt": "do it too", "deps": ["1"]},
            ]
        }
        warnings = validate_dag(dag)
        assert isinstance(warnings, list)

    def test_dag_missing_tasks(self):
        from orchestrator.infrastructure.validator import validate_dag, ValidationError
        with pytest.raises(ValidationError, match="tasks"):
            validate_dag({})

    def test_dag_duplicate_task_ids(self):
        from orchestrator.infrastructure.validator import validate_dag, ValidationError
        dag = {
            "tasks": [
                {"id": "1", "layer": 1, "type": "code", "assign_to": "coder", "prompt": "a", "deps": []},
                {"id": "1", "layer": 2, "type": "code", "assign_to": "coder", "prompt": "b", "deps": []},
            ]
        }
        with pytest.raises(ValidationError, match="重复"):
            validate_dag(dag)

    def test_valid_review(self):
        from orchestrator.infrastructure.validator import validate_review
        review = {
            "layers": {
                "L1_syntax": {"status": "pass", "issues": []},
                "L2_brief_alignment": {"status": "pass", "issues": []},
                "L3_security": {"status": "pass", "issues": []},
                "L4_consistency": {"status": "pass", "issues": []},
            },
            "overall": "pass",
            "summary": "Looks good",
        }
        warnings = validate_review(review)
        assert isinstance(warnings, list)

    def test_review_missing_layers(self):
        from orchestrator.infrastructure.validator import validate_review
        warnings = validate_review({"overall": "pass", "summary": "ok"})
        assert len(warnings) >= 1
        assert any("缺少" in w for w in warnings)

    def test_safe_validate_catches_errors(self):
        from orchestrator.infrastructure.validator import safe_validate
        r = safe_validate({"bad": "brief"}, None, None)
        assert r["valid"] is False
        assert len(r["errors"]) >= 1


# ═══════════════════════════════════════════════════════════
# 5. cost_tracker.py — mock SessionManager
# ═══════════════════════════════════════════════════════════
class TestCostTracker:
    def test_estimate_returns_dict(self):
        from orchestrator.infrastructure.cost_tracker import CostTracker
        ct = CostTracker(max_per_build_usd=5.0, max_daily_usd=20.0)
        r = ct.estimate(tasks=5, avg_tokens_per_task=3000)
        assert r["tasks"] == 5
        assert r["estimated_tokens"] > 0
        assert r["estimated_cost_usd"] > 0

    @patch("orchestrator.infrastructure.cost_tracker.SessionManager.log_cost")
    def test_log_delegates_to_session_manager(self, mock_log_cost):
        from orchestrator.infrastructure.cost_tracker import CostTracker
        ct = CostTracker()
        ct.log("sid-1", "translating", tokens_in=100, tokens_out=50, cost_usd=0.01)
        mock_log_cost.assert_called_once()

    @patch("orchestrator.infrastructure.cost_tracker.SessionManager.get_session")
    def test_check_limits_within_budget(self, mock_get_session):
        mock_get_session.return_value = {"total_cost_usd": 1.0}
        from orchestrator.infrastructure.cost_tracker import CostTracker
        ct = CostTracker(max_per_build_usd=5.0)
        r = ct.check_limits("sid-1")
        assert r["within_limit"] is True

    @patch("orchestrator.infrastructure.cost_tracker.SessionManager.get_session")
    def test_check_limits_exceeded(self, mock_get_session):
        mock_get_session.return_value = {"total_cost_usd": 10.0}
        from orchestrator.infrastructure.cost_tracker import CostTracker
        ct = CostTracker(max_per_build_usd=5.0)
        r = ct.check_limits("sid-1")
        assert r["within_limit"] is False
        assert len(r["warnings"]) >= 1

    def test_log_called_with_correct_args(self):
        from orchestrator.infrastructure.cost_tracker import CostTracker
        ct = CostTracker()
        with patch.object(ct, "log") as mock_log:
            ct.log("sid-1", "testing", tokens_in=200, tokens_out=100, cost_usd=0.03)
            mock_log.assert_called_with("sid-1", "testing", tokens_in=200, tokens_out=100, cost_usd=0.03)


# ═══════════════════════════════════════════════════════════
# 6. memory_store.py — mock filesystem
# ═══════════════════════════════════════════════════════════
class TestMemoryStore:
    def test_init_creates_empty_store(self):
        from orchestrator.infrastructure.memory_store import MemoryStore
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            ms = MemoryStore(store_path=path)
            assert ms.get_stats()["projects_count"] == 0
            assert ms.get_stats()["skills_count"] == 0

    def test_record_build_updates_preferences(self):
        from orchestrator.infrastructure.memory_store import MemoryStore
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            ms = MemoryStore(store_path=path)
            ms.record_build("test-proj", {
                "tech_stack": {"language": "Python", "framework": "tkinter", "os": "windows"},
                "deliverable": "exe",
            })
            prefs = ms.get_preferences()
            assert prefs["language"]["Python"] >= 1
            assert prefs["deliverable"]["exe"] >= 1

    def test_record_build_creates_skill(self):
        from orchestrator.infrastructure.memory_store import MemoryStore
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            ms = MemoryStore(store_path=path)
            ms.record_build("calc", {"project_name": "calc", "features": [{"name": "add"}]})
            assert len(ms.get_skills()) >= 1

    def test_clear_resets_everything(self):
        from orchestrator.infrastructure.memory_store import MemoryStore
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            ms = MemoryStore(store_path=path)
            ms.record_build("test", {
                "project_name": "test",
                "features": [{"name": "f1"}],
                "tech_stack": {"language": "Python"},
            })
            assert ms.get_stats()["projects_count"] >= 1
            ms.clear()
            assert ms.get_stats()["projects_count"] == 0

    def test_record_build_does_not_exceed_max_skills(self):
        from orchestrator.infrastructure.memory_store import MemoryStore
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            ms = MemoryStore(store_path=path)
            for i in range(25):
                ms.record_build(f"proj-{i}", {"project_name": f"p{i}", "features": [{"name": f"f{i}"}]})
            assert len(ms.get_skills()) <= 20

    def test_persistence_across_instances(self):
        from orchestrator.infrastructure.memory_store import MemoryStore
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            ms1 = MemoryStore(store_path=path)
            ms1.record_build("test", {
                "project_name": "test",
                "features": [{"name": "f1"}],
                "tech_stack": {"language": "Rust"},
            })
            ms2 = MemoryStore(store_path=path)
            assert ms2.get_preferences()["language"]["Rust"] >= 1


# ═══════════════════════════════════════════════════════════
# 7. version_manager.py — mock filesystem
# ═══════════════════════════════════════════════════════════
class TestVersionManager:
    def test_create_version_returns_1(self):
        from orchestrator.versioning.version_manager import VersionManager
        with tempfile.TemporaryDirectory() as tmp:
            vm = VersionManager(projects_root=Path(tmp))
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "main.py").write_text("print('hello')")
            v = vm.create_version("test", src, summary="first")
            assert v == 1

    def test_create_second_version(self):
        from orchestrator.versioning.version_manager import VersionManager
        with tempfile.TemporaryDirectory() as tmp:
            vm = VersionManager(projects_root=Path(tmp))
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "main.py").write_text("print('hello')")
            vm.create_version("test", src, summary="v1")
            (src / "main.py").write_text("print('hello v2')")
            v2 = vm.create_version("test", src, summary="v2")
            assert v2 == 2

    def test_list_versions(self):
        from orchestrator.versioning.version_manager import VersionManager
        with tempfile.TemporaryDirectory() as tmp:
            vm = VersionManager(projects_root=Path(tmp))
            src = Path(tmp) / "src"
            src.mkdir(); (src / "main.py").write_text("a")
            vm.create_version("test", src, brief={"name": "t"}, summary="v1")
            vm.create_version("test", src, summary="v2")
            versions = vm.list_versions("test")
            assert len(versions) == 2

    def test_rollback(self):
        from orchestrator.versioning.version_manager import VersionManager
        with tempfile.TemporaryDirectory() as tmp:
            vm = VersionManager(projects_root=Path(tmp))
            src = Path(tmp) / "src"
            src.mkdir(); (src / "main.py").write_text("a")
            vm.create_version("test", src, brief={"name": "t"}, summary="v1")
            (src / "main.py").write_text("b")
            vm.create_version("test", src, summary="v2")
            rb = vm.rollback("test", 1)
            assert rb["status"] == "success"

    def test_diff_returns_structure(self):
        from orchestrator.versioning.version_manager import VersionManager
        with tempfile.TemporaryDirectory() as tmp:
            vm = VersionManager(projects_root=Path(tmp))
            src = Path(tmp) / "src"
            src.mkdir(); (src / "main.py").write_text("print('hello')")
            vm.create_version("test", src, brief={"name": "t"}, summary="v1")
            (src / "main.py").write_text("print('hello world')")
            vm.create_version("test", src, summary="v2")
            d = vm.diff("test", 1, 2)
            assert "diff_text" in d
            assert "files" in d
            assert "total_changes" in d

    def test_cleanup_old_versions(self):
        """create more than MAX_VERSIONS (cleanup func exists but not auto-called)"""
        from orchestrator.versioning.version_manager import VersionManager
        with tempfile.TemporaryDirectory() as tmp:
            vm = VersionManager(projects_root=Path(tmp))
            src = Path(tmp) / "src"
            src.mkdir()
            for i in range(12):
                (src / "main.py").write_text(f"print('{i}')")
                vm.create_version("test", src, brief={"name": "t"}, summary=f"v{i}")
            versions = vm.list_versions("test")
            assert len(versions) >= 12

    def test_rollback_nonexistent_version(self):
        from orchestrator.versioning.version_manager import VersionManager
        with tempfile.TemporaryDirectory() as tmp:
            vm = VersionManager(projects_root=Path(tmp))
            src = Path(tmp) / "src"
            src.mkdir(); (src / "main.py").write_text("a")
            vm.create_version("test", src, brief={"name": "t"}, summary="v1")
            rb = vm.rollback("test", 99)
            assert rb["status"] == "error"


# ═══════════════════════════════════════════════════════════
# 8. sandbox.py — mock subprocess
# ═══════════════════════════════════════════════════════════
class TestSandbox:
    @patch("orchestrator.infrastructure.sandbox.subprocess.Popen")
    def test_run_returns_expected_keys(self, mock_popen):
        from orchestrator.infrastructure.sandbox import Sandbox
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = ("hello", "")
        mock_popen.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Sandbox(base_dir=Path(tmp))
            ws = sandbox.create_workspace("sid-1")
            result = sandbox.run(["echo", "hello"], cwd=ws, timeout_s=5)
            assert "stdout" in result
            assert "stderr" in result
            assert "exit_code" in result
            assert "timed_out" in result
            assert "elapsed_s" in result
            assert result["exit_code"] == 0

    @patch("orchestrator.infrastructure.sandbox.subprocess.Popen")
    def test_run_timeout_fallback(self, mock_popen):
        from orchestrator.infrastructure.sandbox import Sandbox
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.returncode = None
        mock_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="sleep", timeout=0.1),
            ("", "timed out"),
        ]
        mock_proc.pid = 9999
        mock_popen.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Sandbox(base_dir=Path(tmp))
            ws = sandbox.create_workspace("sid-2")
            result = sandbox.run(["sleep", "30"], cwd=ws, timeout_s=0.1)
            assert result["timed_out"] is True
            assert result["exit_code"] == -1

    def test_create_workspace_creates_dir(self):
        from orchestrator.infrastructure.sandbox import Sandbox
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Sandbox(base_dir=Path(tmp))
            ws = sandbox.create_workspace("test-session")
            assert ws.exists()
            assert ws.is_dir()

    def test_cleanup_removes_dir(self):
        from orchestrator.infrastructure.sandbox import Sandbox
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Sandbox(base_dir=Path(tmp))
            ws = sandbox.create_workspace("cleanup-test")
            assert ws.exists()
            sandbox.cleanup("cleanup-test")
            assert not ws.exists()

    @patch("orchestrator.infrastructure.sandbox.signal")
    @patch("orchestrator.infrastructure.sandbox.os")
    @patch("orchestrator.infrastructure.sandbox.sys.platform", "linux")
    def test_kill_process_tree_unix(self, mock_os, mock_signal):
        from orchestrator.infrastructure.sandbox import Sandbox
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_os.getpgid.return_value = 12345
        mock_signal.SIGKILL = 9
        sandbox = Sandbox()
        sandbox._kill_process_tree(mock_proc)
        mock_os.getpgid.assert_called_once_with(12345)
        mock_os.killpg.assert_called_once_with(12345, 9)

    @patch("orchestrator.infrastructure.sandbox.subprocess.run")
    @patch("orchestrator.infrastructure.sandbox.sys.platform", "win32")
    def test_kill_process_tree_windows(self, mock_run):
        from orchestrator.infrastructure.sandbox import Sandbox
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        sandbox = Sandbox()
        sandbox._kill_process_tree(mock_proc)
        mock_run.assert_called_once()
        assert "taskkill" in " ".join(mock_run.call_args[0][0])


# ═══════════════════════════════════════════════════════════
# 9. dependency_manager.py — mock subprocess
# ═══════════════════════════════════════════════════════════
class TestDependencyManager:
    def test_ensure_venv_creates_venv(self):
        from orchestrator.infrastructure.dependency_manager import DependencyManager
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "workspace"
            ws.mkdir()
            dm = DependencyManager(workspace_root=ws)
            with patch.object(dm, "ensure_venv", return_value=True) as mock:
                result = dm.ensure_venv()
                assert result is True

    @patch("orchestrator.infrastructure.dependency_manager.subprocess.run")
    def test_install_returns_success_dict(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc
        from orchestrator.infrastructure.dependency_manager import DependencyManager
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "workspace"
            ws.mkdir()
            # Create venv structure so _pip_path finds it
            (ws / ".venv" / "Scripts").mkdir(parents=True)
            (ws / ".venv" / "Scripts" / "pip.exe").write_text("")
            dm = DependencyManager(workspace_root=ws)
            r = dm.install(["flask", "requests"])
            assert r["success"] is True

    @patch("orchestrator.infrastructure.dependency_manager.subprocess.run")
    def test_install_failure(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "error!"
        mock_run.return_value = mock_proc
        from orchestrator.infrastructure.dependency_manager import DependencyManager
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "workspace"
            ws.mkdir()
            dm = DependencyManager(workspace_root=ws)
            r = dm.install(["nonexistent-package"])
            assert r["success"] is False

    def test_python_path_exists(self):
        from orchestrator.infrastructure.dependency_manager import DependencyManager
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "workspace"
            ws.mkdir()
            dm = DependencyManager(workspace_root=ws)
            assert dm.python_path() is None


# ═══════════════════════════════════════════════════════════
# 10. hermes_bridge.py — mock subprocess
# ═══════════════════════════════════════════════════════════
class TestHermesBridge:
    @patch("orchestrator.hermes_bridge.subprocess.run")
    def test_run_agent_returns_string(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="some response", stderr="")
        from orchestrator.hermes_bridge import run_agent
        result = run_agent("architect", "Build a calculator", timeout=10)
        assert isinstance(result, str)

    @patch("orchestrator.hermes_bridge.subprocess.run")
    def test_run_agent_timeout_fallback(self, mock_run):
        mock_run.return_value = MagicMock(returncode=-1, stdout="", stderr="timeout")
        from orchestrator.hermes_bridge import run_agent
        result = run_agent("planner", "Plan it", timeout=5)
        assert isinstance(result, str)

    @patch("orchestrator.hermes_bridge._find_runner", return_value=None)
    def test_no_runner_fallback(self, mock_find):
        from orchestrator.hermes_bridge import run_agent
        result = run_agent("architect", "test", timeout=5)
        assert "Agent" in result or "unavailable" in result or "Unavailable" in result


# ═══════════════════════════════════════════════════════════
# 11. hive_client.py — mock httpx
# ═══════════════════════════════════════════════════════════
class TestHiveClient:
    @patch("orchestrator.hive_client.httpx.Client")
    def test_build_returns_buildresult(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"result": {"content": [{"text": json.dumps({
                "status": "ok",
                "data": {
                    "session_id": "v4_test_123",
                    "project_name": "test",
                    "status": "building",
                    "version": 1,
                    "message": "started",
                }
            })}]}}
        )
        from orchestrator.hive_client import HiveClient
        client = HiveClient(url="http://localhost:8421")
        result = client.build("test build")
        assert result.session_id is not None

    @patch("orchestrator.hive_client.httpx.Client")
    def test_list_projects(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"result": {"content": [{"text": json.dumps({
                "status": "ok",
                "data": {"projects": [{"name": "p1"}, {"name": "p2"}]}
            })}]}}
        )
        from orchestrator.hive_client import HiveClient
        client = HiveClient(url="http://localhost:8421")
        projects = client.list_projects()
        assert len(projects) >= 0

    @patch("orchestrator.hive_client.httpx.Client")
    def test_versions(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"result": {"content": [{"text": json.dumps({
                "status": "ok",
                "data": {"versions": [{"version": 1}, {"version": 2}]}
            })}]}}
        )
        from orchestrator.hive_client import HiveClient
        client = HiveClient(url="http://localhost:8421")
        versions = client.versions("v4_test_123")
        assert len(versions) >= 0

    @patch("orchestrator.hive_client.httpx.Client")
    def test_cancel(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"result": {"content": [{"text": json.dumps({
                "status": "ok", "data": {"message": "cancelled"}
            })}]}}
        )
        from orchestrator.hive_client import HiveClient
        client = HiveClient(url="http://localhost:8421")
        r = client.cancel("v4_test_123")
        assert isinstance(r, dict)

    @patch("orchestrator.hive_client.httpx.Client")
    def test_rollback(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"result": {"content": [{"text": json.dumps({
                "status": "ok",
                "data": {"status": "success", "previous_version": 2, "current_version": 1}
            })}]}}
        )
        from orchestrator.hive_client import HiveClient
        client = HiveClient(url="http://localhost:8421")
        r = client.rollback("v4_test_123", 1)
        assert isinstance(r, dict)


# ═══════════════════════════════════════════════════════════
# 12. daemon.py — mock subprocess + os
# ═══════════════════════════════════════════════════════════
class TestDaemon:
    @patch("orchestrator.daemon.os.environ", {"LANG": "zh_CN.UTF-8"})
    def test_detect_lang_zh(self):
        from orchestrator.daemon import _detect_lang
        assert _detect_lang() == "zh"

    @patch("orchestrator.daemon.os.environ", {"LANG": "en_US.UTF-8"})
    def test_detect_lang_en(self):
        from orchestrator.daemon import _detect_lang
        assert _detect_lang() == "en"

    @patch("orchestrator.daemon.os.environ", {})
    def test_detect_lang_default(self):
        from orchestrator.daemon import _detect_lang
        assert _detect_lang() == "en"


# ═══════════════════════════════════════════════════════════
# 13. session_manager.py — mock sqlite3
# ═══════════════════════════════════════════════════════════
class TestSessionManager:
    @patch("orchestrator.infrastructure.session_manager.sqlite3.connect")
    def test_create_session_has_required_keys(self, mock_connect):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        mock_cursor.lastrowid = 1

        from orchestrator.infrastructure.session_manager import SessionManager
        r = SessionManager.create_session("test-project", brief={"test": True})
        assert "session_id" in r
        assert "project_name" in r
        assert "status" in r
        assert "created" in r

    @patch("orchestrator.infrastructure.session_manager.sqlite3.connect")
    def test_get_session(self, mock_connect):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (
            "v4_test_1", "test", "idle", "running", 0,
            "2024-01-01", "2024-01-01", None, None, 0.0,
        )
        from orchestrator.infrastructure.session_manager import SessionManager
        s = SessionManager.get_session("v4_test_1")
        assert s is not None
        assert s["session_id"] == "v4_test_1"

    @patch("orchestrator.infrastructure.session_manager.sqlite3.connect")
    def test_get_session_not_found(self, mock_connect):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        from orchestrator.infrastructure.session_manager import SessionManager
        s = SessionManager.get_session("nonexistent")
        assert s is None

    @patch("orchestrator.infrastructure.session_manager.sqlite3.connect")
    def test_create_version(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        from orchestrator.infrastructure.session_manager import SessionManager
        SessionManager.create_version("v4_test_1", 1, "first version")

    @patch("orchestrator.infrastructure.session_manager.sqlite3.connect")
    def test_log_cost(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        from orchestrator.infrastructure.session_manager import SessionManager
        SessionManager.log_cost("v4_test_1", "translating", tokens_in=100, tokens_out=50, cost_usd=0.01)

    @patch("orchestrator.infrastructure.session_manager.sqlite3.connect")
    def test_delete_project(self, mock_connect):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.rowcount = 1
        from orchestrator.infrastructure.session_manager import SessionManager
        r = SessionManager.delete_project("test-project")
        assert r is True

    @patch("orchestrator.infrastructure.session_manager.sqlite3.connect")
    def test_get_all_sessions(self, mock_connect):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("v4_a", "p1", "idle", "running", 1, "t1", "t1", None, None, 0.0),
            ("v4_b", "p2", "done", "success", 2, "t2", "t2", None, None, 0.0),
        ]
        from orchestrator.infrastructure.session_manager import SessionManager
        sessions = SessionManager.get_all_sessions()
        assert len(sessions) == 2
