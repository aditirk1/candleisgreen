"""Capability map (config/capabilities.yaml).

Spec principle 3: a feature without adequate data shows NOT AVAILABLE and the reason.
Code asks `require(name)` before using a capability. A capability that is not available
raises, so nothing can quietly run on data the platform does not have.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "capabilities.yaml"


class Status(str, Enum):
    AVAILABLE = "available"
    LIMITED = "limited"
    NOT_AVAILABLE = "not_available"


class CapabilityNotAvailableError(RuntimeError):
    pass


class LevelState(str, Enum):
    YES = "yes"
    PARTIAL = "partial"
    WAITING = "waiting"  # built, waiting for a key, a license confirmation or a first live check
    NO = "no"


# The eight levels, in order. Each answers one question about an asset class.
LEVELS = (
    ("source_exists", "A free source exists"),
    ("adapter", "Adapter built"),
    ("history_verified", "Historical data checked"),
    ("realtime_verified", "Current prices checked"),
    ("research", "Research"),
    ("simulation", "Simulation inside the platform"),
    ("broker_paper", "Paper trading through a broker"),
    ("live_execution", "Live trading"),
)


class Level(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: LevelState
    note: str
    checked: Optional[str] = None   # date of a live check, required for a verified level marked yes
    modules: tuple[str, ...] = ()   # code that implements an adapter, research or simulation level


class Levels(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_exists: Level
    adapter: Level
    history_verified: Level
    realtime_verified: Level
    research: Level
    simulation: Level
    broker_paper: Level
    live_execution: Level

    @model_validator(mode="after")
    def _honest(self) -> "Levels":
        if self.live_execution.state is not LevelState.NO:
            raise ValueError("live execution is never built in this project")
        for name in ("history_verified", "realtime_verified"):
            lvl = getattr(self, name)
            if lvl.state is LevelState.YES and not lvl.checked:
                raise ValueError(f"{name} marked yes needs the date of the live check")
        for name in ("adapter", "research", "simulation", "broker_paper"):
            lvl = getattr(self, name)
            if lvl.state in (LevelState.YES, LevelState.PARTIAL, LevelState.WAITING) and not lvl.modules:
                raise ValueError(f"{name} marked {lvl.state.value} must name the code that implements it")
        if self.broker_paper.state is LevelState.YES and self.adapter.state is not LevelState.YES:
            raise ValueError("broker paper trading needs a built adapter")
        return self


class Capability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Status
    sources: tuple[str, ...] = ()
    reason: Optional[str] = None
    note: Optional[str] = None
    levels: Optional[Levels] = None

    @model_validator(mode="after")
    def _reason_when_not_fully_available(self) -> "Capability":
        if self.status is not Status.AVAILABLE and not self.reason:
            raise ValueError("a limited or unavailable capability must state its reason")
        if self.status is not Status.NOT_AVAILABLE and not self.sources:
            raise ValueError("an available or limited capability must name its sources")
        return self

    @property
    def label(self) -> str:
        if self.status is Status.NOT_AVAILABLE:
            return f"NOT AVAILABLE. {self.reason}"
        if self.status is Status.LIMITED:
            return f"LIMITED. {self.reason}"
        return "AVAILABLE"


class CapabilityMap(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capabilities_version: str
    capabilities: dict[str, Capability]

    def get(self, name: str) -> Capability:
        if name not in self.capabilities:
            raise KeyError(f"unknown capability '{name}'")
        return self.capabilities[name]

    def require(self, name: str) -> Capability:
        cap = self.get(name)
        if cap.status is Status.NOT_AVAILABLE:
            raise CapabilityNotAvailableError(f"{name}: {cap.label}")
        return cap


def load_capabilities(path: str | Path | None = None) -> CapabilityMap:
    with open(path or DEFAULT_PATH, "r", encoding="utf-8") as handle:
        return CapabilityMap.model_validate(yaml.safe_load(handle))
