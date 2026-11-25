"""Headless EAGLE v6.6.0 CLI runner using ``xvfb-run`` and isolated staging.

Every CLI operation copies target files into a temporary staging directory so
live project files (potentially open in the user's EAGLE GUI) are never locked
or mutated.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from eagle6_mcp.config import EagleConfig

_FOCUS_HELPER = Path(__file__).with_name("_xvfb_focus_exec.py")


BOARD_LAYER_PRESETS: dict[str, list[int]] = {
    # Top copper, pads, vias, dimension, tPlace, tNames, tDocu
    "top_copper": [1, 17, 18, 20, 21, 25, 51],
    # Bottom copper, pads, vias, dimension, bPlace, bNames, bDocu
    "bottom_copper": [16, 17, 18, 20, 22, 26, 52],
    # Top/bottom copper, pads, vias, unrouted airwires, dimension, tPlace, tNames
    "all_copper": [1, 16, 17, 18, 19, 20, 21, 25],
    # Top assembly drawing: dimension, tPlace, tNames, tValues, tDocu
    "top_assembly": [20, 21, 25, 27, 51],
    # Bottom assembly drawing: dimension, bPlace, bNames, bValues, bDocu
    "bottom_assembly": [20, 22, 26, 28, 52],
    # Airwires focus: pads, vias, unrouted, dimension
    "unrouted": [17, 18, 19, 20],
}


@dataclass
class CommandResult:
    """Captured output of a headless EAGLE CLI invocation."""

    returncode: int
    stdout: str
    stderr: str
    command: list[str]


class EagleRunner:
    """Executes CadSoft EAGLE v6.6.0 commands headlessly on staged file copies."""

    def __init__(self, config: EagleConfig) -> None:
        self.config = config
        self.config.render_dir.mkdir(parents=True, exist_ok=True)
        self.config.staging_root.mkdir(parents=True, exist_ok=True)

    def _check_binaries(self) -> None:
        if not self.config.eagle_bin.is_file():
            raise FileNotFoundError(
                f"EAGLE binary not found at '{self.config.eagle_bin}'."
            )
        if shutil.which(self.config.xvfb_run_bin) is None:
            raise FileNotFoundError(
                f"'{self.config.xvfb_run_bin}' not found on PATH. "
                "Install xvfb to enable headless EAGLE CLI operations."
            )

    def _run_editor_command(self, target_file: Path, eagle_cmd: str) -> CommandResult:
        """Execute ``eagle -C <eagle_cmd> <target_file>`` under ``xvfb-run -a``.

        Uses ``_xvfb_focus_exec.py`` inside Xvfb so EAGLE 6's Qt4 editor window
        receives X11 focus and dispatches ``-C`` commands without requiring a
        full window manager.
        """
        self._check_binaries()
        cmd = [
            self.config.xvfb_run_bin,
            "-a",
            "-s",
            "-screen 0 1280x1024x24",
            sys.executable,
            str(_FOCUS_HELPER),
            str(self.config.eagle_bin),
            "-C",
            eagle_cmd,
            str(target_file),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.config.cli_timeout_seconds,
            check=False,
        )
        return CommandResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            command=cmd,
        )

    @staticmethod
    def _short_hash(path: Path) -> str:
        digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()
        return digest[:8]

    def render_schematic(
        self,
        sch_path: str | Path,
        sheet: int = 1,
        dpi: int = 200,
    ) -> Path:
        """Render a schematic sheet to a PNG in ``config.render_dir``.

        Only the ``.sch`` file is copied into staging so EAGLE opens it cleanly
        without triggering forward/back-annotation dialogs.
        """
        src = Path(sch_path).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Schematic file not found: {src}")
        if sheet < 1:
            raise ValueError("Sheet number must be >= 1.")
        if not (50 <= dpi <= 1200):
            raise ValueError("DPI must be between 50 and 1200.")

        out_name = f"{src.stem}_{self._short_hash(src)}_s{sheet}_{dpi}dpi.png"
        out_path = self.config.render_dir / out_name
        if out_path.exists():
            out_path.unlink()

        with tempfile.TemporaryDirectory(dir=self.config.staging_root) as tmp:
            staged = Path(tmp) / src.name
            shutil.copy2(src, staged)
            eagle_cmd = (
                f"SET CONFIRM YES; EDIT .s{sheet}; WINDOW FIT; "
                f"EXPORT IMAGE '{out_path}' {dpi}; QUIT"
            )
            res = self._run_editor_command(staged, eagle_cmd)

        if not out_path.is_file() or out_path.stat().st_size == 0:
            raise RuntimeError(
                f"EAGLE failed to render schematic '{src}' (exit={res.returncode}). "
                f"stderr={res.stderr.strip()!r}"
            )
        return out_path

    def render_board(
        self,
        brd_path: str | Path,
        preset: str = "all_copper",
        custom_layers: list[int] | None = None,
        dpi: int = 300,
    ) -> Path:
        """Render a PCB board to a PNG using a layer preset or custom layer list."""
        src = Path(brd_path).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Board file not found: {src}")
        if not (50 <= dpi <= 1200):
            raise ValueError("DPI must be between 50 and 1200.")

        if custom_layers:
            layers = sorted({int(layer) for layer in custom_layers})
            tag = "layers_" + "-".join(str(layer) for layer in layers[:6])
        else:
            preset_key = preset.lower().strip()
            if preset_key not in BOARD_LAYER_PRESETS:
                valid = ", ".join(sorted(BOARD_LAYER_PRESETS.keys()))
                raise ValueError(f"Unknown preset '{preset}'. Valid presets: {valid}")
            layers = BOARD_LAYER_PRESETS[preset_key]
            tag = preset_key

        out_name = f"{src.stem}_{self._short_hash(src)}_{tag}_{dpi}dpi.png"
        out_path = self.config.render_dir / out_name
        if out_path.exists():
            out_path.unlink()

        layer_str = " ".join(str(layer) for layer in layers)
        with tempfile.TemporaryDirectory(dir=self.config.staging_root) as tmp:
            staged = Path(tmp) / src.name
            shutil.copy2(src, staged)
            eagle_cmd = (
                f"SET CONFIRM YES; DISPLAY NONE {layer_str}; WINDOW FIT; "
                f"EXPORT IMAGE '{out_path}' {dpi}; QUIT"
            )
            res = self._run_editor_command(staged, eagle_cmd)

        if not out_path.is_file() or out_path.stat().st_size == 0:
            raise RuntimeError(
                f"EAGLE failed to render board '{src}' (exit={res.returncode}). "
                f"stderr={res.stderr.strip()!r}"
            )
        return out_path

    def convert_legacy_to_xml(self, file_path: str | Path) -> Path:
        """Convert a pre-v6 binary ``.sch``, ``.brd``, or ``.lbr`` into a staged XML copy.

        The original file is never modified. The converted XML copy is saved in
        ``config.staging_root / 'converted'`` so all Phase 1 XML parsers can
        inspect it directly.
        """
        src = Path(file_path).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(f"EAGLE file not found: {src}")

        out_dir = self.config.staging_root / "converted" / self._short_hash(src)
        out_dir.mkdir(parents=True, exist_ok=True)
        staged = out_dir / src.name
        shutil.copy2(src, staged)

        # SET CONFIRM YES automatically confirms EAGLE's v5->v6 XML conversion prompt.
        res = self._run_editor_command(staged, "SET CONFIRM YES; WRITE; QUIT")
        if res.returncode != 0 or not staged.is_file():
            raise RuntimeError(
                f"EAGLE failed to convert '{src}' to XML (exit={res.returncode}). "
                f"stderr={res.stderr.strip()!r}"
            )
        return staged
