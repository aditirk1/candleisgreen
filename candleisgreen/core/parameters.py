"""Parameter registry (config/parameters.yaml).

Every config value has a basis, and the basis decides how the software treats it:

- empirical: carries a citation. Changed only with new evidence.
- safeguard: limits damage. Never varied by an experiment, search or optimizer.
- provisional: an initial configuration. Labeled PROVISIONAL where it decides an outcome.
  Experiments may vary it, and every variant counts in the trial registry.
- external_fact: an official or conventional number with a source and a date.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Optional

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from .config import DEFAULT_CONFIG_PATH

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "parameters.yaml"
METADATA_KEYS = ("config_version", "spec_version", "description")


class Basis(str, Enum):
    EMPIRICAL = "empirical"
    SAFEGUARD = "safeguard"
    PROVISIONAL = "provisional"
    EXTERNAL_FACT = "external_fact"


class NotTunableError(ValueError):
    """Raised when an experiment tries to vary a safeguard or an external fact."""


class Parameter(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    basis: Basis
    source: Optional[str] = None
    as_of: Optional[str] = None
    review: Optional[str] = None
    change_policy: Optional[str] = None

    @model_validator(mode="after")
    def _evidence_matches_basis(self) -> "Parameter":
        need = {
            Basis.EMPIRICAL: ("source",),
            Basis.SAFEGUARD: ("change_policy",),
            Basis.PROVISIONAL: ("review",),
            Basis.EXTERNAL_FACT: ("source", "as_of"),
        }[self.basis]
        missing = [name for name in need if not getattr(self, name)]
        if missing:
            raise ValueError(f"a {self.basis.value} parameter needs {', '.join(missing)}")
        return self

    @property
    def label(self) -> str:
        return {
            Basis.EMPIRICAL: f"EMPIRICAL ({self.source})",
            Basis.SAFEGUARD: "SAFEGUARD",
            Basis.PROVISIONAL: "PROVISIONAL",
            Basis.EXTERNAL_FACT: f"EXTERNAL FACT as of {self.as_of}",
        }[self.basis]


class ParameterRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    registry_version: str
    parameters: dict[str, Parameter]

    def get(self, path: str) -> Parameter:
        if path not in self.parameters:
            raise KeyError(f"parameter '{path}' is not classified in config/parameters.yaml")
        return self.parameters[path]

    def label(self, path: str) -> str:
        return self.get(path).label

    def assert_tunable(self, path: str) -> None:
        """Experiments call this before varying a parameter."""
        basis = self.get(path).basis
        if basis in (Basis.SAFEGUARD, Basis.EXTERNAL_FACT):
            raise NotTunableError(f"'{path}' is a {basis.value} and cannot be varied by an experiment")

    def paths(self, basis: Basis) -> tuple[str, ...]:
        return tuple(p for p, v in self.parameters.items() if v.basis is basis)


def config_leaves(raw: dict[str, Any], prefix: str = "") -> Iterator[str]:
    """Every parameter path in a raw config mapping, skipping metadata keys."""
    for key, value in raw.items():
        if key in METADATA_KEYS:
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from config_leaves(value, path)
        else:
            yield path


def load_registry(path: str | Path | None = None) -> ParameterRegistry:
    with open(path or DEFAULT_PATH, "r", encoding="utf-8") as handle:
        return ParameterRegistry.model_validate(yaml.safe_load(handle))


def unclassified(config_path: str | Path | None = None, registry: ParameterRegistry | None = None) -> tuple[list[str], list[str]]:
    """Return (config values with no classification, registry entries with no config value)."""
    reg = registry or load_registry()
    with open(config_path or DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as handle:
        leaves = set(config_leaves(yaml.safe_load(handle)))
    known = set(reg.parameters)
    return sorted(leaves - known), sorted(known - leaves)
