# devBoard PRD (Product Requirements Document)

## 1. Product Overview

**devBoard** is a lightweight project dashboard for developers who manage multiple projects in a single workspace. It provides a single-pane-of-glass view of all sub-projects, their health status, associated plans, and development activity.

### Target Users

- Developers managing 5+ projects in a workspace
- Teams using Claude Code for plan-driven development
- Anyone who wants a quick overview of project portfolio health

### Core Value Proposition

Replace manual mental tracking and scattered notes with an auto-generated, always-up-to-date dashboard that answers: *What projects do I have? Which are active? What's the plan?*

---

## 2. Functional Requirements

### FR-1: Workspace Configuration

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-1.1 | User can set a workspace root directory via web UI | P0 | Done |
| FR-1.2 | Workspace path persists across server restarts | P0 | Done |
| FR-1.3 | User can switch workspace at any time | P1 | Done |
| FR-1.4 | User can reset workspace back to unconfigured state | P2 | Done |

### FR-2: Project Scanning

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-2.1 | Auto-detect sub-directories as projects | P0 | Done |
| FR-2.2 | Detect tech stack from file markers (requirements.txt, package.json, etc.) | P0 | Done |
| FR-2.3 | Detect git status: commit count, last commit message | P0 | Done |
| FR-2.4 | Detect version from CHANGELOG.md | P1 | Done |
| FR-2.5 | Count TODO/FIXME/TBD markers in source files | P1 | Done |
| FR-2.6 | Derive activity status from multiple signals (git, file mtime, CLAUDE.md) | P0 | Done |
| FR-2.7 | Support manual status override per project | P1 | Done |
| FR-2.8 | Skip common non-project directories (node_modules, .git, __pycache__, etc.) | P0 | Done |

