"""Phase 1: split adjustment, the universe and the Level A trend baseline."""
from datetime import date, datetime, timezone

import numpy as np
import pytest

from candleisgreen.core.config import load_config
from candleisgreen.data.adjust import adjust_closes
from candleisgreen.models import ts_momentum


def test_split_is_removed_from_history_only_once_effective():
    closes = [(date(2026, 5, 1), 200.0), (date(2026, 5, 4), 101.0)]
    split = [{"action_type": "forward_splits", "effective_date": date(2026, 5, 4), "raw": {"new_rate": 2, "old_rate": 1}}]
    adj = adjust_closes(closes, split, date(2026, 5, 4))
    assert adj[0][1] == pytest.approx(100.0) and adj[1][1] == 101.0
    assert adjust_closes(closes, split, date(2026, 5, 1))[0][1] == 200.0  # not yet effective


def test_dividend_adjustment_scales_earlier_prices():
    closes = [(date(2026, 3, 13), 30.0), (date(2026, 3, 16), 29.75)]
    div = [{"action_type": "cash_dividends", "effective_date": date(2026, 3, 16), "raw": {"rate": 0.25}}]
    adj = adjust_closes(closes, div, date(2026, 3, 16))
    assert adj[0][1] == pytest.approx(30.0 * (1 - 0.25 / 30.0))


def test_score_sign_and_clip():
    cfg = load_config().models.ts_momentum
    rng = np.random.default_rng(60)
    up = 50 * np.exp(np.cumsum(rng.normal(0.002, 0.01, 300)))
    down = 50 * np.exp(np.cumsum(rng.normal(-0.002, 0.01, 300)))
    assert ts_momentum.score(up, cfg) > 0 > ts_momentum.score(down, cfg)
    assert abs(ts_momentum.score(np.linspace(10, 100, 300), cfg)) <= cfg.clip
    assert ts_momentum.score(up[:100], cfg) is None  # not enough history


def test_skip_window_ignores_the_last_month():
    cfg = load_config().models.ts_momentum
    base = list(50 * np.exp(np.linspace(0, 0.3, 280)))
    crash = base[:-10] + [base[-11] * 0.5] * 10  # crash inside the skipped month
    assert ts_momentum.score(base, cfg) == pytest.approx(ts_momentum.score(crash, cfg))


def test_universe_and_scores_on_the_synthetic_market():
    from candleisgreen import universe
    from candleisgreen.data.instruments import InstrumentMaster
    from candleisgreen.data.pit_store import PointInTimeStore
    from candleisgreen.sources import recorder
    from candleisgreen.sources.alpaca import AlpacaData
    from candleisgreen.sources.alpaca_fake import FakeAlpacaTransport

    cfg = load_config()
    now = datetime(2026, 11, 19, 21, 20, tzinfo=timezone.utc)
    store = PointInTimeStore()
    master = InstrumentMaster(store.connection)
    recorder.backfill(date(2025, 6, 2), date(2026, 11, 19), AlpacaData(FakeAlpacaTransport(now=now), cfg.sources.alpaca),
                      store, master, now, cfg)
    decision = datetime(2026, 11, 19, 21, 30, tzinfo=timezone.utc)
    members = {m.symbol: m for m in universe.build(decision, store, master, cfg)}
    assert "DLST" not in members  # delisted in September
    assert {"UPCO", "DNCO", "FLAT", "SPLT", "RNMX", "BIGX"} <= set(members)
    from candleisgreen.data.adjust import adjust_closes

    def s(sym):
        iid = members[sym].instrument_id
        obs = store.as_of(decision).series(iid, "close")
        adj = adjust_closes([(o.event_time.date(), o.value) for o in obs], master.actions(iid), decision.date())
        return ts_momentum.score([c for _, c in adj], cfg.models.ts_momentum)

    assert s("UPCO") > 0 > s("DNCO")
    assert s("SPLT") > 0  # the 2-for-1 split does not look like a crash after adjustment
