# EAGLE v6 MCP Server — Phase 1 & Phase 2 Implementation Plan

- **Date:** 2026-11-24
- **Target Application:** CadSoft EAGLE v6.6.0 (`/opt/eagle-6.6.0/bin/eagle`)
- **User Data Root:** `/home/beattidp/eagle6/` (`projects/`, `lbr/`, `dru/`, `cam/`, `scr/`, `ulp/`)
- **Runtime Environment:** Python 3.13 (`pyenv` virtualenv `eagle6-mcp` via `.python-version`), `xvfb-run` (`/usr/bin/xvfb-run`)
- **Schema Reference:** `/opt/eagle-6.6.0/doc/eagle.dtd`, `/opt/eagle-6.6.0/doc/eagle.1`

---

## 1. Objectives & Design Philosophy

The EAGLE v6 MCP server will allow an AI assistant to inspect, visually review, audit, and safely assist in completing older and unfinished EAGLE 6.6.0 schematic and PCB designs.

### Two-Layer Architecture

1. **Layer 1 — Pure Python XML Engine (Headless, Fast, Read-Only)**
   - Directly parses EAGLE 6 XML files (`.sch`, `.brd`, `.lbr`, `.dru`) without invoking the EAGLE executable or X11.
   - Zero risk of corrupting user designs or breaking forward/back-annotation.
   - Powers discovery, BOM extraction, netlist graph analysis, board geometry/routing inspection, library auditing, and `.sch` ↔ `.brd` consistency checks.

2. **Layer 2 — EAGLE CLI + ULP / Script Bridge (`xvfb-run`)**
   - Invokes `/opt/eagle-6.6.0/bin/eagle` headlessly via `xvfb-run -a` for editor commands (`-C "<commands>; QUIT"`) and directly for command-line CAM jobs (`-X`).
   - Powers high-DPI schematic/board PNG rendering (enabling multimodal visual inspection), official ERC/DRC execution via custom ULPs, legacy v4/v5 binary-to-XML conversion, and validated `.scr` edit script dry-runs.

### Safety Invariants

- **Never mutate `.sch` or `.brd` XML directly.** Direct XML edits risk breaking EAGLE's forward/back-annotation consistency. All design edits flow through EAGLE `.scr` scripts executed by EAGLE itself.
- **Isolated staging for CLI operations.** Before running `/opt/eagle-6.6.0/bin/eagle -C ...`, project files are copied into an isolated temporary staging directory so files currently open in the user's EAGLE GUI are never locked, overwritten, or clobbered.
- **Non-destructive legacy conversion.** If pre-v6 binary `.sch`/`.brd`/`.lbr` files are encountered, conversion to XML happens on a staged copy unless the user explicitly exports/saves it.
- **Human-in-the-loop edits.** Phase 2 edit tools generate readable, commented `.scr` scripts and validate them on a staged copy (with before/after ERC/DRC diffs) before the user runs them in EAGLE with full Undo support.

---

## 2. Proposed Repository Layout

Following project conventions (`.agents/rules/design-docs.md`, `python` skill, `documentation` skill):

```text
EAGLE-6-MCP/
├── .python-version              # "eagle6-mcp"
├── requirements.txt             # Relaxed constraints (>=) generated from virtualenv
├── doc/
│   ├── plans/                   # YYYY-MM-DD_*.md planning documents
│   ├── features/                # NN_*.md implemented feature references
│   ├── walkthroughs/            # YYYY-MM-DD_*.md verification walkthroughs
│   └── worklogs/                # YYYY-MM-DD_*.md session activity logs
├── src/
│   └── eagle6_mcp/
│       ├── __init__.py
│       ├── config.py            # Paths (EAGLE bin, user/system dirs, staging, timeouts)
│       ├── server.py            # FastMCP server registration & entry point
│       ├── models/              # Domain dataclasses (Schematic, Board, Library, DRU, etc.)
│       ├── parsers/             # XML parsers & legacy binary format detector
│       ├── analyzers/           # Schematic, board, consistency, and library analyzers
│       ├── runner/              # xvfb-run + EAGLE CLI subprocess & staging manager
│       ├── ulp/                 # Custom ULPs for structured ERC/DRC extraction (Phase 2)
│       └── scripts/             # .scr script generator & validator (Phase 2)
└── tests/
    ├── fixtures/                # Minimal synthetic .sch, .brd, .lbr, .dru XML fixtures
    ├── test_parsers.py
    ├── test_analyzers.py
    ├── test_runner.py
    └── test_scripts.py          # Phase 2
```

---

## 3. Phase 1: Read-Only Design Review & Visual Inspection (MVP)

**Goal:** Give the assistant complete visibility into EAGLE 6 projects — structurally (XML), electrically (netlists/BOMs/checks), physically (placement/routing/DRU), and visually (rendered PNGs) — with zero write risk to user files.

### 3.1 Core Infrastructure & Discovery Tools

