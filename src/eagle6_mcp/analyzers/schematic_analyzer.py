"""Engineering analysis and static electrical review for EAGLE v6 schematics."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from eagle6_mcp.models.library import Device, DeviceSet, Pin
from eagle6_mcp.models.schematic import Part, PinRef, Schematic


class SchematicAnalyzer:
    """Performs BOM extraction, netlist aggregation, and static schematic checks."""

    # Common power/ground net naming patterns for rail inventory & split-rail hints
    _POWER_NET_RE = re.compile(
        r"^(GND|AGND|DGND|PGND|VSS|AVSS|VEE|VCC|VDD|AVDD|DVDD|VBUS|VBAT|VIN|VOUT|"
        r"[+-]?\d+(?:\.\d+)?V\d*|3V3|5V|12V|24V|1V8|2V5)(?:[_-].*)?$",
        re.IGNORECASE,
    )

    def __init__(self, schematic: Schematic) -> None:
        self.schematic = schematic

    def resolve_device(self, part: Part) -> tuple[DeviceSet | None, Device | None]:
        """Look up a part's embedded library :class:`DeviceSet` and :class:`Device`."""
        lib = self.schematic.libraries.get(part.library)
        if lib is None:
            return None, None
        ds = lib.devicesets.get(part.deviceset)
        if ds is None:
            return None, None
        for dev in ds.devices:
            if dev.name == part.device:
                return ds, dev
        return ds, None

    def is_supply_or_non_bom_part(self, part: Part) -> bool:
        """Return True if a part has no physical PCB package (e.g., supply symbol, frame)."""
        _, dev = self.resolve_device(part)
        if dev is not None:
            return dev.package is None
        # Fallback heuristic when embedded library info is absent
        return part.library.lower().startswith("supply") or part.name.startswith("FRAME")

    def effective_value(self, part: Part) -> str:
        """Compute EAGLE's effective display value for a schematic part.

        EAGLE 6 value resolution rules when ``<part value=...>`` is omitted:
        - If ``uservalue="yes"`` on the deviceset, the default value is empty (``""``).
        - Otherwise, ``*`` in the deviceset name is replaced by ``part.technology``
          and ``?`` is replaced by ``part.device`` (or ``part.device`` is appended
          when no ``?`` placeholder is present).
        """
        if part.value is not None:
            return part.value
        ds, _ = self.resolve_device(part)
        if ds is not None and ds.uservalue:
            return ""
        val = part.deviceset
        tech = "" if part.technology in {"", "''"} else part.technology
        dev = "" if part.device in {"", "''"} else part.device
        if "*" in val:
            val = val.replace("*", tech)
        if "?" in val:
            val = val.replace("?", dev)
        elif dev:
            val = f"{val}{dev}"
        return val

    def build_bom(self, grouped: bool = True, include_non_bom: bool = False) -> list[dict[str, Any]]:
        """Build a Bill of Materials from schematic parts.

        Args:
            grouped: When True, collapse identical ``(value, deviceset, package, library)``
                rows with quantity and sorted reference designators.
            include_non_bom: When True, include package-less supply/frame symbols.
        """
        rows: list[dict[str, Any]] = []
        part_sheets: dict[str, set[int]] = defaultdict(set)
        for sh in self.schematic.sheets:
            for inst in sh.instances:
                part_sheets[inst.part].add(sh.number)

        for name in sorted(self.schematic.parts.keys()):
            part = self.schematic.parts[name]
            is_non_bom = self.is_supply_or_non_bom_part(part)
            if is_non_bom and not include_non_bom:
                continue
            _, dev = self.resolve_device(part)
            package = dev.package if dev else None
            rows.append(
                {
                    "part": part.name,
                    "value": self.effective_value(part),
                    "deviceset": part.deviceset,
                    "device": part.device,
                    "package": package or "",
                    "library": part.library,
                    "sheets": sorted(part_sheets.get(part.name, set())),
                    "attributes": dict(part.attributes),
                }
            )

        if not grouped:
            return rows

        groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            key = (row["value"], row["deviceset"], row["package"], row["library"])
            groups[key].append(row)

        grouped_bom: list[dict[str, Any]] = []
        for (value, deviceset, package, library), members in sorted(groups.items()):
            # Merge common attributes (e.g., MPN) when present
            merged_attrs: dict[str, str] = {}
            for m in members:
                for k, v in m["attributes"].items():
                    if k not in merged_attrs and v:
                        merged_attrs[k] = v
            grouped_bom.append(
                {
                    "quantity": len(members),
                    "parts": [m["part"] for m in members],
                    "value": value,
                    "deviceset": deviceset,
                    "package": package,
                    "library": library,
                    "attributes": merged_attrs,
                }
            )
        return grouped_bom

    def aggregated_nets(self) -> dict[str, dict[str, Any]]:
        """Aggregate net segments across all sheets into a unified netlist dict."""
        nets: dict[str, dict[str, Any]] = {}
        for sh in self.schematic.sheets:
            for net in sh.nets:
                entry = nets.setdefault(
                    net.name,
                    {
                        "name": net.name,
                        "net_class": net.net_class,
                        "sheets": set(),
                        "pinrefs": [],
                        "segment_count": 0,
                        "has_label": False,
                    },
                )
                entry["sheets"].add(sh.number)
                entry["segment_count"] += len(net.segments)
                for seg in net.segments:
                    if seg.has_label:
                        entry["has_label"] = True
                    entry["pinrefs"].extend(seg.pinrefs)
        return nets

    def build_netlist(
        self, net_filter: str | None = None, part_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Return filtered netlist with connected ``(part, gate, pin, sheet)`` endpoints."""
        nf = net_filter.lower().strip() if net_filter else None
        pf = part_filter.lower().strip() if part_filter else None

        result: list[dict[str, Any]] = []
        for name, data in sorted(self.aggregated_nets().items()):
            if nf and nf not in name.lower():
                continue
            pinrefs: list[PinRef] = data["pinrefs"]
            if pf and not any(pf in pr.part.lower() for pr in pinrefs):
                continue

            nc = self.schematic.classes.get(data["net_class"])
            result.append(
                {
                    "name": name,
                    "net_class": data["net_class"],
                    "net_class_name": nc.name if nc else "default",
                    "sheets": sorted(data["sheets"]),
                    "pin_count": len(pinrefs),
                    "pins": [
                        {
                            "part": pr.part,
                            "gate": pr.gate,
                            "pin": pr.pin,
                            "sheet": pr.sheet,
                        }
                        for pr in pinrefs
                    ],
                }
            )
        return result

    def inspect_part(self, part_name: str) -> dict[str, Any]:
        """Return detailed metadata and full pin-to-net map for a single part."""
        part = self.schematic.parts.get(part_name)
        if part is None:
            raise KeyError(f"Part '{part_name}' not found in schematic.")

        # Map (gate, pin) -> net_name from all sheets
        pin_to_net: dict[tuple[str, str], str] = {}
        for sh in self.schematic.sheets:
            for net in sh.nets:
                for seg in net.segments:
                    for pr in seg.pinrefs:
                        if pr.part == part_name:
                            pin_to_net[(pr.gate, pr.pin)] = net.name

        instances = [
            {
                "gate": inst.gate,
                "sheet": inst.sheet,
                "x_mm": inst.x_mm,
                "y_mm": inst.y_mm,
                "rot": inst.rot,
            }
            for sh in self.schematic.sheets
            for inst in sh.instances
            if inst.part == part_name
        ]

        ds, dev = self.resolve_device(part)
        lib = self.schematic.libraries.get(part.library)

        # Build connect lookup: (gate, pin) -> pad
        pin_to_pad: dict[tuple[str, str], str] = {}
        if dev is not None:
            for c in dev.connects:
                pin_to_pad[(c.gate, c.pin)] = c.pad

        pins_info: list[dict[str, Any]] = []
        if ds is not None and lib is not None:
            for gate in ds.gates:
                sym = lib.symbols.get(gate.symbol)
                if sym is None:
                    continue
                for pin in sym.pins:
                    pins_info.append(
                        {
                            "gate": gate.name,
                            "pin": pin.name,
                            "direction": pin.direction,
                            "pad": pin_to_pad.get((gate.name, pin.name), ""),
                            "net": pin_to_net.get((gate.name, pin.name)),
                        }
                    )
        else:
            # Fallback if library definition is missing
            for (gate_name, pin_name), net_name in sorted(pin_to_net.items()):
                pins_info.append(
                    {
                        "gate": gate_name,
                        "pin": pin_name,
                        "direction": "unknown",
                        "pad": "",
                        "net": net_name,
                    }
                )

        return {
            "name": part.name,
            "value": self.effective_value(part),
            "explicit_value": part.value,
            "library": part.library,
            "deviceset": part.deviceset,
            "device": part.device,
            "package": dev.package if dev else None,
            "technology": part.technology,
            "attributes": dict(part.attributes),
            "instances": instances,
            "pins": pins_info,
        }

    def review(self) -> dict[str, Any]:
        """Run static electrical and design-hygiene checks across the schematic."""
        agg_nets = self.aggregated_nets()

        # 1. Single-pin / dangling nets
        single_pin_nets: list[dict[str, Any]] = []
        zero_pin_nets: list[str] = []
        power_rails: list[dict[str, Any]] = []

        for name, data in sorted(agg_nets.items()):
            pinrefs: list[PinRef] = data["pinrefs"]
            if len(pinrefs) == 0:
                zero_pin_nets.append(name)
            elif len(pinrefs) == 1:
                pr = pinrefs[0]
                single_pin_nets.append(
                    {
                        "net": name,
                        "part": pr.part,
                        "gate": pr.gate,
                        "pin": pr.pin,
                        "sheet": pr.sheet,
                        "has_label": data["has_label"],
                    }
                )
            if self._POWER_NET_RE.match(name):
                power_rails.append(
                    {
                        "net": name,
                        "pin_count": len(pinrefs),
                        "sheets": sorted(data["sheets"]),
                    }
                )

        # 2. Connected pins lookup
        connected_pins: set[tuple[str, str, str]] = set()
        for data in agg_nets.values():
            for pr in data["pinrefs"]:
                connected_pins.add((pr.part, pr.gate, pr.pin))

        # 3. Unconnected pins on placed parts (excluding explicit direction="nc")
        unconnected_pins: list[dict[str, Any]] = []
        missing_values: list[dict[str, Any]] = []
        unannotated_parts: list[str] = []

        placed_gates: dict[str, set[str]] = defaultdict(set)
        for sh in self.schematic.sheets:
            for inst in sh.instances:
                placed_gates[inst.part].add(inst.gate)

        for name, part in sorted(self.schematic.parts.items()):
            if "?" in name:
                unannotated_parts.append(name)

            is_non_bom = self.is_supply_or_non_bom_part(part)
            ds, dev = self.resolve_device(part)
            if not is_non_bom and ds is not None and ds.uservalue and not part.value:
                missing_values.append(
                    {"part": name, "deviceset": part.deviceset, "library": part.library}
                )

            if is_non_bom or ds is None:
                continue

            lib = self.schematic.libraries.get(part.library)
            if lib is None:
                continue

            for gate in ds.gates:
                if gate.name not in placed_gates.get(name, set()):
                    continue
                sym = lib.symbols.get(gate.symbol)
                if sym is None:
                    continue
                # Only flag unconnected pins on multi-pin components (>2 pins) or power pins
                is_multi_pin = len(sym.pins) > 2
                for pin in sym.pins:
                    if pin.direction == "nc":
                        continue
                    if (name, gate.name, pin.name) not in connected_pins:
                        if is_multi_pin or pin.direction in {"pwr", "sup", "in"}:
                            unconnected_pins.append(
                                {
                                    "part": name,
                                    "gate": gate.name,
                                    "pin": pin.name,
                                    "direction": pin.direction,
                                }
                            )

        # 4. Detect potential split ground rails (e.g., GND + AGND + DGND)
        gnd_rails = [
            r["net"]
            for r in power_rails
            if "GND" in r["net"].upper() or "VSS" in r["net"].upper()
        ]

        return {
            "file_path": self.schematic.file_path,
            "sheet_count": len(self.schematic.sheets),
            "total_parts": len(self.schematic.parts),
            "bom_part_count": sum(
                1 for p in self.schematic.parts.values() if not self.is_supply_or_non_bom_part(p)
            ),
            "total_nets": len(agg_nets),
            "findings": {
                "single_pin_nets": single_pin_nets,
                "zero_pin_nets": zero_pin_nets,
                "unconnected_pins": unconnected_pins,
                "missing_values": missing_values,
                "unannotated_parts": unannotated_parts,
                "power_rails": power_rails,
                "multiple_ground_rails_detected": len(gnd_rails) > 1,
                "ground_rails": gnd_rails,
            },
        }
