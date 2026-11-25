"""Engineering analysis for EAGLE v6 PCB board (``.brd``) files."""

from __future__ import annotations

from typing import Any

from eagle6_mcp.models.board import Board
from eagle6_mcp.parsers.dru_parser import DruParser

MM_PER_MIL = 0.0254
COPPER_LAYER_MIN = 1
COPPER_LAYER_MAX = 16
DIMENSION_LAYER = 20


class BoardAnalyzer:
    """Computes board dimensions, placement tables, routing status, and DRU summaries."""

    def __init__(self, board: Board) -> None:
        self.board = board

    def compute_outline_bbox_mm(self) -> dict[str, float] | None:
        """Compute board bounding box from Dimension layer (layer 20) geometry."""
        xs: list[float] = []
        ys: list[float] = []

        for w in self.board.plain_wires:
            if w.layer == DIMENSION_LAYER:
                xs.extend([w.x1_mm, w.x2_mm])
                ys.extend([w.y1_mm, w.y2_mm])

        for cx, cy, r, layer in self.board.plain_circles:
            if layer == DIMENSION_LAYER:
                xs.extend([cx - r, cx + r])
                ys.extend([cy - r, cy + r])

        for x1, y1, x2, y2, layer in self.board.plain_rectangles:
            if layer == DIMENSION_LAYER:
                xs.extend([x1, x2])
                ys.extend([y1, y2])

        if not xs or not ys:
            return None

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        width_mm = round(max_x - min_x, 3)
        height_mm = round(max_y - min_y, 3)
        return {
            "min_x_mm": round(min_x, 3),
            "min_y_mm": round(min_y, 3),
            "max_x_mm": round(max_x, 3),
            "max_y_mm": round(max_y, 3),
            "width_mm": width_mm,
            "height_mm": height_mm,
            "width_mil": round(width_mm / MM_PER_MIL, 1),
            "height_mil": round(height_mm / MM_PER_MIL, 1),
        }

    def summarize(self) -> dict[str, Any]:
        """Produce a high-level physical and routing summary of the board."""
        used_copper_layers: set[int] = set()
        total_airwires = 0
        total_routed_wires = 0
        total_vias = 0
        total_polygons = 0
        trace_widths: list[float] = []
        drill_sizes: list[float] = []

        for sig in self.board.signals.values():
            total_vias += len(sig.vias)
            total_polygons += len(sig.polygons)
            for via in sig.vias:
                if via.drill_mm > 0:
                    drill_sizes.append(via.drill_mm)
            for poly in sig.polygons:
                if COPPER_LAYER_MIN <= poly.layer <= COPPER_LAYER_MAX:
                    used_copper_layers.add(poly.layer)
            for w in sig.wires:
                if w.is_airwire:
                    total_airwires += 1
                else:
                    total_routed_wires += 1
                    if w.width_mm > 0:
                        trace_widths.append(w.width_mm)
                    if COPPER_LAYER_MIN <= w.layer <= COPPER_LAYER_MAX:
                        used_copper_layers.add(w.layer)

        top_count = 0
        bottom_count = 0
        smd_count = 0
        tht_count = 0

        for elem in self.board.elements.values():
            if elem.is_bottom:
                bottom_count += 1
            else:
                top_count += 1
            lib = self.board.libraries.get(elem.library)
            pkg = lib.packages.get(elem.package) if lib else None
            if pkg is not None:
                if pkg.is_smd:
                    smd_count += 1
                elif pkg.is_tht:
                    tht_count += 1
                for pad in pkg.pads:
                    if pad.drill_mm > 0:
                        drill_sizes.append(pad.drill_mm)

        for _, _, hole_drill in self.board.plain_holes:
            if hole_drill > 0:
                drill_sizes.append(hole_drill)

        total_signals = len(self.board.signals)
        unrouted_signals = sum(
            1
            for sig in self.board.signals.values()
            if any(w.is_airwire for w in sig.wires)
        )
        routed_signals = total_signals - unrouted_signals
        routing_pct = (
            round(100.0 * routed_signals / total_signals, 1) if total_signals else 100.0
        )

        return {
            "file_path": self.board.file_path,
            "eagle_version": self.board.eagle_version,
            "outline": self.compute_outline_bbox_mm(),
            "layer_setup": self.board.design_rules.params.get("layerSetup", ""),
            "used_copper_layers": sorted(used_copper_layers),
            "components": {
                "total": len(self.board.elements),
                "top": top_count,
                "bottom": bottom_count,
                "smd_only": smd_count,
                "through_hole": tht_count,
            },
            "routing": {
                "total_signals": total_signals,
                "fully_routed_signals": routed_signals,
                "signals_with_airwires": unrouted_signals,
                "signal_completion_pct": routing_pct,
                "total_airwires": total_airwires,
                "total_routed_segments": total_routed_wires,
                "total_vias": total_vias,
                "total_copper_polygons": total_polygons,
                "min_trace_width_mm": round(min(trace_widths), 4) if trace_widths else None,
                "min_drill_mm": round(min(drill_sizes), 4) if drill_sizes else None,
            },
        }

    def get_placement(
        self, part_filter: str | None = None, side: str = "all"
    ) -> list[dict[str, Any]]:
        """Return component placement coordinates, rotation, side, and package."""
        pf = part_filter.lower().strip() if part_filter else None
        side_norm = side.lower().strip()
        rows: list[dict[str, Any]] = []

        for name in sorted(self.board.elements.keys()):
            elem = self.board.elements[name]
            if pf and pf not in name.lower() and pf not in elem.value.lower():
                continue
            if side_norm in {"top", "bottom"} and elem.side != side_norm:
                continue
            rows.append(
                {
                    "name": elem.name,
                    "value": elem.value,
                    "package": elem.package,
                    "library": elem.library,
                    "x_mm": round(elem.x_mm, 3),
                    "y_mm": round(elem.y_mm, 3),
                    "rot": elem.rot,
                    "angle_deg": elem.angle_deg,
                    "side": elem.side,
                    "locked": elem.locked,
                }
            )
        return rows

    def get_routing_status(
        self, unrouted_only: bool = False, signal_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Return per-signal routing metrics, trace widths, and unrouted airwires."""
        sf = signal_filter.lower().strip() if signal_filter else None
        rows: list[dict[str, Any]] = []

        for name in sorted(self.board.signals.keys()):
            if sf and sf not in name.lower():
                continue
            sig = self.board.signals[name]
            airwires = [w for w in sig.wires if w.is_airwire]
            routed = [w for w in sig.wires if not w.is_airwire]

            if unrouted_only and not airwires:
                continue

            routed_length_mm = round(sum(w.length_mm for w in routed), 3)
            layers_used = sorted(
                {w.layer for w in routed} | {p.layer for p in sig.polygons}
            )
            widths = sorted({round(w.width_mm, 4) for w in routed if w.width_mm > 0})
            nc = self.board.classes.get(sig.net_class)

            rows.append(
                {
                    "signal": sig.name,
                    "net_class": sig.net_class,
                    "net_class_name": nc.name if nc else "default",
                    "net_class_min_width_mm": nc.width_mm if nc else 0.0,
                    "contact_count": len(sig.contactrefs),
                    "routed_segment_count": len(routed),
                    "routed_length_mm": routed_length_mm,
                    "layers_used": layers_used,
                    "trace_widths_mm": widths,
                    "via_count": len(sig.vias),
                    "polygon_count": len(sig.polygons),
                    "airwire_count": len(airwires),
                    "airwires": [
                        {
                            "x1_mm": round(aw.x1_mm, 3),
                            "y1_mm": round(aw.y1_mm, 3),
                            "x2_mm": round(aw.x2_mm, 3),
                            "y2_mm": round(aw.y2_mm, 3),
                            "extent": aw.extent,
                        }
                        for aw in airwires
                    ],
                }
            )
        return rows

    def summarize_design_rules(self) -> dict[str, Any]:
        """Return key manufacturing design rule constraints in raw and mm units."""
        dr = self.board.design_rules
        key_fields = [
            "layerSetup",
            "mdWireWire",
            "mdWirePad",
            "mdWireVia",
            "mdPadPad",
            "mdPadVia",
            "mdViaVia",
            "mdSmdPad",
            "mdSmdVia",
            "mdSmdSmd",
            "mdCopperDimension",
            "mdDrill",
            "msWidth",
            "msDrill",
            "msMicroVia",
            "rlMinPadTop",
            "rlMinViaOuter",
            "mlMinStopFrame",
        ]
        highlights: dict[str, Any] = {}
        for k in key_fields:
            if k in dr.params:
                raw = dr.params[k]
                mm = DruParser.to_mm(raw)
                highlights[k] = {"raw": raw, "mm": mm} if mm is not None else raw

        return {
            "name": dr.name,
            "description": dr.description,
            "highlights": highlights,
            "all_params": dict(dr.params),
        }
