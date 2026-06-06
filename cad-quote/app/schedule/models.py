from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class CircuitRow:
    circuit: str = ""
    breaker: str = ""
    poles: str = ""
    curve: str = ""
    rating: str = ""
    phase: str = ""
    cable: str = ""
    conduit: str = ""
    load: str = ""
    usage: str = ""
    y: float = 0.0
    raw_texts: List[str] = field(default_factory=list)


@dataclass
class PanelHeader:
    name: str = ""
    code: str = ""
    pe: str = ""
    kx: str = ""
    cos_phi: str = ""
    ijs: str = ""
    main_breaker: str = ""
    contactor: str = ""
    spd: str = ""
    size: str = ""
    install: str = ""
    extras: Dict[str, str] = field(default_factory=dict)


@dataclass
class PanelSchedule:
    header: PanelHeader
    circuits: List[CircuitRow]
