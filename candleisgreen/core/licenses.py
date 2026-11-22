"""License registry (config/licenses.yaml). Data and derived results keep their license tags.

A use is allowed only when every license involved marks it `permitted`. `unverified` and
unknown licenses are refused.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

import yaml
from pydantic import BaseModel, ConfigDict

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "licenses.yaml"


class Permission(str, Enum):
    PERMITTED = "permitted"
    NOT_PERMITTED = "not_permitted"
    UNVERIFIED = "unverified"


class LicenseNotPermittedError(RuntimeError):
    pass


class License(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str
    research: Permission
    paper_trading: Permission
    note: Optional[str] = None


class LicenseRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    registry_version: str
    licenses: dict[str, License]

    def problems(self, license_ids: Iterable[str], use: str) -> list[str]:
        if use not in ("research", "paper_trading"):
            raise ValueError(f"unknown use '{use}'")
        out = []
        for lid in sorted(set(license_ids)):
            lic = self.licenses.get(lid)
            if lic is None:
                out.append(f"license '{lid}' is not in config/licenses.yaml")
            elif getattr(lic, use) is not Permission.PERMITTED:
                out.append(f"license '{lid}' is {getattr(lic, use).value} for {use}")
        return out

    def assert_use(self, license_ids: Iterable[str], use: str) -> None:
        ids = tuple(license_ids)
        if not ids:
            raise LicenseNotPermittedError(f"no license recorded, {use} refused")
        found = self.problems(ids, use)
        if found:
            raise LicenseNotPermittedError("; ".join(found))


def load_licenses(path: str | Path | None = None) -> LicenseRegistry:
    with open(path or DEFAULT_PATH, "r", encoding="utf-8") as handle:
        return LicenseRegistry.model_validate(yaml.safe_load(handle))
