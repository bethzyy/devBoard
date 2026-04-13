"""
Dashboard Configuration Manager.
Manages workspace paths and per-workspace project configs in a single app_config.json.
"""

import json
from pathlib import Path

# Tool-internal paths (never workspace-dependent)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
APP_CONFIG_FILE = DATA_DIR / "app_config.json"
LEGACY_CONFIG_FILE = Path(__file__).resolve().parent / "projects_config.json"


def load_config():
    """Load app config, returning empty defaults if file missing."""
    if not APP_CONFIG_FILE.exists():
        return {"workspace": None, "plans_dir": None, "workspaces": {}}
    try:
        with open(APP_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # Ensure keys exist
        cfg.setdefault("workspace", None)
        cfg.setdefault("plans_dir", None)
        cfg.setdefault("workspaces", {})
        return cfg
    except (json.JSONDecodeError, OSError):
        return {"workspace": None, "plans_dir": None, "workspaces": {}}


def save_config(config):
    """Save config to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(APP_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _normalize_path(path_str):
    """Normalize a path string to a canonical form for use as dict key."""
    return str(Path(path_str).resolve()).replace("\\", "/")


def get_workspace():
    """Get configured workspace path, or None."""
    cfg = load_config()
    ws = cfg.get("workspace")
    if ws and Path(ws).is_dir():
        return Path(ws)
    return None


def set_workspace(path_str):
    """Set workspace path, save config, return updated config."""
    cfg = load_config()
    cfg["workspace"] = _normalize_path(path_str)
    # Ensure workspace block exists
    ws_key = cfg["workspace"]
    cfg["workspaces"].setdefault(ws_key, {"categories_order": [], "projects": {}})
    save_config(cfg)
    return cfg


def get_plans_dir():
    """Get plans directory path. Defaults to ~/.claude/plans."""
    cfg = load_config()
    custom = cfg.get("plans_dir")
    if custom:
        p = Path(custom)
        if p.is_dir():
            return p
    return Path.home() / ".claude" / "plans"


def get_project_config(ws_path_str):
    """Get per-workspace project config dict."""
    cfg = load_config()
    ws_key = _normalize_path(ws_path_str)
    return cfg.get("workspaces", {}).get(ws_key, {})


def get_project_meta(ws_path_str):
    """Get the projects metadata dict for a workspace."""
    ws_cfg = get_project_config(ws_path_str)
    return ws_cfg.get("projects", {})


def get_categories_order(ws_path_str):
    """Get category ordering for a workspace."""
    ws_cfg = get_project_config(ws_path_str)
    order = ws_cfg.get("categories_order", [])
    return order if order else None


def save_project_config(ws_path_str, projects_meta, categories_order=None):
    """Save per-workspace project config."""
    cfg = load_config()
    ws_key = _normalize_path(ws_path_str)
    cfg["workspaces"].setdefault(ws_key, {})
    cfg["workspaces"][ws_key]["projects"] = projects_meta
    if categories_order:
        cfg["workspaces"][ws_key]["categories_order"] = categories_order
    save_config(cfg)


def migrate_legacy_config():
    """One-time migration from projects_config.json to app_config.json.

    If projects_config.json exists and app_config.json has no workspaces data,
    import the legacy config.
    """
    if not LEGACY_CONFIG_FILE.exists():
        return

    cfg = load_config()

    # Only migrate if workspaces is empty
    if any(ws.get("projects") for ws in cfg.get("workspaces", {}).values()):
        return

    try:
        with open(LEGACY_CONFIG_FILE, "r", encoding="utf-8") as f:
            legacy = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    # Determine workspace from legacy WORKSPACE_ROOT (3 levels up from dashboard/)
    legacy_workspace = str(
        Path(__file__).resolve().parent.parent.parent
    ).replace("\\", "/")

    # Set as current workspace
    cfg["workspace"] = legacy_workspace
    cfg["workspaces"][legacy_workspace] = {
        "categories_order": [
            "AI 产品", "求职工具链", "AI 基础设施",
            "开发工具", "知识库 & 文档", "实验 & 兴趣",
        ],
        "projects": legacy,
    }
    save_config(cfg)
    print(f"Migrated legacy config for workspace: {legacy_workspace}")
