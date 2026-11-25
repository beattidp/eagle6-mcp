"""Cross-file consistency analyzer between EAGLE ``.sch`` and ``.brd`` files."""

from __future__ import annotations

from typing import Any

from eagle6_mcp.analyzers.schematic_analyzer import SchematicAnalyzer
from eagle6_mcp.models.board import Board
from eagle6_mcp.models.schematic import Schematic


class ConsistencyAnalyzer:
    """Checks forward/back-annotation consistency between schematic and board."""

    def __init__(self, schematic: Schematic, board: Board) -> None:
        self.schematic = schematic
        self.board = board
        self._sch_analyzer = SchematicAnalyzer(schematic)

    def check(self) -> dict[str, Any]:
        """Compare parts/elements, values/packages, and nets/signals.

        Package-less schematic parts (such as supply symbols and drawing frames)
        are intentionally excluded from the board element comparison.
        """
        # 1. Physical parts present on schematic vs elements on board
        sch_physical: dict[str, tuple[str, str]] = {}
        for name, part in self.schematic.parts.items():
            if self._sch_analyzer.is_supply_or_non_bom_part(part):
                continue
            _, dev = self._sch_analyzer.resolve_device(part)
            pkg = dev.package if dev and dev.package else ""
            val = self._sch_analyzer.effective_value(part)
            sch_physical[name] = (val, pkg)

        brd_elements = {
            name: (elem.value, elem.package)
            for name, elem in self.board.elements.items()
        }

        only_in_sch = sorted(set(sch_physical) - set(brd_elements))
        only_in_brd = sorted(set(brd_elements) - set(sch_physical))

        value_mismatches: list[dict[str, str]] = []
        package_mismatches: list[dict[str, str]] = []
        for name in sorted(set(sch_physical) & set(brd_elements)):
            s_val, s_pkg = sch_physical[name]
            b_val, b_pkg = brd_elements[name]
            if s_val != b_val:
                value_mismatches.append(
                    {"part": name, "schematic_value": s_val, "board_value": b_val}
                )
            if s_pkg and b_pkg and s_pkg != b_pkg:
                package_mismatches.append(
                    {"part": name, "schematic_package": s_pkg, "board_package": b_pkg}
                )

        # 2. Nets vs signals (only compare schematic nets that have at least one physical pin)
        agg_nets = self._sch_analyzer.aggregated_nets()
        sch_nets = {
            net_name
            for net_name, data in agg_nets.items()
            if any(pr.part in sch_physical for pr in data["pinrefs"])
        }
        brd_signals = set(self.board.signals.keys())

        nets_only_in_sch = sorted(sch_nets - brd_signals)
        signals_only_in_brd = sorted(brd_signals - sch_nets)

        consistent = not any(
            [
                only_in_sch,
                only_in_brd,
                value_mismatches,
                package_mismatches,
                nets_only_in_sch,
                signals_only_in_brd,
            ]
        )

        return {
            "consistent": consistent,
            "schematic_path": self.schematic.file_path,
            "board_path": self.board.file_path,
            "parts_only_in_schematic": only_in_sch,
            "elements_only_in_board": only_in_brd,
            "value_mismatches": value_mismatches,
            "package_mismatches": package_mismatches,
            "nets_only_in_schematic": nets_only_in_sch,
            "signals_only_in_board": signals_only_in_brd,
        }