### FR-3: Plan Integration

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-3.1 | Scan Claude Code plans directory (`~/.claude/plans/`) | P0 | Done |
| FR-3.2 | Auto-link plans to projects by keyword matching in plan content | P0 | Done |
| FR-3.3 | Display plan title, date, and summary excerpt | P0 | Done |
| FR-3.4 | Render plan markdown as HTML in a detail page | P1 | Done |
| FR-3.5 | Allow user to set plan status (not_started/in_progress/completed/deleted) | P0 | Done |
| FR-3.6 | Soft-delete plans (mark deleted, don't remove file) | P1 | Done |
| FR-3.7 | Show 20 most recent plans in a sidebar section | P2 | Done |

### FR-4: Dashboard UI

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-4.1 | Display all projects in a grouped table (by category) | P0 | Done |
| FR-4.2 | Summary cards showing project/plan/TODO counts | P0 | Done |
| FR-4.3 | Filter by status (active/stale/complete/has-docs) | P0 | Done |
| FR-4.4 | Full-text search across project names, descriptions, plans | P0 | Done |
| FR-4.5 | Collapsible category groups | P1 | Done |
| FR-4.6 | Color-coded status badges and activity age indicators | P1 | Done |
| FR-4.7 | Rescan button to refresh data | P0 | Done |
| FR-4.8 | Responsive layout for mobile/tablet | P2 | Done |

### FR-5: Project Metadata

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-5.1 | Assign category per project (user-configurable) | P0 | Done |
| FR-5.2 | Assign priority (high/medium/low) per project | P1 | Done |
| FR-5.3 | Assign project type (Web App, CLI Tool, etc.) | P1 | Done |
| FR-5.4 | Custom category ordering (user-configurable) | P1 | Done |
| FR-5.5 | Metadata persists across rescans | P0 | Done |

---

## 3. Non-Functional Requirements

| ID | Requirement | Target | Status |
|----|-------------|--------|--------|
| NFR-1 | Scan time for 50 projects | < 30 seconds | Met |
| NFR-2 | Page load time (after scan) | < 2 seconds | Met |
| NFR-3 | Scanner is stateless (pure functions, no side effects except output file) | Must | Met |
| NFR-4 | No hardcoded absolute paths | Must | Met |
| NFR-5 | No external API dependencies (runs fully offline) | Must | Met |
| NFR-6 | Plan status changes survive rescan | Must | Met |

---

## 4. Design System

### Visual Identity

The UI follows a **dark header + light body** pattern, inspired by the Sentry design system adapted with a blue color palette. Selected through multi-angle scoring across 58 real-world design themes.

**Selection rationale:**
- Sentry scored highest (67/100) across 3 industry angles (developer-tools, saas, ai-ml)
- Personality match: `playful + technical + vibrant` — only theme scoring >30 on personality dimension
- Adapted from full dark mode to dark-header/light-body after user feedback that pure dark felt too heavy

### Color Palette

| Role | Color | Hex |
|------|-------|-----|
| Header background | Navy gradient | `#0f1a2e` -> `#162a48` |
| Interactive / Links | Brand blue | `#3b82f6` |
| Active status | Green | `#3d7a10` |
| Stale status | Orange | `#b56e1a` |
| Complete status | Muted purple-gray | `#7a74a0` |
| Paused status | Pink | `#b5446a` |
| Body background | Light blue-white | `#f5f7fb` |
| Cards / Surfaces | White | `#ffffff` |
| Borders | Blue-gray | `#dde3ef` |

### Typography

- **UI font**: Rubik (system fallback: -apple-system, Segoe UI, Helvetica)
- **Code/paths**: SF Mono / Fira Code / Consolas monospace
- **Labels**: Uppercase with letter-spacing (Sentry pattern)

---

## 5. Technical Architecture

### Three-Layer Design

```
Config Layer (config.py)
    | workspace path, project metadata
Scanner Layer (scanner.py)
    | dashboard.json
Server Layer (server.py)
    | merge with plans_status.json -> HTML
Browser
```

### Key Design Decisions

1. **Scanner is stateless**: `scan_all(workspace_path, plans_dir, project_config)` — no module-level state, testable in isolation
2. **Plan matching is dynamic**: project names come from workspace directory listing at scan time, not hardcoded
3. **Soft delete for plans**: deleted plans are marked in `plans_status.json`, source file untouched
4. **Per-workspace config**: category order and project metadata are keyed by workspace path in `app_config.json`
5. **Dark header + light body**: visual depth from navy header, readability from light content area

### Status Derivation Logic

```
days_since_activity <= 14  -> active
days_since_activity <= 60  -> stale
days_since_activity > 60   -> stale
manual override            -> user-specified status
```

Activity signals (in priority order):
1. Git last commit date
2. CLAUDE.md modification time
3. CHANGELOG.md modification time
4. Most recently modified source file

---

## 6. Data Model

### app_config.json

```json
{
  "workspace": "C:/path/to/workspace",
  "plans_dir": null,
  "workspaces": {
    "C:/path/to/workspace": {
      "categories_order": ["Category A", "Category B"],
      "projects": {
        "project-name": {
          "category": "Category A",
          "priority": "high",
          "project_type": "Web App",
          "status_override": "complete"
        }
      }
    }
  }
}
```

### dashboard.json (scan output)

```json
{
  "scan_time": "2026-04-14 10:00:00",
  "workspace": "C:/path/to/workspace",
  "total_projects": 35,
  "total_plans": 134,
  "summary": { "active": 7, "stale": 17, "complete": 4, "paused": 0, "total_todos": 168 },
  "projects": [...],
  "recent_plans": [...]
}
```

---

## 7. Future Considerations (Out of Scope for v1)

- [ ] Project detail page with full metadata editing
- [ ] Drag-and-drop category ordering in UI
- [ ] WebSocket for live scan progress
- [ ] Multi-user support with authentication
- [ ] Export to PDF/CSV
- [ ] Trend charts (project activity over time)
- [ ] Integration with GitHub Issues / Jira
- [ ] Configurable scan schedule (auto-rescan interval)
- [ ] Dark/light mode toggle
