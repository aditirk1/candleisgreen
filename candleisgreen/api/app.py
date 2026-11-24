"""Workstation API for the Overview and Execution screens. Binds to localhost only.

Writes only two things: approvals and rejections to the journal, and the kill switch to
the risk service. It never talks to a broker.
"""
from __future__ import annotations

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
from ..risk.client import RiskClient

USER = "user:aditi"
UI_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"


class KillSwitchBody(BaseModel):
    engaged: bool


class RejectBody(BaseModel):
    reason: str = "rejected by user"


def create_app(workdir: Path, risk_url: str, cfg: Optional[AppConfig] = None, clock=utc_now) -> FastAPI:
    cfg = cfg or load_config()
    workdir = Path(workdir)
    audit = AuditLog(workdir / "audit.sqlite")
    journal = Journal(workdir / "journal.sqlite", audit, cfg.execution.simulator_starting_equity_usd,
                      f"config:{cfg.config_version}:{cfg.config_hash}", shared_across_threads=True)
    risk = RiskClient(risk_url, timeout=2.0)
    research = ResearchRegistry(workdir / "research.sqlite", audit, shared_across_threads=True)
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
        return {"claims": claims, "experiments": research.experiments(), "failures": research.failures(),
                "trial_count": research.variant_count()}

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

    if (UI_DIST / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            return FileResponse(UI_DIST / "index.html")

    return app
