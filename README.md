# devBoard

A generic project dashboard that scans a workspace directory, detects sub-projects (tech stack, git status, versions, TODOs), and presents them in a web UI with Claude Code plan integration.

## Features

- **Auto-detection**: Scans workspace for sub-projects, detecting tech stack, git status, versions, entry points, and TODO counts
- **Claude Code plans**: Parses `~/.claude/plans/` and links plans to projects by keyword matching
- **Category grouping**: Projects grouped by configurable categories with custom ordering
- **Status tracking**: Derives project status (active/stale/complete) from activity signals, with manual override
- **Plan status management**: Mark plans as not started, in progress, completed, or soft-deleted
- **Filtering & search**: Filter by status, search across project names, descriptions, and plans
- **Configurable workspace**: Set workspace path via browser, persists across restarts

## Quick Start

```bash
# Start server (default port 9999)
python -m dashboard.server

# Custom port
DASHBOARD_PORT=8080 python -m dashboard.server

# CLI-only scan (writes data/dashboard.json, no server)
python -m dashboard.scanner
```

Open http://localhost:9999 and enter your workspace directory path.

## Requirements

- Python 3.8+
- Flask
- Markdown

```bash
pip install flask markdown
```

## Architecture

```
dashboard/
├── config.py    # Workspace config, persistence, migration
├── scanner.py   # Stateless scanning engine (pure functions)
├── server.py    # Flask routes, merges scanner output with user edits
└── templates/   # Jinja2 HTML (dashboard, setup, plan detail)
```

**Data flow**: Config -> Scanner -> Server -> Browser

1. User sets workspace path via `/setup` page
2. Scanner walks the workspace, detects projects and plans
3. Server merges scan data with user-edited statuses
4. Dashboard renders grouped, filterable project table

### Data files (in `data/`)

| File | Purpose |
|------|---------|
| `app_config.json` | Workspace path, project metadata, category order |
| `dashboard.json` | Full scan output (regenerated each scan) |
| `plans_status.json` | User-edited plan statuses (preserved across scans) |

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard (redirects to `/setup` if no workspace) |
| GET | `/setup` | Workspace configuration page |
| POST | `/scan` | Trigger rescan |
| GET | `/plan/<filename>` | View single plan rendered as HTML |
| GET | `/api/workspace` | Get workspace info |
| POST | `/api/workspace` | Set workspace path (triggers scan) |
| DELETE | `/api/workspace` | Reset workspace |
| PATCH | `/api/plan/<filename>/status` | Update plan status |
| GET | `/api/data` | Raw JSON scan data |

## License

MIT