| Tool Name | Purpose | Key Inputs | Output |
| :--- | :--- | :--- | :--- |
| `list_projects` | Discover EAGLE projects in `/home/beattidp/eagle6/projects` (or custom path) | `root_dir` (optional) | Project paths, `.sch`/`.brd`/`.epf` presence, format (`xml` vs `legacy_binary`), mtimes |
| `get_project_summary` | High-level health snapshot of a design | `project_path` | Sheet count, part count, net count, board dimensions, layer count, routing %, `.sch`/`.brd` pairing status |
| `list_libraries` | Search local (`/home/beattidp/eagle6/lbr`) and system (`/opt/eagle-6.6.0/lbr`) libraries | `query` (optional), `scope` (`user`/`system`/`all`) | Library filenames, paths, and sizes |

### 3.2 Schematic Analysis Tools

| Tool Name | Purpose | Key Inputs | Output |
| :--- | :--- | :--- | :--- |
| `get_schematic_bom` | Extract grouped or itemized Bill of Materials | `sch_path`, `grouped` (bool) | Refdes list, value, device, package, library, quantity, custom attributes (e.g., MPN, DNP) |
| `get_schematic_netlist` | Extract full or filtered electrical connectivity | `sch_path`, `net_filter` (optional), `part_filter` (optional) | Nets with net class and connected `(part, gate, pin, sheet)` endpoints |
| `inspect_schematic_part` | Deep dive on a single component | `sch_path`, `part_name` | Device/package/library, value, attributes, all gates, every pin and its connected net |
| `review_schematic` | Automated static electrical/hygiene audit | `sch_path` | Single-pin/dangling nets, unconnected IC pins, missing values, power/ground rail inventory (highlighting potential split rails), duplicate/unannotated designators |

### 3.3 Board Analysis Tools

| Tool Name | Purpose | Key Inputs | Output |
| :--- | :--- | :--- | :--- |
| `get_board_summary` | Physical & routing overview of PCB | `brd_path` | Board outline bounding box (mm & mil), active copper layers, component counts (top/bottom, SMD/THT), signal count, airwire count, via count, min trace width, min drill |
| `get_board_placement` | Component placement table | `brd_path`, `part_filter` (optional), `side` (`top`/`bottom`/`all`) | Refdes, value, package, `(x, y)` mm, rotation, mirrored/bottom flag |
| `get_board_routing_status` | Per-signal routing & airwire breakdown | `brd_path`, `unrouted_only` (bool), `signal_filter` (optional) | Signal name, net class, routed wire count/length/layers, via count, airwire count & endpoints, trace widths used |
| `get_design_rules` | Inspect `.dru` file or embedded board design rules | `brd_path` or `dru_path` | Clearances (wire/pad/via/smd), min width, min drill, restring, copper-to-dimension, layer stackup string |
| `check_sch_brd_consistency` | Static forward/back-annotation sanity check | `sch_path`, `brd_path` | Parts missing on board/schematic, value or package mismatches, net/signal membership discrepancies |

### 3.4 Library Inspection Tools

| Tool Name | Purpose | Key Inputs | Output |
| :--- | :--- | :--- | :--- |
| `inspect_library` | Browse contents of a `.lbr` (or embedded libraries in `.sch`/`.brd`) | `path`, `query` (optional) | Devicesets, packages, and symbols with descriptions |
| `inspect_library_device` | Inspect symbol pins, footprint pads, and pin-to-pad mapping | `path`, `deviceset_name` | Pin directions (`in`/`out`/`pwr`/`pas`/`nc`), gate-to-pad connections, pad/SMD dimensions, drill diameters |

### 3.5 Visual Inspection & Legacy Support (`xvfb-run` + EAGLE CLI)

| Tool Name | Purpose | Key Inputs | Output |
| :--- | :--- | :--- | :--- |
| `render_schematic` | Export a schematic sheet as PNG via `EXPORT IMAGE` | `sch_path`, `sheet` (default 1), `dpi` (default 200) | Saved PNG path (and optional MCP image content) for visual inspection |
| `render_board` | Export PCB layers as PNG via `EXPORT IMAGE` | `brd_path`, `preset` (`top_copper`, `bottom_copper`, `all_copper`, `top_assembly`, `bottom_assembly`, `unrouted`, or custom layer list), `dpi` (default 300) | Saved PNG path (and optional MCP image content) |
| `convert_legacy_project` | Convert a pre-v6 binary `.sch`/`.brd`/`.lbr` into a staged XML copy | `file_path` | Path to staged XML copy so all Phase 1 XML tools can inspect it safely |

### 3.6 Phase 1 Dependencies & Verification

- **Python dependencies** (installed in `eagle6-mcp` virtualenv, recorded in `requirements.txt` with `>=`):
  - `mcp` (official Python MCP SDK / FastMCP)
  - `lxml` (fast XML parsing, XPath, optional DTD validation against `eagle.dtd`)
  - `pydantic` (structured tool schemas & models)
  - `pytest` (unit and regression testing)
