"""Unit tests for EAGLE v6 XML/DRU parsers and legacy binary format detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from eagle6_mcp.models import FileFormat
from eagle6_mcp.parsers import (
    BoardParser,
    DruParser,
    FormatDetector,
    LegacyBinaryFormatError,
    LibraryParser,
    SchematicParser,
)


def test_format_detector(sample_project_dir: Path) -> None:
    assert FormatDetector.detect(sample_project_dir / "demo.sch") == FileFormat.XML
    assert FormatDetector.detect(sample_project_dir / "demo.brd") == FileFormat.XML
    assert FormatDetector.detect(sample_project_dir / "old_v5.sch") == FileFormat.LEGACY_BINARY
    assert FormatDetector.detect(sample_project_dir / "missing.sch") == FileFormat.UNKNOWN


def test_legacy_binary_raises_clear_error(sample_project_dir: Path) -> None:
    with pytest.raises(LegacyBinaryFormatError) as exc_info:
        SchematicParser.parse_file(sample_project_dir / "old_v5.sch")
    assert "convert_legacy_project" in str(exc_info.value)


def test_library_parser(sample_project_dir: Path) -> None:
    lib = LibraryParser.parse_file(sample_project_dir / "testlib.lbr")
    assert lib.name == "testlib"
    assert set(lib.packages.keys()) == {"0805", "DIP8"}
    assert lib.packages["0805"].is_smd is True
    assert lib.packages["DIP8"].is_tht is True
    assert len(lib.packages["DIP8"].holes) == 1
    assert set(lib.symbols.keys()) == {"R", "MCU4", "GND"}
    assert "MCU" in lib.devicesets
    assert len(lib.devicesets["MCU"].devices[0].connects) == 4


def test_schematic_parser(sample_project_dir: Path) -> None:
    sch = SchematicParser.parse_file(sample_project_dir / "demo.sch")
    assert sch.eagle_version == "6.6.0"
    assert len(sch.sheets) == 1
    assert set(sch.parts.keys()) == {"R1", "R2", "U1", "GND1"}
    assert sch.parts["R1"].attributes["MPN"] == "RC0805FR-0710KL"
    assert sch.parts["R2"].value is None
    assert len(sch.sheets[0].nets) == 3


def test_board_parser(sample_project_dir: Path) -> None:
    brd = BoardParser.parse_file(sample_project_dir / "demo.brd")
    assert brd.eagle_version == "6.6.0"
    assert len(brd.plain_wires) == 4
    assert brd.elements["R1"].side == "top"
    assert brd.elements["R1"].angle_deg == 90.0
    assert brd.elements["R2"].side == "bottom"
    assert brd.design_rules.params["msWidth"] == "8mil"
    assert len(brd.signals["VCC"].vias) == 1
    assert brd.signals["GND"].wires[0].is_airwire is True


def test_dru_parser_and_unit_conversion(sample_project_dir: Path) -> None:
    dr = DruParser.parse_file(sample_project_dir / "custom.dru")
    assert dr.params["mdWireWire"] == "6mil"
    assert DruParser.to_mm("8mil") == pytest.approx(0.2032, abs=1e-4)
    assert DruParser.to_mm("0.15mm") == pytest.approx(0.15, abs=1e-6)
    assert DruParser.to_mm("(1*16)") is None
