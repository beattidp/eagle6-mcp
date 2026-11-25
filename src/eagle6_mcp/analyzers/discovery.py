"""Discovery utilities for EAGLE projects and libraries across search roots."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from eagle6_mcp.config import EagleConfig
from eagle6_mcp.models.common import LibraryFileInfo, ProjectInfo
from eagle6_mcp.parsers.base import FormatDetector


class ProjectDiscoverer:
    """Scans configured directories to locate EAGLE projects and libraries."""

    def __init__(self, config: EagleConfig) -> None:
        self.config = config

    def list_projects(
        self, root_dir: str | Path | None = None, max_depth: int = 4
    ) -> list[ProjectInfo]:
        """Discover EAGLE design pairs (``.sch`` / ``.brd``) under project roots.

        Groups files by ``(parent_dir, stem)`` so paired schematics and boards
        appear as a single :class:`ProjectInfo` entry, alongside any ``eagle.epf``
        in the same folder.
        """
        roots = (
            [Path(root_dir).expanduser()]
            if root_dir
            else self.config.existing_project_dirs()
        )
        grouped: dict[tuple[Path, str], dict[str, Path]] = {}

        for root in roots:
            if not (root.exists() and root.is_dir()):
                continue
            for path in self._walk_limited(root, max_depth=max_depth):
                suffix = path.suffix.lower()
                if suffix not in {".sch", ".brd"}:
                    continue
                key = (path.parent, path.stem)
                entry = grouped.setdefault(key, {})
                entry[suffix] = path

        projects: list[ProjectInfo] = []
        for (parent, stem), files in sorted(grouped.items(), key=lambda x: str(x[0])):
            sch = files.get(".sch")
            brd = files.get(".brd")
            epf = parent / "eagle.epf"
            mtimes = [p.stat().st_mtime for p in (sch, brd) if p is not None]
            latest_iso = (
                datetime.fromtimestamp(max(mtimes), tz=timezone.utc).isoformat()
                if mtimes
                else None
            )
            projects.append(
                ProjectInfo(
                    name=stem,
                    directory=str(parent),
                    sch_path=str(sch) if sch else None,
                    brd_path=str(brd) if brd else None,
                    epf_path=str(epf) if epf.is_file() else None,
                    sch_format=FormatDetector.detect(sch) if sch else None,
                    brd_format=FormatDetector.detect(brd) if brd else None,
                    last_modified=latest_iso,
                )
            )
        return projects

    def list_libraries(
        self, query: str | None = None, scope: str = "all"
    ) -> list[LibraryFileInfo]:
        """List ``.lbr`` files across user and/or system library directories."""
        system_lbr = (self.config.eagle_install_dir / "lbr").resolve()
        q = query.lower().strip() if query else None
        results: list[LibraryFileInfo] = []

        for lib_dir in self.config.existing_library_dirs(scope=scope):
            dir_scope = "system" if lib_dir.resolve() == system_lbr else "user"
            for path in sorted(lib_dir.glob("*.lbr")):
                if q and q not in path.stem.lower():
                    continue
                results.append(
                    LibraryFileInfo(
                        name=path.stem,
                        path=str(path),
                        scope=dir_scope,
                        file_format=FormatDetector.detect(path),
                        size_bytes=path.stat().st_size,
                    )
                )
        return results

    @staticmethod
    def _walk_limited(root: Path, max_depth: int) -> list[Path]:
        """Recursively collect files up to ``max_depth`` levels below ``root``."""
        found: list[Path] = []
        base_parts = len(root.parts)
        for current_root, dirnames, filenames in root.walk(on_error=lambda _: None):
            depth = len(current_root.parts) - base_parts
            # Skip hidden directories and limit traversal depth
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            if depth >= max_depth:
                dirnames[:] = []
            for fname in filenames:
                found.append(current_root / fname)
        return found