- **Verification plan**:
  - Unit tests in `tests/` covering XML parsing, netlist graph construction, board geometry/airwires, DRU parsing, and analyzer findings using synthetic fixtures.
  - Smoke/integration tests against `PRPP-controller` (`prpp-mcu.sch` / `prpp-mcu.brd`) including `xvfb-run` PNG rendering.
- **Milestone Git Tag:** `v0.1.0-phase1`

---

## 4. Phase 2: Official ERC/DRC, Assisted Editing (`.scr`), and Manufacturing Exports

**Goal:** Move from static analysis to authoritative EAGLE ERC/DRC diagnostics, safe script-based design modifications, and fabrication/assembly output workflows.

### 4.1 Official ERC & DRC via Custom ULPs

EAGLE 6's `ERC` and `DRC` commands execute inside the editor and expose results to ULPs (`schematic(S)` / `board(B)` error iteration). We will ship small, self-contained ULPs in `src/eagle6_mcp/ulp/` that serialize results to JSON.

| Tool Name | Purpose | Key Inputs | Output |
| :--- | :--- | :--- | :--- |
| `run_erc` | Run official EAGLE ERC on a staged project copy | `sch_path` | Structured JSON: error/warning/approved counts, severity, sheet, `(x, y)` coords, message |
| `run_drc` | Run official EAGLE DRC on a staged board copy | `brd_path`, `dru_path` (optional) | Structured JSON: clearance, overlap, drill, width, stopmask, angle, and airwire violations with layer & `(x, y)` coords |
| `render_drc_region` | Render a zoomed-in board PNG centered on a DRC violation | `brd_path`, `x_mm`, `y_mm`, `radius_mm`, `layers` | Cropped/windowed PNG highlighting the violation area |

### 4.2 Safe Assisted Editing via EAGLE Scripts (`.scr`)

Rather than editing XML directly, the server builds validated EAGLE `.scr` command scripts that preserve forward/back-annotation.

| Tool Name | Purpose | Key Inputs | Output |
| :--- | :--- | :--- | :--- |
| `generate_edit_script` | Generate a commented `.scr` script from structured edit intents | `target` (`sch`/`brd`), `operations` (list of typed ops: `set_value`, `rename_part`, `set_attribute`, `add_part`, `move_part`, `rotate_part`, `set_net_class`, `change_width`, `smash_labels`, etc.) | Commented `.scr` text + pre-flight validation notes (verifying parts/nets/libraries exist) |
| `validate_edit_script` | Dry-run a `.scr` script on a staged copy of `.sch` + `.brd` | `project_path`, `script_content`, `run_checks` (bool) | EAGLE exit status, consistency check result, before/after ERC/DRC delta, and summary of modified parts/nets |
| `save_edit_script` | Save a validated `.scr` script into the project or `/home/beattidp/eagle6/scr/` | `script_content`, `output_path` | Written path + exact command (`SCRIPT <filename>`) for the user to execute in EAGLE GUI |

### 4.3 Manufacturing & Documentation Exports

| Tool Name | Purpose | Key Inputs | Output |
| :--- | :--- | :--- | :--- |
| `export_bom` | Generate clean fabrication/purchasing BOM | `sch_path`, `format` (`csv`/`markdown`), `group_by` | Formatted BOM file or text |
| `export_pick_and_place` | Extract SMD/THT centroid table (top & bottom) | `brd_path`, `units` (`mm`/`mil`) | Refdes, value, package, `(x, y)`, rotation, side |
| `run_cam_job` | Execute headless CAM processor (`eagle -X`) to generate Gerbers & Excellon drills | `brd_path`, `cam_profile` (or layer preset), `output_dir` | Manifest of generated files, sizes, and CAM exit status/warnings |

### 4.4 MCP Client Integration & Milestone

- Configure the server in `.agents/mcp_config.json` (or user MCP config) invoking the `eagle6-mcp` pyenv Python binary.
- Full regression test suite covering ULP JSON parsing, `.scr` generation/escaping, staged dry-run execution, and CAM output verification.
- **Milestone Git Tag:** `v0.2.0-phase2`

---

## 5. Open Decisions Before Starting Phase 1

1. **MCP Transport:** Standard `stdio` (recommended for local Antigravity/IDE MCP integration) or local Streamable HTTP (similar to the existing `freecad` server in `.agents/mcp_config.json`)?
2. **Rendered Image Storage:** Should `render_schematic` / `render_board` write PNGs to a temporary cache directory (e.g., `/tmp/eagle6-mcp-renders/`) and return both the path and inline image data, or store them inside a project-local subfolder?
3. **Priority Design Targets:** Beyond `PRPP-controller`, are there specific older/unfinished projects (especially any pre-v6 binary files or custom `.dru`/`.cam` files) you want us to keep in mind for early testing?
