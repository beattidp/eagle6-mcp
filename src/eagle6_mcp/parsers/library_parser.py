"""Parser for EAGLE v6 library files (``.lbr``) and embedded ``<libraries>``."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from eagle6_mcp.models.library import (
    Connect,
    Device,
    DeviceSet,
    Gate,
    Hole,
    Library,
    Package,
    Pad,
    Pin,
    Smd,
    Symbol,
)
from eagle6_mcp.parsers.base import BaseEagleParser


class LibraryParser(BaseEagleParser):
    """Parses standalone ``.lbr`` files and embedded ``<library>`` elements."""

    @classmethod
    def parse_file(cls, lbr_path: str | Path) -> Library:
        """Parse a standalone EAGLE v6 ``.lbr`` XML file."""
        path = Path(lbr_path)
        root = cls.load_root(path)
        drawing = root.find("drawing")
        if drawing is None:
            raise ValueError(f"Missing <drawing> element in {path}")
        lib_el = drawing.find("library")
        if lib_el is None:
            raise ValueError(f"Missing <library> element in {path}")
        return cls.parse_library_element(lib_el, fallback_name=path.stem)

    @classmethod
    def parse_embedded_libraries(cls, parent_el: etree._Element) -> dict[str, Library]:
        """Parse ``<libraries><library .../></libraries>`` inside a ``.sch`` or ``.brd``."""
        result: dict[str, Library] = {}
        libs_el = parent_el.find("libraries")
        if libs_el is None:
            return result
        for lib_el in libs_el.findall("library"):
            lib = cls.parse_library_element(lib_el)
            result[lib.name] = lib
        return result

    @classmethod
    def parse_library_element(
        cls, lib_el: etree._Element, fallback_name: str = ""
    ) -> Library:
        """Parse a single ``<library>`` XML element into a :class:`Library`."""
        name = lib_el.get("name") or fallback_name
        description = cls.parse_description(lib_el)

        symbols: dict[str, Symbol] = {}
        symbols_el = lib_el.find("symbols")
        if symbols_el is not None:
            for sym_el in symbols_el.findall("symbol"):
                sym = cls._parse_symbol(sym_el)
                symbols[sym.name] = sym

        packages: dict[str, Package] = {}
        packages_el = lib_el.find("packages")
        if packages_el is not None:
            for pkg_el in packages_el.findall("package"):
                pkg = cls._parse_package(pkg_el)
                packages[pkg.name] = pkg

        devicesets: dict[str, DeviceSet] = {}
        ds_parent = lib_el.find("devicesets")
        if ds_parent is not None:
            for ds_el in ds_parent.findall("deviceset"):
                ds = cls._parse_deviceset(ds_el)
                devicesets[ds.name] = ds

        return Library(
            name=name,
            description=description,
            symbols=symbols,
            packages=packages,
            devicesets=devicesets,
        )

    @classmethod
    def _parse_symbol(cls, sym_el: etree._Element) -> Symbol:
        pins = [
            Pin(
                name=p.get("name", ""),
                x_mm=cls.parse_float(p.get("x")),
                y_mm=cls.parse_float(p.get("y")),
                direction=p.get("direction", "io"),
                function=p.get("function", "none"),
                length=p.get("length", "long"),
                visible=p.get("visible", "both"),
                rot=p.get("rot", "R0"),
                swaplevel=cls.parse_int(p.get("swaplevel")),
            )
            for p in sym_el.findall("pin")
        ]
        return Symbol(
            name=sym_el.get("name", ""),
            description=cls.parse_description(sym_el),
            pins=pins,
        )

    @classmethod
    def _parse_package(cls, pkg_el: etree._Element) -> Package:
        pads = [
            Pad(
                name=p.get("name", ""),
                x_mm=cls.parse_float(p.get("x")),
                y_mm=cls.parse_float(p.get("y")),
                drill_mm=cls.parse_float(p.get("drill")),
                diameter_mm=cls.parse_float(p.get("diameter")),
                shape=p.get("shape", "round"),
                rot=p.get("rot", "R0"),
                stop=cls.parse_bool(p.get("stop"), default=True),
                thermals=cls.parse_bool(p.get("thermals"), default=True),
            )
            for p in pkg_el.findall("pad")
        ]
        smds = [
            Smd(
                name=s.get("name", ""),
                x_mm=cls.parse_float(s.get("x")),
                y_mm=cls.parse_float(s.get("y")),
                dx_mm=cls.parse_float(s.get("dx")),
                dy_mm=cls.parse_float(s.get("dy")),
                layer=cls.parse_int(s.get("layer"), default=1),
                roundness=cls.parse_int(s.get("roundness")),
                rot=s.get("rot", "R0"),
                stop=cls.parse_bool(s.get("stop"), default=True),
                cream=cls.parse_bool(s.get("cream"), default=True),
                thermals=cls.parse_bool(s.get("thermals"), default=True),
            )
            for s in pkg_el.findall("smd")
        ]
        holes = [
            Hole(
                x_mm=cls.parse_float(h.get("x")),
                y_mm=cls.parse_float(h.get("y")),
                drill_mm=cls.parse_float(h.get("drill")),
            )
            for h in pkg_el.findall("hole")
        ]
        return Package(
            name=pkg_el.get("name", ""),
            description=cls.parse_description(pkg_el),
            pads=pads,
            smds=smds,
            holes=holes,
        )

    @classmethod
    def _parse_deviceset(cls, ds_el: etree._Element) -> DeviceSet:
        gates: list[Gate] = []
        gates_el = ds_el.find("gates")
        if gates_el is not None:
            for g in gates_el.findall("gate"):
                gates.append(
                    Gate(
                        name=g.get("name", ""),
                        symbol=g.get("symbol", ""),
                        x_mm=cls.parse_float(g.get("x")),
                        y_mm=cls.parse_float(g.get("y")),
                        addlevel=g.get("addlevel", "next"),
                        swaplevel=cls.parse_int(g.get("swaplevel")),
                    )
                )

        devices: list[Device] = []
        devices_el = ds_el.find("devices")
        if devices_el is not None:
            for d in devices_el.findall("device"):
                connects: list[Connect] = []
                connects_el = d.find("connects")
                if connects_el is not None:
                    for c in connects_el.findall("connect"):
                        connects.append(
                            Connect(
                                gate=c.get("gate", ""),
                                pin=c.get("pin", ""),
                                pad=c.get("pad", ""),
                                route=c.get("route", "all"),
                            )
                        )
                technologies: dict[str, dict[str, str]] = {}
                techs_el = d.find("technologies")
                if techs_el is not None:
                    for t in techs_el.findall("technology"):
                        tname = t.get("name", "")
                        technologies[tname] = cls.parse_attributes(t)

                devices.append(
                    Device(
                        name=d.get("name", ""),
                        package=d.get("package"),
                        connects=connects,
                        technologies=technologies,
                    )
                )

        return DeviceSet(
            name=ds_el.get("name", ""),
            prefix=ds_el.get("prefix", ""),
            uservalue=cls.parse_bool(ds_el.get("uservalue"), default=False),
            description=cls.parse_description(ds_el),
            gates=gates,
            devices=devices,
        )
