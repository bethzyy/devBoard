"""
Project Dashboard Scanner - scans all sub-projects and Claude Code plans.
Outputs pm/data/dashboard.json for the web dashboard.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Tool-internal paths (not workspace-dependent)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "dashboard.json"

# Directories to skip
SKIP_DIRS = {
    ".claude", ".github", ".git", "__pycache__", "node_modules",
    "backup", "downloads", "images", "test", "tests", "temp",
    "transcripts", ".vscode", ".idea", "dist", "build",
}

# Entry point files to look for, in priority order
ENTRY_POINTS = ["run.py", "app.py", "server.py", "main.py", "gui.py", "manage.py"]


def run_git(path, *args):
    """Run a git command in a directory, return stdout or empty string."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=str(path),
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def detect_tech_stack(project_dir):
    """Detect tech stack from file markers."""
    stack = []
    has_python = False
    has_nodejs = False

    if (project_dir / "requirements.txt").exists():
        stack.append("Python")
        has_python = True
    if (project_dir / "package.json").exists():
        stack.append("Node.js")
        has_nodejs = True
    if (project_dir / "Dockerfile").exists() or (project_dir / "docker-compose.yml").exists():
        stack.append("Docker")
    if list(project_dir.glob("*.pyx")):
        stack.append("Cython")
    if (project_dir / "manifest.json").exists():
        stack.append("Extension")
    if (project_dir / "miniprogram").is_dir():
        stack.append("Mini-Program")

    # Scan for Python files if not detected via requirements.txt
    if not has_python and list(project_dir.glob("*.py")):
        stack.insert(0, "Python")
        has_python = True
    # Scan for JS/TS files
    if not has_nodejs and (list(project_dir.glob("*.js")) or list(project_dir.glob("*.ts"))):
        stack.append("Node.js")
        has_nodejs = True

    # Detect Flask/Django/FastAPI
    if has_python:
        req_file = project_dir / "requirements.txt"
        if req_file.exists():
            try:
                content = req_file.read_text(encoding="utf-8", errors="replace").lower()
                if "flask" in content:
                    stack.append("Flask")
                if "django" in content:
                    stack.append("Django")
                if "fastapi" in content:
                    stack.append("FastAPI")
            except Exception:
                pass

    # Detect Electron
    if has_nodejs:
        pkg_file = project_dir / "package.json"
        if pkg_file.exists():
            try:
                content = pkg_file.read_text(encoding="utf-8", errors="replace").lower()
                if "electron" in content:
                    stack.append("Electron")
            except Exception:
                pass

    return stack


def detect_entry_point(project_dir):
    """Find the main entry point file."""
    for name in ENTRY_POINTS:
        if (project_dir / name).exists():
            return name
    # Fallback: first .py file
    py_files = sorted(project_dir.glob("*.py"))
    if py_files:
        return py_files[0].name
    return None


def extract_version(project_dir):
    """Extract version from CHANGELOG.md."""
    changelog = project_dir / "CHANGELOG.md"
    if not changelog.exists():
        return None
    try:
        content = changelog.read_text(encoding="utf-8", errors="replace")
        # Match patterns like: ## v89.38 (2026-01-26) or ## [v2.2.5] - 2026-01-06
        match = re.search(r"##\s*\[?(v?[\d]+\.[\d]+[\.\d]*)\]?", content)
        if match:
            v = match.group(1)
            return v if v.startswith("v") else f"v{v}"
    except Exception:
        pass
    return None


def extract_description(project_dir):
    """Extract project description from README.md or CLAUDE.md."""
    for filename in ["CLAUDE.md", "README.md"]:
        filepath = project_dir / filename
        if not filepath.exists():
            continue
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Found first non-heading, non-empty line
                if len(line) > 10:
                    return line[:150]
        except Exception:
            pass
    return None


