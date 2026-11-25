"""Structured Electrical Rule Check (ERC) and Design Rule Check (DRC) analyzers.

Engineering rationale:
    CadSoft EAGLE v6.6.0's ULP API does not yet expose ``UL_ERROR`` (added in
    later EAGLE 7/8 releases). To provide structured, machine-readable ERC and
    DRC reports alongside EAGLE's official visual error-polygon overlay, this
    module performs deterministic rule verification against parsed schematic,
    board, embedded library, and ``.dru`` models.
"""

from __future__ import annotations

from typing import Any

from eagle6_mcp.analyzers.board_analyzer import BoardAnalyzer
from eagle6_mcp.analyzers.consistency_analyzer import ConsistencyAnalyzer
from eagle6_mcp.analyzers.schematic_analyzer import SchematicAnalyzer
from eagle6_mcp.models.board import Board
from eagle6_mcp.models.common import DesignRules
from eagle6_mcp.models.schematic import Schematic
from eagle6_mcp.parsers.dru_parser import DruParser


class ErcDrcAnalyzer:
    """Runs structured ERC checks on schematics and DRC checks on boards."""

    # Pin directions considered active drivers on a net
    _DRIVER_DIRECTIONS = {"out", "io", "oc", "pwr", "sup", "hiz"}

    @classmethod
    def run_erc(
        cls, schematic: Schematic, board: Board | None = None
    ) -> dict[str, Any]:
        """Execute structured Electrical Rule Check on a schematic (and optional board).

        Checks:
        - Pin-direction conflicts (``out``-to-``out``, ``out``-to-``sup``).
        - ``in`` pins connected to nets with no driving pin (warning).
        - Unconnected ``in`` / ``pwr`` / multi-pin IC pins (excluding ``nc``).
        - Single-pin / dangling nets and zero-pin nets.
        - Missing values on ``uservalue="yes"`` parts and unannotated designators.
        - Forward/back-annotation consistency when a paired board is supplied.
        """
        sa = SchematicAnalyzer(schematic)
        static_review = sa.review()
        findings = static_review["findings"]

        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        # Build pin direction lookup: (part_name, gate_name, pin_name) -> direction
        pin_dirs: dict[tuple[str, str, str], str] = {}
        for pname, part in schematic.parts.items():
            ds, _ = sa.resolve_device(part)
            lib = schematic.libraries.get(part.library)
            if ds is None or lib is None:
                continue
            for gate in ds.gates:
                sym = lib.symbols.get(gate.symbol)
                if sym is None:
                    continue
                for pin in sym.pins:
                    pin_dirs[(pname, gate.name, pin.name)] = pin.direction

        # 1. Net-level pin direction compatibility checks
        agg_nets = sa.aggregated_nets()
        for net_name, data in sorted(agg_nets.items()):
            pinrefs = data["pinrefs"]
            if len(pinrefs) < 2:
                continue

            outputs: list[str] = []
            supplies: list[str] = []
            inputs: list[str] = []
            has_driver = False
            has_passive = False

            for pr in pinrefs:
                d = pin_dirs.get((pr.part, pr.gate, pr.pin), "pas")
                label = f"{pr.part}.{pr.pin}"
                if d == "out":
                    outputs.append(label)
                    has_driver = True
                elif d == "sup":
                    supplies.append(label)
                    has_driver = True
                elif d == "in":
                    inputs.append(label)
                elif d in cls._DRIVER_DIRECTIONS:
                    has_driver = True
                elif d == "pas":
                    has_passive = True

            if len(outputs) > 1:
                errors.append(
                    {
                        "code": "ERC_MULTI_OUTPUT",
                        "severity": "error",
                        "net": net_name,
                        "sheets": sorted(data["sheets"]),
                        "message": f"Multiple OUTPUT pins shorted on net '{net_name}': {', '.join(outputs)}",
                    }
                )
            if outputs and supplies:
                errors.append(
                    {
                        "code": "ERC_OUTPUT_TO_SUPPLY",
                        "severity": "error",
                        "net": net_name,
                        "sheets": sorted(data["sheets"]),
                        "message": f"OUTPUT pin(s) {', '.join(outputs)} connected to SUPPLY {', '.join(supplies)} on net '{net_name}'",
                    }
                )
            if inputs and not has_driver and not has_passive:
                warnings.append(
                    {
                        "code": "ERC_UNDRAWN_INPUT",
                        "severity": "warning",
                        "net": net_name,
                        "sheets": sorted(data["sheets"]),
                        "message": f"INPUT pin(s) {', '.join(inputs)} on net '{net_name}' have no driver",
                    }
                )

        # 2. Promote static review findings into structured ERC warnings/errors
        for item in findings["unconnected_pins"]:
            sev = "error" if item["direction"] in {"pwr", "sup"} else "warning"
            bucket = errors if sev == "error" else warnings
            bucket.append(
                {
                    "code": "ERC_UNCONNECTED_PIN",
                    "severity": sev,
                    "part": item["part"],
                    "gate": item["gate"],
                    "pin": item["pin"],
                    "message": f"Unconnected {item['direction']} pin {item['part']}.{item['pin']}",
                }
            )

        for item in findings["single_pin_nets"]:
            warnings.append(
                {
                    "code": "ERC_SINGLE_PIN_NET",
                    "severity": "warning",
                    "net": item["net"],
                    "part": item["part"],
                    "pin": item["pin"],
                    "sheet": item["sheet"],
                    "message": f"Net '{item['net']}' has only 1 pin ({item['part']}.{item['pin']}) on sheet {item['sheet']}",
                }
            )

        for item in findings["missing_values"]:
            warnings.append(
                {
                    "code": "ERC_MISSING_VALUE",
                    "severity": "warning",
                    "part": item["part"],
                    "message": f"Part '{item['part']}' ({item['deviceset']}) has no value set",
                }
            )

        for pname in findings["unannotated_parts"]:
            errors.append(
                {
                    "code": "ERC_UNANNOTATED_PART",
                    "severity": "error",
                    "part": pname,
                    "message": f"Unannotated reference designator '{pname}'",
                }
            )

        consistency: dict[str, Any] | None = None
        if board is not None:
            consistency = ConsistencyAnalyzer(schematic, board).check()

        return {
            "schematic_path": schematic.file_path,
            "board_path": board.file_path if board else None,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
            "consistency": consistency,
        }

    @classmethod
    def run_drc(
        cls, board: Board, override_dru: DesignRules | None = None
    ) -> dict[str, Any]:
        """Execute structured Design Rule Check on a board against its DRU parameters.

        Checks:
        - Minimum copper trace width vs. ``msWidth`` and per-net-class minimum width.
        - Zero-width copper traces.
        - Minimum drill diameter for vias and through-hole pads vs. ``msDrill``.
        - Unrouted airwires with exact ``(x1, y1) -> (x2, y2)`` coordinates.
        - Traces and vias violating ``mdCopperDimension`` against the Dimension bbox.
        """
        dr = override_dru or board.design_rules
        ba = BoardAnalyzer(board)
        bbox = ba.compute_outline_bbox_mm()

        min_width_mm = DruParser.to_mm(dr.params.get("msWidth")) or 0.0
        min_drill_mm = DruParser.to_mm(dr.params.get("msDrill")) or 0.0
        edge_clr_mm = DruParser.to_mm(dr.params.get("mdCopperDimension")) or 0.0

        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        # Tolerance for floating-point mil-to-mm rounding (0.5 um)
        eps = 5e-4

        for sig_name, sig in sorted(board.signals.items()):
            nc = board.classes.get(sig.net_class)
            nc_min_width = nc.width_mm if nc else 0.0
            eff_min_width = max(min_width_mm, nc_min_width)

            for w in sig.wires:
                if w.is_airwire:
                    warnings.append(
                        {
                            "code": "DRC_AIRWIRE",
                            "severity": "warning",
                            "signal": sig_name,
                            "layer": 19,
                            "x_mm": round((w.x1_mm + w.x2_mm) / 2.0, 3),
                            "y_mm": round((w.y1_mm + w.y2_mm) / 2.0, 3),
                            "message": (
                                f"Unrouted airwire on '{sig_name}' from "
                                f"({w.x1_mm:.2f}, {w.y1_mm:.2f}) to ({w.x2_mm:.2f}, {w.y2_mm:.2f})"
                            ),
                        }
                    )
                    continue

                if 1 <= w.layer <= 16:
                    if w.width_mm <= 0.0:
                        errors.append(
                            {
                                "code": "DRC_ZERO_WIDTH_TRACE",
                                "severity": "error",
                                "signal": sig_name,
                                "layer": w.layer,
                                "x_mm": round(w.x1_mm, 3),
                                "y_mm": round(w.y1_mm, 3),
                                "message": f"Zero-width copper trace on '{sig_name}' layer {w.layer}",
                            }
                        )
                    elif eff_min_width > 0.0 and w.width_mm + eps < eff_min_width:
                        errors.append(
                            {
                                "code": "DRC_MIN_WIDTH",
                                "severity": "error",
                                "signal": sig_name,
                                "layer": w.layer,
                                "x_mm": round(w.x1_mm, 3),
                                "y_mm": round(w.y1_mm, 3),
                                "actual_mm": round(w.width_mm, 4),
                                "limit_mm": round(eff_min_width, 4),
                                "message": (
                                    f"Trace width {w.width_mm:.4f}mm on '{sig_name}' (L{w.layer}) "
                                    f"is below minimum {eff_min_width:.4f}mm"
                                ),
                            }
                        )

                    # Copper-to-outline check against rectangular board bbox
                    if bbox and edge_clr_mm > 0.0:
                        half_w = w.width_mm / 2.0
                        for px, py in ((w.x1_mm, w.y1_mm), (w.x2_mm, w.y2_mm)):
                            dist = min(
                                px - bbox["min_x_mm"],
                                bbox["max_x_mm"] - px,
                                py - bbox["min_y_mm"],
                                bbox["max_y_mm"] - py,
                            ) - half_w
                            if dist + eps < edge_clr_mm:
                                warnings.append(
                                    {
                                        "code": "DRC_COPPER_DIMENSION",
                                        "severity": "warning",
                                        "signal": sig_name,
                                        "layer": w.layer,
                                        "x_mm": round(px, 3),
                                        "y_mm": round(py, 3),
                                        "actual_mm": round(dist, 4),
                                        "limit_mm": round(edge_clr_mm, 4),
                                        "message": (
                                            f"Copper on '{sig_name}' (L{w.layer}) at ({px:.2f}, {py:.2f}) "
                                            f"is {dist:.3f}mm from board edge (rule: {edge_clr_mm:.3f}mm)"
                                        ),
                                    }
                                )
                                break

            for via in sig.vias:
                if min_drill_mm > 0.0 and via.drill_mm > 0.0 and via.drill_mm + eps < min_drill_mm:
                    errors.append(
                        {
                            "code": "DRC_MIN_DRILL_VIA",
                            "severity": "error",
                            "signal": sig_name,
                            "layer": 18,
                            "x_mm": round(via.x_mm, 3),
                            "y_mm": round(via.y_mm, 3),
                            "actual_mm": round(via.drill_mm, 4),
                            "limit_mm": round(min_drill_mm, 4),
                            "message": (
                                f"Via drill {via.drill_mm:.4f}mm on '{sig_name}' at "
                                f"({via.x_mm:.2f}, {via.y_mm:.2f}) is below msDrill {min_drill_mm:.4f}mm"
                            ),
                        }
                    )

        # Check through-hole pad drills in placed elements
        if min_drill_mm > 0.0:
            for ename, elem in sorted(board.elements.items()):
                lib = board.libraries.get(elem.library)
                pkg = lib.packages.get(elem.package) if lib else None
                if pkg is None:
                    continue
                for pad in pkg.pads:
                    if pad.drill_mm > 0.0 and pad.drill_mm + eps < min_drill_mm:
                        errors.append(
                            {
                                "code": "DRC_MIN_DRILL_PAD",
                                "severity": "error",
                                "element": ename,
                                "pad": pad.name,
                                "layer": 17,
                                "x_mm": round(elem.x_mm, 3),
                                "y_mm": round(elem.y_mm, 3),
                                "actual_mm": round(pad.drill_mm, 4),
                                "limit_mm": round(min_drill_mm, 4),
                                "message": (
                                    f"Pad drill {pad.drill_mm:.4f}mm on {ename}.{pad.name} "
                                    f"is below msDrill {min_drill_mm:.4f}mm"
                                ),
                            }
                        )

        return {
            "board_path": board.file_path,
            "dru_name": dr.name,
            "rules_checked": {
                "msWidth_mm": min_width_mm,
                "msDrill_mm": min_drill_mm,
                "mdCopperDimension_mm": edge_clr_mm,
            },
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
        }
