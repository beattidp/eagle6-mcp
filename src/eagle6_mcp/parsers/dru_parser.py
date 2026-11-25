"""Parser for EAGLE Design Rule files (``.dru``) and embedded ``<designrules>`` XML."""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from eagle6_mcp.models.common import DesignRules


class DruParser:
    """Parses both standalone key=value ``.dru`` files and board ``<designrules>`` XML."""

    # Matches EAGLE unit strings like "8mil", "0.2mm", "20mil", "0.01inch"
    _UNIT_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*(mm|mil|inch|mic)?\s*$", re.I)

    @classmethod
    def parse_xml_element(cls, dr_el: etree._Element | None) -> DesignRules:
        """Parse an embedded ``<designrules>`` element from a ``.brd`` file."""
        if dr_el is None:
            return DesignRules()
        name = dr_el.get("name", "default")
        desc_el = dr_el.find("description")
        desc = (desc_el.text or "").strip() if desc_el is not None else ""
        params: dict[str, str] = {}
        for p in dr_el.findall("param"):
            pname = p.get("name")
            if pname:
                params[pname] = p.get("value", "")
        return DesignRules(name=name, description=desc, params=params)

    @classmethod
    def parse_file(cls, dru_path: str | Path) -> DesignRules:
        """Parse a standalone CadSoft EAGLE ``.dru`` text file."""
        path = Path(dru_path)
        if not path.is_file():
            raise FileNotFoundError(f"DRU file not found: {path}")

        description_lines: list[str] = []
        params: dict[str, str] = {}
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if key.startswith("description"):
                    description_lines.append(val)
                else:
                    params[key] = val

        return DesignRules(
            name=path.stem,
            description="\n".join(description_lines),
            params=params,
        )

    @classmethod
    def to_mm(cls, value: str | None) -> float | None:
        """Convert an EAGLE DRU dimension string (mm/mil/inch/mic) to millimeters.

        Returns ``None`` if the string is not a numeric dimension (e.g., layer
        setup expressions like ``(1*16)``).
        """
        if not value:
            return None
        match = cls._UNIT_RE.match(value)
        if not match:
            return None
        num = float(match.group(1))
        unit = (match.group(2) or "mm").lower()
        if unit == "mm":
            return num
        if unit == "mil":
            return round(num * 0.0254, 6)
        if unit == "inch":
            return round(num * 25.4, 6)
        if unit == "mic":
            return round(num * 0.001, 6)
        return None