def count_todos(project_dir):
    """Count TODO/TBD/FIXME markers in source files (max depth 2, fast)."""
    count = 0
    patterns = re.compile(r"\b(TODO|TBD|FIXME|HACK)\b", re.IGNORECASE)
    extensions = {".py", ".md"}
    skip_subdirs = {"node_modules", "__pycache__", ".git", ".claude", "dist", "build", "test", "tests"}

    try:
        for root, dirs, files in os.walk(project_dir):
            # Limit depth to 2 levels
            depth = Path(root).relative_to(project_dir).parts
            if len(depth) > 2:
                dirs.clear()
                continue
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip_subdirs]
            for f in files:
                ext = Path(f).suffix
                if ext not in extensions:
                    continue
                filepath = Path(root) / f
                try:
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                    count += len(patterns.findall(content))
                except Exception:
                    pass
    except Exception:
        pass
    return count


def has_tests(project_dir):
    """Check if project has test infrastructure."""
    for name in ["test", "tests", "__tests__", "spec"]:
        if (project_dir / name).is_dir():
            return True
    # Check for test_*.py files
    if list(project_dir.glob("test_*.py")) or list(project_dir.glob("*_test.py")):
        return True
    return False


def count_source_files(project_dir):
    """Count source code files (max depth 3)."""
    count = 0
    extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".vue", ".svelte"}
    skip_subdirs = {"node_modules", "__pycache__", ".git", ".claude", "dist", "build"}
    try:
        for root, dirs, files in os.walk(project_dir):
            depth = Path(root).relative_to(project_dir).parts
            if len(depth) > 3:
                dirs.clear()
                continue
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip_subdirs]
            for f in files:
                if Path(f).suffix in extensions:
                    count += 1
    except Exception:
        pass
    return count


def get_latest_activity(project_dir):
    """Get the latest activity date from multiple signals."""
    best_date = None
    best_source = None

    # Signal 1: Git last commit
    git_dir = project_dir / ".git"
    if git_dir.exists():
        git_date_str = run_git(project_dir, "log", "-1", "--format=%ai")
        if git_date_str:
            try:
                git_date = datetime.fromisoformat(git_date_str.split("+")[0].strip())
                if best_date is None or git_date > best_date:
                    best_date = git_date
                    best_source = "git_commit"
            except (ValueError, IndexError):
                pass

    # Signal 2: CLAUDE.md mtime
    claude_md = project_dir / "CLAUDE.md"
    if claude_md.exists():
        try:
            mtime = datetime.fromtimestamp(claude_md.stat().st_mtime)
            if best_date is None or mtime > best_date:
                best_date = mtime
                best_source = "claude_md"
        except OSError:
            pass

    # Signal 3: CHANGELOG.md mtime
    changelog = project_dir / "CHANGELOG.md"
    if changelog.exists():
        try:
            mtime = datetime.fromtimestamp(changelog.stat().st_mtime)
            if best_date is None or mtime > best_date:
                best_date = mtime
                best_source = "changelog"
        except OSError:
            pass

    # Signal 4: Most recently modified .py/.js/.ts file (sample, not full walk)
    for ext in ["*.py", "*.js", "*.ts"]:
        newest = None
        for f in project_dir.glob(ext):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if newest is None or mtime > newest:
                    newest = mtime
            except OSError:
                pass
        if newest and (best_date is None or newest > best_date):
            best_date = newest
            best_source = "file_mtime"

    return best_date, best_source


def derive_status(days_since_activity, config_override=None):
    """Derive project status from activity and config."""
    if config_override:
        return config_override
    if days_since_activity is None:
        return "unknown"
    if days_since_activity <= 14:
        return "active"
    elif days_since_activity <= 60:
        return "stale"
    else:
        return "stale"


