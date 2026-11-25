"""Safe EAGLE v6 script (``.scr``) generator with pre-flight validation.

Generates human-readable, commented CadSoft EAGLE command scripts from
structured edit intents so design modifications always execute through EAGLE
itself (preserving forward/back-annotation and full GUI Undo support).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eagle6_mcp.parsers import BoardParser, SchematicParser


def _quote(text: str) -> str:
    """Safely single-quote a string argument for EAGLE script syntax."""
    escaped = str(text).replace("'", "''")
    return f"'{escaped}'"


class ScriptBuilder:
    """Builds and pre-flight validates EAGLE ``.scr`` edit scripts."""

    SUPPORTED_OPS = {
        "set_value",
        "rename_part",
        "set_attribute",
        "delete_attribute",
        "add_part",
        "move_part",
        "rotate_part",
        "mirror_part",
        "smash_part",
        "set_net_class",
        "change_width",
        "raw_command",
    }

    @classmethod
    def generate(
        cls,
        target: str,
        operations: list[dict[str, Any]],
        project_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Generate a commented ``.scr`` script from typed edit operations.

        Args:
            target: ``"sch"`` (schematic) or ``"brd"`` (board).
            operations: List of dicts, each containing ``"op"`` plus op-specific keys.
            project_path: Optional ``.sch`` or ``.brd`` path for pre-flight checks.
        """
        target_norm = target.lower().strip()
        if target_norm not in {"sch", "brd"}:
            raise ValueError("`target` must be 'sch' or 'brd'.")

        existing_parts: set[str] | None = None
        if project_path:
            p = Path(project_path).expanduser()
            if p.is_file():
                if p.suffix.lower() == ".sch":
                    existing_parts = set(SchematicParser.parse_file(p).parts.keys())
                elif p.suffix.lower() == ".brd":
                    existing_parts = set(BoardParser.parse_file(p).elements.keys())

        lines: list[str] = [
            f"# Auto-generated EAGLE v6 edit script (target: {target_norm.upper()})",
            "# Review carefully, then execute in EAGLE via: SCRIPT <filename>.scr",
            "GRID MM;",
            "",
        ]
        preflight_warnings: list[str] = []

        for idx, spec in enumerate(operations, start=1):
            op = str(spec.get("op", "")).strip().lower()
            if op not in cls.SUPPORTED_OPS:
                valid = ", ".join(sorted(cls.SUPPORTED_OPS))
                raise ValueError(
                    f"Operation #{idx} has unsupported op '{op}'. Valid ops: {valid}"
                )

            comment = spec.get("comment")
            if comment:
                lines.append(f"# {comment}")

            if op == "set_value":
                part = str(spec["part"])
                value = str(spec["value"])
                cls._check_part_exists(part, existing_parts, preflight_warnings)
                lines.append(f"VALUE {part} {_quote(value)};")

            elif op == "rename_part":
                old_name = str(spec["old_name"])
                new_name = str(spec["new_name"])
                cls._check_part_exists(old_name, existing_parts, preflight_warnings)
                if existing_parts is not None and new_name in existing_parts:
                    preflight_warnings.append(
                        f"Rename target '{new_name}' already exists in design."
                    )
                lines.append(f"NAME {old_name} {new_name};")

            elif op == "set_attribute":
                part = str(spec["part"])
                attr_name = str(spec["name"])
                attr_value = str(spec["value"])
                cls._check_part_exists(part, existing_parts, preflight_warnings)
                lines.append(f"ATTRIBUTE {part} {attr_name} {_quote(attr_value)};")

            elif op == "delete_attribute":
                part = str(spec["part"])
                attr_name = str(spec["name"])
                cls._check_part_exists(part, existing_parts, preflight_warnings)
                lines.append(f"ATTRIBUTE {part} {attr_name} DELETE;")

            elif op == "add_part":
                device = str(spec["device"])
                library = str(spec["library"])
                x_mm = float(spec["x_mm"])
                y_mm = float(spec["y_mm"])
                rot = str(spec.get("rot", "R0"))
                name = spec.get("name")
                if name:
                    lines.append(
                        f"ADD {_quote(f'{device}@{library}')} {name} {rot} ({x_mm:.3f} {y_mm:.3f});"
                    )
                else:
                    lines.append(
                        f"ADD {_quote(f'{device}@{library}')} {rot} ({x_mm:.3f} {y_mm:.3f});"
                    )

            elif op == "move_part":
                part = str(spec["part"])
                x_mm = float(spec["x_mm"])
                y_mm = float(spec["y_mm"])
                cls._check_part_exists(part, existing_parts, preflight_warnings)
                lines.append(f"MOVE {part} ({x_mm:.3f} {y_mm:.3f});")

            elif op == "rotate_part":
                part = str(spec["part"])
                rot = str(spec["rot"])
                cls._check_part_exists(part, existing_parts, preflight_warnings)
                lines.append(f"ROTATE ={rot} {part};")

            elif op == "mirror_part":
                part = str(spec["part"])
                cls._check_part_exists(part, existing_parts, preflight_warnings)
                lines.append(f"MIRROR {part};")

            elif op == "smash_part":
                part = str(spec["part"])
                cls._check_part_exists(part, existing_parts, preflight_warnings)
                lines.append(f"SMASH {part};")

            elif op == "set_net_class":
                num = int(spec["number"])
                name = str(spec["name"])
                width_mm = float(spec["width_mm"])
                clearance_mm = float(spec.get("clearance_mm", 0.0))
                drill_mm = float(spec.get("drill_mm", 0.0))
                lines.append(
                    f"CLASS {num} {name} {width_mm:.4f} {clearance_mm:.4f} {drill_mm:.4f};"
                )

            elif op == "change_width":
                width_mm = float(spec["width_mm"])
                x_mm = float(spec["x_mm"])
                y_mm = float(spec["y_mm"])
                lines.append(f"CHANGE WIDTH {width_mm:.4f} ({x_mm:.3f} {y_mm:.3f});")

            elif op == "raw_command":
                cmd = str(spec["command"]).strip()
                if not cmd.endswith(";"):
                    cmd += ";"
                lines.append(cmd)

        lines.append("")
        return {
            "target": target_norm,
            "operation_count": len(operations),
            "preflight_warnings": preflight_warnings,
            "script": "\n".join(lines),
        }

    @staticmethod
    def _check_part_exists(
        part: str, existing_parts: set[str] | None, warnings: list[str]
    ) -> None:
        if existing_parts is not None and part not in existing_parts:
            warnings.append(f"Part '{part}' was not found in the target design file.")
