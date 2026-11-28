"""News made readable: categories, company links, price moves as observations, and the stock explainer."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from candleisgreen import news_insight as ni
from candleisgreen.api.app import create_app
from tests.phase1_env import DECIDE_NOW, EXEC_NOW, build_env

UTC = timezone.utc


def test_categories_come_from_words_then_from_feed():
    rules = ni.load_rules()
    assert ni.classify_story("Minutes of the Federal Open Market Committee", ["fed_press"], rules)["id"] == "monetary_policy"
    assert ni.classify_story("Nihat Cardak", ["sec_litigation"], rules)["id"] == "enforcement"
    assert ni.classify_story("College Fed Challenge winners", ["fed_press"], rules) is None
    assert all("can_affect" in r and "what_it_is" in r for r in rules)


def test_company_links_need_the_full_name_capitalized_in_the_text():
    idx = ni.CompanyIndex.build(ni.TICKERS_FIXTURE)
    assert idx.link("Enforcement action against American Express Company") == ["AXP"]
    assert idx.link("approval of application by The Bank of Nova Scotia") == ["BNS"]
    assert idx.link("we ate an apple inc. at lunch") == []
    assert idx.link("A national bank and a first capital group") == []  # common words never link alone


def test_price_moves_use_only_closes_known_by_now(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    when = datetime(2026, 11, 17, 15, tzinfo=UTC)
    closes = ni.load_closes(env.store, when - timedelta(days=10), DECIDE_NOW)
    out = ni.price_moves(closes, env.master, ["UPCO", "ZZZZ"], when)
    upco, zzzz = out["tickers"]
    assert upco["session"] == "2026-11-17" and upco["move"] is not None
    assert zzzz["move"] is None and zzzz["reason"] == "not in the recorded data"
    assert out["market"]["session"] == "2026-11-17" and out["market"]["names"] >= 3
    later = ni.price_moves(ni.load_closes(env.store, when, datetime(2026, 11, 17, 21, 0, tzinfo=UTC)), env.master, ["UPCO"], when)
    assert later["tickers"][0]["move"] is None  # the close was not usable yet


def test_bulk_read_matches_the_as_of_rule(tmp_path):
    env = build_env(tmp_path, "manual_simulation")
    start = DECIDE_NOW - timedelta(days=10)
    bulk = env.store.as_of(DECIDE_NOW).values_between("close", start, DECIDE_NOW)
    iid = env.master.instrument_for_symbol("UPCO")
    one = [(o.event_time, o.value) for o in env.store.as_of(DECIDE_NOW).series(iid, "close") if o.event_time >= start]
    assert bulk[iid] == one
    before_close = datetime(2026, 11, 19, 21, 0, tzinfo=UTC)  # the Nov 19 close is recorded at 21:20 UTC
    early = env.store.as_of(before_close).values_between("close", start, DECIDE_NOW)
    assert max(t for t, _ in early[iid]).date().isoformat() == "2026-11-18"


def test_news_and_stock_endpoints(tmp_path):
    from candleisgreen.sources.rss import NewsStore, ingest
    from tests.phase1_env import ROOT

    env = build_env(tmp_path, "manual_simulation")
    env.store.close()
    news = NewsStore(tmp_path / "news.sqlite")
    feed = next(f for f in env.cfg.news.feeds if f.name == "fed_press")
    ingest(feed, (ROOT / "tests" / "fixtures" / "rss" / "fed_press.xml").read_bytes(), news, EXEC_NOW - timedelta(hours=2), env.cfg)
    news.close()
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", env.cfg, clock=lambda: EXEC_NOW))
    rows = api.get("/api/news", params={"view": "live"}).json()["clusters"]
    axp = next(r for r in rows if "American Express" in r["headline"])
    assert axp["tickers"] == ["AXP"] and axp["category"]["label"] == "Enforcement"
    assert axp["prices"]["tickers"][0]["reason"] == "not in the recorded data"
    assert all(r["summary"] is None or r["summary"].rstrip(".") != r["headline"].rstrip(".") for r in rows)
    assert [r["headline"] for r in api.get("/api/news", params={"view": "live", "ticker": "AXP"}).json()["clusters"]] == [axp["headline"]]
    s = api.get("/api/stock/UPCO").json()
    assert s["status"] == "OK" and s["name"] == "Upward Industries Inc" and "uptrend" in s["system_view"]
    assert max(h["date"] for h in s["history"]) <= EXEC_NOW.date().isoformat()
    assert s["can_trade"] and s["price"]["change"]["1 year"] is not None
    assert api.get("/api/stock/NOPE").json()["status"] == "NOT AVAILABLE"


def test_ranking_components_and_materiality():
    ranking, rules = ni.load_ranking(), ni.load_rules()
    rate = ni.classify_story("Federal Reserve issues FOMC statement", ["fed_press"], rules)
    r = ni.rank("Federal Reserve issues FOMC statement", [], rate, 1, ranking, set())
    assert r["materiality"] == "MATERIAL" and r["score"] == 3.0  # rate news moves the whole market
    enf = ni.classify_story("enforcement action against American Express Company", ["fed_press"], rules)
    named = ni.rank("enforcement action against American Express Company", ["AXP"], enf, 1, ranking, set())
    assert named["materiality"] == "MATERIAL" and named["score"] == 4.0
    held = ni.rank("enforcement action against American Express Company", ["AXP"], enf, 3, ranking, {"AXP"})
    assert held["score"] == 4.0 + 3.0 + 1.0  # held company and two repeats
    routine = ni.rank("Federal Reserve announces College Fed Challenge winners", [], None, 1, ranking, set())
    assert routine["materiality"] == "ROUTINE" and routine["score"] < 0
    people = ni.rank("Nihat Cardak", [], ni.classify_story("Nihat Cardak", ["sec_litigation"], rules), 1, ranking, set())
    assert people["materiality"] == "ROUTINE"  # a case against individuals cannot move a listed stock
    assert sum(c["points"] for c in held["components"]) == held["score"]


def test_api_sorts_by_relevance_or_recency_and_reports_excerpt_quality(tmp_path):
    from candleisgreen.sources.rss import NewsStore, ingest
    from tests.phase1_env import ROOT

    env = build_env(tmp_path, "manual_simulation")
    env.store.close()
    news = NewsStore(tmp_path / "news.sqlite")
    for name, fname in (("fed_press", "fed_press"), ("sec_press", "sec_press")):
        feed = next(f for f in env.cfg.news.feeds if f.name == name)
        ingest(feed, (ROOT / "tests" / "fixtures" / "rss" / f"{fname}.xml").read_bytes(), news, EXEC_NOW - timedelta(hours=2), env.cfg)
    news.close()
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", env.cfg, clock=lambda: EXEC_NOW))
    rel = api.get("/api/news", params={"view": "live"}).json()
    scores = [r["rank"]["score"] for r in rel["clusters"]]
    assert scores == sorted(scores, reverse=True) and rel["sort"] == "relevance"
    rec = api.get("/api/news", params={"view": "live", "sort": "recency"}).json()["clusters"]
    assert [r["first_usable_at"] for r in rec] == sorted((r["first_usable_at"] for r in rec), reverse=True)
    fed = [r for r in rel["clusters"] if r["feeds"] == ["fed_press"]]
    assert all(r["excerpt"] == "headline_only" for r in fed)  # Fed items repeat the title
    assert any(r["excerpt"] == "summary" for r in rel["clusters"] if "sec_press" in r["feeds"])
    item = rel["clusters"][0]["items_detail"][0]
    assert {"feed", "link", "published_at", "first_seen_at", "first_usable_at", "license"} <= set(item)
    assert all(r["category"] is None or r["category"]["hypothesis"] for r in rel["clusters"])


def test_templated_headlines_about_different_events_stay_separate():
    from candleisgreen.sources.rss import same_story

    assert not same_story("Federal Reserve Board announces approval of application by Isabella Bank Corporation",
                          "Federal Reserve Board announces approval of application by Fleur Capital Corporation", 0.6)
    assert not same_story("Minutes of the Federal Open Market Committee, October 27-28, 2026",
                          "Minutes of the Federal Open Market Committee, September 15-16, 2026", 0.6)
    assert same_story("SEC Charges Acme Corp. With Fraud", "SEC charges Acme Corp. with fraud", 0.6)
