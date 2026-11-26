---
name: eagle6-design-review
description: Workflows for reviewing, visually inspecting, auditing (ERC/DRC), safely editing via .scr scripts, and exporting manufacturing files for CadSoft EAGLE v6.6.0 schematics (.sch), boards (.brd), and libraries (.lbr) using the eagle6-mcp server.
---

# EAGLE v6 Design Review & Assisted Editing Workflow

Use the `eagle6-mcp` MCP tools whenever inspecting or assisting with CadSoft EAGLE v6 (`.sch`, `.brd`, `.lbr`, `.dru`) or legacy v4/v5 binary designs.

## 1. Discovery & Legacy v4/v5 Handling
- Start with `list_projects` or `get_project_summary` to inspect `.sch`/`.brd` pairing and file format (`xml` vs `legacy_binary`).
- If a file is `legacy_binary`, call `convert_legacy_project` first to obtain a non-destructive staged XML copy, then pass `staged_xml_path` to XML analysis tools.

## 2. Design Review & Visual Inspection
- Use `review_schematic`, `get_schematic_bom`, `get_schematic_netlist`, and `inspect_schematic_part` for electrical review.
- Use `get_board_summary`, `get_board_placement`, `get_board_routing_status`, `get_design_rules`, and `check_sch_brd_consistency` for layout review.
- Use `run_erc` and `run_drc` (with `render_overlay=True` when checking clearances/overlaps) for rule diagnostics.
- Use `render_schematic`, `render_board`, and `render_drc_region` to visually inspect sheets, copper layers, and DRC violation coordinates.

## 3. Safe Assisted Editing (`.scr` Workflow)
- Never edit `.sch` or `.brd` XML files directly (this risks breaking EAGLE forward/back-annotation).
- Generate edits with `generate_edit_script`, dry-run them on a staged paired copy with `validate_edit_script`, review the before/after diffs and ERC/DRC deltas with the user, and only then persist via `save_edit_script` for execution inside the EAGLE GUI (`SCRIPT '<path>';`).

## 4. Manufacturing Exports
- Use `export_bom` (`csv` or `markdown`), `export_pick_and_place` (`mm` or `mil`), and `run_cam_job` (`2layer_gerber`, `4layer_gerber`, or custom layers) for fabrication/assembly outputs.
