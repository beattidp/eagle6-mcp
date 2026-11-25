"""Domain models for EAGLE v6 schematic (``.sch``) files."""

from __future__ import annotations

from dataclasses import dataclass, field

from eagle6_mcp.models.common import Layer, NetClass
from eagle6_mcp.models.library import Library


@dataclass
class PinRef:
    """Reference to a specific part/gate/pin connected to a net segment."""

    part: str
    gate: str
    pin: str
    sheet: int = 1


@dataclass
class NetSegment:
    """A contiguous graphical segment of a schematic net on a single sheet."""

    sheet: int
    pinrefs: list[PinRef] = field(default_factory=list)
    has_label: bool = False
    wire_count: int = 0
    junction_count: int = 0


@dataclass
class Net:
    """Named electrical net on a sheet (aggregated across sheets by analyzers)."""

    name: str
    net_class: int = 0
    sheet: int = 1
    segments: list[NetSegment] = field(default_factory=list)


@dataclass
class PartInstance:
    """Placement of a single gate of a Part on a schematic sheet."""

    part: str
    gate: str
    sheet: int
    x_mm: float
    y_mm: float
    rot: str = "R0"
    smashed: bool = False


@dataclass
class Part:
    """Logical component instantiated in the schematic ``<parts>`` table."""

    name: str
    library: str
    deviceset: str
    device: str
    technology: str = ""
    value: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class Sheet:
    """A single schematic sheet (1-indexed in EAGLE UI)."""

    number: int
    description: str = ""
    instances: list[PartInstance] = field(default_factory=list)
    nets: list[Net] = field(default_factory=list)
    bus_names: list[str] = field(default_factory=list)


@dataclass
class Schematic:
    """Top-level parsed EAGLE v6 schematic model."""

    file_path: str
    eagle_version: str
    description: str = ""
    layers: dict[int, Layer] = field(default_factory=dict)
    classes: dict[int, NetClass] = field(default_factory=dict)
    libraries: dict[str, Library] = field(default_factory=dict)
    parts: dict[str, Part] = field(default_factory=dict)
    sheets: list[Sheet] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)
