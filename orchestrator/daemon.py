"""
HIVE v4.1 — Daemon management CLI

Usage:
  python -m orchestrator.daemon start     # Start daemon
  python -m orchestrator.daemon stop      # Stop daemon
  python -m orchestrator.daemon status    # Check status
  python -m orchestrator.daemon status --text  # Plain text status (no browser fallback)
"""

import json
import os
import signal
import sys
import time
from pathlib import Path

from orchestrator.i18n import TXT, tt


_HIVE_DIR = Path.home() / ".hermes" / "hive-v4"
_PID_FILE = _HIVE_DIR / "daemon.pid"
_LOG_FILE = _HIVE_DIR / "daemon.log"


def _detect_lang() -> str:
    """Detect language from env LANG. Defaults to en."""
    lang = os.environ.get("LANG", "").lower()
    if lang.startswith("zh"):
        return "zh"
    return "en"


_LANG = _detect_lang()


def start():
    """Start HIVE Daemon."""
    if _PID_FILE.exists():
        try:
            pid = int(_PID_FILE.read_text().strip())
            os.kill(pid, 0)
            print(tt(TXT["DAEMON_RUNNING"], _LANG, pid=pid))
            print(tt(TXT["DAEMON_DASHBOARD"], _LANG))
            return
        except (OSError, ValueError):
            _PID_FILE.unlink(missing_ok=True)

    _HIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Start background process (prefer venv Python)
    import subprocess
    _venv_python = Path(__file__).resolve().parent.parent / ".venv"
    if sys.platform == "win32":
        _venv_python = _venv_python / "Scripts" / "python.exe"
    else:
        _venv_python = _venv_python / "bin" / "python"
    python = str(_venv_python) if _venv_python.exists() else sys.executable

    proc = subprocess.Popen(
        [python, "-m", "orchestrator.mcp_server", "--daemon"],
        stdout=open(_LOG_FILE, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    _PID_FILE.write_text(str(proc.pid))

    # Wait for startup
    for _ in range(5):
        time.sleep(1)
        try:
            import urllib.request
            resp = urllib.request.urlopen("http://127.0.0.1:8421/dashboard", timeout=2)
            if resp.status == 200:
                print(tt(TXT["DAEMON_STARTING"], _LANG, pid=proc.pid))
                print(tt(TXT["DAEMON_DASHBOARD"], _LANG))
                print(tt(TXT["DAEMON_MCP"], _LANG))
                return
        except Exception:
            continue

    print(tt(TXT["DAEMON_STARTING"], _LANG, pid=proc.pid))
    print(tt(TXT["DAEMON_WAITING"], _LANG))


def stop():
    """Stop HIVE Daemon."""
    if not _PID_FILE.exists():
        print(tt(TXT["DAEMON_NOT_RUNNING"], _LANG))
        return

    try:
        pid = int(_PID_FILE.read_text().strip())
        if sys.platform == "win32":
            os.kill(pid, signal.CTRL_BREAK_EVENT)
        else:
            os.kill(pid, signal.SIGTERM)
        _PID_FILE.unlink(missing_ok=True)
        print(tt(TXT["DAEMON_STOPPED"], _LANG, pid=pid))
    except (OSError, ValueError) as e:
        print(tt(TXT["DAEMON_STOP_FAILED"], _LANG, error=e))
        _PID_FILE.unlink(missing_ok=True)


def status(text_mode: bool = False):
    """Check HIVE Daemon status."""
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8421/dashboard", timeout=3)
        if resp.status == 200:
            pid_info = ""
            if _PID_FILE.exists():
                try:
                    pid_info = f" (PID {_PID_FILE.read_text().strip()})"
                except Exception:
                    pass
            print(f"{tt(TXT['DAEMON_STATUS_OK'], _LANG)}{pid_info}")
            print(tt(TXT["DAEMON_DASHBOARD"], _LANG))
            print(tt(TXT["DAEMON_MCP"], _LANG))

            if text_mode:
                try:
                    url = "http://127.0.0.1:8421/mcp"
                    req = urllib.request.Request(
                        url,
                        data=json.dumps({"jsonrpc": "2.0", "method": "tools/call",
                                         "params": {"name": "hive_status", "arguments": {}},
                                         "id": 1}).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    mcp_resp = urllib.request.urlopen(req, timeout=5)
                    data = json.loads(mcp_resp.read())
                    result = data.get("result", {})
                    label = "daemon status" if _LANG == "en" else "daemon状态"
                    print(f"\n--- {label} ---")
                    print(f"Session: {result.get('session_id', '-')}")
                    print(f"Phase: {result.get('state', 'idle')}")
                    print(f"Project: {result.get('project_name', '-')}")
                except Exception as e:
                    print(f"\n({e})")
            return
    except Exception:
        pass

    print(tt(TXT["DAEMON_STATUS_DEAD"], _LANG))
    _PID_FILE.unlink(missing_ok=True)


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        start()
        return

    cmd = sys.argv[1]
    if cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "status":
        text_mode = "--text" in sys.argv
        status(text_mode=text_mode)
    else:
        print(tt(TXT["DAEMON_UNKNOWN_CMD"], _LANG, cmd=cmd))
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
