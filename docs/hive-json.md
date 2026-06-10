# HIVE Configuration (`hive.json`)

The `hive.json` file in the project root controls HIVE's runtime behavior. It is read at daemon startup by `orchestrator/mcp_server.py`.

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

---

## Fields

### `version` (string)

HIVE schema version. Currently `"4.1.0"`. Used for forward compatibility.

### `mcp_port` (integer, default: `8421`)

Port the daemon listens on for both the MCP JSON-RPC endpoint and the Dashboard web UI.

```
http://127.0.0.1:{mcp_port}/dashboard
http://127.0.0.1:{mcp_port}/mcp
```

### `dashboard` (boolean, default: `true`)

Whether to serve the web-based Dashboard UI alongside the MCP API. Set to `false` in headless/CI environments to save resources.

### `max_workers` (integer, default: `3`)

Max number of parallel Coder worker processes for code generation. Higher values may speed up multi-file builds but consume more Hermes-agent quota.

---

## `cost` object

Controls token-based cost estimation and budget enforcement.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_per_build_usd` | number | `5.0` | Hard cap per single build iteration. Build is aborted if exceeded. |
| `max_daily_usd` | number | `20.0` | Hard cap for all builds combined in a calendar day. |
| `warn_at_usd` | number | `1.0` | Emit a warning to the Dashboard log at this threshold. |

All values are in **USD**. Cost is calculated from token usage (input/output) using conservative per-1K-token rates:

- Input: `$0.00015 / 1K tokens`
- Output: `$0.00060 / 1K tokens`

These are deliberately above typical GPT-4o/Claude pricing to provide a safety margin.

---

## Example: Minimal config

```json
{
  "version": "4.1.0",
  "mcp_port": 8421,
  "max_workers": 2
}
```

Missing fields fall back to their defaults. `max_workers: 2` reduces parallelism for slower machines.

---

## Example: CI / headless config

```json
{
  "version": "4.1.0",
  "mcp_port": 8421,
  "dashboard": false,
  "max_workers": 1,
  "cost": {
    "max_per_build_usd": 10.0,
    "max_daily_usd": 50.0
  }
}
```

Disables the Dashboard HTML renderer and sets higher budget limits for longer-running CI builds.

---

## Notes

- The daemon reads `hive.json` once at startup. Restart the daemon to pick up changes.
- If `hive.json` is missing or invalid JSON, the daemon falls back to internal defaults and logs a warning.
- Cost tracking requires `session_manager.py` (SQLite). Budget caps are enforced in `cost_tracker.py`.
