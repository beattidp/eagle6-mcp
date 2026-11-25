"""Unit tests for schematic, board, consistency, library, and discovery analyzers."""

from __future__ import annotations

from pathlib import Path

from eagle6_mcp.analyzers import (
    BoardAnalyzer,
    ConsistencyAnalyzer,
    LibraryAnalyzer,
    ProjectDiscoverer,
    SchematicAnalyzer,
)
from eagle6_mcp.config import EagleConfig
from eagle6_mcp.parsers import BoardParser, LibraryParser, SchematicParser


def test_schematic_analyzer_bom_netlist_review(sample_project_dir: Path) -> None:
    sch = SchematicParser.parse_file(sample_project_dir / "demo.sch")
    analyzer = SchematicAnalyzer(sch)

    bom = analyzer.build_bom(grouped=False)
    part_names = {row["part"] for row in bom}
    # Supply symbol GND1 has no package and must be excluded from BOM by default
    assert part_names == {"R1", "R2", "U1"}

    netlist = analyzer.build_netlist(net_filter="vcc")
    assert len(netlist) == 1
    assert netlist[0]["name"] == "VCC"
    assert netlist[0]["pin_count"] == 2

    part_info = analyzer.inspect_part("U1")
    pin_map = {p["pin"]: p["net"] for p in part_info["pins"]}
    assert pin_map["VCC"] == "VCC"
    assert pin_map["GND"] == "GND"
    assert pin_map["IO0"] is None

    review = analyzer.review()
    findings = review["findings"]
    assert any(n["net"] == "N$1" for n in findings["single_pin_nets"])
    # R2 has uservalue="yes" and no explicit value
    assert any(m["part"] == "R2" for m in findings["missing_values"])
    # U1.IO0 is unconnected (io), while U1.NC1 (direction="nc") must NOT be flagged
    unconn_pins = {(u["part"], u["pin"]) for u in findings["unconnected_pins"]}
    assert ("U1", "IO0") in unconn_pins
    assert ("U1", "NC1") not in unconn_pins


def test_board_analyzer_summary_placement_routing(sample_project_dir: Path) -> None:
    brd = BoardParser.parse_file(sample_project_dir / "demo.brd")
    analyzer = BoardAnalyzer(brd)

    summary = analyzer.summarize()
    assert summary["outline"]["width_mm"] == 50.0
    assert summary["outline"]["height_mm"] == 30.0
    assert summary["components"]["total"] == 3
    assert summary["components"]["top"] == 2
    assert summary["components"]["bottom"] == 1
    assert summary["routing"]["total_airwires"] == 1
    assert summary["routing"]["total_vias"] == 1

    bottom_parts = analyzer.get_placement(side="bottom")
    assert [p["name"] for p in bottom_parts] == ["R2"]

    unrouted = analyzer.get_routing_status(unrouted_only=True)
    assert [s["signal"] for s in unrouted] == ["GND"]
    assert unrouted[0]["airwire_count"] == 1


def test_consistency_analyzer(sample_project_dir: Path) -> None:
    sch = SchematicParser.parse_file(sample_project_dir / "demo.sch")
    brd = BoardParser.parse_file(sample_project_dir / "demo.brd")
    report = ConsistencyAnalyzer(sch, brd).check()
    assert report["consistent"] is True
    assert report["parts_only_in_schematic"] == []
    assert report["elements_only_in_board"] == []


def test_library_analyzer(sample_project_dir: Path) -> None:
    lib = LibraryParser.parse_file(sample_project_dir / "testlib.lbr")
    analyzer = LibraryAnalyzer(lib)
    summary = analyzer.summarize(query="mcu")
    assert summary["counts"]["devicesets"] == 1
    dev = analyzer.inspect_deviceset("MCU")
    assert dev["devices"][0]["package"] == "DIP8"
    assert len(dev["devices"][0]["connects"]) == 4


def test_project_discoverer(sample_project_dir: Path) -> None:
    cfg = EagleConfig(project_dirs=[sample_project_dir], library_dirs=[sample_project_dir])
    disc = ProjectDiscoverer(cfg)
    projects = disc.list_projects()
    by_name = {p.name: p for p in projects}
    assert "demo" in by_name
    assert by_name["demo"].sch_format.value == "xml"
    assert by_name["demo"].brd_format.value == "xml"
    assert by_name["old_v5"].sch_format.value == "legacy_binary"
