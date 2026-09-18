"""MCP server exposing tools to inspect, edit, and run Godot projects.

Connects as a stdio MCP server to clients such as GitHub Copilot Chat (VS Code)
or the Codex CLI. See README.md for client configuration examples.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("godot-mcp")

# ---------------------------------------------------------------------------
# Godot executable discovery
# ---------------------------------------------------------------------------

_CANDIDATE_NAMES = [
    "godot",
    "godot4",
    "Godot",
    "Godot_v4.5-stable_win64.exe",
    "Godot_v4.4-stable_win64.exe",
    "Godot_v4.3-stable_win64.exe",
]


def find_godot_executable() -> Optional[str]:
    env_path = os.environ.get("GODOT_MCP_GODOT_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    for name in _CANDIDATE_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


# ---------------------------------------------------------------------------
# Background process management (single running instance at a time)
# ---------------------------------------------------------------------------

_process_lock = threading.Lock()
_process: Optional[subprocess.Popen] = None
_output_lines: list[str] = []
_output_thread: Optional[threading.Thread] = None


def _pump_output(pipe) -> None:
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            with _process_lock:
                _output_lines.append(line.rstrip("\n"))
    finally:
        pipe.close()


def _resolve_project_dir(project_path: str) -> Path:
    """Resolve and validate a Godot project directory path."""
    path = Path(project_path).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")
    if path.is_file():
        path = path.parent
    if not (path / "project.godot").exists():
        raise ValueError(f"No project.godot found in: {path}")
    return path


def _resolve_within(root: Path, relative_or_absolute: str) -> Path:
    """Resolve a path, ensuring the result stays within root (no path traversal)."""
    candidate = Path(relative_or_absolute)
    resolved = candidate if candidate.is_absolute() else (root / candidate)
    resolved = resolved.resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError(f"Path '{relative_or_absolute}' escapes project root '{root}'")
    return resolved


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_godot_version() -> str:
    """Return the installed Godot engine version string."""
    exe = find_godot_executable()
    if not exe:
        return (
            "Godot executable not found. Set the GODOT_MCP_GODOT_PATH environment "
            "variable to the full path of the Godot executable."
        )
    result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15)
    return result.stdout.strip() or result.stderr.strip()


@mcp.tool()
def list_projects(search_path: str) -> list[str]:
    """Recursively find Godot projects (folders containing project.godot) under search_path."""
    root = Path(search_path).expanduser().resolve()
    if not root.exists():
        raise ValueError(f"Path does not exist: {root}")
    return [str(p.parent) for p in root.rglob("project.godot")]


@mcp.tool()
def get_project_info(project_path: str) -> str:
    """Return the raw contents of project.godot for the given project directory."""
    root = _resolve_project_dir(project_path)
    return (root / "project.godot").read_text(encoding="utf-8")


@mcp.tool()
def list_scenes(project_path: str) -> list[str]:
    """List all .tscn scene files in the project, relative to the project root."""
    root = _resolve_project_dir(project_path)
    return [str(p.relative_to(root)) for p in root.rglob("*.tscn")]


@mcp.tool()
def list_scripts(project_path: str) -> list[str]:
    """List all .gd script files in the project, relative to the project root."""
    root = _resolve_project_dir(project_path)
    return [str(p.relative_to(root)) for p in root.rglob("*.gd")]


@mcp.tool()
def read_script(project_path: str, script_path: str) -> str:
    """Read a GDScript file's contents. script_path is relative to the project root."""
    root = _resolve_project_dir(project_path)
    target = _resolve_within(root, script_path)
    if not target.exists():
        raise ValueError(f"Script not found: {script_path}")
    return target.read_text(encoding="utf-8")


@mcp.tool()
def write_script(project_path: str, script_path: str, content: str) -> str:
    """Create or overwrite a GDScript file. script_path is relative to the project root."""
    root = _resolve_project_dir(project_path)
    target = _resolve_within(root, script_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {target.relative_to(root)}"


@mcp.tool()
def get_scene_tree(project_path: str, scene_path: str) -> str:
    """Parse a .tscn file and return a human-readable summary of its node hierarchy."""
    root = _resolve_project_dir(project_path)
    target = _resolve_within(root, scene_path)
    if not target.exists():
        raise ValueError(f"Scene not found: {scene_path}")

    text = target.read_text(encoding="utf-8")
    node_pattern = re.compile(
        r'\[node name="(?P<name>[^"]+)"(?: type="(?P<type>[^"]+)")?(?: parent="(?P<parent>[^"]+)")?'
    )
    lines = []
    for match in node_pattern.finditer(text):
        name = match.group("name")
        node_type = match.group("type") or "(instance)"
        parent = match.group("parent") or "."
        depth = 0 if parent == "." else parent.count("/") + 1
        lines.append(f"{'  ' * depth}{name} [{node_type}] (parent={parent})")
    return "\n".join(lines) if lines else "(no nodes found)"


@mcp.tool()
def run_project(project_path: str, scene_path: Optional[str] = None, headless: bool = True) -> str:
    """Launch the Godot project (optionally a specific scene) as a background process.

    Only one run can be active at a time; call stop_project first to restart.
    Use get_debug_output to read captured stdout/stderr.
    """
    global _process, _output_thread
    exe = find_godot_executable()
    if not exe:
        raise ValueError(
            "Godot executable not found. Set GODOT_MCP_GODOT_PATH environment variable."
        )
    root = _resolve_project_dir(project_path)

    with _process_lock:
        if _process is not None and _process.poll() is None:
            raise ValueError("A project is already running. Call stop_project first.")
        _output_lines.clear()

    args = [exe, "--path", str(root)]
    if headless:
        args.append("--headless")
    if scene_path:
        scene_file = _resolve_within(root, scene_path)
        args.append(str(scene_file))

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    with _process_lock:
        _process = proc
    thread = threading.Thread(target=_pump_output, args=(proc.stdout,), daemon=True)
    thread.start()
    _output_thread = thread
    return f"Started Godot (pid={proc.pid}) for project {root}"


@mcp.tool()
def stop_project() -> str:
    """Terminate the currently running Godot project process, if any."""
    global _process
    with _process_lock:
        proc = _process
    if proc is None or proc.poll() is not None:
        return "No running project."
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return f"Stopped process (pid={proc.pid})"


@mcp.tool()
def get_debug_output(clear: bool = False) -> str:
    """Return captured stdout/stderr from the running (or last run) Godot process."""
    with _process_lock:
        output = "\n".join(_output_lines)
        if clear:
            _output_lines.clear()
    return output or "(no output captured)"


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
