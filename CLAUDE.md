# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**devBoard** — A generic project dashboard tool that scans a workspace directory, detects sub-projects (tech stack, git status, versions, TODOs), and presents them in a web UI with Claude Code plan integration. Users configure the workspace path via the browser; it persists across restarts.

## Commands

```bash
# Start server (default port 9999)
python -m dashboard.server

# Start on custom port
DASHBOARD_PORT=8080 python -m dashboard.server

# CLI-only scan (writes data/dashboard.json, no server)
python -m dashboard.scanner
```

## Architecture

Three-layer design: **Config -> Scanner -> Server**

```
dashboard/
├── config.py    # Single source of truth for all paths and workspace settings
├── scanner.py   # Stateless scanning engine — pure functions, parameterized
├── server.py    # Flask routes, merges scanner output with user-edited statuses
└── templates/   # Jinja2 HTML (dashboard.html, setup.html, plan_detail.html)
```

### Data flow

1. **Startup**: `server.py` calls `migrate_legacy_config()` (one-time import from `projects_config.json` -> `app_config.json`)
2. **Request**: `GET /` -> checks `config.get_workspace()` -> no workspace? redirect `/setup` -> has workspace? load `data/dashboard.json` -> merge `plans_status.json` -> group by category -> render
3. **Setup**: User enters directory path -> `POST /api/workspace` -> `config.set_workspace()` -> `scanner.scan_all()` -> redirect to dashboard
4. **Rescan**: `POST /scan` -> re-runs scanner with current config -> redirect

### Path resolution

All paths derive from `__file__` relative positions — **no hardcoded absolute paths**:
- `config.py`: `DATA_DIR = __file__/../../data/` — stores `app_config.json`, `plans_status.json`
- `scanner.py`: `OUTPUT_FILE = __file__/../../data/dashboard.json`
- `server.py`: `DATA_DIR = __file__/../data/` (same location via different traversal)

Workspace and plans directory come from `app_config.json` at runtime.

### Design System

UI uses a **dark header + light body** pattern (Sentry-inspired, blue palette):
- Header: navy gradient (`#0f1a2e`), white text, lime-green title accent
- Body: light blue-tinted white (`#f5f7fb`), white cards
- Interactive: `#3b82f6` (brand blue), status colors: green/orange/gray/pink
- Fonts: Rubik (system fallback), SF Mono for code/paths
- CSS variables defined in `:root` block of each template

### Persistence files (in `data/`, gitignored)

| File | Purpose | Written by |
|------|---------|-----------|
| `app_config.json` | Workspace path, per-workspace project metadata, category order | config.py |
| `dashboard.json` | Full scan output (overwritten each scan) | scanner.py |
| `plans_status.json` | User-edited plan statuses (preserved across scans) | server.py |

### Key APIs

- `GET/POST/DELETE /api/workspace` — workspace management
- `PATCH /api/plan/<filename>/status` — update plan status (not_started/in_progress/completed/deleted)
- `GET /api/data` — raw JSON scan data
- `POST /scan` — trigger rescan

## Key design decisions

- **Scanner is stateless**: `scan_all(workspace_path, plans_dir, project_config)` — no module-level workspace constants
- **Plan matching is dynamic**: project names extracted from workspace directory listing, not hardcoded
- **Soft delete for plans**: marks as deleted in `plans_status.json`, doesn't remove the file
- **Category ordering**: per-workspace, stored in `app_config.json` under `workspaces.<path>.categories_order`
- **Template caching disabled**: `TEMPLATES_AUTO_RELOAD=True` for development convenience
