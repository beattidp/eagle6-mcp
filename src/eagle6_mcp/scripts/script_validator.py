"""Staged dry-run validation and safe persistence for EAGLE ``.scr`` edit scripts."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from eagle6_mcp.analyzers.consistency_analyzer import ConsistencyAnalyzer
from eagle6_mcp.analyzers.erc_drc_analyzer import ErcDrcAnalyzer
from eagle6_mcp.analyzers.schematic_analyzer import SchematicAnalyzer
from eagle6_mcp.config import EagleConfig
from eagle6_mcp.parsers import BoardParser, SchematicParser
from eagle6_mcp.runner import EagleRunner


class ScriptValidator:
    """Dry-runs ``.scr`` scripts on isolated staged copies and computes before/after diffs."""

    def __init__(self, config: EagleConfig, runner: EagleRunner | None = None) -> None:
        self.config = config
        self.runner = runner or EagleRunner(config)

    def validate(
        self,
        project_path: str | Path,
        script_content: str,
        run_checks: bool = True,
        keep_staged: bool = False,
    ) -> dict[str, Any]:
        """Execute ``script_content`` against a staged copy of ``project_path``.

        If a sibling ``.brd``/``.sch`` exists in the same folder, both are staged
        so EAGLE's forward/back-annotation executes exactly as it would in the
        user's GUI. Original user files are never modified.

        Args:
            project_path: Path to the target ``.sch`` or ``.brd`` file.
            script_content: EAGLE ``.scr`` commands to execute on the staged copy.
            run_checks: When ``True``, compute sch/brd consistency and ERC/DRC deltas.
            keep_staged: When ``True``, preserve the isolated staging directory
                under ``self.config.staging_root`` and return ``staged_dir``,
                ``staged_brd_path``, and ``staged_sch_path`` so downstream tools
                (such as ``eagle6-freerouting``) can inspect or route the staged
                board without touching original user files.
        """
        target = Path(project_path).expanduser().resolve()
        if not target.is_file():
            raise FileNotFoundError(f"Project file not found: {target}")
        suffix = target.suffix.lower()
        if suffix not in {".sch", ".brd"}:
            raise ValueError("`project_path` must be a .sch or .brd file.")

        sibling_ext = ".brd" if suffix == ".sch" else ".sch"
        sibling = target.with_suffix(sibling_ext)
        if not sibling.is_file():
            # Also check uppercase Windows sibling extension
            alt_sibling = target.with_suffix(sibling_ext.upper())
            sibling = alt_sibling if alt_sibling.is_file() else None

        self.config.staging_root.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix="validate_", dir=self.config.staging_root))
        keep_dir = False
        try:
            staged_target = tmp_dir / EagleRunner._staged_filename(target)
            shutil.copy2(target, staged_target)

            staged_sibling: Path | None = None
            if sibling is not None:
                staged_sibling = tmp_dir / EagleRunner._staged_filename(sibling)
                shutil.copy2(sibling, staged_sibling)

            staged_sch = staged_target if suffix == ".sch" else staged_sibling
            staged_brd = staged_target if suffix == ".brd" else staged_sibling

            # Capture before snapshots
            before_sch = SchematicParser.parse_file(staged_sch) if staged_sch else None
            before_brd = BoardParser.parse_file(staged_brd) if staged_brd else None

            scr_file = tmp_dir / "dry_run_edit.scr"
            scr_file.write_text(script_content, encoding="utf-8")

            eagle_cmd = f"SET CONFIRM YES; SCRIPT '{scr_file}'; WRITE; QUIT"
            res = self.runner._run_editor_command(staged_target, eagle_cmd)

            # Re-parse after script execution
            after_sch = SchematicParser.parse_file(staged_sch) if staged_sch else None
            after_brd = BoardParser.parse_file(staged_brd) if staged_brd else None

            diff: dict[str, Any] = {}
            if before_sch and after_sch:
                diff["schematic"] = self._diff_schematics(before_sch, after_sch)
            if before_brd and after_brd:
                diff["board"] = self._diff_boards(before_brd, after_brd)

            consistency: dict[str, Any] | None = None
            erc_delta: dict[str, Any] | None = None
            drc_delta: dict[str, Any] | None = None

            if run_checks:
                if after_sch and after_brd:
                    consistency = ConsistencyAnalyzer(after_sch, after_brd).check()
                if before_sch and after_sch:
                    b_erc = ErcDrcAnalyzer.run_erc(before_sch)
                    a_erc = ErcDrcAnalyzer.run_erc(after_sch)
                    erc_delta = {
                        "errors_before": b_erc["error_count"],
                        "errors_after": a_erc["error_count"],
                        "warnings_before": b_erc["warning_count"],
                        "warnings_after": a_erc["warning_count"],
                    }
                if before_brd and after_brd:
                    b_drc = ErcDrcAnalyzer.run_drc(before_brd)
                    a_drc = ErcDrcAnalyzer.run_drc(after_brd)
                    drc_delta = {
                        "errors_before": b_drc["error_count"],
                        "errors_after": a_drc["error_count"],
                        "warnings_before": b_drc["warning_count"],
                        "warnings_after": a_drc["warning_count"],
                    }

            result = {
                "success": res.returncode == 0,
                "exit_code": res.returncode,
                "stderr": res.stderr.strip(),
                "paired_files_staged": staged_sibling is not None,
                "staged_dir": str(tmp_dir) if keep_staged else None,
                "staged_brd_path": (
                    str(staged_brd) if (keep_staged and staged_brd is not None) else None
                ),
                "staged_sch_path": (
                    str(staged_sch) if (keep_staged and staged_sch is not None) else None
                ),
                "diff": diff,
                "consistency": consistency,
                "erc_delta": erc_delta,
                "drc_delta": drc_delta,
            }
            keep_dir = keep_staged
            return result
        finally:
            if not keep_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    @staticmethod
    def save_script(script_content: str, output_path: str | Path) -> dict[str, str]:
        """Write a validated ``.scr`` script to disk and return the EAGLE GUI command."""
        out = Path(output_path).expanduser().resolve()
        if out.suffix.lower() != ".scr":
            raise ValueError("`output_path` must have a '.scr' extension.")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(script_content, encoding="utf-8")
        return {
            "output_path": str(out),
            "eagle_gui_command": f"SCRIPT '{out}';",
        }

    @staticmethod
    def _diff_schematics(before: Any, after: Any) -> dict[str, Any]:
        b_sa = SchematicAnalyzer(before)
        a_sa = SchematicAnalyzer(after)
        b_parts = set(before.parts.keys())
        a_parts = set(after.parts.keys())

        value_changes: list[dict[str, str]] = []
        attr_changes: list[dict[str, Any]] = []
        for pname in sorted(b_parts & a_parts):
            bv = b_sa.effective_value(before.parts[pname])
            av = a_sa.effective_value(after.parts[pname])
            if bv != av:
                value_changes.append({"part": pname, "before": bv, "after": av})
            if before.parts[pname].attributes != after.parts[pname].attributes:
                attr_changes.append(
                    {
                        "part": pname,
                        "before": dict(before.parts[pname].attributes),
                        "after": dict(after.parts[pname].attributes),
                    }
                )

        return {
            "parts_added": sorted(a_parts - b_parts),
            "parts_removed": sorted(b_parts - a_parts),
            "value_changes": value_changes,
            "attribute_changes": attr_changes,
        }

    @staticmethod
    def _diff_boards(before: Any, after: Any) -> dict[str, Any]:
        b_elems = set(before.elements.keys())
        a_elems = set(after.elements.keys())

        value_changes: list[dict[str, str]] = []
        moved: list[dict[str, Any]] = []
        for ename in sorted(b_elems & a_elems):
            be = before.elements[ename]
            ae = after.elements[ename]
            if be.value != ae.value:
                value_changes.append({"element": ename, "before": be.value, "after": ae.value})
            if (
                abs(be.x_mm - ae.x_mm) > 1e-3
                or abs(be.y_mm - ae.y_mm) > 1e-3
                or be.rot != ae.rot
            ):
                moved.append(
                    {
                        "element": ename,
                        "before": {"x_mm": be.x_mm, "y_mm": be.y_mm, "rot": be.rot},
                        "after": {"x_mm": ae.x_mm, "y_mm": ae.y_mm, "rot": ae.rot},
                    }
                )

        return {
            "elements_added": sorted(a_elems - b_elems),
            "elements_removed": sorted(b_elems - a_elems),
            "value_changes": value_changes,
            "placement_changes": moved,
        }
