"""Inspection and auditing utilities for EAGLE v6 libraries."""

from __future__ import annotations

from typing import Any

from eagle6_mcp.models.library import Library


class LibraryAnalyzer:
    """Summarizes library contents and inspects individual devicesets/footprints."""

    def __init__(self, library: Library) -> None:
        self.library = library

    def summarize(self, query: str | None = None) -> dict[str, Any]:
        """List devicesets, packages, and symbols in the library with optional filter."""
        q = query.lower().strip() if query else None

        devicesets = [
            {
                "name": ds.name,
                "prefix": ds.prefix,
                "uservalue": ds.uservalue,
                "gate_count": len(ds.gates),
                "device_variants": [
                    {"device": d.name, "package": d.package} for d in ds.devices
                ],
                "description": ds.description[:200],
            }
            for ds in sorted(self.library.devicesets.values(), key=lambda x: x.name)
            if not q or q in ds.name.lower() or q in ds.description.lower()
        ]

        packages = [
            {
                "name": pkg.name,
                "pad_count": len(pkg.pads),
                "smd_count": len(pkg.smds),
                "hole_count": len(pkg.holes),
                "type": "smd" if pkg.is_smd else ("tht" if pkg.is_tht else "mechanical"),
            }
            for pkg in sorted(self.library.packages.values(), key=lambda x: x.name)
            if not q or q in pkg.name.lower()
        ]

        symbols = [
            {"name": sym.name, "pin_count": len(sym.pins)}
            for sym in sorted(self.library.symbols.values(), key=lambda x: x.name)
            if not q or q in sym.name.lower()
        ]

        return {
            "library": self.library.name,
            "description": self.library.description,
            "counts": {
                "devicesets": len(devicesets),
                "packages": len(packages),
                "symbols": len(symbols),
            },
            "devicesets": devicesets,
            "packages": packages,
            "symbols": symbols,
        }

    def inspect_deviceset(self, deviceset_name: str) -> dict[str, Any]:
        """Return detailed pinout, pad/SMD geometry, and connect table for a deviceset."""
        ds = self.library.devicesets.get(deviceset_name)
        if ds is None:
            raise KeyError(
                f"Deviceset '{deviceset_name}' not found in library '{self.library.name}'."
            )

        gates_info: list[dict[str, Any]] = []
        for gate in ds.gates:
            sym = self.library.symbols.get(gate.symbol)
            gates_info.append(
                {
                    "gate": gate.name,
                    "symbol": gate.symbol,
                    "addlevel": gate.addlevel,
                    "pins": [
                        {
                            "name": p.name,
                            "direction": p.direction,
                            "function": p.function,
                            "x_mm": p.x_mm,
                            "y_mm": p.y_mm,
                        }
                        for p in (sym.pins if sym else [])
                    ],
                }
            )

        devices_info: list[dict[str, Any]] = []
        for dev in ds.devices:
            pkg = self.library.packages.get(dev.package) if dev.package else None
            pkg_summary: dict[str, Any] | None = None
            if pkg is not None:
                pkg_summary = {
                    "name": pkg.name,
                    "pads": [
                        {
                            "name": p.name,
                            "x_mm": p.x_mm,
                            "y_mm": p.y_mm,
                            "drill_mm": p.drill_mm,
                            "diameter_mm": p.diameter_mm,
                            "shape": p.shape,
                        }
                        for p in pkg.pads
                    ],
                    "smds": [
                        {
                            "name": s.name,
                            "x_mm": s.x_mm,
                            "y_mm": s.y_mm,
                            "dx_mm": s.dx_mm,
                            "dy_mm": s.dy_mm,
                            "layer": s.layer,
                        }
                        for s in pkg.smds
                    ],
                    "holes": [
                        {"x_mm": h.x_mm, "y_mm": h.y_mm, "drill_mm": h.drill_mm}
                        for h in pkg.holes
                    ],
                }
            devices_info.append(
                {
                    "device": dev.name,
                    "package": dev.package,
                    "package_details": pkg_summary,
                    "connects": [
                        {
                            "gate": c.gate,
                            "pin": c.pin,
                            "pad": c.pad,
                            "route": c.route,
                        }
                        for c in dev.connects
                    ],
                    "technologies": dev.technologies,
                }
            )

        return {
            "library": self.library.name,
            "deviceset": ds.name,
            "prefix": ds.prefix,
            "uservalue": ds.uservalue,
            "description": ds.description,
            "gates": gates_info,
            "devices": devices_info,
        }
