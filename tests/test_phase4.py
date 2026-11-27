"""Phase 4 acceptance: a replay cannot see later news or prices at earlier timestamps.
Also RSS ingestion on real government feeds, clustering, and predict-first scoring."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from candleisgreen.core.config import FeedConfig, load_config
from candleisgreen.core.schemas import CollectionMode, Observation
from candleisgreen.data.instruments import InstrumentMaster
from candleisgreen.data.pit_store import PointInTimeStore
from candleisgreen.sources import recorder, rss
from candleisgreen.sources.alpaca import AlpacaData
from candleisgreen.sources.alpaca_fake import FakeAlpacaTransport
from candleisgreen.teaching.predictions import PredictionError, Predictions
from candleisgreen.teaching.replay import Replay

UTC = timezone.utc
FIX = Path(__file__).parent / "fixtures" / "rss"
SEEN = datetime(2026, 11, 24, 6, 0, tzinfo=UTC)


def _feed(name):
    return next(f for f in load_config().news.feeds if f.name == name)


@pytest.fixture
def news(tmp_path):
    cfg = load_config()
    store = rss.NewsStore(tmp_path / "news.sqlite")
    counts = {n: rss.ingest(_feed(n), (FIX / f"{x}.xml").read_bytes(), store, SEEN, cfg)
              for n, x in (("sec_press", "sec_press"), ("sec_litigation", "sec_lit"), ("fed_press", "fed_press"))}
    return cfg, store, counts


def test_real_feeds_parse_with_hashes_and_summaries(news):
    cfg, store, counts = news
    assert counts == {"sec_press": 25, "sec_litigation": 25, "fed_press": 20}
    items = store.as_of(SEEN + timedelta(seconds=1), limit=500)
    assert len(items) == 70
    assert all(len(i.content_hash) == 64 and len(i.summary) <= cfg.news.max_summary_chars for i in items)
    assert all(i.first_usable_at >= i.first_seen_at for i in items)  # never usable before the platform saw it


def test_ingesting_twice_adds_nothing(news):
    cfg, store, _ = news
    again = rss.ingest(_feed("sec_press"), (FIX / "sec_press.xml").read_bytes(), store, SEEN + timedelta(hours=1), cfg)
    assert again == 0


def test_duplicate_story_clusters(tmp_path):
    cfg = load_config()
    store = rss.NewsStore(tmp_path / "n.sqlite")
    feed = FeedConfig(name="t", url="x", license="us_government_public")
    t = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
    items = [{"guid": "1", "title": "Federal Reserve Board announces approval of bank merger application",
              "link": "a", "summary": "", "published_at": t, "tickers": ()},
             {"guid": "2", "title": "Federal Reserve announces approval of bank merger application", "link": "b",
              "summary": "", "published_at": t + timedelta(hours=1), "tickers": ()},
             {"guid": "3", "title": "SEC charges adviser with fraud", "link": "c", "summary": "",
              "published_at": t, "tickers": ()}]
    store.add(feed, items, t + timedelta(hours=2), cfg)
    clusters = store.clusters(t + timedelta(hours=3))
    assert sorted(c["items"] for c in clusters) == [1, 2]


def test_hostile_xml_is_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><rss><channel><item><title>&b;</title></item></channel></rss>'
    with pytest.raises(Exception):
        rss.parse_feed(bomb, FeedConfig(name="t", url="x", license="x"), SEEN, 500)


def test_tickers_are_linked_from_exchange_mentions():
    xml = b"<rss><channel><item><title>Acme (NASDAQ: ACME) settles</title><description>Also (NYSE: XYZ)</description></item></channel></rss>"
    items = rss.parse_feed(xml, FeedConfig(name="t", url="x", license="x"), SEEN, 500)
    assert items[0]["tickers"] == ("ACME", "XYZ")


# Acceptance: replay ----------------------------------------------------------------------

@pytest.fixture
def market(tmp_path):
    cfg = load_config()
    now = datetime(2026, 11, 19, 21, 20, tzinfo=UTC)
    store = PointInTimeStore()
    master = InstrumentMaster(store.connection)
    recorder.backfill(date(2025, 6, 2), date(2026, 11, 19), AlpacaData(FakeAlpacaTransport(now=now), cfg.sources.alpaca),
                      store, master, now, cfg)
    return cfg, store, master


def test_replay_cannot_see_later_prices_news_or_corrections(market, tmp_path):
    cfg, store, master = market
    news = rss.NewsStore(tmp_path / "news.sqlite")
    feed = FeedConfig(name="t", url="x", license="us_government_public")
    early = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    late = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    news.add(feed, [{"guid": "early", "title": "Early story about rates", "link": "e", "summary": "", "published_at": early,
                     "tickers": ("UPCO",)}], early, cfg)
    news.add(feed, [{"guid": "late", "title": "Later story about earnings", "link": "l", "summary": "", "published_at": late,
                     "tickers": ("UPCO",)}], late, cfg)
    # A correction to a September close, published in late October.
    iid = master.instrument_for_symbol("UPCO")
    orig = store.as_of(late).series(iid, "close")
    sept = next(o for o in orig if o.event_time.date() == date(2026, 9, 15))
    corrected = Observation(**{**sept.model_dump(), "value": sept.value * 1.5, "vintage": 1, "published_at": late,
                               "vendor_available_at": late, "first_usable_at": late, "ingested_at": late})
    store.add([corrected])

    replay = Replay(store, news, master, cursor=datetime(2026, 10, 5, 12, 0, tzinfo=UTC),
                    end=datetime(2026, 11, 19, 21, 30, tzinfo=UTC))
    seen = replay.view("UPCO")
    assert [n["title"] for n in seen["news"]] == ["Early story about rates"]
    assert max(p["date"] for p in seen["prices"]) < "2026-10-05"
    sept_seen = next(p for p in replay.prices("UPCO", last=60) if p["date"] == "2026-09-15")
    assert sept_seen["value"] == sept.value and sept_seen["vintage"] == 0  # the correction is not known yet
    assert all(datetime.fromisoformat(p["usable_from"]) < replay.cursor for p in replay.prices("UPCO", last=500))

    for _ in range(20):
        replay.advance()
    later = replay.view("UPCO")
    assert {n["title"] for n in later["news"]} == {"Early story about rates", "Later story about earnings"}
    sept_now = next(p for p in replay.prices("UPCO", last=60) if p["date"] == "2026-09-15")
    assert sept_now["vintage"] == 1 and sept_now["value"] == pytest.approx(sept.value * 1.5)
    assert later["intraday"].startswith("NOT AVAILABLE")
    with pytest.raises(ValueError):
        replay.advance(timedelta(days=400))


# Predict first ---------------------------------------------------------------------------

def test_predictions_score_with_brier_and_calibrate(market, tmp_path):
    cfg, store, master = market
    preds = Predictions(tmp_path / "teaching.sqlite")
    made = datetime(2026, 10, 1, 21, 30, tzinfo=UTC)
    preds.add("user:aditi", "UPCO", master, "up", 10, 0.8, made, SEEN, "replay")
    preds.add("user:aditi", "DNCO", master, "up", 10, 0.7, made, SEEN, "replay")
    preds.add("user:aditi", "FLAT", master, "down", 10, 0.6, datetime(2026, 11, 18, 21, 30, tzinfo=UTC), SEEN)
    assert preds.resolve(store, datetime(2026, 11, 19, 21, 30, tzinfo=UTC)) == 2  # the third is not due yet
    cal = preds.calibration("user:aditi")
    outcomes = {p["symbol"]: p["outcome"] for p in preds.list("user:aditi")}
    assert outcomes["FLAT"] is None and cal.resolved == 2
    expected = ((0.8 - outcomes["UPCO"]) ** 2 + (0.7 - outcomes["DNCO"]) ** 2) / 2
    assert cal.brier == pytest.approx(expected) and cal.baseline_brier == 0.25
    early_clock = made + timedelta(days=3)  # before either horizon ends
    assert preds.calibration("user:aditi", replay_clock=early_clock).resolved == 0  # nothing revealed early
    with pytest.raises(PredictionError):
        preds.add("user:aditi", "UPCO", master, "sideways", 5, 0.5, made, SEEN)
    with pytest.raises(PredictionError):
        preds.add("user:aditi", "NOPE", master, "up", 5, 0.5, made, SEEN)
