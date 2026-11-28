"""Workstation API for the Overview and Execution screens. Binds to localhost only.

Writes only two things: approvals and rejections to the journal, and the kill switch to
the risk service. It never talks to a broker.
"""
from __future__ import annotations

import json

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..core.audit import AuditLog
from ..core.config import AppConfig, load_config
from ..core.timeutil import utc_now
from ..data.pit_store import PointInTimeStore
from ..earnings import consensus_label, scorecard
from ..execution_quality import by_window
from ..jobs import heartbeat_stale, read_heartbeat
from ..journal import Journal
from ..research.registry import ResearchRegistry
from ..reasoning import explain
from ..sources.rss import NewsStore
from ..teaching.predictions import PredictionError, Predictions
from ..teaching.replay import Replay
from ..data.instruments import InstrumentMaster
from ..risk.client import RiskClient

USER = "user:aditi"
UI_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"


class KillSwitchBody(BaseModel):
    engaged: bool


class RejectBody(BaseModel):
    reason: str = "rejected by user"


def _refusal(exc: Exception) -> str:
    """The risk service's own reason for refusing, or that it could not be reached."""
    import urllib.error
    if isinstance(exc, urllib.error.HTTPError):
        try:
            return str(json.loads(exc.read().decode("utf-8")).get("error", exc.reason))
        except Exception:
            return str(exc.reason)
    return f"Risk service unreachable ({type(exc).__name__})"


class CaptureBody(BaseModel):
    kind: str
    content: str = ""
    url: Optional[str] = None
    filename: Optional[str] = None


class IdeaBody(BaseModel):
    idea: str


class ReviewBody(BaseModel):
    correct: bool


class LimitBody(BaseModel):
    key: str
    value: Optional[float] = None


class PredictionBody(BaseModel):
    symbol: str
    direction: str
    horizon_days: int
    probability: float
    replay_cursor: Optional[str] = None


