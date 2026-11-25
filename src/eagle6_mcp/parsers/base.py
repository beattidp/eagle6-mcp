"""Base XML parser and format detector for EAGLE v6 files.

Provides safe XML loading with ``lxml`` (entities disabled to prevent XXE)
and detects pre-v6 binary EAGLE files so callers receive actionable errors
directing them to ``convert_legacy_project``.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from eagle6_mcp.models.common import FileFormat, Layer, NetClass


class LegacyBinaryFormatError(ValueError):
    """Raised when an EAGLE v4/v5 binary file is passed to an XML parser."""

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = str(file_path)
        super().__init__(
            f"'{self.file_path}' is in legacy EAGLE binary format (pre-v6). "
            "Use `convert_legacy_project` to create a staged XML copy first."
        )


class FormatDetector:
    """Detects whether an EAGLE file is v6 XML, legacy binary, or unknown."""

    # Pre-v6 CadSoft EAGLE binary files begin with 0x10 0x00 (record header).
    _LEGACY_MAGIC_PREFIXES = (b"\x10\x00", b"\x10\x80")

    @classmethod
    def detect(cls, file_path: str | Path) -> FileFormat:
        """Inspect leading bytes of ``file_path`` to determine its EAGLE format."""
        path = Path(file_path)
        if not path.is_file():
            return FileFormat.UNKNOWN

        with path.open("rb") as fh:
            header = fh.read(256)

        stripped = header.lstrip()
        if stripped.startswith(b"<?xml") or stripped.startswith(b"<eagle"):
            return FileFormat.XML
        if any(header.startswith(magic) for magic in cls._LEGACY_MAGIC_PREFIXES):
            return FileFormat.LEGACY_BINARY
        # Heuristic: non-text binary bytes in header indicate legacy binary
        if b"\x00" in header:
            return FileFormat.LEGACY_BINARY
        return FileFormat.UNKNOWN


class BaseEagleParser:
    """Shared XML parsing utilities for EAGLE v6.6.0 DTD-compliant documents."""

    @staticmethod
    def load_root(file_path: str | Path) -> etree._Element:
        """Parse an EAGLE XML file and return its ``<eagle>`` root element.

        Raises:
            FileNotFoundError: If the file does not exist.
            LegacyBinaryFormatError: If the file is a pre-v6 binary EAGLE file.
            ValueError: If the file is not a valid EAGLE XML document.
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"EAGLE file not found: {path}")

        fmt = FormatDetector.detect(path)
        if fmt == FileFormat.LEGACY_BINARY:
            raise LegacyBinaryFormatError(path)
        if fmt != FileFormat.XML:
            raise ValueError(f"File is not a recognized EAGLE XML document: {path}")

        parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
        tree = etree.parse(str(path), parser)
        root = tree.getroot()
        if root.tag != "eagle":
            raise ValueError(f"Expected <eagle> root element, found <{root.tag}> in {path}")
        return root

    @staticmethod
    def parse_bool(value: str | None, default: bool = False) -> bool:
        """Parse an EAGLE ``(no | yes)`` boolean attribute."""
        if value is None:
            return default
        return value.strip().lower() == "yes"

    @staticmethod
    def parse_float(value: str | None, default: float = 0.0) -> float:
        """Parse a floating-point coordinate or dimension attribute."""
        if value is None or value == "":
            return default
        return float(value)

    @staticmethod
    def parse_int(value: str | None, default: int = 0) -> int:
        """Parse an integer attribute."""
        if value is None or value == "":
            return default
        return int(value)

    @classmethod
    def parse_layers(cls, drawing_el: etree._Element) -> dict[int, Layer]:
        """Parse ``<layers><layer .../></layers>`` under ``<drawing>``."""
        layers: dict[int, Layer] = {}
        layers_el = drawing_el.find("layers")
        if layers_el is None:
            return layers
        for el in layers_el.findall("layer"):
            num = cls.parse_int(el.get("number"))
            layers[num] = Layer(
                number=num,
                name=el.get("name", ""),
                color=cls.parse_int(el.get("color")),
                fill=cls.parse_int(el.get("fill")),
                visible=cls.parse_bool(el.get("visible"), default=True),
                active=cls.parse_bool(el.get("active"), default=True),
            )
        return layers

    @classmethod
    def parse_classes(cls, parent_el: etree._Element) -> dict[int, NetClass]:
        """Parse ``<classes><class .../></classes>`` under schematic or board."""
        classes: dict[int, NetClass] = {}
        classes_el = parent_el.find("classes")
        if classes_el is None:
            return classes
        for el in classes_el.findall("class"):
            num = cls.parse_int(el.get("number"))
            clearances: dict[int, float] = {}
            for clr in el.findall("clearance"):
                other = cls.parse_int(clr.get("class"))
                clearances[other] = cls.parse_float(clr.get("value"))
            classes[num] = NetClass(
                number=num,
                name=el.get("name", f"class_{num}"),
                width_mm=cls.parse_float(el.get("width")),
                drill_mm=cls.parse_float(el.get("drill")),
                clearances_mm=clearances,
            )
        return classes

    @staticmethod
    def parse_attributes(parent_el: etree._Element) -> dict[str, str]:
        """Parse child ``<attribute name=... value=.../>`` elements."""
        attrs: dict[str, str] = {}
        for el in parent_el.findall("attribute"):
            name = el.get("name")
            if name:
                attrs[name] = el.get("value", "")
        return attrs

    @staticmethod
    def parse_description(parent_el: etree._Element) -> str:
        """Extract text from the first ``<description>`` child element."""
        desc = parent_el.find("description")
        if desc is None or desc.text is None:
            return ""
        return desc.text.strip()
