# EAGLE 6 MCP Server — User & Deployment Guide

This guide explains how to deploy `eagle6-mcp` once on your Linux workstation and use it with **Google Antigravity** across any existing or brand-new EAGLE hardware project folder.

> **Platform Support:** `eagle6-mcp` is designed and tested for **Linux** only. It has **not** been tested or validated on Windows or macOS. Replace `<username>` in the paths below with your Linux username (note that JSON configuration files do not expand `$USER` or `~`).

---

## 1. One-Time Installation

You do **not** install `eagle6-mcp` inside every hardware project folder. Instead, install it once into its dedicated Python virtual environment (e.g., `pyenv` virtualenv `eagle6-mcp`):

```bash
cd /path/to/EAGLE-6-MCP
pip install -r requirements.txt
pip install --no-deps -e .
```

Verify the installed console entry point:

```bash
which eagle6-mcp
# Expected: /home/<username>/.pyenv/shims/eagle6-mcp
# Full virtualenv binary (recommended for mcp_config.json):
/home/<username>/.pyenv/versions/3.13.1/envs/eagle6-mcp/bin/eagle6-mcp --help 2>&1 || true
```

> **Why use the full virtualenv binary path in `mcp_config.json`?**
> MCP clients spawn stdio servers outside your interactive shell, where `pyenv` shims may not be on `PATH`. Pointing directly to `.../envs/eagle6-mcp/bin/eagle6-mcp` guarantees the right Python environment is always used regardless of which project folder you open.

---

## 2. Deploying with Google Antigravity

Antigravity discovers MCP servers from two places: **Global Configuration** (recommended) or a **Plugin Bundle**.

### Option A: Global Registration (Recommended)

Edit (or create) `~/.gemini/config/mcp_config.json` and add the `eagle6` server entry:

```json
{
  "mcpServers": {
    "eagle6": {
      "command": "/home/<username>/.pyenv/versions/3.13.1/envs/eagle6-mcp/bin/eagle6-mcp",
      "env": {
        "EAGLE6_BIN": "/opt/eagle-6.6.0/bin/eagle",
        "EAGLE6_USER_DIR": "/home/<username>/eagle6",
        "EAGLE6_PROJECT_DIRS": "/home/<username>/eagle6/projects:/home/<username>/hdw:/home/<username>/eagle/projects",
        "EAGLE6_LIBRARY_DIRS": "/home/<username>/eagle6/lbr:/home/<username>/eagle/lbr:/opt/eagle-6.6.0/lbr",
        "EAGLE6_RENDER_DIR": "/tmp/eagle6-mcp-renders"
      }
    }
  }
}
```

### Option B: Antigravity Plugin Bundle (Toggleable)

If you prefer to turn the EAGLE tools on only when doing hardware work, place the same `mcp_config.json` inside a plugin folder at `~/.gemini/config/plugins/eagle6-mcp/` alongside a `plugin.json`, then toggle it in Antigravity's **Plugins Manager**.

### Verifying Connection in Antigravity

1. Reload or start a new Antigravity session.
2. Open **Additional Options (`...`) > MCP Servers** in the Antigravity UI.
3. Confirm **`eagle6`** is connected and lists all **26 tools**.

---

## 3. Using `eagle6-mcp` in a New Hardware Project Folder

Once registered globally, you can open **any** folder in Antigravity (e.g., `/home/<username>/hdw/my-new-board/` or `/home/<username>/eagle6/projects/sensor-v2/`) and immediately ask the agent to inspect or assist with your design — **no per-project setup is required**.

Every tool accepts explicit file or directory paths, so even if the new folder is not listed in `EAGLE6_PROJECT_DIRS`, you can simply ask:
- *"Summarize the EAGLE project in this folder and run ERC and DRC."*
- *"Render sheet 1 of `controller.sch` and the top copper of `controller.brd` so we can review the layout."*
- *"Check all connections on `U1` and list any unconnected pins or single-pin nets."*
- *"Show me all remaining unrouted airwires on `Anz-baseboard.brd`."*

If you create a new permanent hardware root folder and want `list_projects` (with no arguments) to include it automatically, append it to `EAGLE6_PROJECT_DIRS` in `~/.gemini/config/mcp_config.json`.

---

## 4. Common Workflows

### A. Reviewing an Older EAGLE v4/v5 Binary Project
1. Ask the agent to run `list_projects` — legacy binary files are flagged as `legacy_binary`.
2. Ask the agent to convert it (`convert_legacy_project`). This writes a converted XML copy under `/tmp/eagle6-mcp-staging/converted/` **without touching your original v5 file**.
3. The agent can then run BOM, netlist, ERC, DRC, and PNG rendering on the staged XML copy.

### B. Safe Assisted Editing (`.scr` Workflow)
1. Describe the edits you want (e.g., *"Set R12 to 4.7k, add MPN attributes to the 0805 resistors, and check if anything breaks"*).
2. The agent calls `generate_edit_script` to produce a commented `.scr` script with pre-flight checks.
3. The agent calls `validate_edit_script` to dry-run the script on a staged copy of your `.sch` + `.brd`, showing you the exact before/after diff, consistency status, and ERC/DRC delta.
4. Once you approve, the agent calls `save_edit_script` to save e.g. `fixes.scr` in your project folder.
5. Open your project in EAGLE 6 GUI (both `.sch` and `.brd` open) and type:
   ```text
   SCRIPT '/path/to/fixes.scr';
   ```
   EAGLE applies the changes cleanly with full forward/back-annotation and **Undo** support.

### C. Visual DRC Debugging
- Run `run_drc(brd_path, render_overlay=True)` to get both structured rule violations and EAGLE's native DRC error-polygon PNG.
- For any coordinate `(x_mm, y_mm)` of interest, run `render_drc_region(brd_path, x_mm, y_mm, radius_mm=5.0)` to zoom in tightly on that area.

### D. Generating Manufacturing Outputs
- **BOM:** `export_bom(sch_path, format="csv", output_path=".../bom.csv")`
- **Pick-and-Place:** `export_pick_and_place(brd_path, units="mm", smd_only=True, output_path=".../pnp.csv")`
- **Gerbers & Drills:** `run_cam_job(brd_path, output_dir=".../cam_out", preset="2layer_gerber")` (runs completely headlessly via `eagle -X`).

---

## 5. Troubleshooting

- **`xvfb-run` not found:** Install `xvfb` (`sudo apt install xvfb`). Pure XML tools and `-X` CAM jobs work without it, but PNG rendering, DRC overlays, legacy conversion, and `.scr` dry-runs require `xvfb-run` and `xwininfo`.
- **Server doesn't appear in Antigravity:** Verify `~/.gemini/config/mcp_config.json` is valid JSON and that `"command"` points directly to the `eagle6-mcp` binary inside the `eagle6-mcp` virtualenv.
- **Test the server directly from a terminal:**
  ```bash
  /home/<username>/.pyenv/versions/3.13.1/envs/eagle6-mcp/bin/python -m pytest /path/to/EAGLE-6-MCP/tests -v
  ```
