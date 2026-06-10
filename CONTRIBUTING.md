# Contributing to HIVE v4

Thank you for considering contributing! This document outlines the guidelines.

## Before You Start

- **Check existing issues** — someone may already be working on it.
- **Open an issue first** for significant changes — get feedback before writing code.
- **Follow the project conventions** — see below.

## Development Setup

```bash
# Clone and enter project
git clone <repo>
cd hermes-hive-v4

# Create virtual environment
uv venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Unix

# Install in editable mode
pip install -e ".[dev]"

# Run tests
pytest tests/
```

## Code Style

- **One file, one responsibility.** One function, one responsibility.
- **Names carry information.** Avoid `tmp`, `data`, `handler`.
- **Comments explain "why", not "what".** Code explains itself.
- **Handle errors.** No bare `except: pass`.
- **Cross-platform is default.** Windows, macOS, Linux.

See `SOUL.md` for the full working principles.

## Pull Request Process

1. Ensure tests pass: `pytest tests/`
2. Add tests for new functionality.
3. Update `README.md` if changing the interface.
4. Keep commits small and descriptive.
5. Reference the issue number in your commit message.

## i18n

User-visible text should be added to `orchestrator/i18n.py` with both `zh` and `en` entries.

- CLI output: use `tt(TXT.MY_KEY, lang)`
- Dashboard: add to `_T` map in `dashboard.html`
- LLM prompts: keep `_ZH` and `_EN` variants in the role file

## Architecture

```
mcp_server.py    → HTTP server + 14 MCP tools
orchestrator.py  → Build orchestration loop
machine.py       → 7-state machine
roles/           → Agent roles (arc, planner, coder, tester, reviewer, toolman)
infrastructure/  → SQLite, sandbox, cost tracker, validator, memory
dashboard/       → WebSocket real-time dashboard
i18n.py          → Internationalization
```

## Questions?

Open a discussion or issue. We're here to help.
