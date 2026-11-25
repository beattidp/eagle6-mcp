"""Configuration management for the EAGLE v6 MCP server.

Centralizes filesystem paths, EAGLE CLI settings, render cache locations,
and default project/library search roots. Environment variables can override
defaults without modifying source code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _split_env_paths(env_var: str, default: list[Path]) -> list[Path]:
    """Parse a colon-separated environment variable into a list of Paths."""
    raw = os.environ.get(env_var)
    if not raw:
        return list(default)
    return [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]


@dataclass
class EagleConfig:
    """Runtime configuration for EAGLE v6 MCP server operations.

    Attributes:
        eagle_bin: Path to the CadSoft EAGLE v6 executable.
        eagle_install_dir: Root directory of the EAGLE v6 installation.
        user_dir: Primary EAGLE v6 user data directory (projects, lbr, dru, etc.).
        project_dirs: Ordered list of directories scanned by ``list_projects``.
        library_dirs: Ordered list of directories scanned by ``list_libraries``.
        render_dir: Directory where exported PNG images are written.
        staging_root: Root directory for isolated temporary staging copies.
        xvfb_run_bin: Executable name or path for ``xvfb-run``.
        cli_timeout_seconds: Maximum wall-clock seconds for EAGLE CLI invocations.
    """

    eagle_bin: Path = field(
        default_factory=lambda: Path(
            os.environ.get("EAGLE6_BIN", "/opt/eagle-6.6.0/bin/eagle")
        )
    )
    eagle_install_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("EAGLE6_INSTALL_DIR", "/opt/eagle-6.6.0")
        )
    )
    user_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("EAGLE6_USER_DIR", "/home/beattidp/eagle6")
        )
    )
    project_dirs: list[Path] = field(
        default_factory=lambda: _split_env_paths(
            "EAGLE6_PROJECT_DIRS",
            [
                Path("/home/beattidp/eagle6/projects"),
                Path("/home/beattidp/hdw"),
                Path("/home/beattidp/vm_shared/hdw/Midnight"),
                Path("/home/beattidp/eagle/projects"),
            ],
        )
    )
    library_dirs: list[Path] = field(
        default_factory=lambda: _split_env_paths(
            "EAGLE6_LIBRARY_DIRS",
            [
                Path("/home/beattidp/eagle6/lbr"),
                Path("/home/beattidp/eagle/lbr"),
                Path("/opt/eagle-6.6.0/lbr"),
            ],
        )
    )
    render_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("EAGLE6_RENDER_DIR", "/tmp/eagle6-mcp-renders")
        )
    )
    staging_root: Path = field(
        default_factory=lambda: Path(
            os.environ.get("EAGLE6_STAGING_ROOT", "/tmp/eagle6-mcp-staging")
        )
    )
    xvfb_run_bin: str = field(
        default_factory=lambda: os.environ.get("EAGLE6_XVFB_BIN", "xvfb-run")
    )
    cli_timeout_seconds: int = field(
        default_factory=lambda: int(os.environ.get("EAGLE6_CLI_TIMEOUT", "60"))
    )

    def existing_project_dirs(self) -> list[Path]:
        """Return only configured project search directories that exist on disk."""
        return [p for p in self.project_dirs if p.exists() and p.is_dir()]

    def existing_library_dirs(self, scope: str = "all") -> list[Path]:
        """Return existing library directories filtered by scope.

        Args:
            scope: One of ``"user"``, ``"system"``, or ``"all"``.
        """
        system_lbr = (self.eagle_install_dir / "lbr").resolve()
        result: list[Path] = []
        for path in self.library_dirs:
            if not (path.exists() and path.is_dir()):
                continue
            is_system = path.resolve() == system_lbr
            if scope == "user" and is_system:
                continue
            if scope == "system" and not is_system:
                continue
            result.append(path)
        return result


DEFAULT_CONFIG = EagleConfig()
