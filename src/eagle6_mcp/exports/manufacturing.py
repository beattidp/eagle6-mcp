"""Manufacturing and documentation export utilities (BOM, Pick-and-Place, CAM presets)."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from eagle6_mcp.analyzers.board_analyzer import MM_PER_MIL
from eagle6_mcp.analyzers.schematic_analyzer import SchematicAnalyzer
from eagle6_mcp.models.board import Board
from eagle6_mcp.models.schematic import Schematic


# Standard EAGLE 6.6.0 CLI CAM layer definitions: (filename_suffix, device, layers)
CAM_PRESETS: dict[str, list[tuple[str, str, list[int]]]] = {
    "2layer_gerber": [
        (".GTL", "GERBER_RS274X", [1, 17, 18]),       # Top Copper
        (".GBL", "GERBER_RS274X", [16, 17, 18]),      # Bottom Copper
        (".GTS", "GERBER_RS274X", [29]),              # Top Soldermask
        (".GBS", "GERBER_RS274X", [30]),              # Bottom Soldermask
        (".GTO", "GERBER_RS274X", [20, 21, 25]),      # Top Silkscreen
        (".GBO", "GERBER_RS274X", [20, 22, 26]),      # Bottom Silkscreen
        (".GTP", "GERBER_RS274X", [31]),              # Top Solder Paste
        (".GBP", "GERBER_RS274X", [32]),              # Bottom Solder Paste
        (".GKO", "GERBER_RS274X", [20]),              # Board Outline / Dimension
        (".XLN", "EXCELLON", [44, 45]),               # Drills & Holes
    ],
    "4layer_gerber": [
        (".GTL", "GERBER_RS274X", [1, 17, 18]),
        (".GL2", "GERBER_RS274X", [2, 17, 18]),
        (".GL3", "GERBER_RS274X", [15, 17, 18]),
        (".GBL", "GERBER_RS274X", [16, 17, 18]),
        (".GTS", "GERBER_RS274X", [29]),
        (".GBS", "GERBER_RS274X", [30]),
        (".GTO", "GERBER_RS274X", [20, 21, 25]),
        (".GBO", "GERBER_RS274X", [20, 22, 26]),
        (".GTP", "GERBER_RS274X", [31]),
        (".GBP", "GERBER_RS274X", [32]),
        (".GKO", "GERBER_RS274X", [20]),
        (".XLN", "EXCELLON", [44, 45]),
    ],
}


class ManufacturingExporter:
    """Exports BOM (CSV/Markdown) and Pick-and-Place centroid tables from XML models."""

    @staticmethod
    def export_bom(
        schematic: Schematic,
        fmt: str = "csv",
        grouped: bool = True,
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Format schematic BOM as CSV or Markdown and optionally save to disk."""
        fmt_norm = fmt.lower().strip()
        if fmt_norm not in {"csv", "markdown"}:
            raise ValueError("`format` must be 'csv' or 'markdown'.")

        rows = SchematicAnalyzer(schematic).build_bom(grouped=grouped)
        content = (
            ManufacturingExporter._format_bom_csv(rows, grouped)
            if fmt_norm == "csv"
            else ManufacturingExporter._format_bom_markdown(rows, grouped)
        )

        saved_path: str | None = None
        if output_path:
            out = Path(output_path).expanduser().resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content, encoding="utf-8")
            saved_path = str(out)

        return {
            "format": fmt_norm,
            "grouped": grouped,
            "row_count": len(rows),
            "output_path": saved_path,
            "content": content,
        }

    @staticmethod
    def _format_bom_csv(rows: list[dict[str, Any]], grouped: bool) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        if grouped:
            writer.writerow(["Qty", "Designators", "Value", "Package", "DeviceSet", "Library", "MPN"])
            for r in rows:
                mpn = r["attributes"].get("MPN") or r["attributes"].get("MFR_PART") or ""
                writer.writerow(
                    [
                        r["quantity"],
                        " ".join(r["parts"]),
                        r["value"],
                        r["package"],
                        r["deviceset"],
                        r["library"],
                        mpn,
                    ]
                )
        else:
            writer.writerow(["Designator", "Value", "Package", "DeviceSet", "Library", "Sheets", "MPN"])
            for r in rows:
                mpn = r["attributes"].get("MPN") or r["attributes"].get("MFR_PART") or ""
                writer.writerow(
                    [
                        r["part"],
                        r["value"],
                        r["package"],
                        r["deviceset"],
                        r["library"],
                        ",".join(str(s) for s in r["sheets"]),
                        mpn,
                    ]
                )
        return buf.getvalue()

    @staticmethod
    def _format_bom_markdown(rows: list[dict[str, Any]], grouped: bool) -> str:
        if grouped:
            lines = [
                "| Qty | Designators | Value | Package | DeviceSet | Library |",
                "| ---: | :--- | :--- | :--- | :--- | :--- |",
            ]
            for r in rows:
                lines.append(
                    f"| {r['quantity']} | {', '.join(r['parts'])} | {r['value']} | "
                    f"{r['package']} | {r['deviceset']} | {r['library']} |"
                )
            return "\n".join(lines) + "\n"

        lines = [
            "| Designator | Value | Package | DeviceSet | Library |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for r in rows:
            lines.append(
                f"| {r['part']} | {r['value']} | {r['package']} | "
                f"{r['deviceset']} | {r['library']} |"
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def export_pick_and_place(
        board: Board,
        units: str = "mm",
        side: str = "all",
        smd_only: bool = False,
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Generate a standard Pick-and-Place centroid CSV from a parsed board."""
        units_norm = units.lower().strip()
        if units_norm not in {"mm", "mil"}:
            raise ValueError("`units` must be 'mm' or 'mil'.")
        side_norm = side.lower().strip()
        if side_norm not in {"all", "top", "bottom"}:
            raise ValueError("`side` must be 'all', 'top', or 'bottom'.")

        scale = 1.0 if units_norm == "mm" else (1.0 / MM_PER_MIL)
        rows: list[dict[str, Any]] = []

        for name in sorted(board.elements.keys()):
            elem = board.elements[name]
            if side_norm != "all" and elem.side != side_norm:
                continue

            lib = board.libraries.get(elem.library)
            pkg = lib.packages.get(elem.package) if lib else None
            mount = "SMD" if (pkg and pkg.is_smd) else ("THT" if (pkg and pkg.is_tht) else "OTHER")
            if smd_only and mount != "SMD":
                continue

            rows.append(
                {
                    "designator": elem.name,
                    "value": elem.value,
                    "package": elem.package,
                    "x": round(elem.x_mm * scale, 3),
                    "y": round(elem.y_mm * scale, 3),
                    "rotation": round(elem.angle_deg, 1),
                    "side": elem.side,
                    "mount": mount,
                }
            )

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "Designator",
                "Value",
                "Package",
                f"Mid X ({units_norm})",
                f"Mid Y ({units_norm})",
                "Rotation",
                "Side",
                "Mount",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r["designator"],
                    r["value"],
                    r["package"],
                    f"{r['x']:.3f}",
                    f"{r['y']:.3f}",
                    f"{r['rotation']:.1f}",
                    r["side"],
                    r["mount"],
                ]
            )
        csv_text = buf.getvalue()

        saved_path: str | None = None
        if output_path:
            out = Path(output_path).expanduser().resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(csv_text, encoding="utf-8")
            saved_path = str(out)

        return {
            "units": units_norm,
            "side": side_norm,
            "smd_only": smd_only,
            "component_count": len(rows),
            "output_path": saved_path,
            "content": csv_text,
        }
