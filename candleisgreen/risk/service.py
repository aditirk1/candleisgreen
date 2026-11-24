"""Risk service: a separate process that owns the kill switch and the limits.

Callers send an order intent and their view of the market. The service loads its own
limits from config, overrides the kill-switch field with its own state, and returns a
decision. It never talks to a broker. Run:

    python -m candleisgreen.risk.service --port 8765 --state-dir var/risk
"""
from __future__ import annotations

import argparse
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from ..core.audit import AuditLog
from ..core.config import AppConfig, load_config
from ..core.schemas import OrderIntent, RiskContext
from ..core.timeutil import utc_now
from .engine import evaluate, evaluate_portfolio, limits_hash

ALLOWED_DISENGAGE_ACTORS = ("user:aditi",)


class RiskState:
    def __init__(self, state_dir: Path, cfg: AppConfig):
        self.dir = state_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg
        self.path = self.dir / "kill_switch.json"
        self.lock = threading.Lock()
        self.audit = AuditLog(self.dir / "risk_audit.sqlite")

    def kill_switch(self) -> bool:
        if not self.path.exists():
            return False
        try:
            return bool(json.loads(self.path.read_text())["engaged"])
        except Exception:
            return True  # unreadable state fails closed

    def set_kill_switch(self, engaged: bool, actor: str) -> None:
        if not engaged and actor not in ALLOWED_DISENGAGE_ACTORS:
            raise PermissionError("only Aditi can release the kill switch")
        with self.lock:
            now = utc_now()
            self.path.write_text(json.dumps({"engaged": engaged, "actor": actor, "at": now.isoformat()}))
            self.audit.append(event_type="kill_switch", entity_id="kill_switch", payload={"engaged": engaged},
                              actor=actor, strategy_version=f"config:{self.cfg.config_version}",
                              event_time=now, received_time=now)


def make_handler(state: RiskState):
    limits = state.cfg.risk.hard_limits

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self):
            if self.path == "/health":
                self._send(200, {"ok": True, "limits_hash": limits_hash(limits), "kill_switch": state.kill_switch()})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            try:
                body = self._body()
                if self.path == "/evaluate":
                    intent = OrderIntent.model_validate(body["intent"])
                    ctx = RiskContext.model_validate({**body["context"], "kill_switch_engaged": state.kill_switch()})
                    self._send(200, {"decision": evaluate(intent, ctx, limits).model_dump(mode="json")})
                elif self.path == "/evaluate-book":
                    reasons = evaluate_portfolio(body["weights"], body["clusters"], limits, body.get("sectors"),
                                                 body.get("sector_cap"))
                    self._send(200, {"reasons": list(reasons)})
                elif self.path == "/kill-switch":
                    state.set_kill_switch(bool(body["engaged"]), str(body.get("actor", "")))
                    self._send(200, {"kill_switch": state.kill_switch()})
                else:
                    self._send(404, {"error": "not found"})
            except PermissionError as exc:
                self._send(403, {"error": str(exc)})
            except Exception as exc:  # malformed input is refused, never approved
                self._send(400, {"error": f"{type(exc).__name__}: {exc}"})

    return Handler


def serve(port: int, state_dir: Path, cfg: Optional[AppConfig] = None) -> ThreadingHTTPServer:
    state = RiskState(state_dir, cfg or load_config())
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))


def main() -> None:
    parser = argparse.ArgumentParser(description="CandleIsGreen risk service. Paper only.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-dir", default="var/risk")
    args = parser.parse_args()
    server = serve(args.port, Path(args.state_dir))
    print(f"risk service listening on 127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
