"""
CodexMemory — Automatic MCP Configuration Installer
====================================================
This script automatically detects:
1. The current Python virtual environment's executable path.
2. The absolute path to mcp_server.py.
3. The user's Antigravity MCP config directory.

Then it writes a perfectly formatted mcp_config.json so the user
never has to manually configure anything on a new PC.

Usage:
    python install_mcp.py
    OR (if installed via pip):
    codexmemory-install
"""
import sys
import os
import json
from pathlib import Path


def main():
    print("=" * 60)
    print("  CodexMemory — 100x Automatic MCP Installer")
    print("=" * 60)

    # 1. Detect the Python executable (inside the venv)
    python_exe = Path(sys.executable).resolve()
    print(f"  [1/3] Python Executable: {python_exe}")

    # 2. Detect mcp_server.py location
    # install_mcp.py lives in src/tools/, same directory as mcp_server.py
    tools_dir = Path(__file__).resolve().parent
    mcp_server_path = tools_dir / "mcp_server.py"

    if not mcp_server_path.exists():
        print(f"  ❌ ERROR: mcp_server.py not found at {mcp_server_path}")
        print("     Make sure install_mcp.py is in the same directory as mcp_server.py")
        sys.exit(1)

    print(f"  [2/3] MCP Server: {mcp_server_path}")

    # 3. Detect the Antigravity MCP config directory
    # Standard location: C:\Users\<User>\.gemini\antigravity\mcp_config.json
    # Also supports: ~/.cursor/mcp.json for Cursor IDE
    home = Path.home()

    config_candidates = [
        home / ".gemini" / "antigravity" / "mcp_config.json",  # Antigravity
        home / ".cursor" / "mcp.json",                          # Cursor IDE
    ]

    config_path = None
    for candidate in config_candidates:
        if candidate.parent.exists():
            config_path = candidate
            break

    if config_path is None:
        # Default to Antigravity
        config_path = config_candidates[0]
        config_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"  [3/3] Config Target: {config_path}")

    # 4. Build the MCP configuration
    mcp_config = {
        "mcpServers": {
            "codexmemory-search": {
                "command": str(python_exe),
                "args": [str(mcp_server_path)],
                "env": {
                    "PYTHONUTF8": "1"
                },
                "disabled": False,
                "autoApprove": []
            }
        }
    }

    # 5. Merge with existing config instead of overwriting
    existing_config = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing_config = json.load(f)
            print(f"\n  📂 Found existing config. Merging...")
        except (json.JSONDecodeError, Exception):
            print(f"\n  ⚠ Existing config is corrupted. Overwriting.")

    # Merge: preserve other MCP servers the user may have
    if "mcpServers" not in existing_config:
        existing_config["mcpServers"] = {}

    existing_config["mcpServers"]["codexmemory-search"] = mcp_config["mcpServers"]["codexmemory-search"]

    # 6. Write the config
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(existing_config, f, indent=4)

    print(f"\n  ✅ Configuration written successfully!")
    print(f"\n  Generated Config:")
    print(f"  " + "-" * 56)
    print(json.dumps(existing_config, indent=4))
    print(f"  " + "-" * 56)
    print(f"\n  🚀 CodexMemory is ready. Restart your IDE to activate.")


if __name__ == "__main__":
    main()
