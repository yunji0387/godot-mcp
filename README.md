# godot-mcp

A Model Context Protocol (MCP) server, written in Python, that lets AI coding
assistants (GitHub Copilot Chat, Codex CLI, etc.) inspect, edit, and run Godot
projects.

## Tools

| Tool | Description |
|---|---|
| `get_godot_version` | Return the installed Godot engine version. |
| `list_projects` | Recursively find Godot projects under a directory. |
| `get_project_info` | Return project metadata and file counts. |
| `list_scenes` | List `.tscn` files in a project. |
| `list_scripts` | List `.gd` files in a project. |
| `read_script` | Read a GDScript file's contents. |
| `write_script` | Create/overwrite a GDScript file. |
| `get_scene_tree` | Parse a `.tscn` file and print its node hierarchy. |
| `run_project` | Launch the project (optionally headless) as a background process. |
| `stop_project` | Terminate the running project process. |
| `get_debug_output` | Read captured stdout/stderr from the running process. |
| `launch_editor` | Launch the Godot editor for a project. |
| `create_scene` | Create a scene with a built-in Godot root node. |
| `add_node` | Add a built-in node to an existing scene. |
| `load_sprite` | Set a texture on a sprite-compatible node. |
| `export_mesh_library` | Export scene meshes as a `MeshLibrary`. |
| `save_scene` | Save a scene, optionally to a new path. |
| `get_uid` | Read a resource's `.uid` sidecar. |
| `update_project_uids` | Resave project resources to update UIDs. |

## Requirements

- [uv](https://docs.astral.sh/uv/) (already installed)
- The Godot executable. The server looks for it in this order:
  1. The `GODOT_MCP_GODOT_PATH` or `GODOT_PATH` environment variable (full path to the exe).
  2. `godot`, `godot4`, or `Godot` on your `PATH`.
  3. A few common Windows filenames (e.g. `Godot_v4.5-stable_win64.exe`) on
     your `PATH`.

  **Recommended**: rename/move the executable to `godot4.exe` (or `godot4` on
  macOS/Linux) inside a folder that's on your `PATH` — it'll be auto-detected
  and you never need to set `GODOT_MCP_GODOT_PATH` at all. Add the folder to
  `PATH` permanently with:

  ```powershell
  $current = [Environment]::GetEnvironmentVariable("Path", "User")
  [Environment]::SetEnvironmentVariable("Path", "$current;C:\path\to\godot4-folder", "User")
  ```

  Restart VS Code / open a new terminal afterwards for the change to apply.

  If you'd rather not touch `PATH`, set `GODOT_MCP_GODOT_PATH` using one of:

  - **VS Code (`.vscode/mcp.json`)**: already wired up via the `godot_path`
    input — you'll be prompted for the path the first time the server starts
    (see below). Leave it blank to fall back to `PATH` auto-detection.
  - **Codex CLI (`~/.codex/config.toml`)**: set it under
    `[mcp_servers.godot-mcp.env]` (see below).
  - **Running/testing manually in a terminal**:
    - PowerShell: `$env:GODOT_MCP_GODOT_PATH = "C:\path\to\Godot.exe"`
    - bash: `export GODOT_MCP_GODOT_PATH=/path/to/godot`
  - **Permanently, for your user account**:
    - PowerShell: `setx GODOT_MCP_GODOT_PATH "C:\path\to\Godot.exe"` (reopen
      the terminal/VS Code afterwards for it to take effect)
    - bash/zsh: add the `export` line above to `~/.bashrc`/`~/.zshrc`

## Setup

```powershell
cd godot-mcp
uv sync
```

Quick smoke test (lists all registered tools):

```powershell
uv run python -c "import asyncio; from godot_mcp.server import mcp; asyncio.run(mcp.list_tools())"
```

## Connect to GitHub Copilot Chat (VS Code)

A config is already provided at [`.vscode/mcp.json`](.vscode/mcp.json), so
this works out of the box when you open the `godot-mcp` folder (or a
workspace containing it) in VS Code. It runs the server via
`uv run python -m godot_mcp.server`. Open the Chat view, switch to Agent
mode, and the `godot-mcp` server's tools should be available (enable it from
the tools picker if prompted). VS Code will prompt you once for the
`godot_path` input — enter the full path to your Godot executable, or leave
it blank to auto-detect `godot`/`godot4` on `PATH`.

If you'd rather create the config by hand (e.g. in a different workspace),
add this to `.vscode/mcp.json`:

```json
{
  "servers": {
    "godot-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/godot-mcp",
        "run",
        "python",
        "-m",
        "godot_mcp.server"
      ],
      "env": {
        "GODOT_MCP_GODOT_PATH": "/absolute/path/to/godot(.exe)"
      }
    }
  }
}
```

> Note: `uv run godot-mcp` (the installed console-script) may be blocked by
> Windows Application Control policies on locked-down machines; invoking via
> `python -m godot_mcp.server` avoids that generated `.exe` wrapper.

## Connect to Codex CLI

Add this to your Codex config (`~/.codex/config.toml`), replacing the paths
with the absolute paths on your machine:

```toml
[mcp_servers.godot-mcp]
command = "uv"
args = ["--directory", "/absolute/path/to/godot-mcp", "run", "python", "-m", "godot_mcp.server"]

[mcp_servers.godot-mcp.env]
GODOT_MCP_GODOT_PATH = "/absolute/path/to/godot(.exe)"
```

Then restart Codex; the `godot-mcp` tools will show up automatically.

## Notes

- `run_project` supports only one active process at a time; call
  `stop_project` before starting another.
- File tools (`read_script`, `write_script`, `get_scene_tree`, etc.) validate
  that paths stay inside the given project directory.
