"""Server tool registration and live EAGLE v6.6.0 CLI integration tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from eagle6_mcp.analyzers import BoardAnalyzer, ConsistencyAnalyzer, SchematicAnalyzer
from eagle6_mcp.config import DEFAULT_CONFIG
from eagle6_mcp.models import FileFormat
from eagle6_mcp.parsers import BoardParser, FormatDetector, SchematicParser
from eagle6_mcp.runner import EagleRunner
from eagle6_mcp.server import create_server


PRPP_SCH = Path.home() / "eagle6" / "projects" / "PRPP-controller" / "prpp-mcu.sch"
PRPP_BRD = Path.home() / "eagle6" / "projects" / "PRPP-controller" / "prpp-mcu.brd"
LEGACY_V5_DIR = Path.home() / "eagle" / "projects"


def test_mcp_server_registers_phase1_tools() -> None:
    server = create_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "list_projects",
        "get_project_summary",
        "list_libraries",
        "get_schematic_bom",
        "get_schematic_netlist",
        "inspect_schematic_part",
        "review_schematic",
        "get_board_summary",
        "get_board_placement",
        "get_board_routing_status",
        "get_design_rules",
        "check_sch_brd_consistency",
        "inspect_library",
        "inspect_library_device",
        "render_schematic",
        "render_board",
        "convert_legacy_project",
    }
    assert expected.issubset(names)


@pytest.mark.skipif(not PRPP_SCH.is_file(), reason="PRPP-controller project not available")
def test_live_prpp_xml_analysis() -> None:
    sch = SchematicParser.parse_file(PRPP_SCH)
    brd = BoardParser.parse_file(PRPP_BRD)

    sch_review = SchematicAnalyzer(sch).review()
    assert sch_review["sheet_count"] >= 1
    assert sch_review["total_parts"] > 0

    brd_summary = BoardAnalyzer(brd).summarize()
    assert brd_summary["components"]["total"] > 0

    consistency = ConsistencyAnalyzer(sch, brd).check()
    assert "consistent" in consistency


@pytest.mark.skipif(
    not (PRPP_SCH.is_file() and DEFAULT_CONFIG.eagle_bin.is_file()),
    reason="EAGLE 6.6.0 or PRPP-controller not available",
)
def test_live_xvfb_render_schematic_and_board() -> None:
    runner = EagleRunner(DEFAULT_CONFIG)

    sch_png = runner.render_schematic(PRPP_SCH, sheet=1, dpi=150)
    assert sch_png.is_file()
    assert sch_png.stat().st_size > 1024
    # Verify PNG magic header
    assert sch_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    brd_png = runner.render_board(PRPP_BRD, preset="all_copper", dpi=150)
    assert brd_png.is_file()
    assert brd_png.stat().st_size > 1024
    assert brd_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.skipif(
    not (LEGACY_V5_DIR.is_dir() and DEFAULT_CONFIG.eagle_bin.is_file()),
    reason="Legacy EAGLE v5 projects directory not available",
)
def test_live_legacy_v5_detection_and_conversion() -> None:
    v5_candidates = sorted(LEGACY_V5_DIR.rglob("*.sch"))
    legacy_file = next(
        (p for p in v5_candidates if FormatDetector.detect(p) == FileFormat.LEGACY_BINARY),
        None,
    )
    if legacy_file is None:
        pytest.skip(f"No legacy binary .sch found in {LEGACY_V5_DIR}")

    runner = EagleRunner(DEFAULT_CONFIG)
    staged_xml = runner.convert_legacy_to_xml(legacy_file)
    assert staged_xml.is_file()
    assert FormatDetector.detect(staged_xml) == FileFormat.XML
    # Verify the converted XML parses cleanly with SchematicParser
    sch = SchematicParser.parse_file(staged_xml)
    assert len(sch.sheets) >= 1
