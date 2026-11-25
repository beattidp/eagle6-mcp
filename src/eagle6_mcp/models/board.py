"""Domain models for EAGLE v6 PCB board (``.brd``) files."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from eagle6_mcp.models.common import DesignRules, Layer, NetClass
from eagle6_mcp.models.library import Library


@dataclass
class ContactRef:
    """Electrical connection from a board signal to an element's pad."""

    element: str
    pad: str
    route: str = "all"
    routetag: str = ""


@dataclass
class Wire:
    """A straight or curved trace/outline/airwire segment in millimeters."""

    x1_mm: float
    y1_mm: float
    x2_mm: float
    y2_mm: float
    width_mm: float
    layer: int
    extent: str | None = None
    curve_deg: float = 0.0
    style: str = "continuous"

    @property
    def is_airwire(self) -> bool:
        """Return True if this wire is an unrouted airwire (layer 19 or extent set)."""
        return self.layer == 19 or self.extent is not None

    @property
    def length_mm(self) -> float:
        """Compute segment length in mm, accounting for circular arc curvature.

        For a chord of length ``c`` and included arc angle ``theta`` (radians),
        arc length is ``(c / (2 * sin(theta / 2))) * theta``.
        """
        chord = math.hypot(self.x2_mm - self.x1_mm, self.y2_mm - self.y1_mm)
        if abs(self.curve_deg) < 1e-6 or chord < 1e-9:
            return chord
        theta = math.radians(abs(self.curve_deg))
        half_sin = math.sin(theta / 2.0)
        if abs(half_sin) < 1e-9:
            return chord
        radius = chord / (2.0 * half_sin)
        return radius * theta


@dataclass
class Via:
    """Inter-layer copper via."""

    x_mm: float
    y_mm: float
    extent: str
    drill_mm: float
    diameter_mm: float = 0.0
    shape: str = "round"


@dataclass
class PolygonVertex:
    """Single vertex of a copper pour or plain polygon."""

    x_mm: float
    y_mm: float
    curve_deg: float = 0.0


@dataclass
class Polygon:
    """Copper pour or mechanical polygon."""

    layer: int
    width_mm: float
    pour: str = "solid"
    isolate_mm: float | None = None
    rank: int = 0
    thermals: bool = True
    orphans: bool = False
    vertices: list[PolygonVertex] = field(default_factory=list)


@dataclass
class Signal:
    """Named electrical signal on the PCB with contacts, traces, vias, and pours."""

    name: str
    net_class: int = 0
    airwires_hidden: bool = False
    contactrefs: list[ContactRef] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    polygons: list[Polygon] = field(default_factory=list)


@dataclass
class BoardElement:
    """Physical component placed on the PCB."""

    name: str
    library: str
    package: str
    value: str
    x_mm: float
    y_mm: float
    rot: str = "R0"
    locked: bool = False
    smashed: bool = False
    attributes: dict[str, str] = field(default_factory=dict)

    @property
    def is_bottom(self) -> bool:
        """Return True if the component is mirrored onto the bottom side ('M' in rot)."""
        return "M" in self.rot.upper()

    @property
    def side(self) -> str:
        """Return ``'bottom'`` if mirrored, otherwise ``'top'``."""
        return "bottom" if self.is_bottom else "top"

    @property
    def angle_deg(self) -> float:
        """Extract numeric rotation angle in degrees from EAGLE rotation string."""
        cleaned = self.rot.upper().lstrip("MSR")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0


@dataclass
class Board:
    """Top-level parsed EAGLE v6 PCB board model."""

    file_path: str
    eagle_version: str
    description: str = ""
    layers: dict[int, Layer] = field(default_factory=dict)
    classes: dict[int, NetClass] = field(default_factory=dict)
    design_rules: DesignRules = field(default_factory=DesignRules)
    libraries: dict[str, Library] = field(default_factory=dict)
    plain_wires: list[Wire] = field(default_factory=list)
    plain_holes: list[tuple[float, float, float]] = field(default_factory=list)
    plain_circles: list[tuple[float, float, float, int]] = field(default_factory=list)
    plain_rectangles: list[tuple[float, float, float, float, int]] = field(
        default_factory=list
    )
    elements: dict[str, BoardElement] = field(default_factory=dict)
    signals: dict[str, Signal] = field(default_factory=dict)
    attributes: dict[str, str] = field(default_factory=dict)
