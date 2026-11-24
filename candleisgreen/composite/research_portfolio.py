"""Spec C.3: each signal's daily research portfolio and its net return series.

Timing. Row t of `z` is the smoothed score known at decision time on day t. Row t of
`returns` is each asset's return from the close of day t to the close of day t + 1, so
the weights set from z[t] earn returns[t]. Weights on day t use returns[: t] only.

Units. Weights are fractions of the research NAV. Volatility is scaled to the configured
target with an ex-ante estimate: the trailing returns of today's weights over
`vol_lookback_days` (DECISIONS D-014).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.config import CompositeConfig


@dataclass(frozen=True)
class MarketInputs:
    returns: np.ndarray  # T x N, close t to close t + 1
    half_spread: np.ndarray  # T x N, fraction of price
    sigma_daily: np.ndarray  # T x N, daily volatility
    adv_usd: np.ndarray  # T x N, average daily dollar volume
    price: np.ndarray  # T x N, for the per-share FINRA fee


@dataclass(frozen=True)
class ResearchSeries:
    weights: np.ndarray  # T x N
    gross: np.ndarray  # T
    cost: np.ndarray  # T, all costs at 1x
    net: np.ndarray  # T
    turnover: np.ndarray  # T, sum of |trade| as a fraction of NAV
    scale: np.ndarray  # T, factor that brought raw weights to the volatility target
    long_only_net: np.ndarray  # T, top quantile minus universe, net of its own costs
    long_only_cost: np.ndarray  # T
    active: np.ndarray  # T, bool, enough history to size the portfolio

    @property
    def vol_scale(self) -> float:
        """g_s: the median sizing factor over active days."""
        live = self.scale[self.active]
        return float(np.median(live)) if live.size else float("nan")


def _raw_weights(z_row: np.ndarray, signal_type: str) -> np.ndarray:
    z_row = np.nan_to_num(z_row, nan=0.0)
    if signal_type == "cross_sectional":
        w = z_row - z_row.mean()
        gross = np.abs(w).sum()
        return w / gross if gross > 0 else w
    return z_row / max(z_row.size, 1)  # time-series and event signals are directional per asset


def trade_costs(trade: np.ndarray, t: int, market: MarketInputs, cfg: CompositeConfig) -> float:
    """Cost of one day's trades as a fraction of research NAV, at 1x."""
    nav = cfg.research_portfolio.research_nav_usd
    size = np.abs(trade)
    dollars = size * nav
    spread = float(market.half_spread[t] @ size)
    adv = np.maximum(market.adv_usd[t], 1.0)
    impact = float((cfg.optimizer.impact_kappa * market.sigma_daily[t] * np.sqrt(dollars / adv)) @ size)
    sold = np.where(trade < 0, dollars, 0.0)
    sec = sold.sum() * cfg.costs.sec_fee_per_million_usd_sold / 1e6
    shares = np.divide(sold, market.price[t], out=np.zeros_like(sold), where=market.price[t] > 0)
    taf = np.minimum(shares * cfg.costs.finra_taf_per_share_sold, cfg.costs.finra_taf_max_per_trade_usd).sum()
    return spread + impact + (sec + taf) / nav


def build(z: np.ndarray, signal_type: str, market: MarketInputs, cfg: CompositeConfig) -> ResearchSeries:
    z = np.asarray(z, dtype=float)
    r = np.nan_to_num(np.asarray(market.returns, dtype=float), nan=0.0)
    T, N = z.shape
    c = cfg.costs
    days = cfg.research_portfolio.trading_days_per_year
    target = cfg.research_portfolio.vol_target_annual
    weights = np.zeros((T, N))
    scale = np.zeros(T)
    active = np.zeros(T, dtype=bool)
    for t in range(T):
        lo = max(0, t - c.vol_lookback_days)
        if t - lo < c.min_vol_history_days:
            continue
        raw = _raw_weights(z[t], signal_type)
        vol = float(np.std(r[lo:t] @ raw, ddof=1)) * np.sqrt(days)
        gross = float(np.abs(raw).sum())
        if not vol > 0 or not gross > 0:
            continue
        scale[t] = min(target / vol, cfg.research_portfolio.max_gross_leverage / gross)
        weights[t] = raw * scale[t]
        active[t] = True
    gross = (weights * r).sum(axis=1)
    trades = np.diff(np.vstack([np.zeros(N), weights]), axis=0)
    turnover = np.abs(trades).sum(axis=1)
    cost = np.array([trade_costs(trades[t], t, market, cfg) for t in range(T)])
    if signal_type == "cross_sectional":
        cost += np.clip(-weights, 0.0, None).sum(axis=1) * c.borrow_rate_annual / days

    # Long-only implementation for the Tier 4 economic value test.
    lo_w = np.zeros((T, N))
    for t in range(T):
        if not active[t]:
            continue
        row = np.nan_to_num(z[t], nan=-np.inf)
        cut = np.quantile(z[t][np.isfinite(z[t])], c.long_only_quantile) if np.isfinite(z[t]).any() else np.inf
        top = row >= cut
        if top.any():
            lo_w[t, top] = 1.0 / top.sum()
    universe = r.mean(axis=1)
    lo_trades = np.diff(np.vstack([np.zeros(N), lo_w]), axis=0)
    lo_cost = np.array([trade_costs(lo_trades[t], t, market, cfg) for t in range(T)])
    lo_net = np.where(active, (lo_w * r).sum(axis=1) - universe, 0.0) - lo_cost
    return ResearchSeries(weights, gross, cost, gross - cost, turnover, scale, lo_net, lo_cost, active)