def create_app(workdir: Path, risk_url: str, cfg: Optional[AppConfig] = None, clock=utc_now) -> FastAPI:
    cfg = cfg or load_config()
    workdir = Path(workdir)
    audit = AuditLog(workdir / "audit.sqlite")
    journal = Journal(workdir / "journal.sqlite", audit, cfg.execution.simulator_starting_equity_usd,
                      f"config:{cfg.config_version}:{cfg.config_hash}", shared_across_threads=True)
    risk = RiskClient(risk_url, timeout=2.0)
    research = ResearchRegistry(workdir / "research.sqlite", audit, shared_across_threads=True)
    news = NewsStore(workdir / "news.sqlite", shared_across_threads=True)
    preds = Predictions(workdir / "teaching.sqlite", shared_across_threads=True)
    from ..research.inbox import Inbox, InboxError
    inbox = Inbox(workdir / "inbox.sqlite", cfg.research.inbox, shared_across_threads=True)
    from ..teaching import lab
    review = lab.Review(workdir / "review.sqlite", cfg.teaching.review_intervals_days, shared_across_threads=True)
    glossary = json.loads((Path(__file__).resolve().parents[2] / "config" / "glossary.json").read_text())
    glossary_terms = glossary["terms"]

    def with_store(fn):
        """Short read-only access to the price database. Returns None when it is busy."""
        try:
            store = PointInTimeStore(workdir / "pit.duckdb", read_only=True)
        except Exception:
            return None
        try:
            return fn(store, _master(store))
        finally:
            store.close()

    def _master(store):
        return InstrumentMaster.reader(store.connection)
    app = FastAPI(title="CandleIsGreen workstation", docs_url=None, redoc_url=None)
    venue = "SIMULATION" if "simulation" in cfg.execution.mode else "PAPER"

    def risk_state() -> dict:
        try:
            h = risk.health()
            return {"status": "OK", "kill_switch": h["kill_switch"]}
        except Exception:
            return {"status": "UNREACHABLE", "kill_switch": None}

    def account() -> dict:
        marks = journal.marks()
        positions = journal.positions()
        rows = []
        value = 0.0
        for iid, qty in sorted(positions.items(), key=lambda kv: marks.get(kv[0], {}).get("symbol", "")):
            m = marks.get(iid)
            price = m["price"] if m else None
            mv = qty * price if price is not None else None
            value += mv or 0.0
            rows.append({"instrument_id": iid, "symbol": m["symbol"] if m else iid, "quantity": qty, "price": price,
                         "market_value": mv, "price_source": m["source"] if m else "NOT AVAILABLE"})
        cash = journal.cash()
        equity = cash + value
        for r in rows:
            r["weight"] = (r["market_value"] / equity) if r["market_value"] is not None and equity else None
        return {"cash": cash, "invested": value, "equity": equity, "positions": rows}

    @app.get("/api/status")
    def status():
        now = clock()
        beat = read_heartbeat(workdir)
        stale = heartbeat_stale(workdir, now, cfg.sources.recorder.heartbeat_max_age_hours)
        return {
            "mode": cfg.execution.mode, "venue": venue, "now": now.isoformat(),
            "feed": {"status": "STALE" if stale else "OK", "last_run": beat.get("finished_at") if beat else None,
                     "job": beat.get("job") if beat else None},
            "risk_service": risk_state(), "api": "OK",
        }

    @app.get("/api/overview")
    def overview():
        acct = account()
        hist = journal.equity_history()
        # Change against the equity recorded at the decision before the latest one.
        prev = hist[-2][1] if len(hist) >= 2 else cfg.execution.simulator_starting_equity_usd
        weights = [p["weight"] for p in acct["positions"] if p["weight"] is not None]
        limits = cfg.risk.hard_limits
        alerts = []
        for p in journal.proposals(status="blocked")[-20:]:
            alerts.append({"symbol": p.symbol, "event": "order blocked", "detail": p.reason.split("\n")[0], "time": p.updated_at})
        if heartbeat_stale(workdir, clock(), cfg.sources.recorder.heartbeat_max_age_hours):
            alerts.insert(0, {"symbol": "", "event": "data job missed its schedule", "detail": "feed STALE", "time": clock().isoformat()})
        def cluster_alert(store, master):
            from ..clusters import UNSTABLE, latest_run
            last = latest_run(store.connection)
            return last if last and last.status == UNSTABLE else None
        unstable = with_store(cluster_alert)
        if unstable:
            alerts.insert(0, {"symbol": "", "event": "clusters unstable, sector limits in use",
                              "detail": f"stability {unstable.stability if unstable.stability is not None else 'NOT AVAILABLE'}",
                              "time": unstable.as_of.isoformat()})
        return {
            "venue": venue, "account_value": acct["equity"], "cash": acct["cash"],
            "todays_change": acct["equity"] - prev, "todays_change_pct": (acct["equity"] - prev) / prev if prev else None,
            "risk_in_use": {"invested_pct": acct["invested"] / acct["equity"] if acct["equity"] else 0.0,
                            "largest_position_pct": max(weights) if weights else 0.0,
                            "position_limit_pct": limits.max_position_pct_equity,
                            "cluster_limit_pct": limits.max_cluster_pct_equity},
            "equity_curve": [{"time": t, "value": v} for t, v in hist],
            "positions": acct["positions"], "alerts": alerts[:20],
        }

    @app.get("/api/home")
    def home():
        """Everything the Home screen needs, most important first. Additive: /api/overview is unchanged."""
        from zoneinfo import ZoneInfo
        from ..calendars import is_trading_day
        from ..core.timeutil import in_local_window
        now = clock()
        acct = account()
        hist = journal.equity_history()
        start = cfg.execution.simulator_starting_equity_usd
        prev = hist[-2][1] if len(hist) >= 2 else start
        gross = sum(abs(p["market_value"] or 0.0) for p in acct["positions"])
        shorts = sum(-(p["market_value"] or 0.0) for p in acct["positions"] if p["quantity"] < 0)
        st = status()
        rs = st["risk_service"]
        local = now.astimezone(ZoneInfo(cfg.time.market_timezone))
        trading_day = is_trading_day(local.date())
        is_open = trading_day and in_local_window(now, "09:30", "16:00", cfg.time.market_timezone)
        sources = {p["price_source"] for p in acct["positions"]}
        vendors = with_store(lambda store, master: sorted({o.vendor for i in master.instruments()[:50]
                                                            for o in store.as_of(now).series(i["instrument_id"], "close")[-1:]})) or []
        synthetic = any("synthetic" in (v or "") for v in list(sources) + vendors)
        attention = []
        if rs.get("kill_switch") is True:
            attention.append({"severity": "critical", "text": "Kill switch is on. No new orders can be sent", "screen": "execution"})
        if rs.get("status") != "OK":
            attention.append({"severity": "critical", "text": f"Risk service {rs.get('status')}. Every order is blocked", "screen": "settings"})
        if st["feed"]["status"] != "OK":
            attention.append({"severity": "critical", "text": "Price data job missed its schedule. Decisions use old prices", "screen": "global"})
        if journal.last_reconciliation() is False:
            attention.append({"severity": "critical", "text": "Broker and journal positions do not match. Trading is paused", "screen": "execution"})
        props = journal.proposals()
        latest = max((p.session_date for p in props), default=None)
        waiting = [p for p in props if p.session_date == latest and p.status == "proposed"]
        if waiting and cfg.execution.mode in ("manual_simulation", "broker_paper_approval"):
            attention.append({"severity": "action", "text": f"{len(waiting)} proposals for {latest} wait for your approval", "screen": "execution"})
        blocked = [p for p in props if p.session_date == latest and p.status == "blocked"]
        if blocked:
            attention.append({"severity": "info", "text": f"{len(blocked)} orders for {latest} were blocked by the risk service: "
                              + ", ".join(sorted({p.symbol for p in blocked})), "screen": "execution"})
        try:
            lim = risk._call("GET", "/limits")
            for k, v in lim.get("pending", {}).items():
                ready = datetime.fromisoformat(v["confirmable_from"]) <= now
                attention.append({"severity": "action" if ready else "info",
                                  "text": f"Limit change {k} to {v['value']} {'can be confirmed now' if ready else 'waits until ' + datetime.fromisoformat(v['confirmable_from']).astimezone(ZoneInfo(cfg.time.market_timezone)).strftime('%Y-%m-%d %H:%M ET')}",
                                  "screen": "rules"})
        except Exception:
            pass
        loss = (prev - acct["equity"]) / prev if prev else 0.0
        stop = cfg.risk.hard_limits.daily_loss_stop_pct_equity
        if loss >= 0.75 * stop:
            attention.append({"severity": "critical" if loss >= stop else "action",
                              "text": f"Loss since the last decision is {loss:.2%}, the stop is {stop:.2%}", "screen": "rules"})
        health = [
            {"part": "Risk service", "status": rs.get("status"), "detail": "kill switch on" if rs.get("kill_switch") else "kill switch off"},
            {"part": "Price data job", "status": st["feed"]["status"], "detail": f"last run {st['feed']['last_run'] or 'never'}"},
            {"part": "Reconciliation", "status": {True: "OK", False: "MISMATCH", None: "NOT RUN"}[journal.last_reconciliation()], "detail": "broker against journal"},
            {"part": "Workstation API", "status": "OK", "detail": f"config {cfg.config_version}"},
        ]
        return {
            "venue": venue, "mode": cfg.execution.mode, "now": now.isoformat(),
            "data": {"kind": "SYNTHETIC" if synthetic else ("LIVE" if vendors else "NONE"),
                     "note": "Every price is invented" if synthetic else ("Recorded market data, delayed" if vendors else "No price data recorded yet")},
            "market": {"status": "OPEN" if is_open else "CLOSED", "trading_day": trading_day, "local_time": local.strftime("%H:%M")},
            "account": {"value": acct["equity"], "cash": acct["cash"], "starting_value": start,
                        "change_since_last_decision": acct["equity"] - prev,
                        "change_since_start": acct["equity"] - start, "change_since_start_pct": (acct["equity"] - start) / start,
                        "invested_pct": gross / acct["equity"] if acct["equity"] else 0.0,
                        "short_pct": shorts / acct["equity"] if acct["equity"] else 0.0},
            "performance": [{"time": t, "value": v} for t, v in hist],
            "needs_attention": attention, "system_health": health,
            "positions": acct["positions"],
        }

    @app.get("/api/execution")
    def execution():
        props = journal.proposals()
        latest = max((p.session_date for p in props), default=None)
        session = [p for p in props if p.session_date == latest]
        def row(p):
            return {"proposal_id": p.proposal_id, "symbol": p.symbol, "side": p.side, "quantity": p.quantity,
                    "signal_strength": p.signal_strength, "model": f"{p.model_id} {p.model_version}",
                    "status": p.status, "reason": p.reason, "session_date": p.session_date}
        return {
            "venue": venue, "session_date": latest, "kill_switch": risk_state()["kill_switch"],
            "approval_queue": [row(p) for p in session if p.status == "proposed"],
            "orders": [row(p) for p in session if p.status != "proposed"],
            "fills": [{**f, "symbol": journal.marks().get(f["instrument_id"], {}).get("symbol", f["instrument_id"])}
                      for f in journal.fills()[-50:]],
            "reconciliation": recon(),
            "execution_quality": [{"window": w.window, "fills": w.fills, "mean_bps": w.mean_bps,
                                   "interval_95": None if w.fills < 2 else list(w.interval_95)}
                                  for w in by_window(journal.fills(), 30)],
            "execution_quality_note": "Paper and simulated fills contain no market impact, so this measures spread and quote quality only",
        }

    def recon() -> dict:
        last = journal.last_reconciliation()
        if last is None:
            return {"status": "NOT AVAILABLE", "reason": "No reconciliation has run yet"}
        return {"status": "MATCHED" if last else "MISMATCH",
                "reason": "Broker positions match the journal" if last else "New orders are blocked until positions match"}

    @app.get("/api/earnings")
    def earnings(instrument_id: Optional[str] = None):
        try:
            store = PointInTimeStore(workdir / "pit.duckdb", read_only=True)
        except Exception as exc:
            return {"status": "NOT AVAILABLE", "reason": f"Filing data is busy or missing ({type(exc).__name__})",
                    "issuers": [], "rows": []}
        try:
            conn = store.connection
            issuers = [dict(zip(("cik", "instrument_id", "ticker"), r)) for r in
                       conn.execute("SELECT cik, instrument_id, ticker FROM issuers ORDER BY ticker").fetchall()]
            for i in issuers:
                row = conn.execute("SELECT industry_ff12 FROM classifications WHERE instrument_id = ? "
                                   "ORDER BY classified_at DESC LIMIT 1", [i["instrument_id"]]).fetchall()
                i["industry"] = row[0][0] if row else "UNKNOWN"
            target = instrument_id or (issuers[0]["instrument_id"] if issuers else None)
            rows = [] if target is None else [
                {"period_end": r.period_end.isoformat(), "eps_diluted": r.eps_diluted, "eps_yoy_change": r.eps_yoy_change,
                 "revenue": r.revenue, "revenue_yoy_pct": r.revenue_yoy_pct, "filed_at": r.filed_at.isoformat(),
                 "source": r.source, "vs_consensus": r.vs_consensus_label}
                for r in scorecard(store, target, clock())]
            return {"status": "OK", "issuers": issuers, "instrument_id": target, "rows": rows,
                    "consensus": consensus_label()}
        finally:
            store.close()

    @app.get("/api/research")
    def research_overview():
        claims = research.claims()
        for c in claims:
            c["tier"] = research.tier(c["signal_id"])[0] if c.get("signal_id") else None
        exps = research.experiments()
        models = [{"experiment_id": e["experiment_id"], "champion": e["plan"].get("champion"),
                   "challenger": e["plan"].get("challenger"), "result": e["result"]}
                  for e in exps if e["study_type"] == "forecast" and e["plan"].get("challenger")]
        return {"claims": claims, "experiments": exps, "failures": research.failures(),
                "trial_count": research.variant_count(), "digests": research.digests(3),
                "reevaluations": research.reevaluations(), "promotions": research.promotions(), "models": models}

    @app.post("/api/promotions/{pid}/{verb}")
    def decide_promotion(pid: str, verb: str):
        if verb not in ("approve", "decline"):
            raise HTTPException(404, "unknown action")
        try:
            research.decide_promotion(pid, verb == "approve", USER, clock())
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {"status": "APPROVED" if verb == "approve" else "DECLINED"}

    @app.get("/api/research/chain/{claim_id}")
    def research_chain(claim_id: str):
        try:
            return research.chain(claim_id)
        except KeyError:
            raise HTTPException(404, "unknown claim")

    @app.get("/api/composite")
    def composite():
        run = research.latest_run()
        return run or {"status": "NOT AVAILABLE", "reason": "No Composite run has been recorded"}

    index_cache: dict = {}

    def company_index(path, master):
        """SEC names change rarely, so the index is rebuilt only when the file or entity names change."""
        from .. import news_insight as ni
        key = (str(path), Path(path).stat().st_mtime if Path(path).exists() else 0, len(master.entity_names()))
        if index_cache.get("key") != key:
            index_cache.update(key=key, index=ni.CompanyIndex.build(path, master))
        return index_cache["index"]

    @app.get("/api/news")
    def news_view(view: str = "live", ticker: Optional[str] = None, sort: str = "relevance"):
        from datetime import timedelta
        from .. import news_insight as ni
        now = clock()
        span = timedelta(hours=cfg.news.live_view_hours) if view == "live" else timedelta(days=cfg.news.recent_view_days)
        clusters = news.clusters(now, since=now - span)
        rules = ni.load_rules()
        tickers_file = workdir / "sec" / "company_tickers.json"

        ranking = ni.load_ranking()
        held = {p.symbol: p for p in journal.proposals() if p.status in ("proposed", "approved")}
        positions = journal.positions()

        def relevance(store, master, linked):
            notes, sectors = [], {}
            for t in linked:
                iid = master.instrument_for_symbol(t)
                if iid is None:
                    continue
                sec = master.sector_at(iid, now)
                if sec and sec != "UNKNOWN":
                    sectors[t] = sec
                if positions.get(iid):
                    notes.append(f"{t} is held: {positions[iid]:g} shares")
                if t in held:
                    notes.append(f"{t} has a proposal for {held[t].session_date}: {held[t].side} {held[t].quantity:g}")
            return notes, sectors

        def enrich(store, master):
            index = company_index(tickers_file if tickers_file.exists() else ni.TICKERS_FIXTURE, master)
            held_syms = set(held) | {s for iid in positions for s in master.symbols(iid)[-1:]}
            earliest = min((datetime.fromisoformat(c["first_usable_at"]) for c in clusters), default=now)
            closes = ni.load_closes(store, earliest - timedelta(days=10), now)
            market_cache: dict = {}
            out = []
            for c in clusters:
                text = f"{c['headline']} {c['summary']}"
                linked = sorted(set(c["tickers"]) | set(index.link(text)))
                summary = c["summary"] if c["summary"] and c["summary"].strip().rstrip(".") != c["headline"].strip().rstrip(".") else None
                cat = ni.classify_story(text, c["feeds"], rules)
                notes, sectors = relevance(store, master, linked)
                out.append({**c, "summary": summary, "tickers": linked, "category": cat,
                            "excerpt": "summary" if summary else "headline_only",
                            "sectors": sectors, "model_relevance": notes,
                            "rank": ni.rank(c["headline"], linked, cat, c["items"], ranking, held_syms),
                            "published_at": c["published_at"].isoformat() if c.get("published_at") else None,
                            "prices": ni.price_moves(closes, master, linked, datetime.fromisoformat(c["first_usable_at"]), market_cache)})
            return out

        rows = with_store(enrich)
        if rows is None:
            rows = []
            for c in clusters:
                cat = ni.classify_story(f"{c['headline']} {c['summary']}", c["feeds"], rules)
                rows.append({**c, "category": cat, "prices": None, "sectors": {}, "model_relevance": [],
                             "excerpt": "summary" if c["summary"] else "headline_only",
                             "published_at": c["published_at"].isoformat() if c.get("published_at") else None,
                             "rank": ni.rank(c["headline"], c["tickers"], cat, c["items"], ranking, set(held))})
        if ticker:
            rows = [r for r in rows if ticker.upper() in r["tickers"]]
        if sort == "recency":
            rows.sort(key=lambda r: (r["first_usable_at"], r["rank"]["score"]), reverse=True)
        else:
            rows.sort(key=lambda r: (r["rank"]["score"], r["first_usable_at"]), reverse=True)
        return {"view": view.upper(), "clusters": rows,
                "sort": sort, "ranking": {"material_threshold": ranking["material_threshold"],
                                          "method": "Sum of: names a listed company, names a company held or proposed, category weight, repeats, minus a routine-announcement penalty. Weights in config/news_rules.yaml"},
                "note": "Why it may matter is a general description. Implications are untested hypotheses. What prices did is an observation, not proof of cause"}

    @app.get("/api/reasoning")
    def reasoning(symbol: str):
        now = clock()
        def run(store, master):
            def freshness(iid):
                obs = store.as_of(now).series(iid, "close")
                return {"last_close_date": obs[-1].event_time.date().isoformat(), "usable_from": obs[-1].first_usable_at.isoformat(),
                        "vendor": obs[-1].vendor} if obs else {"status": "NOT AVAILABLE"}
            return explain(symbol.upper(), now, journal, audit, research, news, master.instrument_for_symbol, freshness)
        out = with_store(run)
        return out or {"symbol": symbol, "status": "NOT AVAILABLE", "reason": "Price data is busy or missing"}

    @app.get("/api/replay")
    def replay(symbol: str, cursor: str):
        when = datetime.fromisoformat(cursor)
        if when.tzinfo is None:
            raise HTTPException(400, "cursor needs a time zone")
        if when > clock():
            raise HTTPException(400, "a replay cannot start in the future")
        out = with_store(lambda store, master: Replay(store, news, master, when, clock()).view(symbol.upper()))
        return out or {"status": "NOT AVAILABLE", "reason": "Price data is busy or missing"}

    @app.post("/api/predictions")
    def predict(body: PredictionBody):
        wall = clock()
        made = datetime.fromisoformat(body.replay_cursor) if body.replay_cursor else wall
        def run(store, master):
            pid = preds.add(USER, body.symbol.upper(), master, body.direction, body.horizon_days, body.probability, made,
                            wall, "replay" if body.replay_cursor else "live")
            preds.resolve(store, wall)
            return pid
        try:
            pid = with_store(run)
        except PredictionError as exc:
            raise HTTPException(400, str(exc))
        if pid is None:
            raise HTTPException(503, "price data is busy")
        return {"prediction_id": pid}

    @app.get("/api/predictions")
    def predictions(cursor: Optional[str] = None):
        from datetime import timedelta
        with_store(lambda store, master: preds.resolve(store, clock()))
        limit = datetime.fromisoformat(cursor) if cursor else None
        rows = preds.list(USER)
        for r in rows:
            due = datetime.fromisoformat(r["made_at"]) + timedelta(days=r["horizon_days"])
            if r["context"] == "replay" and (limit is None or due > limit):
                r["outcome"] = None
                r["status"] = "NOT YET REVEALED"
            else:
                r["status"] = "RESOLVED" if r["outcome"] is not None else "OPEN"
        cal = preds.calibration(USER, replay_clock=limit)
        return {"predictions": rows, "calibration": {"bins": cal.bins, "brier": cal.brier,
                                                     "baseline_brier": cal.baseline_brier, "resolved": cal.resolved}}

    @app.get("/api/global")
    def global_view():
        import json as _json

        from ..core.capabilities import load_capabilities
        from ..global_research import load_fx
        from ..jobs import read_heartbeat
        from ..sources import fx as fxmod

        table = load_fx(workdir)
        rates = []
        for cur, (series, inverted) in fxmod.SERIES.items():
            days = sorted(table.rates.get(cur, {}))
            rates.append({"currency": cur, "series": series, "date": days[-1].isoformat() if days else None,
                          "usd_per_unit": table.usd_per_unit(cur, days[-1]) if days else None})
        evidence_path = workdir / "global" / "momentum_by_market.json"
        evidence = _json.loads(evidence_path.read_text()) if evidence_path.exists() else []
        sessions = [{"slot": s, "utc": t, "last_run": (read_heartbeat(workdir / "heartbeats" / n) or {}).get("finished_at"),
                     "status": (read_heartbeat(workdir / "heartbeats" / n) or {}).get("status", "NOT RUN"), "job": n}
                    for s, t in cfg.markets.sessions_utc.items() for n in [{"asia_pacific": "global_factors", "europe": "fx",
                                                                             "us": "record", "overnight_review": "review"}[s]]]
        caps = load_capabilities()
        entitlements = [{"capability": k, "status": v.status.value, "label": v.label} for k, v in caps.capabilities.items()]
        rules_path = Path(__file__).resolve().parents[2] / "config" / "markets.yaml"
        markets = []
        if rules_path.exists():
            import yaml as _yaml
            markets = _yaml.safe_load(rules_path.read_text()).get("exchanges", [])
        from ..global_research import macro_view
        macro = with_store(lambda store, master: macro_view(store, cfg, clock()))
        return {"sessions": sessions, "fx": rates, "momentum_by_market": evidence, "entitlements": entitlements,
                "markets": markets, "macro": macro if macro is not None else []}

    @app.get("/api/bars/{symbol}")
    def bars_view(symbol: str, days: int = 260):
        """Daily candles known at the clock: open, high, low and close adjusted for splits and dividends
        with the same factor as the close, volume as reported."""
        from ..data.adjust import adjust_closes
        sym, now = symbol.upper(), clock()

        def run(store, master):
            iid = master.instrument_for_symbol(sym)
            if iid is None:
                return {"symbol": sym, "status": "NOT AVAILABLE", "reason": f"{sym} is not in the recorded data"}
            view = store.as_of(now)
            fields = {f: {o.event_time.date(): o.value for o in view.series(iid, f)} for f in ("open", "high", "low", "volume")}
            closes = view.series(iid, "close")[-max(1, min(days, 5000)):]
            raw = [(o.event_time.date(), o.value) for o in closes]
            adj = dict(adjust_closes(raw, master.actions(iid), now.date()))
            rows, missing = [], 0
            for d, c in raw:
                f = adj[d] / c if c else 1.0
                o_, h, l = fields["open"].get(d), fields["high"].get(d), fields["low"].get(d)
                if None in (o_, h, l):
                    missing += 1
                    o_ = h = l = c  # shown as a flat bar and counted below, never invented as a range
                rows.append({"date": d.isoformat(), "open": o_ * f, "high": h * f, "low": l * f, "close": adj[d],
                             "volume": fields["volume"].get(d)})
            return {"symbol": sym, "status": "OK", "bars": rows, "missing_ohlc": missing,
                    "source": closes[-1].vendor if closes else None,
                    "note": "Prices adjusted for splits and dividends. Volume as reported. Daily bars only"}
        return with_store(run) or {"symbol": sym, "status": "NOT AVAILABLE", "reason": "Price data is busy or missing"}

    @app.get("/api/company/{symbol}")
    def company_view(symbol: str):
        """Company intelligence page. Every metric has a source, a period and its age in days."""
        import yaml as _yaml
        from .. import company as co
        from ..data.adjust import adjust_closes
        from ..sources.trials import as_of as trials_as_of
        sym, now = symbol.upper(), clock()
        ff12 = {i["code"]: i["name"] for i in _yaml.safe_load(
            (Path(__file__).resolve().parents[2] / "config" / "ff12_sic.yaml").read_text())["industries"]}

        def run(store, master):
            iid = master.instrument_for_symbol(sym)
            if iid is None:
                rows = store.connection.execute("SELECT instrument_id FROM issuers WHERE upper(ticker) = ?", [sym]).fetchall()
                iid = rows[0][0] if rows else None
            if iid is None:
                return {"symbol": sym, "status": "NOT AVAILABLE", "reason": f"{sym} is not in the recorded data or the SEC issuer list"}
            prof = master.profile(iid, now) or {}
            inst = next((i for i in master.instruments() if i["instrument_id"] == iid), {})
            view = store.as_of(now)
            obs = view.series(iid, "close")
            vols = {o.event_time.date(): o.value for o in view.series(iid, "volume")}
            adj = [c for _, c in adjust_closes([(o.event_time.date(), o.value) for o in obs], master.actions(iid), now.date())]
            price = None
            if obs:
                price = {"value": obs[-1].value, "date": obs[-1].event_time.date().isoformat(), "source": obs[-1].vendor,
                         "as_of_dt": obs[-1].first_usable_at}
            fund = co.fundamentals(store, iid, now)
            sector = master.sector_at(iid, now)
            tag = master.tag(iid, cfg.markets.us_exchanges) if inst else "research_only"
            synthetic = bool(obs) and obs[-1].vendor.endswith("synthetic")
            catalysts = [{"event": f"Trial {t['nct_id']} primary completion", "date": t["primary_completion"],
                          "detail": f"{t['phases'] or 'phase not given'}, {t['overall_status']}, date {(t['primary_completion_type'] or '').lower() or 'type not given'}",
                          "source": "ClinicalTrials.gov, recorded " + t["observed_at"][:10]}
                         for t in trials_as_of(store.connection, now, iid) if t.get("primary_completion")]
            filed = [m for m in fund.values() if m.get("status") == "OK"]
            return {
                "symbol": sym, "status": "OK", "instrument_id": iid,
                "profile": {
                    "name": prof.get("name") or inst.get("name") or sym,
                    "description": (f"{prof['sicDescription']} (SEC industry code {prof.get('sic')})" if prof.get("sicDescription")
                                    else "NOT AVAILABLE. No SEC industry description recorded"),
                    "industry": ff12.get(sector, "Not classified"), "industry_code": sector,
                    "revenue_model": "NOT AVAILABLE. No verified source. The 10-K business section (Item 1) is not parsed",
                    "state_of_incorporation": prof.get("stateOfIncorporation"), "fiscal_year_end": prof.get("fiscalYearEnd"),
                    "exchanges": prof.get("exchanges"), "source": prof.get("_source", "NOT AVAILABLE"), "observed_at": prof.get("_observed_at"),
                },
                "price": {k: v for k, v in (price or {}).items() if k != "as_of_dt"} or None,
                "fundamentals": fund, "valuation": co.valuation(fund, price, now),
                "latest_filing": max((m["as_of"] for m in filed), default=None),
                "risks": co.risks(adj, [vols.get(o.event_time.date(), 0.0) for o in obs], [o.value for o in obs], tag, synthetic, cfg),
                "catalysts": catalysts,
                "catalyst_note": "No free earnings or event calendar. Upcoming dates come only from recorded clinical trials",
                "tag": tag, "synthetic": synthetic, "has_prices": bool(obs),
            }
        out = with_store(run) or {"symbol": sym, "status": "NOT AVAILABLE", "reason": "Data is busy or missing"}
        if out.get("status") == "OK":
            out["news"] = news_view(view="recent", ticker=sym)["clusters"][:6]
            stock = stock_view(sym) if out.pop("has_prices") else {}
            try:
                why = reasoning(sym).get("why_not")
            except Exception:
                why = None
            out["signals"] = {"system_view": stock.get("system_view", "NOT AVAILABLE. No recorded prices, so the trend model has no reading"),
                              "signal": stock.get("signal"), "composite_score": stock.get("composite_score"),
                              "proposal": stock.get("proposal"), "why_not": why}
        return out

    @app.get("/api/stock/{symbol}")
    def stock_view(symbol: str):
        """Everything about one ticker in plain words, built only from recorded data."""
        import math
        import yaml as _yaml
        from ..data.adjust import adjust_closes
        from ..models import ts_momentum
        sym = symbol.upper()
        now = clock()
        ff12 = {i["code"]: i["name"] for i in _yaml.safe_load(
            (Path(__file__).resolve().parents[2] / "config" / "ff12_sic.yaml").read_text())["industries"]}

        def run(store, master):
            iid = master.instrument_for_symbol(sym)
            if iid is None:
                return {"symbol": sym, "status": "NOT AVAILABLE", "reason": f"{sym} is not in the recorded data"}
            inst = next((i for i in master.instruments() if i["instrument_id"] == iid), {})
            names = [n for _, n in master.entity_names(iid)]
            sector = master.sector_at(iid, now)
            obs = store.as_of(now).series(iid, "close")
            adj = [c for _, c in adjust_closes([(o.event_time.date(), o.value) for o in obs], master.actions(iid), now.date())]

            def change(days):
                return adj[-1] / adj[-1 - days] - 1 if len(adj) > days and adj[-1 - days] else None
            rets = [b / a - 1 for a, b in zip(adj[-64:-1], adj[-63:]) if a]
            vol = (sum((r - sum(rets) / len(rets)) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5 * math.sqrt(252) if len(rets) > 2 else None
            m = cfg.models.ts_momentum
            signal = ts_momentum.score(adj, m)
            trend = None
            if len(adj) > m.lookback_days:
                past = adj[-1 - m.lookback_days]
                recent = adj[-1 - m.skip_days]
                trend = recent / past - 1 if past else None
            if signal is None:
                view = "NOT AVAILABLE. Less than a year of recorded prices, so the trend model has no reading"
            else:
                direction = "rose" if (trend or 0) > 0 else "fell"
                view = (f"Over the past year, leaving out the last month, the price {direction} {abs(trend or 0) * 100:.1f}%. "
                        f"The trend model reads this as {'an uptrend' if signal > 0 else 'a downtrend'} "
                        f"with strength {signal:.2f} on a scale of -{m.clip:.0f} to +{m.clip:.0f}. "
                        + ("It only buys uptrends, so this name is a buy candidate." if signal > 0
                           else "It only buys uptrends, so it would not buy this name now."))
            latest = [p for p in journal.proposals() if p.symbol == sym]
            prop = latest[-1] if latest else None
            run_rec = research.latest_run() or {}
            score = next((x["score"] for x in run_rec.get("scores", []) if x["symbol"] == sym), None)
            tag = master.tag(iid, cfg.markets.us_exchanges)
            return {
                "symbol": sym, "status": "OK", "instrument_id": iid,
                "name": names[0] if names else inst.get("name") or sym,
                "type": inst.get("security_type"), "type_inferred": inst.get("type_inferred"),
                "industry": {"code": sector, "plain": ff12.get(sector, "Not classified. No SEC industry code recorded")},
                "price": {"last": obs[-1].value if obs else None, "date": obs[-1].event_time.date().isoformat() if obs else None,
                          "source": obs[-1].vendor if obs else None,
                          "change": {"1 day": change(1), "1 month": change(21), "3 months": change(63), "1 year": change(252)},
                          "volatility_annual": vol},
                "history": [{"date": o.event_time.date().isoformat(), "close": o.value} for o in obs[-260:]],
                "system_view": view, "signal": signal, "composite_score": score,
                "proposal": {"session_date": prop.session_date, "side": prop.side, "quantity": prop.quantity,
                             "status": prop.status} if prop else None,
                "can_trade": tag in ("direct", "proxy"),
                "tag_note": {"direct": "Can be traded in the simulator and the paper account",
                             "proxy": "Traded as a stand-in for another exposure",
                             "research_only": "Research only. Orders are blocked"}.get(tag, tag),
            }
        out = with_store(run)
        if out is None:
            return {"symbol": sym, "status": "NOT AVAILABLE", "reason": "Price data is busy or missing"}
        if out["status"] == "OK":
            out["news"] = news_view(view="recent", ticker=sym)["clusters"][:5]
        return out

    @app.get("/api/autopsy")
    def autopsy_view():
        rows = with_store(lambda store, master: lab.autopsy(journal, audit.records(), store, master, cfg, clock()))
        return {"rows": rows if rows is not None else [], "status": "OK" if rows is not None else "NOT AVAILABLE"}

    @app.get("/api/counterfactual")
    def counterfactual_view(symbol: str, change: str, amount: float = 0.0):
        try:
            out = with_store(lambda store, master: lab.counterfactual(store, master, cfg, symbol.upper(), clock(), change, amount))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return out or {"label": lab.HYPOTHETICAL, "status": "NOT AVAILABLE", "reason": "Price data is busy or missing"}

    @app.get("/api/review")
    def review_due(cursor: Optional[str] = None):
        limit = datetime.fromisoformat(cursor) if cursor else None
        review.sync(USER, preds.list(USER), glossary_terms, clock(), replay_clock=limit)
        return {"cards": review.due(USER, clock())}

    @app.post("/api/review/{card_id}")
    def review_answer(card_id: str, body: ReviewBody):
        try:
            return review.answer(USER, card_id, body.correct, clock())
        except KeyError:
            raise HTTPException(404, "unknown card")

    @app.get("/api/lesson")
    def lesson_view():
        out = with_store(lambda store, master: lab.daily_lesson(glossary, store, master, clock()))
        return out or {"status": "NOT AVAILABLE", "reason": "Price data is busy or missing"}

    @app.get("/api/concepts")
    def concepts_view():
        return {"order": lab.concept_order(glossary["prerequisites"]), "prerequisites": glossary["prerequisites"],
                "terms": {k: v["plain"] for k, v in glossary_terms.items()}}

    @app.post("/api/lab/design")
    def lab_design(body: IdeaBody):
        from ..teaching import experiment_lab
        try:
            out = with_store(lambda store, master: experiment_lab.design(body.idea, store, master, cfg, clock()))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return out or {"status": "NOT AVAILABLE", "reason": "Price data is busy or missing"}

    @app.post("/api/lab/submit")
    def lab_submit(body: IdeaBody):
        """Designed again on the server, so the submitted plan is exactly what the rules produce."""
        from ..teaching import experiment_lab
        designed = lab_design(body)
        if designed.get("status") != "DESIGNED":
            raise HTTPException(400, designed.get("request") or designed.get("reason", "not designed"))
        return {**experiment_lab.submit(designed, research, cfg, clock()), "plan": designed["plan"]}

    @app.get("/api/crises")
    def crises_view():
        rows = with_store(lambda store, master: lab.crisis_library(store, list(cfg.teaching.crises), clock()))
        return {"episodes": rows if rows is not None else []}

    @app.get("/api/intelligence/ownership")
    def ownership_view(symbol: Optional[str] = None):
        """Insider transactions, large-holder filings and 13F holdings as disclosed by the clock. Research only."""
        from ..core.capabilities import load_capabilities
        from ..sources import ownership as own
        now = clock()
        caps = load_capabilities()
        modules = ["insider_transactions", "institutional_holdings", "large_holder_filings", "congressional_disclosures",
                   "government_procurement", "regulatory_actions", "political_sector_exposure"]

        def run(store, master):
            cik = None
            if symbol:
                rows = store.connection.execute("SELECT cik FROM issuers WHERE upper(ticker) = ?", [symbol.upper()]).fetchall()
                cik = rows[0][0] if rows else None
            holdings = own.holdings_as_of(store.connection, now)
            return {"insiders": own.insiders_as_of(store.connection, now, symbol)[:200],
                    "large_holders": own.large_holders_as_of(store.connection, now, cik)[:50],
                    "holdings": holdings[:200], "holdings_total": len(holdings)}
        data = with_store(run) or {"insiders": [], "large_holders": [], "holdings": [], "holdings_total": 0}
        return {**data, "symbol": symbol, "research_only": True,
                "sources": [{"module": m, "status": caps.get(m).status.value, "label": caps.get(m).label} for m in modules],
                "caveats": ["Transaction or quarter-end dates and disclosure dates are shown separately. Records count only from disclosure",
                            "A 13F is a delayed snapshot of long positions. It is not a complete or current portfolio and not evidence of skill",
                            "Sales flagged as 10b5-1 were scheduled in advance under a trading plan",
                            "Nothing here feeds an order until a pre-registered test passes"]}

    @app.get("/api/asset-classes")
    def asset_classes():
        """Each asset class with what the capability registry allows: research, historical prices, paper execution."""
        import yaml as _yaml
        from ..core.capabilities import load_capabilities
        caps = load_capabilities()
        spec = _yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "asset_classes.yaml").read_text())["asset_classes"]

        def facet(name):
            c = caps.get(name)
            return {"capability": name, "status": c.status.value, "label": c.label, "reason": c.reason,
                    "usable": c.status.value in ("available", "limited")}
        out = []
        for a in spec:
            row = {"id": a["id"], "label": a["label"], "research": facet(a["research"]), "history": facet(a["history"]),
                   "paper_execution": facet(a["paper_execution"]), "extra": [facet(x) for x in a.get("extra", [])]}
            row["summary"] = ("Paper trading" if row["paper_execution"]["usable"] else
                              "Research only" if row["research"]["usable"] or row["history"]["usable"] else "No usable data")
            out.append(row)
        return {"asset_classes": out, "note": "From config/capabilities.yaml. No market prices, Greeks or forecasts are shown where data is not available"}

    @app.get("/api/inbox")
    def inbox_list():
        return {"captures": inbox.list(), "auto_fetch_hosts": list(cfg.research.inbox.auto_fetch_hosts)}

    @app.post("/api/inbox")
    def inbox_add(body: CaptureBody):
        try:
            return inbox.capture(body.kind, clock(), body.content, body.url, body.filename)
        except (InboxError, ValueError) as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/opportunities")
    def opportunities():
        from ..models.registry import load_models
        props = journal.proposals()
        latest = max((p.session_date for p in props), default=None)
        models = load_models()
        rows = []
        for p in props:
            if p.session_date != latest:
                continue
            try:
                entry = models.get(p.model_id)
                tier = entry.tier
            except KeyError:
                tier = None
            rows.append({"proposal_id": p.proposal_id, "symbol": p.symbol, "side": p.side, "quantity": p.quantity,
                         "signal_strength": p.signal_strength, "expected_return": "NOT AVAILABLE. The model is not calibrated",
                         "entry": "Limit order priced from a fresh quote at execution", "model": f"{p.model_id} {p.model_version}",
                         "tier": tier, "status": p.status, "risk": p.reason.split(chr(10))[0] if p.reason else "",
                         "instrument_id": p.instrument_id, "decision_date": p.decision_date})
        now = clock()

        def metrics(store, master):
            import math
            from ..data.adjust import adjust_closes
            n = cfg.universe.dollar_volume_window_days
            for r in rows:
                obs = store.as_of(now).series(r["instrument_id"], "close")
                vols = store.as_of(now).series(r["instrument_id"], "volume")[-n:]
                adj = [c for _, c in adjust_closes([(o.event_time.date(), o.value) for o in obs], master.actions(r["instrument_id"]), now.date())]
                ch = lambda k: adj[-1] / adj[-1 - k] - 1 if len(adj) > k and adj[-1 - k] else None
                rets = [b / a - 1 for a, b in zip(adj[-64:-1], adj[-63:]) if a]
                m = sum(rets) / len(rets) if rets else 0.0
                vol = math.sqrt(sum((x - m) ** 2 for x in rets) / (len(rets) - 1) * 252) if len(rets) > 2 else None
                closes_by_day = {o.event_time.date(): o.value for o in obs}
                dv = sorted(v.value * closes_by_day.get(v.event_time.date(), 0.0) for v in vols)
                r["metrics"] = {"change_1m": ch(21), "change_1y": ch(252), "volatility_annual": vol,
                                "median_dollar_volume_20d": dv[len(dv) // 2] if dv else None,
                                "price": obs[-1].value if obs else None,
                                "as_of": obs[-1].event_time.date().isoformat() if obs else None,
                                "source": obs[-1].vendor if obs else None}
                r["direction"] = {"buy": "Long", "sell": "Exit long", "sell_short": "Short", "buy_to_cover": "Exit short"}.get(r["side"], r["side"])
                r["horizon"] = "About one month, re-decided each trading day" if r["model"].startswith("ts_momentum") else "NOT AVAILABLE"
            return True
        with_store(metrics)
        return {"session_date": latest, "venue": venue, "rows": rows,
                "note": "Signal strength ranks names. It is not a forecast return or a probability"}

    @app.get("/api/markets")
    def markets(symbol: Optional[str] = None):
        def run(store, master):
            insts = []
            for i in master.instruments():
                syms = master.symbols(i["instrument_id"])
                insts.append({"instrument_id": i["instrument_id"], "symbol": syms[-1] if syms else i["instrument_id"],
                              "name": i["name"], "type": i["security_type"], "type_inferred": i["type_inferred"],
                              "tag": master.tag(i["instrument_id"], cfg.markets.us_exchanges),
                              "sector": master.sector_at(i["instrument_id"], clock()),
                              "status": master.status(i["instrument_id"]) or "unknown"})
            sel = next((x for x in insts if x["symbol"] == (symbol or "").upper()), insts[0] if insts else None)
            history = []
            if sel:
                history = [{"date": o.event_time.date().isoformat(), "close": o.value, "vendor": o.vendor}
                           for o in store.as_of(clock()).series(sel["instrument_id"], "close")[-250:]]
            run_rec = research.latest_run() or {}
            score = next((s["score"] for s in run_rec.get("scores", []) if sel and s["symbol"] == sel["symbol"]), None)
            from ..sources.trials import as_of as trials_as_of
            trial_rows = trials_as_of(store.connection, clock(), sel["instrument_id"]) if sel else []
            return {"instruments": insts, "selected": sel, "history": history, "composite_score": score,
                    "trials": [{k: t[k] for k in ("nct_id", "title", "overall_status", "phases", "primary_completion",
                                                   "primary_completion_type", "enrollment", "observed_at")} for t in trial_rows]}
        return with_store(run) or {"status": "NOT AVAILABLE", "reason": "Price data is busy or missing"}

    @app.get("/api/backtests")
    def backtests():
        run_rec = research.latest_run() or {}
        vt = cfg.composite.research_portfolio.vol_target_annual
        rows = []
        for s in run_rec.get("signals", []):
            p = s.get("platform") or {}
            mean = p.get("mean_annual")
            rows.append({"signal_id": s["signal_id"], "days": p.get("days"), "mean_annual": mean, "se_annual": p.get("se_annual"),
                         "sharpe": (mean / vt) if mean is not None and p.get("days", 0) > 30 else None,
                         "lower_90_double_cost": p.get("economic_lower_90"), "economic_pass": p.get("economic_pass"),
                         "data_labels": s.get("data_labels"), "record_type": s.get("record_type"), "summary": s["scores"]["economic"]})
        return {"trial_count": research.variant_count(), "rows": rows,
                "method": f"Walk-forward research portfolios scaled to {vt * 100:.0f}% annual volatility, net of modeled costs. The lower bound uses double costs",
                "holdout": "NOT AVAILABLE. No holdout period has been reserved yet"}

    @app.get("/api/experts")
    def experts():
        from ..core.licenses import load_licenses
        lic = load_licenses()
        sources = [{"license": k, "description": v.description, "research": v.research.value,
                    "paper_trading": v.paper_trading.value, "note": v.note} for k, v in lic.licenses.items()]
        return {"sources": sources, "practitioners": [],
                "practitioner_note": "NOT AVAILABLE. No practitioner has scored claims yet. A domain needs 30 before it can become a signal"}

    @app.get("/api/audit")
    def audit_view(limit: int = 200):
        recs = audit.records()[-limit:]
        try:
            limits = risk._call("GET", "/limits")
        except Exception:
            limits = None
        from ..core.parameters import load_registry
        reg = load_registry()
        params = [{"path": p, "basis": v.basis.value, "label": v.label, "note": v.review or v.change_policy or v.source}
                  for p, v in reg.parameters.items()]
        return {"chain_ok": audit.verify() is None, "records": [
            {"seq": r["seq"], "time": r["event_time_utc"], "actor": r["actor"], "event": r["event_type"], "entity": r["entity_id"]}
            for r in reversed(recs)], "limits": limits, "parameters": params}

    @app.post("/api/limits/request")
    def limit_request(body: LimitBody):
        try:
            return risk._call("POST", "/limits/request", {"key": body.key, "value": body.value, "actor": USER})
        except Exception as exc:
            raise HTTPException(400, _refusal(exc))

    @app.post("/api/limits/confirm")
    def limit_confirm(body: LimitBody):
        try:
            return risk._call("POST", "/limits/confirm", {"key": body.key, "actor": USER})
        except Exception as exc:
            raise HTTPException(400, _refusal(exc))

    @app.get("/api/settings")
    def settings():
        import os
        creds = [{"name": n, "purpose": p, "status": "SET" if os.environ.get(n) else "NOT SET"} for n, p in (
            ("APCA_API_KEY_ID", "Alpaca paper key ID"), ("APCA_API_SECRET_KEY", "Alpaca paper secret"),
            ("SEC_USER_AGENT", "SEC contact for EDGAR requests"), ("FRED_API_KEY", "FRED API key for macro vintages"))]
        return {"mode": cfg.execution.mode, "venue": venue, "live_trading": "Not built. Every live route rejects orders",
                "credentials": creds, "monthly_cost_usd": 0, "config_version": cfg.config_version,
                "providers": [f.name for f in cfg.news.feeds] + ["alpaca free plan", "sec edgar", "fred", "osap", "jkp"]}

    @app.post("/api/proposals/{pid}/approve")
    def approve(pid: str):
        try:
            journal.approve(pid, USER, clock())
        except KeyError:
            raise HTTPException(404, "unknown proposal")
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {"status": journal.proposal(pid).status}

    @app.post("/api/proposals/{pid}/reject")
    def reject(pid: str, body: RejectBody = RejectBody()):
        try:
            journal.reject(pid, USER, clock(), body.reason)
        except KeyError:
            raise HTTPException(404, "unknown proposal")
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {"status": journal.proposal(pid).status}

    @app.post("/api/kill-switch")
    def kill_switch(body: KillSwitchBody):
        try:
            return {"kill_switch": risk.set_kill_switch(body.engaged, USER)}
        except Exception as exc:
            raise HTTPException(503, f"risk service did not confirm ({type(exc).__name__})")

    from . import assets as assets_api
    app.include_router(assets_api.build(workdir, cfg, clock))

    if (UI_DIST / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            return FileResponse(UI_DIST / "index.html")

    return app
