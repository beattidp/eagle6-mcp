"""Common domain models shared across EAGLE schematic, board, and library files.

All geometric coordinates and dimensions in EAGLE 6 XML are stored in
millimeters (mm), per ``/opt/eagle-6.6.0/doc/eagle.dtd``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FileFormat(str, Enum):
    """Detected binary vs. XML format of an EAGLE file."""

    XML = "xml"
    LEGACY_BINARY = "legacy_binary"
    UNKNOWN = "unknown"


@dataclass
class Layer:
    """EAGLE drawing layer definition (e.g., 1=Top, 16=Bottom, 20=Dimension)."""

    number: int
    name: str
    color: int = 0
    fill: int = 0
    visible: bool = True
    active: bool = True


@dataclass
class NetClass:
    """EAGLE electrical net class defining default width, drill, and clearances."""

    number: int
    name: str
    width_mm: float = 0.0
    drill_mm: float = 0.0
    clearances_mm: dict[int, float] = field(default_factory=dict)


@dataclass
class DesignRules:
    """Parsed EAGLE Design Rules (from a standalone ``.dru`` or ``<designrules>``).

    Raw parameter values preserve units as written by EAGLE (e.g. ``8mil``,
    ``0.2mm``, ``(1*16)``) so callers can inspect both raw rules and parsed
    millimeter conversions where applicable.
    """

    name: str = "default"
    description: str = ""
    params: dict[str, str] = field(default_factory=dict)


@dataclass
class ProjectInfo:
    """Discovered EAGLE project or design pair on disk."""

    name: str
    directory: str
    sch_path: str | None = None
    brd_path: str | None = None
    epf_path: str | None = None
    sch_format: FileFormat | None = None
    brd_format: FileFormat | None = None
    last_modified: str | None = None


@dataclass
class LibraryFileInfo:
    """Discovered EAGLE library file metadata."""

    name: str
    path: str
    scope: str  # "user" or "system"
    file_format: FileFormat
    size_bytes: int
