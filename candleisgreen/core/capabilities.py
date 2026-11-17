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


class Capability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Status
    sources: tuple[str, ...] = ()
    reason: Optional[str] = None
    note: Optional[str] = None

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
