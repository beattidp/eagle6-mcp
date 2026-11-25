"""Parser for EAGLE v6 schematic (``.sch``) XML files."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from eagle6_mcp.models.schematic import (
    Net,
    NetSegment,
    Part,
    PartInstance,
    PinRef,
    Schematic,
    Sheet,
)
from eagle6_mcp.parsers.base import BaseEagleParser
from eagle6_mcp.parsers.library_parser import LibraryParser


class SchematicParser(BaseEagleParser):
    """Parses CadSoft EAGLE v6 ``.sch`` files into :class:`Schematic` models."""

    @classmethod
    def parse_file(cls, sch_path: str | Path) -> Schematic:
        """Parse an EAGLE v6 ``.sch`` file."""
        path = Path(sch_path)
        root = cls.load_root(path)
        eagle_version = root.get("version", "unknown")

        drawing = root.find("drawing")
        if drawing is None:
            raise ValueError(f"Missing <drawing> element in {path}")
        sch_el = drawing.find("schematic")
        if sch_el is None:
            raise ValueError(f"Missing <schematic> element in {path}")

        layers = cls.parse_layers(drawing)
        classes = cls.parse_classes(sch_el)
        libraries = LibraryParser.parse_embedded_libraries(sch_el)
        description = cls.parse_description(sch_el)

        global_attrs: dict[str, str] = {}
        attrs_el = sch_el.find("attributes")
        if attrs_el is not None:
            global_attrs = cls.parse_attributes(attrs_el)

        parts = cls._parse_parts(sch_el)
        sheets = cls._parse_sheets(sch_el)

        return Schematic(
            file_path=str(path.resolve()),
            eagle_version=eagle_version,
            description=description,
            layers=layers,
            classes=classes,
            libraries=libraries,
            parts=parts,
            sheets=sheets,
            attributes=global_attrs,
        )

    @classmethod
    def _parse_parts(cls, sch_el: etree._Element) -> dict[str, Part]:
        parts: dict[str, Part] = {}
        parts_el = sch_el.find("parts")
        if parts_el is None:
            return parts
        for p in parts_el.findall("part"):
            name = p.get("name", "")
            parts[name] = Part(
                name=name,
                library=p.get("library", ""),
                deviceset=p.get("deviceset", ""),
                device=p.get("device", ""),
                technology=p.get("technology", ""),
                value=p.get("value"),
                attributes=cls.parse_attributes(p),
            )
        return parts

    @classmethod
    def _parse_sheets(cls, sch_el: etree._Element) -> list[Sheet]:
        sheets: list[Sheet] = []
        sheets_el = sch_el.find("sheets")
        if sheets_el is None:
            return sheets

        for idx, sh_el in enumerate(sheets_el.findall("sheet"), start=1):
            instances: list[PartInstance] = []
            insts_el = sh_el.find("instances")
            if insts_el is not None:
                for inst in insts_el.findall("instance"):
                    instances.append(
                        PartInstance(
                            part=inst.get("part", ""),
                            gate=inst.get("gate", ""),
                            sheet=idx,
                            x_mm=cls.parse_float(inst.get("x")),
                            y_mm=cls.parse_float(inst.get("y")),
                            rot=inst.get("rot", "R0"),
                            smashed=cls.parse_bool(inst.get("smashed"), default=False),
                        )
                    )

            nets: list[Net] = []
            nets_el = sh_el.find("nets")
            if nets_el is not None:
                for net_el in nets_el.findall("net"):
                    segments: list[NetSegment] = []
                    for seg_el in net_el.findall("segment"):
                        pinrefs = [
                            PinRef(
                                part=pr.get("part", ""),
                                gate=pr.get("gate", ""),
                                pin=pr.get("pin", ""),
                                sheet=idx,
                            )
                            for pr in seg_el.findall("pinref")
                        ]
                        segments.append(
                            NetSegment(
                                sheet=idx,
                                pinrefs=pinrefs,
                                has_label=bool(seg_el.findall("label")),
                                wire_count=len(seg_el.findall("wire")),
                                junction_count=len(seg_el.findall("junction")),
                            )
                        )
                    nets.append(
                        Net(
                            name=net_el.get("name", ""),
                            net_class=cls.parse_int(net_el.get("class"), default=0),
                            sheet=idx,
                            segments=segments,
                        )
                    )

            bus_names: list[str] = []
            busses_el = sh_el.find("busses")
            if busses_el is not None:
                bus_names = [b.get("name", "") for b in busses_el.findall("bus")]

            sheets.append(
                Sheet(
                    number=idx,
                    description=cls.parse_description(sh_el),
                    instances=instances,
                    nets=nets,
                    bus_names=bus_names,
                )
            )
        return sheets
