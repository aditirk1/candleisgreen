"""Run the workstation API on localhost: python -m candleisgreen.api --workdir var/demo --risk-url http://127.0.0.1:8765"""
import argparse
from pathlib import Path

import uvicorn

from ..core.config import load_config
from .app import create_app

parser = argparse.ArgumentParser()
parser.add_argument("--workdir", default="var/demo")
parser.add_argument("--risk-url", default="http://127.0.0.1:8765")
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--mode", default=None, help="operating mode shown and enforced, for example manual_simulation")
args = parser.parse_args()
cfg = load_config()
if args.mode:
    cfg = cfg.model_copy(update={"execution": cfg.execution.model_copy(update={"mode": args.mode})})
uvicorn.run(create_app(Path(args.workdir), args.risk_url, cfg), host="127.0.0.1", port=args.port, log_level="warning")
