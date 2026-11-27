# EAGLE 6 MCP Server — Technical Specification

- **Package Name:** `eagle6-mcp`
- **Version:** `0.2.0`
- **Platform:** Linux (not tested or validated on Windows or macOS)
- **Protocol:** Model Context Protocol (MCP) over `stdio` transport (`mcp>=2.3.0`)
- **Target CAD Software:** CadSoft EAGLE v6.6.0 for Linux (XML DTD `/opt/eagle-6.6.0/doc/eagle.dtd`)

---

## 1. Package Contract

`eagle6-mcp` is packaged as a standard `pyproject.toml` (`setuptools`) Python distribution:

- **Console script entry point:** `eagle6-mcp` → `eagle6_mcp.server:main`
- **Module entry point:** `python -m eagle6_mcp` → `eagle6_mcp.__main__`
- **Programmatic factory:** `eagle6_mcp.server.create_server(config: EagleConfig | None = None) -> MCPServer`
- **Transport:** `stdio` (JSON-RPC 2.0 over stdin/stdout). The server emits no stray print output to stdout so JSON-RPC framing remains clean.

### Package Structure

```text
src/eagle6_mcp/
├── config.py        # EagleConfig dataclass + environment variable overrides
├── server.py        # MCPServer instantiation & 26 tool registrations
├── models/          # Domain dataclasses (all geometry normalized to mm)
├── parsers/         # lxml XML parsers, DRU parser, legacy binary FormatDetector
├── analyzers/       # Discovery, Schematic, Board, Consistency, Library, ERC/DRC
├── runner/          # xvfb-run + EAGLE CLI staging manager & X11 Qt4 focus helper
├── scripts/         # .scr ScriptBuilder & staged ScriptValidator
└── exports/         # BOM, Pick-and-Place, and headless CAM presets
```

---

## 2. Safety & Data Integrity Invariants

1. **Read-Only XML Access:** The server never directly modifies user `.sch`, `.brd`, or `.lbr` XML files. Direct XML mutation can sever EAGLE's forward/back-annotation.
2. **Isolated Staging:** Every EAGLE CLI invocation (`render_*`, `convert_legacy_project`, `validate_edit_script`, `run_cam_job`) copies source files into a temporary directory under `EAGLE6_STAGING_ROOT` with lowercase extensions (`.sch`, `.brd`, `.lbr`) so live files open in the user's EAGLE GUI are never locked or overwritten.
3. **Human-in-the-Loop Design Edits:** `generate_edit_script` and `validate_edit_script` produce and dry-run `.scr` files on staged copies; `save_edit_script` writes only `.scr` files for the user to execute inside EAGLE GUI (`SCRIPT '<path>';`) with full Undo support.
4. **XXE Protection:** All XML parsing uses `lxml.etree.XMLParser(resolve_entities=False, no_network=True)`.
5. **Legacy Pre-v6 Binary Safety:** `FormatDetector` detects pre-v6 binary files (`0x10 0x00` / `0x10 0x80` / NUL bytes) and raises `LegacyBinaryFormatError`, directing callers to `convert_legacy_project` (which converts a staged copy only).

---

## 3. Headless EAGLE 6.6.0 Execution Model

- **Editor Commands (`-C`):** Executed via `xvfb-run -a -s "-screen 0 1280x1024x24" <python> _xvfb_focus_exec.py <eagle> -C "<cmd>" <staged_file>`.
  - `_xvfb_focus_exec.py` polls `xwininfo -root -tree` and invokes `libX11.so.6` (`XRaiseWindow`, `XSetInputFocus`, `XFlush`) on EAGLE 6's Qt4 editor window so `-C` commands dispatch immediately without a window manager.
  - Commands are prefixed with `SET CONFIRM YES;` to suppress modal confirmation dialogs (e.g., v5→v6 format upgrade prompts).
- **CAM Processor (`-X`):** Executed directly as `<eagle> -X -N -d<device> -o<out> <staged.brd> <layers...>` with no X11/Xvfb dependency.

---

## 4. Complete Tool Specification (26 Tools)

### 4.1 Discovery & Overview
| Tool | Parameters | Returns |
| :--- | :--- | :--- |
| `list_projects` | `root_dir?: str`, `max_depth: int = 4` | List of paired `.sch`/`.brd`/`.epf` records with detected format (`xml` / `legacy_binary`) and mtime |
| `get_project_summary` | `project_path: str` | Combined schematic & board health snapshot |
| `list_libraries` | `query?: str`, `scope: str = "all"` | Matching `.lbr` files across `user`, `system`, or `all` roots |

### 4.2 Schematic Analysis
| Tool | Parameters | Returns |
| :--- | :--- | :--- |
| `get_schematic_bom` | `sch_path: str`, `grouped: bool = True`, `include_non_bom: bool = False` | Grouped or itemized BOM (supply/frame symbols excluded by default) |
| `get_schematic_netlist` | `sch_path: str`, `net_filter?: str`, `part_filter?: str` | Cross-sheet aggregated netlist with net classes and `(part, gate, pin, sheet)` endpoints |
| `inspect_schematic_part` | `sch_path: str`, `part_name: str` | Part metadata, effective value, attributes, instances, and complete pin-to-pad-to-net map |
| `review_schematic` | `sch_path: str` | Static audit: single-pin/zero-pin nets, unconnected IC/power pins (excluding `nc`), missing values, unannotated designators, power/ground rail inventory |

