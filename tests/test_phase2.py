"""Unit and live integration tests for Phase 2 features (ERC/DRC, .scr scripts, CAM/exports)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from eagle6_mcp.analyzers import ErcDrcAnalyzer
from eagle6_mcp.config import DEFAULT_CONFIG
from eagle6_mcp.exports import CAM_PRESETS, ManufacturingExporter
from eagle6_mcp.models import DesignRules
from eagle6_mcp.parsers import BoardParser, SchematicParser
from eagle6_mcp.runner import EagleRunner
from eagle6_mcp.scripts import ScriptBuilder, ScriptValidator
from eagle6_mcp.server import create_server

PRPP_SCH = Path("/home/beattidp/eagle6/projects/PRPP-controller/prpp-mcu.sch")
PRPP_BRD = Path("/home/beattidp/eagle6/projects/PRPP-controller/prpp-mcu.brd")


def test_mcp_server_registers_phase2_tools() -> None:
    server = create_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    expected_phase2 = {
        "run_erc",
        "run_drc",
        "render_drc_region",
        "generate_edit_script",
        "validate_edit_script",
        "save_edit_script",
        "export_bom",
        "export_pick_and_place",
        "run_cam_job",
    }
    assert expected_phase2.issubset(names)
    assert len(names) >= 26


def test_erc_and_drc_analyzers(sample_project_dir: Path) -> None:
    sch = SchematicParser.parse_file(sample_project_dir / "demo.sch")
    brd = BoardParser.parse_file(sample_project_dir / "demo.brd")

    erc = ErcDrcAnalyzer.run_erc(sch, board=brd)
    assert erc["consistency"]["consistent"] is True
    codes = {w["code"] for w in erc["warnings"]}
    assert "ERC_SINGLE_PIN_NET" in codes
    assert "ERC_MISSING_VALUE" in codes
    assert "ERC_UNCONNECTED_PIN" in codes

    # Run DRC with stricter custom DRU to trigger width & drill errors cleanly
    strict_dru = DesignRules(
        name="strict",
        params={"msWidth": "0.6mm", "msDrill": "0.5mm", "mdCopperDimension": "0.5mm"},
    )
    drc = ErcDrcAnalyzer.run_drc(brd, override_dru=strict_dru)
    err_codes = {e["code"] for e in drc["errors"]}
    warn_codes = {w["code"] for w in drc["warnings"]}
    assert "DRC_MIN_WIDTH" in err_codes
    assert "DRC_MIN_DRILL_VIA" in err_codes
    assert "DRC_AIRWIRE" in warn_codes


def test_script_builder_generation_and_preflight(sample_project_dir: Path) -> None:
    res = ScriptBuilder.generate(
        target="sch",
        project_path=sample_project_dir / "demo.sch",
        operations=[
            {"op": "set_value", "part": "R2", "value": "4.7k", "comment": "Populate R2"},
            {"op": "set_attribute", "part": "R1", "name": "DNP", "value": "NO"},
            {"op": "rename_part", "old_name": "R99", "new_name": "R1"},
        ],
    )
    assert "VALUE R2 '4.7k';" in res["script"]
    assert "ATTRIBUTE R1 DNP 'NO';" in res["script"]
    assert "NAME R99 R1;" in res["script"]
    # Pre-flight should warn that R99 doesn't exist and R1 already exists
    assert len(res["preflight_warnings"]) == 2


def test_manufacturing_bom_and_pick_and_place(sample_project_dir: Path, tmp_path: Path) -> None:
    sch = SchematicParser.parse_file(sample_project_dir / "demo.sch")
    brd = BoardParser.parse_file(sample_project_dir / "demo.brd")

    bom_csv = ManufacturingExporter.export_bom(
        sch, fmt="csv", grouped=True, output_path=tmp_path / "bom.csv"
    )
    assert (tmp_path / "bom.csv").is_file()
    assert "RC0805FR-0710KL" in bom_csv["content"]

    bom_md = ManufacturingExporter.export_bom(sch, fmt="markdown", grouped=False)
    assert "| Designator |" in bom_md["content"]

    pnp = ManufacturingExporter.export_pick_and_place(
        brd, units="mm", side="all", smd_only=True, output_path=tmp_path / "pnp.csv"
    )
    assert (tmp_path / "pnp.csv").is_file()
    # R1 and R2 are 0805 SMD; U1 is DIP8 THT and excluded when smd_only=True
    assert pnp["component_count"] == 2
    assert "R1" in pnp["content"]
    assert "U1" not in pnp["content"]


@pytest.mark.skipif(
    not (PRPP_SCH.is_file() and PRPP_BRD.is_file() and DEFAULT_CONFIG.eagle_bin.is_file()),
    reason="EAGLE 6.6.0 or PRPP-controller not available",
)
def test_live_script_dry_run_validation() -> None:
    """Dry-run a VALUE + ATTRIBUTE edit on a staged PRPP-controller copy."""
    gen = ScriptBuilder.generate(
        target="sch",
        project_path=PRPP_SCH,
        operations=[
            {"op": "set_value", "part": "R1", "value": "220R"},
            {"op": "set_attribute", "part": "R1", "name": "TEST_TAG", "value": "OK"},
        ],
    )
    validator = ScriptValidator(DEFAULT_CONFIG)
    result = validator.validate(PRPP_SCH, gen["script"], run_checks=True)
    assert result["success"] is True
    assert result["paired_files_staged"] is True
    # Value change must propagate to schematic diff
    sch_vals = {c["part"]: c["after"] for c in result["diff"]["schematic"]["value_changes"]}
    assert sch_vals.get("R1") == "220R"
    # Forward/back-annotation must also propagate the value change to the staged board!
    brd_vals = {c["element"]: c["after"] for c in result["diff"]["board"]["value_changes"]}
    assert brd_vals.get("R1") == "220R"


@pytest.mark.skipif(
    not (PRPP_BRD.is_file() and DEFAULT_CONFIG.eagle_bin.is_file()),
    reason="EAGLE 6.6.0 or PRPP-controller board not available",
)
def test_live_drc_overlay_region_and_headless_cam(tmp_path: Path) -> None:
    runner = EagleRunner(DEFAULT_CONFIG)

    overlay = runner.render_drc_overlay(PRPP_BRD, dpi=150)
    assert overlay.is_file()
    assert overlay.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    region = runner.render_drc_region(PRPP_BRD, x_mm=20.0, y_mm=20.0, radius_mm=10.0, dpi=150)
    assert region.is_file()
    assert region.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    cam_dir = tmp_path / "gerbers"
    cam = runner.run_cam_job(PRPP_BRD, output_dir=cam_dir, jobs=CAM_PRESETS["2layer_gerber"])
    assert cam["file_count"] == len(CAM_PRESETS["2layer_gerber"])
    assert all(f["exists"] and f["size_bytes"] > 0 for f in cam["files"])
