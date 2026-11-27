"""Academic portfolio evidence: loaders and the reproduction and replication tests.

Open Source Asset Pricing long-short returns (CC BY 4.0) are built from CRSP, which
includes delisted stocks. They support a hypothesis. They never certify a tradable
implementation (spec decision Q14).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from ..composite.stats import newey_west_se
from ..core.config import AppConfig

LICENSE_OSAP = "cc_by_4_0"


@dataclass(frozen=True)
class PublishedClaim:
    signal: str
    authors: str
    year: int
    journal: str
    sample_start: int
    sample_end: int
    monthly_return_pct: float
    t_stat: float
    sign: int
    replication_quality: str
    description: str

    @property
    def selection_cutoff_year(self) -> int:
        """Latest of the sample end and the publication year. Later returns are out of sample."""
        return max(self.sample_end, self.year)

    def card(self) -> dict:
        return {
            "source_type": "paper", "title": f"{self.authors} ({self.year}), {self.signal}", "author_ids": [self.authors],
            "published_at": f"{self.year}-12-31", "market": "US equities", "target": "long-short monthly return",
            "horizon": "1 month", "direction": "positive" if self.sign > 0 else "negative",
            "definition": self.description, "data_required": ["Open Source Asset Pricing long-short returns"],
            "reported_effect": {"monthly_return_pct": self.monthly_return_pct, "t_stat": self.t_stat,
                                "sample": [self.sample_start, self.sample_end]},
            "peer_review_status": self.journal or "unknown", "license": LICENSE_OSAP,
            "replication_quality_in_source": self.replication_quality,
        }


def load_osap(ls_path: Path, doc_path: Path) -> tuple[pd.DataFrame, dict[str, PublishedClaim]]:
    ls = pd.read_parquet(ls_path)
    ls["date"] = pd.to_datetime(ls["date"])
    ls = ls.set_index("date").sort_index()
    doc = pd.read_csv(doc_path)
    claims = {}
    for _, r in doc.iterrows():
        claims[r["Acronym"]] = PublishedClaim(
            signal=r["Acronym"], authors=str(r["Authors"]), year=int(r["Year"]), journal=str(r.get("Journal", "")),
            sample_start=int(r["SampleStartYear"]), sample_end=int(r["SampleEndYear"]),
            monthly_return_pct=float(r["Return"]), t_stat=float(r["T-Stat"]), sign=int(r["Sign"]),
            replication_quality=str(r["Signal Rep Quality"]), description=str(r["LongDescription"]))
    return ls, claims


def _stats(x: pd.Series, lag: int) -> tuple[float, float, int]:
    vals = x.dropna().to_numpy(dtype=float)
    se = newey_west_se(vals, lag)
    mean = float(vals.mean())
    return mean, (mean / se if se > 0 else 0.0), int(vals.size)


def reproduce(series: pd.Series, claim: PublishedClaim, cfg: AppConfig) -> dict:
    """Spec rule: same sign, and inside the paper's interval or at least half its size."""
    rc = cfg.research.reproduction
    x = series[(series.index.year >= claim.sample_start) & (series.index.year <= claim.sample_end)]
    mean, t, n = _stats(x, cfg.research.monthly_hac_lag)
    paper = claim.monthly_return_pct
    half_width = rc.interval_z * abs(paper) / abs(claim.t_stat) if claim.t_stat else float("inf")
    inside = paper - half_width <= mean <= paper + half_width
    big_enough = mean >= rc.min_fraction_of_paper * paper
    passed = mean > 0 and (inside or big_enough)
    return {"period": [claim.sample_start, claim.sample_end], "months": n, "mean_monthly_pct": round(mean, 4),
            "t_stat": round(t, 3), "paper_mean_monthly_pct": paper, "paper_interval": [paper - half_width, paper + half_width],
            "inside_paper_interval": inside, "fraction_of_paper": round(mean / paper, 3) if paper else None,
            "passed": passed}


def replicate_after_cutoff(series: pd.Series, claim: PublishedClaim, cfg: AppConfig) -> dict:
    """Independent period: returns after the selection cutoff, same sign and significant at the configured level."""
    from scipy.stats import norm

    x = series[series.index.year > claim.selection_cutoff_year]
    mean, t, n = _stats(x, cfg.research.monthly_hac_lag)
    crit = norm.ppf(1 - cfg.composite.eligibility.replication_significance / 2)
    return {"period_after": claim.selection_cutoff_year, "months": n, "mean_monthly_pct": round(mean, 4),
            "t_stat": round(t, 3), "critical_t": round(crit, 3), "independence": "period",
            "passed": n >= 24 and mean > 0 and t > crit}


def academic_record(series: pd.Series, claim: PublishedClaim, cfg: AppConfig) -> Optional[dict]:
    """Out-of-sample academic evidence for C.4, rescaled to 10% annual volatility."""
    x = series[series.index.year > claim.selection_cutoff_year].dropna() / 100.0
    if len(x) < 24:
        return None
    vol = float(x.std(ddof=1)) * math.sqrt(12)
    scale = cfg.composite.research_portfolio.vol_target_annual / vol if vol > 0 else 0.0
    mean = float(x.mean()) * 12 * scale
    se = newey_west_se(x.to_numpy(), cfg.research.monthly_hac_lag) * 12 * scale
    return {"mean": mean, "se": se, "months": int(len(x)), "license": LICENSE_OSAP}
