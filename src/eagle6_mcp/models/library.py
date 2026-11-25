"""Domain models for EAGLE v6 library definitions (symbols, packages, devicesets)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Pin:
    """A single schematic symbol pin."""

    name: str
    x_mm: float
    y_mm: float
    direction: str = "io"  # nc, in, out, io, oc, pwr, pas, hiz, sup
    function: str = "none"
    length: str = "long"
    visible: str = "both"
    rot: str = "R0"
    swaplevel: int = 0


@dataclass
class Symbol:
    """Schematic symbol containing named pins and graphical primitives."""

    name: str
    description: str = ""
    pins: list[Pin] = field(default_factory=list)


@dataclass
class Pad:
    """Through-hole pad inside a PCB package footprint."""

    name: str
    x_mm: float
    y_mm: float
    drill_mm: float
    diameter_mm: float = 0.0
    shape: str = "round"
    rot: str = "R0"
    stop: bool = True
    thermals: bool = True


@dataclass
class Smd:
    """Surface-mount pad inside a PCB package footprint."""

    name: str
    x_mm: float
    y_mm: float
    dx_mm: float
    dy_mm: float
    layer: int = 1
    roundness: int = 0
    rot: str = "R0"
    stop: bool = True
    cream: bool = True
    thermals: bool = True


@dataclass
class Hole:
    """Non-plated mounting or alignment hole."""

    x_mm: float
    y_mm: float
    drill_mm: float


@dataclass
class Package:
    """PCB footprint package containing pads, SMDs, and mechanical holes."""

    name: str
    description: str = ""
    pads: list[Pad] = field(default_factory=list)
    smds: list[Smd] = field(default_factory=list)
    holes: list[Hole] = field(default_factory=list)

    @property
    def is_smd(self) -> bool:
        """Return True if the footprint uses SMD pads and no through-hole pads."""
        return bool(self.smds) and not bool(self.pads)

    @property
    def is_tht(self) -> bool:
        """Return True if the footprint has through-hole pads."""
        return bool(self.pads)


@dataclass
class Gate:
    """Gate binding a named gate identifier to a symbol inside a deviceset."""

    name: str
    symbol: str
    x_mm: float = 0.0
    y_mm: float = 0.0
    addlevel: str = "next"
    swaplevel: int = 0


@dataclass
class Connect:
    """Mapping from a symbol gate/pin to one or more footprint pads."""

    gate: str
    pin: str
    pad: str
    route: str = "all"


@dataclass
class Device:
    """Concrete package variant inside a deviceset."""

    name: str
    package: str | None = None
    connects: list[Connect] = field(default_factory=list)
    technologies: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class DeviceSet:
    """EAGLE deviceset combining gates (symbols) and devices (packages)."""

    name: str
    prefix: str = ""
    uservalue: bool = False
    description: str = ""
    gates: list[Gate] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)


@dataclass
class Library:
    """EAGLE library (standalone ``.lbr`` or embedded inside ``.sch``/``.brd``)."""

    name: str
    description: str = ""
    symbols: dict[str, Symbol] = field(default_factory=dict)
    packages: dict[str, Package] = field(default_factory=dict)
    devicesets: dict[str, DeviceSet] = field(default_factory=dict)
