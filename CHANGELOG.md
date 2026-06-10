# Changelog

## v4.1.2 (2026-06-10)

### Fixed
- `python start.py` now works without arguments (defaults to `start` command)

---

## v4.1.1 (2026-06-10)

### Fixed
- Cleaned `_dev/` artifacts from git tracking
- Updated `.gitignore` (dev/ temp/ png coverage)
- Fixed PyPI classifiers (removed invalid AI classifier, SPDX license string)

### Added
- Dashboard screenshot in README as live demo evidence
- "Customize & Extend" section emphasizing open-source / MCP architecture

---

## v4.1.0 (2026-06-10)

### Added
- i18n system: CLI / Dashboard / LLM prompts support Chinese and English
- Language toggle: Dashboard `?lang=zh|en` URL parameter + toggle button
- Cross-platform daemon launcher: `python start.py`
- SDK auto-install: `hive_install_sdk` tool downloads Flutter SDK on demand
- Workspace APIs: `/api/workspace` (disk path), `/api/clean` (temp file cleanup)
- File browser: `/api/tree`, `/api/read` HTTP routes for Dashboard
- Artifact detection: multi-location scan (dist/, build/, target/)

### Changed
- Default language from Chinese to English
- LLM prompts available in both Chinese and English
- `pyproject.toml`: added `[build-system]`, authors, license, classifiers
- `hermes_runner.py` / `hermes_wrapper.py`: Hermes CLI search path now cross-platform
- Dashboard redesigned with Vercel design language
- Daemon CLI output uses `tt()` i18n function

### Fixed
- `_schema_version` table bloat (INSERT OR IGNORE without UNIQUE constraint)
- `_ACTIVE_ORCHESTRATORS` memory leak (added cleanup wrapper)
- SQLite concurrent write lock (threading.Lock)
- `hive_memory` return format inconsistency
- `hive_artifact` only searched `dist/` directory
- Dashboard file browser path handling
- Duplicate `dependencies done` progress event in Toolman
