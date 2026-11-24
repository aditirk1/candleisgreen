"""Phase 1: survivorship-aware forward recorder on the synthetic Alpaca market."""
from datetime import date, datetime, timezone

import pytest

from candleisgreen.core.config import load_config
from candleisgreen.data.instruments import InstrumentMaster, infer_security_type
from candleisgreen.data.pit_store import PointInTimeStore
from candleisgreen.sources import recorder
from candleisgreen.sources.alpaca import AlpacaData, TooEarlyError
from candleisgreen.sources.alpaca_fake import FakeAlpacaTransport

UTC = timezone.utc
NOW = datetime(2026, 11, 19, 21, 20, tzinfo=UTC)  # 16:20 ET


@pytest.fixture
def env():
    cfg = load_config()
    store = PointInTimeStore()
    master = InstrumentMaster(store.connection)
    data = AlpacaData(FakeAlpacaTransport(now=NOW), cfg.sources.alpaca)
    recorder.backfill(date(2025, 6, 2), date(2026, 11, 18), data, store, master, NOW, cfg)
    return cfg, store, master, data


def test_delisted_name_stays_with_its_history(env):
    cfg, store, master, data = env
    iid = master.instrument_for_symbol("DLST")
    assert iid is not None and master.status(iid) == "delisted"
    closes = store.as_of(NOW).series(iid, "close")
    assert closes and closes[-1].event_time.date() == date(2026, 9, 30)


def test_ticker_change_keeps_one_instrument_id(env):
    cfg, store, master, data = env
    new = master.instrument_for_symbol("RNMX")
    assert master.instrument_for_symbol("RNME") == new
    assert set(master.symbols(new)) == {"RNME", "RNMX"}


def test_split_and_dividend_are_stored_and_bars_stay_unadjusted(env):
    cfg, store, master, data = env
    iid = master.instrument_for_symbol("SPLT")
    kinds = {a["action_type"] for a in master.actions(iid)}
    assert kinds == {"forward_splits"}
    closes = {o.event_time.date(): o.value for o in store.as_of(NOW).series(iid, "close")}
    assert closes[date(2026, 5, 4)] < 0.6 * closes[date(2026, 5, 1)]  # raw prices halve on the split
    assert {a["action_type"] for a in master.actions(master.instrument_for_symbol("FLAT"))} == {"cash_dividends"}


def test_backfill_days_are_flagged_without_a_snapshot(env):
    cfg, store, master, data = env
    flags = master.completeness(date(2026, 3, 2))
    assert flags and flags[0]["collection_mode"] == "backfill" and not flags[0]["asset_list_snapshot_taken"]


def test_live_session_is_recorded_once_and_flagged(env):
    cfg, store, master, data = env
    first = recorder.record_session(date(2026, 11, 19), data, store, master, NOW, cfg)
    again = recorder.record_session(date(2026, 11, 19), data, store, master, NOW, cfg)
    assert first.observations_added > 0 and first.completeness_added == 1
    assert again.observations_added == 0 and again.completeness_added == 0 and again.actions_added == 0
    flag = master.completeness(date(2026, 11, 19))[0]
    assert flag["collection_mode"] == "live" and flag["asset_list_snapshot_taken"] and flag["session_open"]


def test_live_values_become_usable_only_after_collection(env):
    cfg, store, master, data = env
    recorder.record_session(date(2026, 11, 19), data, store, master, NOW, cfg)
    iid = master.instrument_for_symbol("UPCO")
    last = store.as_of(datetime(2026, 11, 19, 21, 30, tzinfo=UTC)).series(iid, "close")[-1]
    assert last.event_time.date() == date(2026, 11, 19) and last.first_usable_at == NOW
    before = store.as_of(datetime(2026, 11, 19, 21, 19, tzinfo=UTC)).series(iid, "close")[-1]
    assert before.event_time.date() == date(2026, 11, 18)


def test_a_non_trading_day_is_recorded_as_closed(env):
    cfg, store, master, data = env
    saturday = datetime(2026, 11, 21, 21, 20, tzinfo=UTC)
    data2 = AlpacaData(FakeAlpacaTransport(now=saturday), cfg.sources.alpaca)
    res = recorder.record_session(date(2026, 11, 21), data2, store, master, saturday, cfg)
    flag = master.completeness(date(2026, 11, 21))[0]
    assert res.observations_added == 0 and not flag["session_open"]


def test_free_plan_delay_is_respected():
    cfg = load_config()
    data = AlpacaData(FakeAlpacaTransport(now=NOW), cfg.sources.alpaca)
    with pytest.raises(TooEarlyError):
        data.daily_bars(["UPCO"], date(2026, 11, 19), date(2026, 11, 19), datetime(2026, 11, 19, 21, 10, tzinfo=UTC))


def test_security_type_is_inferred_and_labeled():
    assert infer_security_type("Broad Index ETF Trust") == ("etf", False)
    assert infer_security_type("Upward Industries Inc") == ("common_stock", False)
    assert infer_security_type("Ultra 3X Bear Shares ETF")[1] is True


def test_live_transport_needs_paper_keys(monkeypatch):
    from candleisgreen.sources.alpaca import HttpTransport, MissingCredentialsError

    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    with pytest.raises(MissingCredentialsError):
        HttpTransport(load_config().sources.alpaca)
