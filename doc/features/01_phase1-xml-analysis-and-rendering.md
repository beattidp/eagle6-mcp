# Feature 01 — Phase 1: Read-Only XML Analysis & Headless Rendering

- **Milestone:** Phase 1 (MVP)
- **Date:** 2026-11-24
- **Package:** `src/eagle6_mcp/`

## Overview

Phase 1 implements a strictly read-only MCP server (over `stdio` transport) for inspecting CadSoft EAGLE v6.6.0 projects, schematics (`.sch`), boards (`.brd`), libraries (`.lbr`), and design rules (`.dru`), plus headless visual rendering (`EXPORT IMAGE`) and legacy v4/v5 binary-to-XML conversion via `xvfb-run` + `/opt/eagle-6.6.0/bin/eagle`.

## Architecture

- **`config.py` (`EagleConfig`)**: Centralizes EAGLE binary path, search roots (`/home/beattidp/eagle6/projects`, `/home/beattidp/vm_shared/hdw/Midnight`, `/home/beattidp/eagle/projects`, user/system library roots), render cache (`/tmp/eagle6-mcp-renders`), and staging directory (`/tmp/eagle6-mcp-staging`).
- **`models/`**: Modular domain dataclasses for `Schematic`, `Board`, `Library`, `DesignRules`, `ProjectInfo`, and `LibraryFileInfo` (all geometry in mm per `eagle.dtd`).
- **`parsers/`**:
  - `FormatDetector`: Distinguishes EAGLE 6 XML from pre-v6 binary files (`0x10 0x00` header) and raises `LegacyBinaryFormatError` with an actionable hint to run `convert_legacy_project`.
  - `SchematicParser`, `BoardParser`, `LibraryParser`, `DruParser`: Safe `lxml` parsers (`resolve_entities=False`, `no_network=True`).
- **`analyzers/`**:
  - `ProjectDiscoverer`: Pairs `.sch`/`.brd`/`.epf` across configured roots with format detection.
  - `SchematicAnalyzer`: BOM (grouped/itemized, excluding package-less supply symbols by default), cross-sheet netlist, single-part pin-to-net inspection, and static review (dangling/single-pin nets, unconnected IC pins excluding `direction="nc"`, missing values, power/ground rail inventory).
  - `BoardAnalyzer`: Outline bounding box (mm/mil) from layer 20, active copper layers, component placement (top/bottom, SMD/THT), per-signal routing status with arc-aware wire length and airwires, and DRU summaries.
  - `ConsistencyAnalyzer`: Cross-checks `.sch` vs. `.brd` parts, values, packages, and net/signal membership.
  - `LibraryAnalyzer`: Searches and inspects devicesets, symbols, packages, pad/SMD dimensions, drills, and pin-to-pad connect tables.
- **`runner/eagle_runner.py` (`EagleRunner`) & `_xvfb_focus_exec.py`**:
  - Copies target files into an isolated temporary staging directory before invoking `xvfb-run -a -s "-screen 0 1280x1024x24"` so live GUI files are never locked or modified.
  - Includes `_xvfb_focus_exec.py` to call `libX11.so.6` (`XRaiseWindow` + `XSetInputFocus`) on EAGLE 6's Qt4 editor window once mapped under bare Xvfb (without a window manager, Qt4 never receives `WindowActivate` and `-C` commands hang).
  - Supports `render_schematic`, `render_board` (with layer presets: `top_copper`, `bottom_copper`, `all_copper`, `top_assembly`, `bottom_assembly`, `unrouted`, or custom layers), and `convert_legacy_to_xml`.

## Registered MCP Tools (17)

1. `list_projects`
2. `get_project_summary`
3. `list_libraries`
4. `get_schematic_bom`
5. `get_schematic_netlist`
6. `inspect_schematic_part`
7. `review_schematic`
8. `get_board_summary`
9. `get_board_placement`
10. `get_board_routing_status`
11. `get_design_rules`
12. `check_sch_brd_consistency`
13. `inspect_library`
14. `inspect_library_device`
15. `render_schematic`
16. `render_board`
17. `convert_legacy_project`

## Running the Server

```bash
# Using the project's pyenv virtualenv (eagle6-mcp)
python -m eagle6_mcp
```
