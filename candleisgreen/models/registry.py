"""Model registry state (config/models.yaml): versions, levels and evidence tiers."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict

from ..core.schemas import Venue

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "models.yaml"


class ModelEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    level: str
    tier: int
    family: str
    data_licenses: tuple[str, ...] = ()
    note: Optional[str] = None


class ModelRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    registry_version: str
    models: dict[str, ModelEntry]

    def get(self, model_id: str) -> ModelEntry:
        if model_id not in self.models:
            raise KeyError(f"model '{model_id}' is not registered in config/models.yaml")
        return self.models[model_id]


class RoutingNotAllowedError(RuntimeError):
    pass


def assert_routing_allowed(entry: ModelEntry, venue: Venue, capital_min_tier: int) -> None:
    """A model below the capital tier may only reach the internal simulator."""
    if venue is not Venue.SIMULATION and entry.tier < capital_min_tier:
        raise RoutingNotAllowedError(f"tier {entry.tier} is below the capital tier {capital_min_tier}, simulator only")


def load_models(path: str | Path | None = None) -> ModelRegistry:
    with open(path or DEFAULT_PATH, "r", encoding="utf-8") as handle:
        return ModelRegistry.model_validate(yaml.safe_load(handle))
