"""Global research jobs (spec Phase 6). Research only: no non-US instrument can receive orders.

FX rates come from FRED's public CSV. Global factor returns come from JKP Global Factor Data,
licensed CC BY-NC 4.0, so everything derived from them is tagged and stays research only.
A signal's tier is tracked separately in each market, because post-publication decay differs
by market.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .core.config import AppConfig
from .sources import fx

ROOT = Path(__file__).resolve().parents[1]
FRED_FIXTURES = ROOT / "tests" / "fixtures" / "fred"
JKP_FIXTURES = ROOT / "tests" / "fixtures" / "jkp"
JKP_LICENSE = "cc_by_nc_4_0"


def refresh_fx(workdir: Path, now: datetime, fake: bool) -> dict:
    """Store the latest FRED FX series. Idempotent: the same file content gives the same result."""
    out_dir = workdir / "fx"
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for currency, (series, _) in fx.SERIES.items():
        src = FRED_FIXTURES / f"{series}.csv"
        if fake and not src.exists():
            continue
        text = src.read_text() if fake else fx.fetch(series)
        (out_dir / f"{series}.csv").write_text(text)
        counts[currency] = len(fx.parse_fred_csv(text))
    return {"series": counts, "synthetic_clock": fake}


def load_fx(workdir: Path) -> fx.FxTable:
    rates = {}
    for currency, (series, _) in fx.SERIES.items():
        path = workdir / "fx" / f"{series}.csv"
        if path.exists():
            rates[currency] = fx.parse_fred_csv(path.read_text())
    return fx.FxTable(rates)


def load_jkp(path: Path) -> pd.DataFrame:
    """JKP factor return file: one row per location, factor, date. Columns are normalized here."""
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    need = {"location", "name", "date", "ret"}
    if not need <= set(cols):
        raise ValueError(f"JKP file is missing columns {need - set(cols)}")
    df = df.rename(columns={cols[c]: c for c in need})
    df["date"] = pd.to_datetime(df["date"])
    return df[["location", "name", "date", "ret"]]


def market_tiers(df: pd.DataFrame, factor: str, cutoff_year: int, hac_lag: int = 6) -> list[dict]:
    """Per-market evidence: for each location, the factor's mean and Newey-West t after the cutoff.
    Research only, tagged with the JKP license."""
    from .composite.stats import newey_west_se

    out = []
    for loc, g in df[df["name"] == factor].groupby("location"):
        x = g[g["date"].dt.year > cutoff_year]["ret"].dropna().to_numpy(dtype=float)
        if x.size < 24:
            out.append({"location": loc, "factor": factor, "months": int(x.size), "status": "NOT AVAILABLE",
                        "license": JKP_LICENSE})
            continue
        se = newey_west_se(x, hac_lag)
        t = float(x.mean() / se) if se > 0 else 0.0
        out.append({"location": loc, "factor": factor, "months": int(x.size), "mean_monthly": float(x.mean()),
                    "t_stat": t, "replicates": bool(t > 1.96 and x.mean() > 0), "license": JKP_LICENSE,
                    "use": "research only"})
    return out


def refresh_global_factors(workdir: Path, now: datetime, cfg: AppConfig, fake: bool) -> dict:
    files = sorted(JKP_FIXTURES.glob("*.csv")) if fake else sorted((workdir / "jkp").glob("*.csv"))
    if not files:
        return {"status": "NOT AVAILABLE", "reason": "no JKP files downloaded yet"}
    frames = [load_jkp(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    results = market_tiers(df, "ret_12_1", 1993, cfg.research.monthly_hac_lag)
    (workdir / "global").mkdir(parents=True, exist_ok=True)
    (workdir / "global" / "momentum_by_market.json").write_text(json.dumps(results, default=str, indent=1))
    return {"markets": len(results), "replicating": sum(1 for r in results if r.get("replicates")), "license": JKP_LICENSE}
