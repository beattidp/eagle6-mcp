"""MCP server wiring for CadSoft EAGLE v6.6.0 design review and inspection.

Exposes Phase 1 read-only XML analysis tools and headless ``xvfb-run`` EAGLE CLI
rendering / legacy-conversion tools over the standard ``stdio`` MCP transport.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer

from eagle6_mcp.analyzers import (
    BoardAnalyzer,
    ConsistencyAnalyzer,
    ErcDrcAnalyzer,
    LibraryAnalyzer,
    ProjectDiscoverer,
    SchematicAnalyzer,
)
from eagle6_mcp.config import DEFAULT_CONFIG, EagleConfig
from eagle6_mcp.exports import CAM_PRESETS, ManufacturingExporter
from eagle6_mcp.models.library import Library
from eagle6_mcp.parsers import (
    BoardParser,
    DruParser,
    FormatDetector,
    LibraryParser,
    SchematicParser,
)
from eagle6_mcp.runner import BOARD_LAYER_PRESETS, EagleRunner
from eagle6_mcp.scripts import ScriptBuilder, ScriptValidator


def _load_library_from_any(path: str | Path, library_name: str | None = None) -> Library:
    """Load a :class:`Library` from a standalone ``.lbr`` or embedded in ``.sch``/``.brd``."""
    p = Path(path).expanduser()
    suffix = p.suffix.lower()
    if suffix == ".lbr":
        return LibraryParser.parse_file(p)
    if suffix == ".sch":
        sch = SchematicParser.parse_file(p)
        libs = sch.libraries
    elif suffix == ".brd":
        brd = BoardParser.parse_file(p)
        libs = brd.libraries
    else:
        raise ValueError(f"Unsupported file type for library inspection: {p}")

    if not libs:
        raise ValueError(f"No embedded libraries found in '{p}'.")
    if library_name:
        if library_name not in libs:
            avail = ", ".join(sorted(libs.keys()))
            raise KeyError(
                f"Library '{library_name}' not found in '{p}'. Available: {avail}"
            )
        return libs[library_name]
    if len(libs) == 1:
        return next(iter(libs.values()))
    avail = ", ".join(sorted(libs.keys()))
    raise ValueError(
        f"'{p}' contains multiple embedded libraries. Specify `library_name` "
        f"from: {avail}"
    )


def create_server(config: EagleConfig | None = None) -> MCPServer:
    """Instantiate and register all EAGLE v6 MCP tools on an :class:`MCPServer`."""
    cfg = config or DEFAULT_CONFIG
    discoverer = ProjectDiscoverer(cfg)
    runner = EagleRunner(cfg)
    validator = ScriptValidator(cfg, runner=runner)

    mcp = MCPServer(
        name="eagle6-mcp",
        instructions=(
            "Analysis, static & official ERC/DRC review, headless PNG rendering, "
            "validated .scr edit script generation, and headless CAM/BOM/centroid "
            "exports for CadSoft EAGLE v6.6.0 designs. Never mutates user .sch/.brd files."
        ),
    )

    # ------------------------------------------------------------------
    # 1. Discovery & Project Overview
    # ------------------------------------------------------------------

    @mcp.tool()
    def list_projects(root_dir: str | None = None, max_depth: int = 4) -> list[dict[str, Any]]:
        """List EAGLE projects (.sch/.brd pairs) in configured directories or a custom root.

        Reports detected format (`xml` vs `legacy_binary`) so pre-v6 binary
        projects can be converted safely with `convert_legacy_project`.
        """
        projects = discoverer.list_projects(root_dir=root_dir, max_depth=max_depth)
        return [asdict(p) for p in projects]

    @mcp.tool()
    def get_project_summary(project_path: str) -> dict[str, Any]:
        """Return a high-level summary of an EAGLE project (schematic + board if paired).

        Args:
            project_path: Path to a ``.sch``, ``.brd``, or project directory.
        """
        p = Path(project_path).expanduser().resolve()
        sch_path: Path | None = None
        brd_path: Path | None = None

        if p.is_dir():
            sch_candidates = sorted(p.glob("*.sch"))
            brd_candidates = sorted(p.glob("*.brd"))
            sch_path = sch_candidates[0] if sch_candidates else None
            brd_path = brd_candidates[0] if brd_candidates else None
        elif p.suffix.lower() == ".sch":
            sch_path = p
            sibling = p.with_suffix(".brd")
            brd_path = sibling if sibling.is_file() else None
        elif p.suffix.lower() == ".brd":
            brd_path = p
            sibling = p.with_suffix(".sch")
            sch_path = sibling if sibling.is_file() else None
        else:
            raise ValueError(f"Expected a .sch, .brd, or directory path: {project_path}")

        summary: dict[str, Any] = {
            "sch_path": str(sch_path) if sch_path else None,
            "brd_path": str(brd_path) if brd_path else None,
            "sch_format": FormatDetector.detect(sch_path).value if sch_path else None,
            "brd_format": FormatDetector.detect(brd_path).value if brd_path else None,
        }

        if sch_path and summary["sch_format"] == "xml":
            sch = SchematicParser.parse_file(sch_path)
            sa = SchematicAnalyzer(sch)
            summary["schematic"] = {
                "eagle_version": sch.eagle_version,
                "sheets": len(sch.sheets),
                "total_parts": len(sch.parts),
                "bom_parts": len(sa.build_bom(grouped=False)),
                "nets": len(sa.aggregated_nets()),
                "embedded_libraries": sorted(sch.libraries.keys()),
            }

        if brd_path and summary["brd_format"] == "xml":
            brd = BoardParser.parse_file(brd_path)
            ba = BoardAnalyzer(brd)
            summary["board"] = ba.summarize()

        return summary

    @mcp.tool()
    def list_libraries(query: str | None = None, scope: str = "all") -> list[dict[str, Any]]:
        """List EAGLE ``.lbr`` libraries across user and/or system library paths.

        Args:
            query: Optional case-insensitive substring filter on library name.
            scope: ``"user"``, ``"system"``, or ``"all"``.
        """
        libs = discoverer.list_libraries(query=query, scope=scope)
        return [asdict(lib) for lib in libs]

    # ------------------------------------------------------------------
    # 2. Schematic Analysis
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_schematic_bom(
        sch_path: str, grouped: bool = True, include_non_bom: bool = False
    ) -> list[dict[str, Any]]:
        """Extract a Bill of Materials (BOM) from an EAGLE v6 ``.sch`` file."""
        sch = SchematicParser.parse_file(sch_path)
        return SchematicAnalyzer(sch).build_bom(
            grouped=grouped, include_non_bom=include_non_bom
        )

    @mcp.tool()
    def get_schematic_netlist(
        sch_path: str,
        net_filter: str | None = None,
        part_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Extract full or filtered electrical netlist across all schematic sheets."""
        sch = SchematicParser.parse_file(sch_path)
        return SchematicAnalyzer(sch).build_netlist(
            net_filter=net_filter, part_filter=part_filter
        )

    @mcp.tool()
    def inspect_schematic_part(sch_path: str, part_name: str) -> dict[str, Any]:
        """Inspect a single schematic component's metadata, gates, pads, and pin-to-net map."""
        sch = SchematicParser.parse_file(sch_path)
        return SchematicAnalyzer(sch).inspect_part(part_name)

    @mcp.tool()
    def review_schematic(sch_path: str) -> dict[str, Any]:
        """Run automated static electrical and hygiene checks on an EAGLE v6 schematic.

        Checks single-pin/dangling nets, unconnected IC pins, missing component
        values, unannotated designators, and power/ground rail inventory.
        """
        sch = SchematicParser.parse_file(sch_path)
        return SchematicAnalyzer(sch).review()

    # ------------------------------------------------------------------
    # 3. Board Analysis
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_board_summary(brd_path: str) -> dict[str, Any]:
        """Return board dimensions (mm & mil), layers, component counts, and routing stats."""
        brd = BoardParser.parse_file(brd_path)
        return BoardAnalyzer(brd).summarize()

    @mcp.tool()
    def get_board_placement(
        brd_path: str, part_filter: str | None = None, side: str = "all"
    ) -> list[dict[str, Any]]:
        """Return component placement coordinates (mm), rotation, side, and package."""
        brd = BoardParser.parse_file(brd_path)
        return BoardAnalyzer(brd).get_placement(part_filter=part_filter, side=side)

    @mcp.tool()
    def get_board_routing_status(
        brd_path: str,
        unrouted_only: bool = False,
        signal_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return per-signal routing lengths, layers, widths, vias, and unrouted airwires."""
        brd = BoardParser.parse_file(brd_path)
        return BoardAnalyzer(brd).get_routing_status(
            unrouted_only=unrouted_only, signal_filter=signal_filter
        )

    @mcp.tool()
    def get_design_rules(path: str) -> dict[str, Any]:
        """Parse design rules from either a ``.brd`` (embedded DRU) or standalone ``.dru`` file."""
        p = Path(path).expanduser()
        if p.suffix.lower() == ".dru":
            dr = DruParser.parse_file(p)
            return {
                "name": dr.name,
                "description": dr.description,
                "all_params": dict(dr.params),
            }
        brd = BoardParser.parse_file(p)
        return BoardAnalyzer(brd).summarize_design_rules()

    @mcp.tool()
    def check_sch_brd_consistency(sch_path: str, brd_path: str) -> dict[str, Any]:
        """Cross-check forward/back-annotation consistency between ``.sch`` and ``.brd``."""
        sch = SchematicParser.parse_file(sch_path)
        brd = BoardParser.parse_file(brd_path)
        return ConsistencyAnalyzer(sch, brd).check()

    # ------------------------------------------------------------------
    # 4. Library Inspection
    # ------------------------------------------------------------------

    @mcp.tool()
    def inspect_library(
        path: str, library_name: str | None = None, query: str | None = None
    ) -> dict[str, Any]:
        """List devicesets, packages, and symbols in a ``.lbr`` or embedded in ``.sch``/``.brd``."""
        lib = _load_library_from_any(path, library_name=library_name)
        return LibraryAnalyzer(lib).summarize(query=query)

    @mcp.tool()
    def inspect_library_device(
        path: str, deviceset_name: str, library_name: str | None = None
    ) -> dict[str, Any]:
        """Inspect symbol pin directions, pad/SMD dimensions, drills, and pin-to-pad mapping."""
        lib = _load_library_from_any(path, library_name=library_name)
        return LibraryAnalyzer(lib).inspect_deviceset(deviceset_name)

    # ------------------------------------------------------------------
    # 5. Visual Rendering & Legacy Conversion (xvfb-run + EAGLE CLI)
    # ------------------------------------------------------------------

    @mcp.tool()
    def render_schematic(
        sch_path: str, sheet: int = 1, dpi: int = 200, include_image: bool = True
    ) -> list[Any]:
        """Render a schematic sheet to PNG via headless EAGLE CLI under ``/tmp/``.

        Returns the saved PNG path (and inline image when ``include_image=True``).
        """
        out_path = runner.render_schematic(sch_path=sch_path, sheet=sheet, dpi=dpi)
        meta = f"Rendered schematic sheet {sheet} ({dpi} DPI) to {out_path}"
        if include_image:
            return [meta, Image(path=out_path)]
        return [meta]

    @mcp.tool()
    def render_board(
        brd_path: str,
        preset: str = "all_copper",
        custom_layers: list[int] | None = None,
        dpi: int = 300,
        include_image: bool = True,
    ) -> list[Any]:
        """Render PCB layers to PNG via headless EAGLE CLI under ``/tmp/``.

        Valid presets: ``top_copper``, ``bottom_copper``, ``all_copper``,
        ``top_assembly``, ``bottom_assembly``, ``unrouted``.
        """
        out_path = runner.render_board(
            brd_path=brd_path,
            preset=preset,
            custom_layers=custom_layers,
            dpi=dpi,
        )
        valid_presets = ", ".join(sorted(BOARD_LAYER_PRESETS.keys()))
        meta = (
            f"Rendered board ({preset if not custom_layers else custom_layers}, "
            f"{dpi} DPI) to {out_path}. Presets: {valid_presets}"
        )
        if include_image:
            return [meta, Image(path=out_path)]
        return [meta]

    @mcp.tool()
    def convert_legacy_project(file_path: str) -> dict[str, Any]:
        """Convert a pre-v6 binary ``.sch``, ``.brd``, or ``.lbr`` into a staged XML copy.

        The original file is never modified. Use the returned ``staged_xml_path``
        with all XML analysis tools.
        """
        staged = runner.convert_legacy_to_xml(file_path)
        detected = FormatDetector.detect(staged)
        return {
            "source_path": str(Path(file_path).expanduser().resolve()),
            "staged_xml_path": str(staged),
            "detected_format": detected.value,
        }

    # ------------------------------------------------------------------
    # 6. Phase 2: ERC / DRC & Zoomed DRC Region Rendering
    # ------------------------------------------------------------------

    @mcp.tool()
    def run_erc(sch_path: str, include_board_consistency: bool = True) -> dict[str, Any]:
        """Run structured Electrical Rule Check (ERC) on a schematic (and paired board).

        Checks pin-direction conflicts (out-to-out, out-to-supply, undriven inputs),
        unconnected pins, single-pin nets, missing values, unannotated parts, and
        forward/back-annotation consistency when a sibling ``.brd`` exists.
        """
        p = Path(sch_path).expanduser().resolve()
        sch = SchematicParser.parse_file(p)
        brd = None
        if include_board_consistency:
            sibling = p.with_suffix(".brd")
            if not sibling.is_file():
                sibling = p.with_suffix(".BRD")
            if sibling.is_file() and FormatDetector.detect(sibling).value == "xml":
                brd = BoardParser.parse_file(sibling)
        return ErcDrcAnalyzer.run_erc(sch, board=brd)

    @mcp.tool()
    def run_drc(
        brd_path: str,
        dru_path: str | None = None,
        render_overlay: bool = False,
        dpi: int = 200,
    ) -> dict[str, Any]:
        """Run structured Design Rule Check (DRC) on a board against embedded or external DRU.

        Optionally also runs official EAGLE 6.6.0 ``DRC;`` on a staged copy and
        saves an error-polygon overlay PNG under ``/tmp/eagle6-mcp-renders/``.
        """
        brd = BoardParser.parse_file(brd_path)
        override_dru = DruParser.parse_file(dru_path) if dru_path else None
        report = ErcDrcAnalyzer.run_drc(brd, override_dru=override_dru)
        if render_overlay:
            overlay_png = runner.render_drc_overlay(
                brd_path=brd_path, dru_path=dru_path, dpi=dpi
            )
            report["drc_overlay_png"] = str(overlay_png)
        return report

    @mcp.tool()
    def render_drc_region(
        brd_path: str,
        x_mm: float,
        y_mm: float,
        radius_mm: float = 5.0,
        preset: str = "all_copper",
        custom_layers: list[int] | None = None,
        run_drc: bool = True,
        dpi: int = 300,
        include_image: bool = True,
    ) -> list[Any]:
        """Render a zoomed-in board PNG centered on ``(x_mm, y_mm)`` with optional DRC overlay."""
        out_path = runner.render_drc_region(
            brd_path=brd_path,
            x_mm=x_mm,
            y_mm=y_mm,
            radius_mm=radius_mm,
            preset=preset,
            custom_layers=custom_layers,
            run_drc=run_drc,
            dpi=dpi,
        )
        meta = (
            f"Rendered board region ({x_mm:.2f}, {y_mm:.2f}) mm +/- {radius_mm:.2f} mm "
            f"(drc={run_drc}, {dpi} DPI) to {out_path}"
        )
        if include_image:
            return [meta, Image(path=out_path)]
        return [meta]

    # ------------------------------------------------------------------
    # 7. Phase 2: Safe Assisted Editing via EAGLE Scripts (.scr)
    # ------------------------------------------------------------------

    @mcp.tool()
    def generate_edit_script(
        target: str,
        operations: list[dict[str, Any]],
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """Generate a commented, safely-escaped EAGLE ``.scr`` edit script.

        Supported ``op`` types: ``set_value``, ``rename_part``, ``set_attribute``,
        ``delete_attribute``, ``add_part``, ``move_part``, ``rotate_part``,
        ``mirror_part``, ``smash_part``, ``set_net_class``, ``change_width``,
        ``raw_command``.
        """
        return ScriptBuilder.generate(
            target=target, operations=operations, project_path=project_path
        )

    @mcp.tool()
    def validate_edit_script(
        project_path: str,
        script_content: str,
        run_checks: bool = True,
        keep_staged: bool = False,
    ) -> dict[str, Any]:
        """Dry-run an EAGLE ``.scr`` script on an isolated staged copy of a project.

        Stages both ``.sch`` and ``.brd`` (when paired), executes the script via
        EAGLE 6.6.0 under ``xvfb-run``, and returns before/after diffs,
        consistency results, and ERC/DRC deltas without touching user files.

        When ``keep_staged`` is ``True``, retains the isolated staging directory
        under ``staging_root`` and returns ``staged_dir``, ``staged_brd_path``,
        and ``staged_sch_path`` for downstream tools (e.g. ``eagle6-freerouting``).
        """
        return validator.validate(
            project_path=project_path,
            script_content=script_content,
            run_checks=run_checks,
            keep_staged=keep_staged,
        )

    @mcp.tool()
    def save_edit_script(script_content: str, output_path: str) -> dict[str, str]:
        """Save a reviewed ``.scr`` script to disk and return the EAGLE GUI command."""
        return ScriptValidator.save_script(
            script_content=script_content, output_path=output_path
        )

    # ------------------------------------------------------------------
    # 8. Phase 2: Manufacturing & Documentation Exports
    # ------------------------------------------------------------------

    @mcp.tool()
    def export_bom(
        sch_path: str,
        format: str = "csv",
        grouped: bool = True,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Export a clean fabrication/purchasing BOM in ``csv`` or ``markdown`` format."""
        sch = SchematicParser.parse_file(sch_path)
        return ManufacturingExporter.export_bom(
            schematic=sch, fmt=format, grouped=grouped, output_path=output_path
        )

    @mcp.tool()
    def export_pick_and_place(
        brd_path: str,
        units: str = "mm",
        side: str = "all",
        smd_only: bool = False,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Export an SMD/THT Pick-and-Place centroid CSV table from a ``.brd`` file."""
        brd = BoardParser.parse_file(brd_path)
        return ManufacturingExporter.export_pick_and_place(
            board=brd,
            units=units,
            side=side,
            smd_only=smd_only,
            output_path=output_path,
        )

    @mcp.tool()
    def run_cam_job(
        brd_path: str,
        output_dir: str,
        preset: str = "2layer_gerber",
        custom_jobs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run headless EAGLE CAM Processor (``eagle -X``) to generate Gerbers & Excellon drills.

        Valid presets: ``2layer_gerber``, ``4layer_gerber``. Or pass ``custom_jobs``
        as ``[{"suffix": ".GTL", "device": "GERBER_RS274X", "layers": [1, 17, 18]}]``.
        """
        if custom_jobs:
            jobs = [
                (str(j["suffix"]), str(j["device"]), [int(l) for l in j["layers"]])
                for j in custom_jobs
            ]
        else:
            key = preset.lower().strip()
            if key not in CAM_PRESETS:
                valid = ", ".join(sorted(CAM_PRESETS.keys()))
                raise ValueError(f"Unknown CAM preset '{preset}'. Valid: {valid}")
            jobs = CAM_PRESETS[key]
        return runner.run_cam_job(brd_path=brd_path, output_dir=output_dir, jobs=jobs)

    return mcp


def main() -> None:
    """Entry point for running the EAGLE v6 MCP server over stdio."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