def scan_plans(plans_dir, project_names):
    """Scan Claude Code plans directory and parse plan files.

    Args:
        plans_dir: Path to plans directory
        project_names: list of project name strings for matching
    """
    plans = []

    if not plans_dir.exists():
        return plans

    project_names_lower = {n.lower(): n for n in project_names}

    for md_file in sorted(plans_dir.glob("*.md")):
        plan = {
            "filename": md_file.name,
            "title": None,
            "summary": None,
            "date": None,
            "related_projects": [],
        }

        # Date from file mtime
        try:
            plan["date"] = datetime.fromtimestamp(md_file.stat().st_mtime).strftime("%Y-%m-%d")
        except OSError:
            pass

        # Parse content
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")

            # Extract title (first # heading)
            for line in lines[:20]:
                line = line.strip()
                if line.startswith("# "):
                    plan["title"] = line[2:].strip()
                    break

            # Extract Context summary
            in_context = False
            context_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("## Context") or stripped.startswith("## 背景"):
                    in_context = True
                    continue
                if in_context and stripped.startswith("## "):
                    break
                if in_context and stripped:
                    context_lines.append(stripped)

            if context_lines:
                summary = " ".join(context_lines)
                plan["summary"] = summary[:200]

            # If no title found, use first line
            if not plan["title"]:
                for line in lines:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        plan["title"] = stripped[:80]
                        break

            # Match to projects via keyword search in content
            content_lower = content.lower()
            for pname_lower, pname_orig in project_names_lower.items():
                if pname_lower in content_lower:
                    plan["related_projects"].append(pname_orig)

        except Exception:
            pass

        plans.append(plan)

    return plans


def scan_project(project_dir):
    """Scan a single project directory."""
    name = project_dir.name
    info = {
        "name": name,
        "path": str(project_dir),
        "description": None,
        "status": "unknown",
        "last_activity_date": None,
        "last_activity_source": None,
        "days_since_activity": None,
        "version": None,
        "tech_stack": [],
        "entry_point": None,
        "has_git": False,
        "has_tests": False,
        "has_docker": False,
        "file_count": 0,
        "todo_count": 0,
        "git_commit_count": 0,
        "git_last_commit_msg": None,
        "category": None,
        "priority": None,
        "tags": [],
        "plans": [],
        "plan_count": 0,
    }

    # Basic detection
    info["has_git"] = (project_dir / ".git").exists()
    info["has_tests"] = has_tests(project_dir)
    info["has_docker"] = (project_dir / "Dockerfile").exists() or (project_dir / "docker-compose.yml").exists()
    info["tech_stack"] = detect_tech_stack(project_dir)
    info["entry_point"] = detect_entry_point(project_dir)
    info["version"] = extract_version(project_dir)
    info["description"] = extract_description(project_dir)
    info["file_count"] = count_source_files(project_dir)

    # Git info
    if info["has_git"]:
        commit_count_str = run_git(project_dir, "rev-list", "--count", "HEAD")
        if commit_count_str:
            try:
                info["git_commit_count"] = int(commit_count_str)
            except ValueError:
                pass

        last_msg = run_git(project_dir, "log", "-1", "--format=%s")
        if last_msg:
            info["git_last_commit_msg"] = last_msg[:100]

    # Activity
    activity_date, activity_source = get_latest_activity(project_dir)
    if activity_date:
        info["last_activity_date"] = activity_date.strftime("%Y-%m-%d")
        info["last_activity_source"] = activity_source
        # Handle timezone-aware vs naive datetimes
        now = datetime.now(activity_date.tzinfo) if activity_date.tzinfo else datetime.now()
        days = (now - activity_date).days
        info["days_since_activity"] = days

    # TODOs (sampled - only count, don't list)
    info["todo_count"] = count_todos(project_dir)

    return info