### 4.3 Board Analysis
| Tool | Parameters | Returns |
| :--- | :--- | :--- |
| `get_board_summary` | `brd_path: str` | Layer 20 outline bbox (mm & mil), used copper layers, component counts (top/bottom, SMD/THT), routing completion %, airwire/via counts, min trace width & drill |
| `get_board_placement` | `brd_path: str`, `part_filter?: str`, `side: str = "all"` | Component `(x_mm, y_mm)`, rotation, side (`top`/`bottom`), package, value |
| `get_board_routing_status` | `brd_path: str`, `unrouted_only: bool = False`, `signal_filter?: str` | Per-signal routed length (arc-aware mm), layers, trace widths, vias, polygons, and airwire coordinates |
| `get_design_rules` | `path: str` | Parsed `.dru` file or embedded `.brd` `<designrules>` with raw + mm highlights |
| `check_sch_brd_consistency` | `sch_path: str`, `brd_path: str` | Forward/back-annotation check (EAGLE `*`/`?` value expansion and `@N` package suffix aware) |

### 4.4 Library Inspection
| Tool | Parameters | Returns |
| :--- | :--- | :--- |
| `inspect_library` | `path: str`, `library_name?: str`, `query?: str` | Devicesets, packages, and symbols from a `.lbr` or embedded in `.sch`/`.brd` |
| `inspect_library_device` | `path: str`, `deviceset_name: str`, `library_name?: str` | Symbol pins/directions, pad/SMD dimensions, drills, holes, and gate-to-pad connect table |

### 4.5 Visual Rendering & Legacy Conversion
| Tool | Parameters | Returns |
| :--- | :--- | :--- |
| `render_schematic` | `sch_path: str`, `sheet: int = 1`, `dpi: int = 200`, `include_image: bool = True` | PNG path under `EAGLE6_RENDER_DIR` + inline MCP `Image` |
| `render_board` | `brd_path: str`, `preset: str = "all_copper"`, `custom_layers?: list[int]`, `dpi: int = 300`, `include_image: bool = True` | PNG path + inline MCP `Image` (`top_copper`, `bottom_copper`, `all_copper`, `top_assembly`, `bottom_assembly`, `unrouted`) |
| `convert_legacy_project` | `file_path: str` | Staged XML copy path (`staged_xml_path`) for pre-v6 binary files |

### 4.6 ERC / DRC & Zoomed Region Inspection
| Tool | Parameters | Returns |
| :--- | :--- | :--- |
| `run_erc` | `sch_path: str`, `include_board_consistency: bool = True` | Structured ERC errors & warnings (pin-direction conflicts, undriven inputs, unconnected pins, dangling nets, consistency) |
| `run_drc` | `brd_path: str`, `dru_path?: str`, `render_overlay: bool = False`, `dpi: int = 200` | Structured DRC violations (`msWidth`, net class width, `msDrill`, airwires, `mdCopperDimension`) + optional EAGLE `DRC;` overlay PNG |
| `render_drc_region` | `brd_path: str`, `x_mm: float`, `y_mm: float`, `radius_mm: float = 5.0`, `preset: str = "all_copper"`, `custom_layers?: list[int]`, `run_drc: bool = True`, `dpi: int = 300`, `include_image: bool = True` | Zoomed PNG centered on `(x_mm, y_mm)` + inline MCP `Image` |

### 4.7 Assisted Editing (`.scr`)
| Tool | Parameters | Returns |
| :--- | :--- | :--- |
| `generate_edit_script` | `target: "sch" \| "brd"`, `operations: list[dict]`, `project_path?: str` | Commented `.scr` text + pre-flight warnings |
| `validate_edit_script` | `project_path: str`, `script_content: str`, `run_checks: bool = True`, `keep_staged: bool = False` | Staged dry-run exit status, before/after schematic & board diffs, consistency check, ERC/DRC deltas, and (when `keep_staged=True`) retained `staged_dir`, `staged_brd_path`, and `staged_sch_path` under `staging_root` |
| `save_edit_script` | `script_content: str`, `output_path: str` | Written `.scr` path + exact `SCRIPT '<path>';` EAGLE GUI command |

### 4.8 Manufacturing & Documentation Exports
| Tool | Parameters | Returns |
| :--- | :--- | :--- |
| `export_bom` | `sch_path: str`, `format: "csv" \| "markdown" = "csv"`, `grouped: bool = True`, `output_path?: str` | Formatted BOM text + optional saved file path |
| `export_pick_and_place` | `brd_path: str`, `units: "mm" \| "mil" = "mm"`, `side: "all" \| "top" \| "bottom" = "all"`, `smd_only: bool = False`, `output_path?: str` | Centroid CSV + component count + optional saved file path |
| `run_cam_job` | `brd_path: str`, `output_dir: str`, `preset: "2layer_gerber" \| "4layer_gerber" = "2layer_gerber"`, `custom_jobs?: list[dict]` | Generated Gerber/Excellon file manifest, byte sizes, exit codes, and CAM warnings |
