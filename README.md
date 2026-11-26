# EAGLE 6 MCP Server (`eagle6-mcp`)

An installable Python [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for **CadSoft EAGLE v6.6.0**, enabling AI assistants (such as Google Antigravity) to inspect, visually review, audit (ERC/DRC), safely assist in editing (via validated `.scr` scripts), and export manufacturing files (BOM, Pick-and-Place, RS-274X Gerbers, Excellon drills) for EAGLE v6 XML and legacy v4/v5 binary designs.

## Key Capabilities

- **Zero-risk XML Analysis (Layer 1):** Fast, headless `lxml` parsing of `.sch`, `.brd`, `.lbr`, and `.dru` files — BOMs, cross-sheet netlists, pin-to-net maps, board dimensions, component placement, routing completion/airwires, library auditing, and `.sch` ↔ `.brd` consistency checks.
- **Headless EAGLE CLI Integration (Layer 2):** Isolated temporary staging copies + `xvfb-run` (with a built-in X11 focus helper for EAGLE 6's Qt4 editor window) for high-DPI schematic/board PNG rendering, official `DRC;` error-polygon overlays, zoomed region crops, and non-destructive legacy v4/v5 binary-to-XML conversion.
- **Safe Assisted Editing:** Generates commented `.scr` scripts from typed operations, dry-runs them on staged paired `.sch` + `.brd` copies with before/after diffs and ERC/DRC deltas, and saves reviewed scripts for execution in the EAGLE GUI with full Undo support.
- **Headless Manufacturing Exports:** CSV/Markdown BOMs, SMD/THT Pick-and-Place centroid CSVs, and headless `eagle -X` CAM processor runs (`2layer_gerber`, `4layer_gerber`, or custom layers).

## Prerequisites & Platform Support

> **Platform Support:** This server is built and validated for **Linux** only. It has **not** been tested or validated on Windows or macOS. Layer 2 headless EAGLE operations depend on Linux X11 tooling (`xvfb-run`, `xwininfo`, and `libX11.so.6`).

- **Linux** (tested on x86_64 Linux)
- **CadSoft EAGLE v6.6.0** (default: `/opt/eagle-6.6.0/bin/eagle`)
- **Python 3.11+** (tested on Python 3.13 in `pyenv` virtualenv `eagle6-mcp`)
- **`xvfb` (`xvfb-run`)** and **`xwininfo`** (for headless PNG rendering, DRC overlays, legacy conversion, and `.scr` dry-runs; not required for pure XML analysis or `-X` CAM jobs)

## Installation

```bash
git clone https://github.com/beattidp/eagle6-mcp.git
cd eagle6-mcp

# Activate your virtualenv (pyenv auto-activates via .python-version)
pip install -r requirements.txt
pip install --no-deps -e .
```

This installs the `eagle6-mcp` console entry point (and `python -m eagle6_mcp` module entry point) into your virtualenv.

## Quick Start with Antigravity

### Option A: Install as a Global Antigravity Plugin (Recommended)

This repository includes a self-contained Antigravity plugin bundle in [`plugin/`](plugin/) (MCP server config, `eagle6-design-review` workflow skill, safety rules, and custom `assets/logo.svg` icon).

With your `eagle6-mcp` virtualenv active, run:

```bash
python scripts/install_antigravity_plugin.py
```

This copies `plugin/` into `~/.gemini/config/plugins/eagle6-mcp/` and resolves `mcp_config.json` to your active virtualenv's `eagle6-mcp` binary and default EAGLE paths. *(Use `--dry-run` to preview.)*

If `eagle6-mcp` is already on your global `PATH`, you can alternatively install directly via the Antigravity CLI:

```bash
agy plugin validate ./plugin
agy plugin install ./plugin
```

### Option B: Manual MCP Server Registration

Alternatively, register `eagle6-mcp` directly in `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "eagle6": {
      "command": "/home/<username>/.pyenv/versions/3.13.1/envs/eagle6-mcp/bin/eagle6-mcp",
      "env": {
        "EAGLE6_BIN": "/opt/eagle-6.6.0/bin/eagle",
        "EAGLE6_PROJECT_DIRS": "/home/<username>/eagle6/projects:/home/<username>/hdw:/home/<username>/eagle/projects",
        "EAGLE6_LIBRARY_DIRS": "/home/<username>/eagle6/lbr:/home/<username>/eagle/lbr:/opt/eagle-6.6.0/lbr"
      }
    }
  }
}
```

Then open **Additional Options (`...`) > MCP Servers** (or **Customizations > Plugins**) in Antigravity to verify `eagle6-mcp` is connected with all **26 tools**.

## Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `EAGLE6_BIN` | `/opt/eagle-6.6.0/bin/eagle` | Path to EAGLE 6.6.0 executable |
| `EAGLE6_INSTALL_DIR` | `/opt/eagle-6.6.0` | EAGLE installation root |
| `EAGLE6_USER_DIR` | `/home/<username>/eagle6` | User EAGLE data directory |
| `EAGLE6_PROJECT_DIRS` | `/home/<username>/eagle6/projects:/home/<username>/hdw:...` | Colon-separated project search roots |
| `EAGLE6_LIBRARY_DIRS` | `/home/<username>/eagle6/lbr:/home/<username>/eagle/lbr:/opt/eagle-6.6.0/lbr` | Colon-separated library search roots |
| `EAGLE6_RENDER_DIR` | `/tmp/eagle6-mcp-renders` | Output directory for exported PNGs |
| `EAGLE6_STAGING_ROOT` | `/tmp/eagle6-mcp-staging` | Isolated temporary staging root |
| `EAGLE6_XVFB_BIN` | `xvfb-run` | Path/name of `xvfb-run` |
| `EAGLE6_CLI_TIMEOUT` | `60` | Subprocess timeout in seconds |

## Documentation

- **Technical Specification:** [doc/specification.md](doc/specification.md)
- **User & Deployment Guide:** [doc/user-guide.md](doc/user-guide.md)
- **Implementation Plan:** [doc/plans/2026-11-24_eagle6-mcp-phase1-phase2-plan.md](doc/plans/2026-11-24_eagle6-mcp-phase1-phase2-plan.md)
- **Feature References:**
  - [doc/features/01_phase1-xml-analysis-and-rendering.md](doc/features/01_phase1-xml-analysis-and-rendering.md)
  - [doc/features/02_phase2-erc-drc-scripts-and-cam.md](doc/features/02_phase2-erc-drc-scripts-and-cam.md)

## Running Tests

```bash
pytest -v
```
