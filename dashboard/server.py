"""
Project Dashboard Flask Server - serves the unified project dashboard.
Supports configurable workspace — user sets workspace dir via UI.
"""

import json
import markdown
import os
import sys
from pathlib import Path
from flask import Flask, render_template, redirect, url_for, request, jsonify

from dashboard.config import (
    load_config, save_config, get_workspace, set_workspace,
    get_plans_dir, get_project_meta, get_categories_order,
    migrate_legacy_config, get_project_config,
)
from dashboard.scanner import scan_all as run_scan_all

# Tool-internal paths
DASHBOARD_DIR = Path(__file__).resolve().parent
DATA_DIR = DASHBOARD_DIR.parent / "data"
DASHBOARD_JSON = DATA_DIR / "dashboard.json"
PLANS_STATUS_FILE = DATA_DIR / "plans_status.json"

app = Flask(__name__, template_folder=str(DASHBOARD_DIR / "templates"))
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True


def load_data():
    """Load dashboard data from JSON file."""
    if not DASHBOARD_JSON.exists():
        return None
    try:
        with open(DASHBOARD_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}


def load_plans_status():
    """Load plan statuses from persistence file."""
    if PLANS_STATUS_FILE.exists():
        try:
            with open(PLANS_STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_plans_status(statuses):
    """Save plan statuses to persistence file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PLANS_STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(statuses, f, ensure_ascii=False, indent=2)


# === Jinja template helpers ===
STATUS_LABELS = {
    "not_started": "未开始",
    "in_progress": "进行中",
    "completed": "已完成",
    "deleted": "已删除",
}


def status_label(status):
    return STATUS_LABELS.get(status, status)


app.jinja_env.globals["statusLabel"] = status_label


def _do_scan(workspace_path):
    """Run scan for a given workspace path."""
    return run_scan_all(
        workspace_path=workspace_path,
        plans_dir=get_plans_dir(),
        project_config=get_project_meta(str(workspace_path)),
    )


def _inject_plan_statuses(data):
    """Inject user-edited plan statuses into data."""
    statuses = load_plans_status()
    deleted = {fn for fn, info in statuses.items() if info.get("deleted")}

    for proj in data.get("projects", []):
        for plan in proj.get("plans", []):
            fn = plan["filename"]
            if fn in deleted:
                plan["user_status"] = "deleted"
            elif fn in statuses:
                plan["user_status"] = statuses[fn].get("status", "not_started")
            else:
                plan["user_status"] = "not_started"

    for plan in data.get("recent_plans", []):
        fn = plan["filename"]
        if fn in deleted:
            plan["user_status"] = "deleted"
        elif fn in statuses:
            plan["user_status"] = statuses[fn].get("status", "not_started")
        else:
            plan["user_status"] = "not_started"

    data["deleted_plans"] = list(deleted)


def _group_projects(data, workspace_path_str):
    """Group projects by category with ordered output."""
    from collections import OrderedDict

    cat_order = get_categories_order(workspace_path_str)
    groups = {}
    for proj in data.get("projects", []):
        cat = proj.get("category") or "未分类"
        groups.setdefault(cat, []).append(proj)

    if cat_order:
        ordered = OrderedDict()
        for cat in cat_order:
            if cat in groups:
                ordered[cat] = groups.pop(cat)
        ordered.update(groups)  # append any remaining
    else:
        # Default: alphabetical
        ordered = OrderedDict(sorted(groups.items()))
    data["groups"] = ordered


# === Routes ===

@app.route("/")
def index():
    """Main dashboard page."""
    ws = get_workspace()
    if ws is None:
        return redirect(url_for("setup_page"))

    data = load_data()
    if data is None:
        # Auto-scan if data doesn't exist yet
        data = _do_scan(ws)

    if data is None:
        return redirect(url_for("setup_page"))

    try:
        _inject_plan_statuses(data)
        _group_projects(data, str(ws))

        # Add workspace info for template
        data["workspace"] = str(ws)
        data["workspace_configured"] = True

        return render_template("dashboard.html", data=data)
    except Exception:
        import traceback
        return f"<pre>{traceback.format_exc()}</pre>", 500


@app.route("/setup")
def setup_page():
    """Setup page — shown when no workspace is configured."""
    cfg = load_config()
    current_ws = cfg.get("workspace")
    return render_template("setup.html", current_workspace=current_ws)


@app.route("/scan", methods=["POST"])
def run_scan():
    """Trigger a fresh scan."""
    ws = get_workspace()
    if ws is None:
        return redirect(url_for("setup_page"))
    _do_scan(ws)
    return redirect(url_for("index"))


@app.route("/plan/<path:filename>")
def view_plan(filename):
    """View a single plan file rendered as HTML."""
    plans_dir = get_plans_dir()
    plan_path = plans_dir / filename
    if not plan_path.exists() or not filename.endswith(".md"):
        return "<h1>Plan not found</h1>", 404

    try:
        content = plan_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"<h1>Error reading plan: {e}</h1>", 500

    # Convert markdown to HTML
    html_content = markdown.markdown(
        content,
        extensions=["tables", "fenced_code", "toc"],
    )

    # Get plan title from first heading
    title = filename
    for line in content.split("\n"):
        if line.strip().startswith("# "):
            title = line.strip()[2:]
            break

    data = load_data()
    statuses = load_plans_status()
    plan_status = statuses.get(filename, {}).get("status", "not_started")

    return render_template(
        "plan_detail.html",
        title=title,
        filename=filename,
        content=html_content,
        data=data,
        plan_status=plan_status,
    )


# === Workspace API ===

@app.route("/api/workspace", methods=["GET"])
def api_get_workspace():
    """Get current workspace info."""
    cfg = load_config()
    ws = cfg.get("workspace")
    return jsonify({
        "workspace": ws,
        "plans_dir": str(get_plans_dir()),
        "configured": ws is not None,
    })


@app.route("/api/workspace", methods=["POST"])
def api_set_workspace():
    """Set workspace path, trigger scan."""
    body = request.get_json(silent=True)
    if not body or "path" not in body:
        return jsonify({"error": "Missing 'path' field"}), 400

    path_str = body["path"].strip()
    if not path_str:
        return jsonify({"error": "Path is required"}), 400

    path = Path(path_str)
    try:
        path = path.resolve()
    except OSError:
        pass

    if not path.is_dir():
        return jsonify({"error": f"目录不存在或不可访问: {path}"}), 400

    # Update config
    set_workspace(str(path))

    # Trigger scan
    result = _do_scan(path)

    return jsonify({
        "ok": True,
        "workspace": str(path),
        "projects": result.get("total_projects", 0) if result else 0,
    })


@app.route("/api/workspace", methods=["DELETE"])
def api_reset_workspace():
    """Reset workspace — go back to setup."""
    cfg = load_config()
    cfg["workspace"] = None
    save_config(cfg)
    return jsonify({"ok": True})


# === Plan Status API ===

@app.route("/api/plan/<path:filename>/status", methods=["PATCH"])
def update_plan_status(filename):
    """Update a plan's status."""
    body = request.get_json(silent=True)
    if not body or "status" not in body:
        return jsonify({"error": "Missing 'status' field"}), 400

    new_status = body["status"]
    valid = {"not_started", "in_progress", "completed", "deleted"}
    if new_status not in valid:
        return jsonify({"error": f"Invalid status. Must be one of: {valid}"}), 400

    statuses = load_plans_status()
    if filename not in statuses:
        statuses[filename] = {}

    if new_status == "deleted":
        statuses[filename]["deleted"] = True
        statuses[filename]["status"] = "deleted"
    else:
        statuses[filename]["deleted"] = False
        statuses[filename]["status"] = new_status

    statuses[filename]["updated_at"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    save_plans_status(statuses)
    return jsonify({"ok": True, "filename": filename, "status": new_status})


@app.route("/api/plan/<path:filename>", methods=["DELETE"])
def delete_plan(filename):
    """Soft-delete a plan."""
    statuses = load_plans_status()
    if filename not in statuses:
        statuses[filename] = {}

    statuses[filename]["deleted"] = True
    statuses[filename]["status"] = "deleted"
    statuses[filename]["updated_at"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    save_plans_status(statuses)
    return jsonify({"ok": True, "filename": filename})


# === Project Field API ===

@app.route("/api/project/<name>/priority", methods=["PATCH"])
def update_project_priority(name):
    """Update a project's priority (persisted to app_config.json)."""
    body = request.get_json(silent=True)
    if not body or "priority" not in body:
        return jsonify({"error": "Missing 'priority' field"}), 400

    new_priority = body["priority"]
    valid = {"high", "medium", "low"}
    if new_priority not in valid:
        return jsonify({"error": f"Invalid priority. Must be one of: {valid}"}), 400

    ws = get_workspace()
    if ws is None:
        return jsonify({"error": "No workspace configured"}), 400

    cfg = load_config()
    ws_key = str(ws).replace("\\", "/")
    proj = cfg.get("workspaces", {}).get(ws_key, {}).get("projects", {}).get(name)
    if proj is None:
        return jsonify({"error": f"Project '{name}' not found"}), 404

    proj["priority"] = new_priority
    save_config(cfg)

    # Also update the live dashboard.json
    data = load_data()
    if data:
        for p in data.get("projects", []):
            if p["name"] == name:
                p["priority"] = new_priority
                break
        with open(DASHBOARD_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True, "name": name, "priority": new_priority})


@app.route("/api/project/<name>/status", methods=["PATCH"])
def update_project_status(name):
    """Update a project's status override (persisted to app_config.json)."""
    body = request.get_json(silent=True)
    if not body or "status" not in body:
        return jsonify({"error": "Missing 'status' field"}), 400

    new_status = body["status"]
    valid = {"active", "stale", "complete", "paused", "unknown"}
    if new_status not in valid:
        return jsonify({"error": f"Invalid status. Must be one of: {valid}"}), 400

    ws = get_workspace()
    if ws is None:
        return jsonify({"error": "No workspace configured"}), 400

    cfg = load_config()
    ws_key = str(ws).replace("\\", "/")
    proj = cfg.get("workspaces", {}).get(ws_key, {}).get("projects", {}).get(name)
    if proj is None:
        return jsonify({"error": f"Project '{name}' not found"}), 404

    proj["status_override"] = new_status
    save_config(cfg)

    # Also update the live dashboard.json
    data = load_data()
    if data:
        for p in data.get("projects", []):
            if p["name"] == name:
                p["status"] = new_status
                break
        with open(DASHBOARD_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True, "name": name, "status": new_status})


@app.route("/api/data")
def api_data():
    """JSON API endpoint."""
    data = load_data()
    if data is None:
        return {"error": "No data"}, 404
    return data


if __name__ == "__main__":
    # Migrate legacy config if needed
    migrate_legacy_config()

    port = int(os.environ.get("DASHBOARD_PORT", 9999))
    print(f"Starting Project Dashboard at http://localhost:{port}")
    print(f"Data file: {DASHBOARD_JSON}")
    ws = get_workspace()
    if ws:
        print(f"Workspace: {ws}")
    else:
        print("No workspace configured — visit /setup to configure")
    app.run(host="0.0.0.0", port=port, debug=False)
