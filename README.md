<div align="center">

<br>

# **HIVE** v4.1

**Multi-Agent Build Orchestrator**

<br>

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3ecf8e?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License MIT](https://img.shields.io/badge/License-MIT-171717?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/✓-152%20tests-171717?style=flat-square)](tests/)
[![Hermes](https://img.shields.io/badge/Powered%20by-Hermes%20Agent-533afd?style=flat-square)](https://github.com/NousResearch/hermes-agent)

> **One sentence → automated build → iterable artifact.**

<br>

</div>

---

## ✦ Overview

HIVE is an **AI-native build orchestration engine**. Feed it a sentence — _"make a calculator with Python tkinter"_ — and six specialized agent roles (ARC, PLANNER, CODER, TESTER, REVIEWER, TOOLMAN) translate, decompose, generate, test, review, and package your project into a shippable artifact. With iteration loops, rollback, and cross-project memory.

Built on [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous Research.

<br>

---

## ✦ Quick Start

<div align="center">

### **1.** Install Hermes Agent

</div>

Choose your platform:

| Platform | Command |
|----------|---------|
| 🐧 Linux / macOS / WSL2 | `curl -fsSL https://hermes-agent.nousresearch.com/install.sh \| bash` |
| 🪟 Windows (PowerShell) | `iex (irm https://hermes-agent.nousresearch.com/install.ps1)` |
| 📦 pip (any OS) | `pip install hermes-agent` |

```bash
hermes setup   # configure your LLM provider
hermes --version
# → Hermes Agent v0.16.0
```

<div align="center">

### **2.** Install & Start HIVE

</div>

```bash
pip install -e ".[dev]"
python start.py
# → Dashboard:  http://127.0.0.1:8421/dashboard
# → MCP:        http://127.0.0.1:8421/mcp
```

> 💡 Hermes stores its config at `~/.hermes/`. HIVE stores sessions at `~/.hermes/hive-v4/`.

<div align="right">
  <sub><a href="#install-hermes-agent">↑ Full install guide</a></sub>
</div>

---

## ✦ Architecture

Six agents collaborate through a **7-state pipeline**, coordinated by a central orchestrator.

```
                    ┌──────────────────────────────────────────────┐
                    │           H I V E   O r c h e s t r a t o r  │
                    └──────────┬───────────────────────┬───────────┘
                               │                       │
    ┌──────────┐    ┌──────────▼────────┐    ┌─────────▼──────────┐
    │  INPUT   │    │      ARC          │    │     PLANNER        │
    │  "Build  │───▶│  (Architect)      │───▶│  (Decomposition)   │
    │   calc"  │    │  → brief.json     │    │  → dag.json        │
    └──────────┘    └───────────────────┘    └─────────┬──────────┘
                                                        │
                    ┌───────────────────────────────────▼────────────┐
                    │     CODER POOL (×3 parallel)    +   TESTER    │
                    │     ┌──────────┐ ┌──────────┐ ┌──────────┐    │
                    │     │  coder 1 │ │  coder 2 │ │  coder 3 │    │
                    │     └──────────┘ └──────────┘ └──────────┘    │
                    └───────────────────────┬───────────────────────┘
                                            │
                    ┌───────────────────────▼───────────────────────┐
                    │            REVIEWER (4-layer)                │
                    │  L1 syntax  ·  L2 alignment  ·  L3 security  │
                    │  ·  L4 consistency                           │
                    └───────────────────────┬───────────────────────┘
                                            │
                    ┌───────────────────────▼───────────────────────┐
                    │  TOOLMAN  →  install deps  →  run tests      │
                    │           →  package artifact                │
                    └───────────────────────────────────────────────┘
```

**States**: `idle → translating → planning → executing → testing → done`  
**Loop**:  ↻ `done → idle` — iterate until satisfied.

---

## ✦ Features

<br>

|  | Feature |  |
|---|---|---|
| 🛠️ | **15 MCP Tools** — Build, iterate, diff, rollback, status, file ops, SDK install, memory, and more | `hive_build` · `hive_iterate` · `hive_rollback` |
| 🌐 | **Cross-platform** — Windows · macOS · Linux | Same codebase, zero platform hacks |
| 🌍 | **i18n** — English + Chinese UI & LLM prompts | `?lang=zh` or `LANG=zh_CN` to switch |
| 📊 | **Dashboard** — Real-time WebSocket console with file browser, artifact viewer, live logs | Built with FastAPI + uvicorn |
| 📦 | **Auto SDK Install** — `hive_install_sdk("flutter")` downloads missing toolchains on demand | Supports Python, Flutter, Rust, Go, Node |
| 🔖 | **Versioning** — Snapshot-based with diff & rollback | `hive_diff(sid, v1, v2)` |
| 💰 | **Cost Tracking** — Per-build and daily budget limits with warning thresholds | Configurable via `hive.json` |
| 🛡️ | **Sandbox** — Isolated execution with timeout and cross-platform process tree kill | `start_new_session` + `killpg` fallback |
| 🧠 | **Cross-project Memory** — Learns preferences and extracts skills across builds | `hive_memory(action="stats")` |
| 📎 | **File Upload** — .txt / .md / .json / .yaml / .py as build requirements | Drag-and-drop on Dashboard |

### Supported Tech Stacks

| Stack | Test Runner | Build | Artifact |
|-------|-------------|-------|----------|
| Python + tkinter | `pytest` | PyInstaller | `.exe` |
| Python + FastAPI | `pytest` | Docker | `.tar` |
| Flutter / Dart | `flutter test` | `flutter build apk` | `.apk` |
| Rust | `cargo test` | `cargo build --release` | binary |
| Go | `go test` | `go build` | binary |
| Node.js / React | `vitest` | `vite build` | static |

<br>

---

## ✦ MCP Tools

| Tool | Purpose |
|------|---------|
| `hive_build(description)` | Start a new build |
| `hive_iterate(session_id, request)` | Iterate on existing project |
| `hive_rollback(session_id, version)` | Rollback to a previous version |
| `hive_versions(session_id)` | List all versions |
| `hive_diff(session_id, v1, v2)` | Diff two versions |
| `hive_status(session_id)` | Query build status (state, progress, ETA) |
| `hive_cancel(session_id)` | Cancel a running build |
| `hive_ls(path)` | Browse workspace files |
| `hive_read(path)` | Read file content |
| `hive_artifact(session_id)` | List build artifacts |
| `hive_list_projects()` | List all projects |
| `hive_delete_project(name)` | Delete a project |
| `hive_dashboard_url()` | Get the dashboard URL |
| `hive_memory(action)` | Cross-project memory (stats / preferences) |
| `hive_install_sdk(tech_stack)` | Download a missing SDK |

<br>

---

## ✦ Python SDK

```python
from hive_client import HiveClient

client = HiveClient(url="http://127.0.0.1:8421")

# One-shot build
build = client.build("Make a calculator with Python tkinter")
result = build.wait()
print(result.artifacts)

# Iterate
v2 = build.iterate("Make the buttons bigger")
v2.wait()
print(v2.diff)
```

<br>

---

## ✦ Project Structure

<details>
<summary><code>orchestrator/</code> — 6 roles · 7 infrastructure modules · dashboard · versioning</summary>

```
orchestrator/
├── mcp_server.py          # HTTP server + 15 MCP tools + dashboard routes
├── orchestrator.py        # Build orchestration loop
├── machine.py             # 7-state state machine
├── daemon.py              # Daemon CLI (start / stop / status)
├── i18n.py                # Internationalization (zh / en)
├── roles/
│   ├── arc.py             # Architect (requirements → brief.json)
│   ├── planner.py         # Planner (brief → DAG)
│   ├── coder.py           # Coder pool (3 parallel workers)
│   ├── tester.py          # Independent test writer
│   ├── reviewer.py        # 4-layer review
│   └── toolman.py         # Delivery (install / test / package)
├── infrastructure/
│   ├── session_manager.py # SQLite persistence
│   ├── sandbox.py         # Isolated execution
│   ├── cost_tracker.py    # Budget management
│   ├── validator.py       # Schema validation
│   ├── dependency_manager.py # venv management
│   ├── errors.py          # Unified error codes
│   └── memory_store.py    # Cross-project memory
├── dashboard/
│   └── templates/dashboard.html  # Web console
├── versioning/
│   └── version_manager.py # Snapshot versioning
├── hermes_bridge.py       # Hermes CLI bridge
├── hermes_runner.py       # Isolated subprocess runner
├── hive_client.py         # Python SDK
└── hermes_wrapper.py      # (deprecated)
```
</details>

<br>

---

## ✦ Install Hermes Agent

Hermes Agent (by [Nous Research](https://github.com/NousResearch)) powers all LLM calls — ARC, PLANNER, CODER, TESTER, REVIEWER. HIVE invokes it through `hermes_bridge.py`.

**Linux / macOS / WSL2**
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc
hermes setup
```

**Windows (native PowerShell)**
```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
# Then restart terminal:
hermes setup
```

**Via pip (any platform)**
```bash
pip install hermes-agent
hermes setup
```

Verify: `hermes --version` → `Hermes Agent v0.16.0`

<br>

---

## ✦ Configuration

Adjust runtime behavior via `hive.json` in the project root:

```json
{
  "version": "4.1.0",
  "mcp_port": 8421,
  "dashboard": true,
  "max_workers": 3,
  "cost": {
    "max_per_build_usd": 5.0,
    "max_daily_usd": 20.0,
    "warn_at_usd": 1.0
  }
}
```

See [docs/hive-json.md](docs/hive-json.md) for all fields and examples.

<br>

---

## ✦ Language / 语言

<pre>
<b>English</b> is the default.  Append <code>?lang=zh</code> to the Dashboard URL
or set <code>LANG=zh_CN</code> in your environment to switch to <b>Chinese</b>.

<b>默认英文。</b> 在 Dashboard URL 后加 <code>?lang=zh</code> 或在终端设置
<code>LANG=zh_CN</code> 即可切换为中文。
</pre>

LLM role prompts (ARC, PLANNER, CODER, TESTER) are available in both languages.

<br>

---

## ✦ Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

| Test suite | Count | Depends on Hermes |
|------------|-------|-------------------|
| `tests/test_unit.py` | 21 | ❌ |
| `tests/test_edge.py` | 18 | ❌ |
| `tests/test_mock.py` | 77 | ❌ |
| `tests/test_phase1_acceptance.py` | 36 | ⚠️ partial |
| `tests/test_phase2_acceptance.py` | — | ⚠️ partial |
| `tests/test_phase3_acceptance.py` | — | ⚠️ partial |

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

<br>

---

## ✦ Project Status

**Beta** — v4.1.0. Handles Python projects reliably; Flutter / Rust / Go / Node support requires the corresponding SDK on the host.

<br>

---

<div align="center">

| | |
|---|---|
| [![License MIT](https://img.shields.io/badge/License-MIT-171717?style=flat-square)](LICENSE) | [![GitHub Issues](https://img.shields.io/github/issues/Ebonyhtx/Hermes-Hive?style=flat-square&color=171717)](https://github.com/Ebonyhtx/Hermes-Hive/issues) |
| [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-3ecf8e?style=flat-square)](.github/PULL_REQUEST_TEMPLATE.md) | [![Built by Nous Research](https://img.shields.io/badge/Built%20by-Nous%20Research-533afd?style=flat-square)](https://nousresearch.com) |

**MIT** — see [LICENSE](LICENSE).

<br>

</div>
