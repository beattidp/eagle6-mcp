"""Parser for EAGLE v6 PCB board (``.brd``) XML files."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from eagle6_mcp.models.board import (
    Board,
    BoardElement,
    ContactRef,
    Polygon,
    PolygonVertex,
    Signal,
    Via,
    Wire,
)
from eagle6_mcp.parsers.base import BaseEagleParser
from eagle6_mcp.parsers.dru_parser import DruParser
from eagle6_mcp.parsers.library_parser import LibraryParser


class BoardParser(BaseEagleParser):
    """Parses CadSoft EAGLE v6 ``.brd`` files into :class:`Board` models."""

    @classmethod
    def parse_file(cls, brd_path: str | Path) -> Board:
        """Parse an EAGLE v6 ``.brd`` file."""
        path = Path(brd_path)
        root = cls.load_root(path)
        eagle_version = root.get("version", "unknown")

        drawing = root.find("drawing")
        if drawing is None:
            raise ValueError(f"Missing <drawing> element in {path}")
        brd_el = drawing.find("board")
        if brd_el is None:
            raise ValueError(f"Missing <board> element in {path}")

        layers = cls.parse_layers(drawing)
        classes = cls.parse_classes(brd_el)
        design_rules = DruParser.parse_xml_element(brd_el.find("designrules"))
        libraries = LibraryParser.parse_embedded_libraries(brd_el)
        description = cls.parse_description(brd_el)

        global_attrs: dict[str, str] = {}
        attrs_el = brd_el.find("attributes")
        if attrs_el is not None:
            global_attrs = cls.parse_attributes(attrs_el)

        plain_wires, plain_holes, plain_circles, plain_rects = cls._parse_plain(brd_el)
        elements = cls._parse_elements(brd_el)
        signals = cls._parse_signals(brd_el)

        return Board(
            file_path=str(path.resolve()),
            eagle_version=eagle_version,
            description=description,
            layers=layers,
            classes=classes,
            design_rules=design_rules,
            libraries=libraries,
            plain_wires=plain_wires,
            plain_holes=plain_holes,
            plain_circles=plain_circles,
            plain_rectangles=plain_rects,
            elements=elements,
            signals=signals,
            attributes=global_attrs,
        )

    @classmethod
    def _parse_wire(cls, w_el: etree._Element) -> Wire:
        return Wire(
            x1_mm=cls.parse_float(w_el.get("x1")),
            y1_mm=cls.parse_float(w_el.get("y1")),
            x2_mm=cls.parse_float(w_el.get("x2")),
            y2_mm=cls.parse_float(w_el.get("y2")),
            width_mm=cls.parse_float(w_el.get("width")),
            layer=cls.parse_int(w_el.get("layer")),
            extent=w_el.get("extent"),
            curve_deg=cls.parse_float(w_el.get("curve")),
            style=w_el.get("style", "continuous"),
        )

    @classmethod
    def _parse_polygon(cls, p_el: etree._Element) -> Polygon:
        vertices = [
            PolygonVertex(
                x_mm=cls.parse_float(v.get("x")),
                y_mm=cls.parse_float(v.get("y")),
                curve_deg=cls.parse_float(v.get("curve")),
            )
            for v in p_el.findall("vertex")
        ]
        iso_raw = p_el.get("isolate")
        return Polygon(
            layer=cls.parse_int(p_el.get("layer")),
            width_mm=cls.parse_float(p_el.get("width")),
            pour=p_el.get("pour", "solid"),
            isolate_mm=cls.parse_float(iso_raw) if iso_raw is not None else None,
            rank=cls.parse_int(p_el.get("rank")),
            thermals=cls.parse_bool(p_el.get("thermals"), default=True),
            orphans=cls.parse_bool(p_el.get("orphans"), default=False),
            vertices=vertices,
        )

    @classmethod
    def _parse_plain(
        cls, brd_el: etree._Element
    ) -> tuple[
        list[Wire],
        list[tuple[float, float, float]],
        list[tuple[float, float, float, int]],
        list[tuple[float, float, float, float, int]],
    ]:
        plain = brd_el.find("plain")
        if plain is None:
            return [], [], [], []
        wires = [cls._parse_wire(w) for w in plain.findall("wire")]
        holes = [
            (
                cls.parse_float(h.get("x")),
                cls.parse_float(h.get("y")),
                cls.parse_float(h.get("drill")),
            )
            for h in plain.findall("hole")
        ]
        circles = [
            (
                cls.parse_float(c.get("x")),
                cls.parse_float(c.get("y")),
                cls.parse_float(c.get("radius")),
                cls.parse_int(c.get("layer")),
            )
            for c in plain.findall("circle")
        ]
        rects = [
            (
                cls.parse_float(r.get("x1")),
                cls.parse_float(r.get("y1")),
                cls.parse_float(r.get("x2")),
                cls.parse_float(r.get("y2")),
                cls.parse_int(r.get("layer")),
            )
            for r in plain.findall("rectangle")
        ]
        return wires, holes, circles, rects

    @classmethod
    def _parse_elements(cls, brd_el: etree._Element) -> dict[str, BoardElement]:
        elements: dict[str, BoardElement] = {}
        elems_el = brd_el.find("elements")
        if elems_el is None:
            return elements
        for e in elems_el.findall("element"):
            name = e.get("name", "")
            elements[name] = BoardElement(
                name=name,
                library=e.get("library", ""),
                package=e.get("package", ""),
                value=e.get("value", ""),
                x_mm=cls.parse_float(e.get("x")),
                y_mm=cls.parse_float(e.get("y")),
                rot=e.get("rot", "R0"),
                locked=cls.parse_bool(e.get("locked"), default=False),
                smashed=cls.parse_bool(e.get("smashed"), default=False),
                attributes=cls.parse_attributes(e),
            )
        return elements

    @classmethod
    def _parse_signals(cls, brd_el: etree._Element) -> dict[str, Signal]:
        signals: dict[str, Signal] = {}
        sigs_el = brd_el.find("signals")
        if sigs_el is None:
            return signals
        for s in sigs_el.findall("signal"):
            name = s.get("name", "")
            contactrefs = [
                ContactRef(
                    element=cr.get("element", ""),
                    pad=cr.get("pad", ""),
                    route=cr.get("route", "all"),
                    routetag=cr.get("routetag", ""),
                )
                for cr in s.findall("contactref")
            ]
            wires = [cls._parse_wire(w) for w in s.findall("wire")]
            vias = [
                Via(
                    x_mm=cls.parse_float(v.get("x")),
                    y_mm=cls.parse_float(v.get("y")),
                    extent=v.get("extent", "1-16"),
                    drill_mm=cls.parse_float(v.get("drill")),
                    diameter_mm=cls.parse_float(v.get("diameter")),
                    shape=v.get("shape", "round"),
                )
                for v in s.findall("via")
            ]
            polygons = [cls._parse_polygon(p) for p in s.findall("polygon")]
            signals[name] = Signal(
                name=name,
                net_class=cls.parse_int(s.get("class"), default=0),
                airwires_hidden=cls.parse_bool(s.get("airwireshidden"), default=False),
                contactrefs=contactrefs,
                wires=wires,
                vias=vias,
                polygons=polygons,
            )
        return signals
