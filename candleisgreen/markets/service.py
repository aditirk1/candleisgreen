"""Recording jobs for the asset classes beyond stocks. Read only. Each returns a plain summary.

Run from the command line:
  .venv/bin/python -m candleisgreen.markets.service crypto --workdir var/live
  .venv/bin/python -m candleisgreen.markets.service cot --workdir var/live
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from ..core.config import AppConfig, load_config
from ..core.timeutil import utc_now
from .futures import parse_code, parse_settlements, products
from .store import Bar, MarketStore

STORE_FILE = "markets.sqlite"


def record_crypto(store: MarketStore, api, cfg: AppConfig, now: datetime) -> dict:
    """Daily bars for every listed pair, from the day after the last stored bar."""
    from ..sources.alpaca_crypto import to_bars
    out = {}
    for sym in cfg.assets.crypto.symbols:
        have = [s for s in store.symbols("crypto") if s[1] == sym and s[0] == "alpaca_us"]
        start = (have[0][3].date() + timedelta(days=1)) if have and have[0][3] else cfg.assets.crypto.history_start
        rows = api.daily_bars([sym], start).get(sym, [])
        out[sym] = store.add_bars(to_bars(sym, rows, now), now)
    return {"job": "crypto", "stored": out, "at": now.isoformat()}


def record_cot(store: MarketStore, transport, cfg: AppConfig, now: datetime, since: Optional[date] = None) -> dict:
    """Commitments of Traders for each futures product in its matching report, about three years back."""
    from ..sources.cftc import LICENSE, VENDOR, InvalidReportError, fetch, first_usable_at, validate
    since = since or (now.date() - timedelta(weeks=cfg.assets.futures.cot_percentile_window_weeks + 4))
    out, rejected = {}, {}
    for code, p in products().items():
        rows = fetch(transport, p.cot_dataset, p.cftc_code, since=since)
        n, bad = 0, []
        for r in rows:
            try:
                rep = validate(r, p.cot_dataset, p.cftc_code)
            except (InvalidReportError, KeyError, ValueError) as exc:
                bad.append(str(exc))
                continue
            n += store.add_report(p.cot_dataset, p.cftc_code, rep, r, VENDOR, LICENSE, now, first_usable_at(rep, now, cfg.assets.futures))
        out[code] = n
        if bad:
            rejected[code] = bad[:5]
    return {"job": "cot", "stored": out, "rejected": rejected, "at": now.isoformat()}


class SettlementUploadError(ValueError):
    pass


def load_settlements(store: MarketStore, text: str, now: datetime, source: str, license_confirmed: bool) -> dict:
    """Your own settlement file, research only. You must say where it came from and confirm its terms allow
    personal research. Prices must be positive, dates must be in the past, and one contract cannot have two
    different prices on the same day."""
    if not license_confirmed:
        raise SettlementUploadError("Confirm that the source's terms allow you to use these prices for personal research")
    source = (source or "").strip()
    if len(source) < 8:
        raise SettlementUploadError("Say where the prices came from, for example the CME Daily Bulletin of a given date")
    series = parse_settlements(text)
    for code, rows in series.items():
        seen: dict = {}
        for d, s in rows:
            if s <= 0:
                raise SettlementUploadError(f"{code} {d}: a settlement price must be positive")
            if d >= now.date():
                raise SettlementUploadError(f"{code} {d}: a settlement must be from a past trading day")
            if d in seen and seen[d] != s:
                raise SettlementUploadError(f"{code} {d}: two different prices for the same day")
            seen[d] = s
    vendor = f"user_upload: {source[:160]}"
    n = 0
    for code, rows in series.items():
        # A settlement is published the evening of its trading day, so it counts from the end of that day.
        day = lambda d: datetime(d.year, d.month, d.day, tzinfo=now.tzinfo)  # noqa: E731
        bars = [Bar("future", "user_upload", code, "1Day", day(d), s, s, s, s, None, True, vendor, "user_upload", day(d) + timedelta(days=1))
                for d, s in sorted(set(rows))]
        n += store.add_bars(bars, now)
    return {"contracts": sorted(series), "stored": n, "source": source}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Record data for crypto and futures positioning. Read only.")
    parser.add_argument("job", choices=["crypto", "cot"])
    parser.add_argument("--workdir", default="var/live")
    args = parser.parse_args(argv)
    cfg = load_config()
    wd = Path(args.workdir)
    wd.mkdir(parents=True, exist_ok=True)
    store = MarketStore(wd / STORE_FILE, shared=False)
    now = utc_now()
    if args.job == "crypto":
        from ..sources.alpaca_crypto import AlpacaCrypto, transport_from_env
        out = record_crypto(store, AlpacaCrypto(transport_from_env(cfg.sources.alpaca), cfg.sources.alpaca, cfg.assets.crypto), cfg, now)
    else:
        from ..sources.public_http import PublicTransport
        out = record_cot(store, PublicTransport(), cfg, now)
    print(json.dumps(out, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