def scan_all(workspace_path=None, plans_dir=None, project_config=None):
    """Scan all projects and plans, output dashboard.json.

    Args:
        workspace_path: Path to workspace root (required)
        plans_dir: Path to plans directory (optional, defaults to ~/.claude/plans)
        project_config: dict of per-project metadata (optional)
    Returns:
        dict of scan output
    """
    if workspace_path is None:
        print("Error: workspace_path is required")
        return None
    workspace_path = Path(workspace_path)
    if plans_dir is None:
        plans_dir = Path.home() / ".claude" / "plans"
    else:
        plans_dir = Path(plans_dir)
    if project_config is None:
        project_config = {}

    print(f"Scanning workspace: {workspace_path}")
    print(f"Plans directory: {plans_dir}")

    # Ensure output directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Scan plans first
    print("Scanning Claude Code plans...")
    # Build project names list dynamically from discovered dirs (pre-scan)
    pre_scan_names = []
    for entry in sorted(workspace_path.iterdir()):
        if entry.is_dir() and not entry.name.startswith(".") and entry.name not in SKIP_DIRS:
            pre_scan_names.append(entry.name)
    all_plans = scan_plans(plans_dir, pre_scan_names)
    print(f"  Found {len(all_plans)} plan files")

    # Build project→plans mapping
    plans_by_project = {}
    for plan in all_plans:
        for proj in plan["related_projects"]:
            plans_by_project.setdefault(proj, []).append(plan)

    # Scan projects
    print("Scanning projects...")
    projects = []
    project_dirs = []

    for entry in sorted(workspace_path.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name in SKIP_DIRS:
            continue
        project_dirs.append(entry)

    for project_dir in project_dirs:
        info = scan_project(project_dir)
        projects.append(info)

    print(f"  Found {len(projects)} projects")

    # Load manual config (from parameter)
    config = project_config
    print(f"  Loaded config for {len(config)} projects")

    # Merge config and plans into projects
    now = datetime.now()
    for proj in projects:
        name = proj["name"]

        # Merge manual config
        cfg = config.get(name, {})
        if "category" in cfg:
            proj["category"] = cfg["category"]
        if "priority" in cfg:
            proj["priority"] = cfg["priority"]
        if "project_type" in cfg:
            proj["project_type"] = cfg["project_type"]
        if "tags" in cfg:
            proj["tags"] = cfg["tags"]
        if "status_override" in cfg:
            proj["status"] = cfg["status_override"]
        else:
            # Derive status from activity
            proj["status"] = derive_status(proj["days_since_activity"])
        if "paused_reason" in cfg:
            proj["paused_reason"] = cfg["paused_reason"]

        # Assign plans
        # Match by exact name (case-insensitive)
        matched_plans = []
        name_lower = name.lower()
        for plan in all_plans:
            for rp in plan["related_projects"]:
                if rp.lower() == name_lower:
                    matched_plans.append({
                        "filename": plan["filename"],
                        "title": plan["title"],
                        "date": plan["date"],
                        "summary": plan["summary"],
                    })
                    break

        # Sort plans by date descending
        matched_plans.sort(key=lambda p: p.get("date", ""), reverse=True)
        proj["plans"] = matched_plans
        proj["plan_count"] = len(matched_plans)

    # Build output
    output = {
        "scan_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "workspace": str(workspace_path),
        "total_projects": len(projects),
        "total_plans": len(all_plans),
        "summary": {
            "active": sum(1 for p in projects if p["status"] == "active"),
            "stale": sum(1 for p in projects if p["status"] == "stale"),
            "complete": sum(1 for p in projects if p["status"] == "complete"),
            "paused": sum(1 for p in projects if p["status"] == "paused"),
            "unknown": sum(1 for p in projects if p["status"] == "unknown"),
            "total_todos": sum(p["todo_count"] for p in projects),
        },
        "projects": projects,
        "recent_plans": sorted(
            [{"filename": p["filename"], "title": p["title"], "date": p["date"],
              "related_projects": p["related_projects"]}
             for p in all_plans],
            key=lambda p: p.get("date", ""),
            reverse=True,
        )[:20],
    }

    # Write output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nScan complete!")
    print(f"  Projects: {len(projects)}")
    print(f"  Active: {output['summary']['active']}")
    print(f"  Stale: {output['summary']['stale']}")
    print(f"  Complete: {output['summary']['complete']}")
    print(f"  Paused: {output['summary']['paused']}")
    print(f"  Total TODOs: {output['summary']['total_todos']}")
    print(f"  Plans: {len(all_plans)}")
    print(f"  Output: {OUTPUT_FILE}")

    return output


if __name__ == "__main__":
    from dashboard.config import load_config, get_plans_dir, get_project_meta
    cfg = load_config()
    ws = cfg.get("workspace")
    if not ws:
        print("No workspace configured. Run the server and configure via UI, or edit app_config.json.")
        sys.exit(1)
    if not Path(ws).is_dir():
        print(f"Workspace path does not exist: {ws}")
        sys.exit(1)
    scan_all(
        workspace_path=ws,
        plans_dir=get_plans_dir(),
        project_config=get_project_meta(ws),
    )
