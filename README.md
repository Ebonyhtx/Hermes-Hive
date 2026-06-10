# HIVE v4.1 — Multi-Agent Build Orchestrator

> One sentence → automated build → iterable artifact.

HIVE is a multi-agent orchestration system built on top of [Hermes Agent](https://github.com/NousResearch/hermes-agent). Describe what you want in one sentence, and HIVE handles the rest: requirements translation, task decomposition, coding, testing, review, and packaging — with support for iterative refinement.

---

## Quick Start

```bash
# Requires Python ≥ 3.11 and Hermes Agent installed

# Install HIVE
pip install -e ".[dev]"

# Start the daemon
python start.py
# → Dashboard: http://127.0.0.1:8421/dashboard
# → MCP:       http://127.0.0.1:8421/mcp

# Check status
python start.py status

# Stop daemon
python start.py stop
```

### Install Hermes Agent

Hermes Agent (by [Nous Research](https://github.com/NousResearch)) is the LLM backend that powers ARC, PLANNER, CODER, TESTER, and REVIEWER. It runs as a CLI tool that HIVE invokes through `hermes_bridge.py`.

**Linux / macOS / WSL2**
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc    # or ~/.zshrc
hermes setup        # configure your LLM provider
```

**Windows (native, PowerShell)**
```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
# Then restart your terminal and run:
hermes setup
```

**Via pip (any platform)**
```bash
pip install hermes-agent
hermes setup
```

After installation, verify:
```bash
hermes --version
# → Hermes Agent v0.16.0
```

> 💡 Hermes stores its configuration at `~/.hermes/`. The setup wizard helps you pick an LLM provider (OpenAI, Nous Portal, OpenRouter, etc.).

### Requirements

- **Python ≥ 3.11**
- **[Hermes Agent](https://github.com/NousResearch/hermes-agent)** — LLM calls (install separately, see below)
- Dependencies: fastmcp, fastapi, uvicorn, transitions, httpx, pydantic

---

## How It Works

```
User Input → ARC → PLANNER → CODER + TESTER → REVIEWER → TOOLMAN → Artifact
              ↑        ↑         ↑               ↑          ↑
         Translate  Schedule   Execute         Review    Package
```

**7-state machine**: `idle → translating → planning → executing → testing → done` (with iteration loop)

**6 agent roles**:
| Role | Responsibility |
|------|---------------|
| **ARC** | Translates natural language → structured brief.json |
| **PLANNER** | Breaks brief → DAG of tasks |
| **CODER** | Generates code (3 parallel workers) |
| **TESTER** | Writes test cases independently |
| **REVIEWER** | 4-layer review (syntax, alignment, security, consistency) |
| **TOOLMAN** | Installs deps, runs tests, packages artifacts |

---

## Features

| Feature | Description |
|---------|-------------|
| **14 MCP tools** | Build, iterate, diff, rollback, status — full API via MCP |
| **Cross-platform** | Windows / macOS / Linux |
| **i18n** | Chinese and English UI + LLM prompts. `?lang=zh` or `LANG=zh_CN` to switch |
| **Dashboard** | Real-time WebSocket console with file browser, artifact viewer, log |
| **Auto SDK install** | `hive_install_sdk("flutter")` downloads missing toolchains |
| **File upload** | Upload `.txt/.md/.json/.yaml/.py` as build requirements |
| **Versioning** | Snapshot-based version manager with diff and rollback |
| **Cost tracking** | Per-build and daily budget limits |
| **Sandbox** | Isolated execution with timeout and process tree kill |

### Supported Tech Stacks

| Stack | Test | Build | Artifact |
|-------|------|-------|----------|
| Python + tkinter | `pytest` | `pyinstaller` | `.exe` |
| Python + FastAPI | `pytest` | `docker build` | `.tar` |
| **Flutter / Dart** | `flutter test` | `flutter build apk` | `.apk` |
| Rust | `cargo test` | `cargo build --release` | binary |
| Go | `go test` | `go build` | binary |
| Node.js / React | `vitest` | `vite build` | static |

---

## MCP Tools (API)

| Tool | Purpose |
|------|---------|
| `hive_build(description)` | Start a new build |
| `hive_iterate(session_id, request)` | Iterate on existing project |
| `hive_rollback(session_id, version)` | Rollback to version |
| `hive_versions(session_id)` | List versions |
| `hive_diff(session_id, v1, v2)` | Diff two versions |
| `hive_status(session_id)` | Query build status |
| `hive_ls(path)` | Browse workspace files |
| `hive_read(path)` | Read file content |
| `hive_artifact(session_id)` | List build artifacts |
| `hive_cancel(session_id)` | Cancel running build |
| `hive_list_projects()` | List all projects |
| `hive_delete_project(name)` | Delete project |
| `hive_dashboard_url()` | Get dashboard URL |
| `hive_memory(action)` | Cross-project memory |
| `hive_install_sdk(tech_stack)` | Download missing SDK (e.g. Flutter) |

---

## Architecture

```
orchestrator/
├── mcp_server.py          # HTTP server + 15 MCP tools + dashboard routes
├── orchestrator.py        # Build orchestration loop
├── machine.py             # 7-state machine
├── daemon.py              # Daemon CLI (start/stop/status)
├── i18n.py                # Internationalization (zh/en)
├── roles/
│   ├── arc.py             # Architect (requirements → brief)
│   ├── planner.py         # Planner (brief → DAG)
│   ├── coder.py           # Coder pool (3 parallel workers)
│   ├── tester.py          # Independent test writer
│   ├── reviewer.py        # 4-layer review
│   └── toolman.py         # Delivery (install/test/package + SDK auto-install)
├── infrastructure/
│   ├── session_manager.py # SQLite persistence
│   ├── sandbox.py         # Isolated execution
│   ├── cost_tracker.py    # Budget management
│   ├── validator.py       # Schema validation
│   ├── dependency_manager.py # venv management
│   ├── errors.py          # Unified error codes
│   └── memory_store.py    # Cross-project memory
├── dashboard/
│   └── templates/dashboard.html  # Web console (Vercel design)
├── versioning/
│   └── version_manager.py # Snapshot versioning
├── hermes_bridge.py       # Hermes CLI bridge
├── hermes_runner.py       # Isolated subprocess runner
├── hive_client.py         # Python SDK
└── hermes_wrapper.py      # (deprecated)
```

---

## Python SDK

```python
from hive_client import HiveClient

client = HiveClient(url="http://127.0.0.1:8421")

# One-shot build
build = client.build("Make a calculator with Python tkinter")
result = build.wait()
print(result.artifacts)

# Iterate
v2 = build.iterate("Make buttons bigger")
v2.wait()
print(v2.diff)
```

---

## Language / 语言

**English** is the default. Append `?lang=zh` to the Dashboard URL or set `LANG=zh_CN` for the CLI to switch to **Chinese**.

**默认英文。** 在 Dashboard URL 后加 `?lang=zh` 或在终端设置 `LANG=zh_CN` 即可切换为中文。

LLM prompts — role prompts (ARC, PLANNER, CODER, TESTER) are available in both English and Chinese, selected by the `lang` parameter.

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Project Status

HIVE is in **beta** (v4.1.0). It handles Python projects reliably; Flutter/Rust/Go/Node support requires the corresponding SDK to be installed on the host.

---

## License

MIT — see [LICENSE](LICENSE).
