# Feature 02 — Phase 2: ERC/DRC Diagnostics, Assisted `.scr` Editing, and Headless CAM Exports

- **Milestone:** Phase 2 (`v0.2.0-phase2`)
- **Date:** 2026-11-24
- **Package:** `src/eagle6_mcp/`

## Overview

Phase 2 extends the `eagle6-mcp` server from read-only review to structured ERC/DRC diagnostics, zoomed DRC region inspection, safe script-based assisted editing with isolated dry-run validation, and headless manufacturing exports (BOM, Pick-and-Place centroids, and RS-274X Gerber + Excellon CAM jobs).

## Engineering Note on EAGLE 6.6.0 ERC/DRC

CadSoft EAGLE v6.6.0's ULP API does not yet expose `UL_ERROR` (introduced in EAGLE 7/8). Accordingly, Phase 2 combines:
1. **Deterministic Python rule checking (`ErcDrcAnalyzer`)** for machine-readable JSON diagnostics (pin-direction conflicts, undriven inputs, unconnected pins, single-pin nets, missing values, unannotated parts, `.sch`↔`.brd` consistency, minimum trace widths vs. `msWidth`/net-class, minimum via/pad drills vs. `msDrill`, unrouted airwires, and copper-to-dimension checks).
2. **Official EAGLE 6.6.0 `DRC;` visual overlays (`EagleRunner.render_drc_overlay` & `render_drc_region`)** executed on staged copies via `xvfb-run` so any geometric clearance, overlap, or stopmask error polygons computed by EAGLE's native engine can be visually inspected.

## Architecture & Modules

- **`analyzers/erc_drc_analyzer.py` (`ErcDrcAnalyzer`)**: Structured `run_erc()` and `run_drc()`.
- **`scripts/script_builder.py` (`ScriptBuilder`)**: Generates commented, safely-escaped `.scr` scripts from typed edit operations (`set_value`, `rename_part`, `set_attribute`, `delete_attribute`, `add_part`, `move_part`, `rotate_part`, `mirror_part`, `smash_part`, `set_net_class`, `change_width`, `raw_command`) with optional pre-flight checks against an existing `.sch`/`.brd`.
- **`scripts/script_validator.py` (`ScriptValidator`)**:
  - `validate()`: Copies `.sch` and sibling `.brd` (when paired) into an isolated staging directory, runs `SET CONFIRM YES; SCRIPT '<staged.scr>'; WRITE; QUIT` via EAGLE 6.6.0 under `xvfb-run`, computes before/after part/value/attribute/placement diffs, verifies forward/back-annotation consistency, and reports ERC/DRC deltas without touching user files.
  - `save_script()`: Saves reviewed `.scr` scripts to disk and returns the exact `SCRIPT '<path>';` GUI command.
- **`exports/manufacturing.py` (`ManufacturingExporter`, `CAM_PRESETS`)**:
  - CSV and Markdown BOM exports (`export_bom`).
  - SMD/THT Pick-and-Place centroid CSV exports (`export_pick_and_place`, mm or mil).
  - Standard `2layer_gerber` and `4layer_gerber` CAM presets for `EagleRunner.run_cam_job()` (`eagle -X -N`, completely headless without Xvfb).

## New MCP Tools Added in Phase 2 (9 tools; 26 total)

1. `run_erc`
2. `run_drc`
3. `render_drc_region`
4. `generate_edit_script`
5. `validate_edit_script`
6. `save_edit_script`
7. `export_bom`
8. `export_pick_and_place`
9. `run_cam_job`

## Verification

- `pytest -v`: **22/22 tests passing** in 5.80s (`tests/test_phase2.py`), including live staged `.scr` dry-run validation proving forward/back-annotation propagation across `prpp-mcu.sch` + `prpp-mcu.brd`, live DRC overlay + zoomed region rendering, and headless 10-file 2-layer Gerber/Excellon CAM generation.
