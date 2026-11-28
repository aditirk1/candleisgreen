"""The eight-level capability registry, and the asset API in offline conditions."""
import importlib

import yaml
from fastapi.testclient import TestClient

from candleisgreen.api.app import create_app
from candleisgreen.core.capabilities import LEVELS, LevelState, load_capabilities
from candleisgreen.core.config import load_config
from tests.phase1_env import EXEC_NOW, ROOT


def test_every_asset_class_has_all_eight_levels_and_no_live_trading():
    caps = load_capabilities()
    for a in yaml.safe_load((ROOT / "config" / "asset_classes.yaml").read_text())["asset_classes"]:
        lv = caps.get(a["capability"]).levels
        assert lv is not None
        assert lv.live_execution.state is LevelState.NO
        assert [k for k, _ in LEVELS] == list(type(lv).model_fields)


def test_every_module_a_level_names_exists():
    caps = load_capabilities()
    for name, cap in caps.capabilities.items():
        if not cap.levels:
            continue
        for key, _ in LEVELS:
            for mod in getattr(cap.levels, key).modules:
                importlib.import_module(mod)


def test_a_verified_level_carries_its_check_date():
    caps = load_capabilities()
    for cap in caps.capabilities.values():
        if cap.levels:
            for key in ("history_verified", "realtime_verified"):
                lvl = getattr(cap.levels, key)
                assert lvl.state is not LevelState.YES or lvl.checked


def test_asset_api_works_offline_and_says_what_is_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("OANDA_PRACTICE_TOKEN", raising=False)
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", load_config(), clock=lambda: EXEC_NOW))
    lv = api.get("/api/assets/levels").json()
    assert [a["id"] for a in lv["asset_classes"]] == ["stocks_etfs", "options", "futures", "forex", "crypto"]
    assert all(len(a["levels"]) == 8 and a["levels"][-1]["state"] == "no" for a in lv["asset_classes"])
    chain = api.get("/api/assets/options/chain", params={"underlying": "SPY"}).json()
    assert chain["status"] == "NOT AVAILABLE" and "APCA_API_KEY_ID" in chain["reason"]
    fx = api.get("/api/assets/forex").json()
    assert fx["status"] == "NOT AVAILABLE" and len(fx["steps"]) == 2
    c = api.get("/api/assets/crypto").json()
    assert not c["recorded"] and all(r["days"] == 0 for r in c["rows"])
    fut = api.get("/api/assets/futures").json()
    es = next(p for p in fut["products"] if p["code"] == "ES")
    assert es["verified"] is False and es["front"] == "ESZ26" and "cot" not in es


def test_strategy_and_model_endpoints(tmp_path):
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", load_config(), clock=lambda: EXEC_NOW))
    body = {"legs": [{"underlying": "SPY", "expiry": "2026-12-18", "kind": "call", "strike": 600, "quantity": 1, "premium": 10},
                     {"underlying": "SPY", "expiry": "2026-12-18", "kind": "call", "strike": 610, "quantity": -1, "premium": 6}]}
    p = api.post("/api/assets/options/strategy", json=body).json()
    assert p["max_loss"] == 400 and p["max_gain"] == 600 and p["breakevens"] == [604.0] and len(p["points"]) == 81
    bad = api.post("/api/assets/options/strategy", json={"legs": [{"symbol": "NOPE", "quantity": 1, "premium": 1}]})
    assert bad.status_code == 400
    m = api.get("/api/assets/options/model", params={"kind": "call", "spot": 100, "strike": 100, "days": 365, "volatility": 0.2, "rate": 0.05}).json()
    assert round(m["price"], 2) == 10.45 and "Not a market price" in m["label"]


def test_settlement_upload_builds_a_continuous_series(tmp_path):
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", load_config(), clock=lambda: EXEC_NOW.replace(year=2026, month=12, day=20)))
    text = "date,contract,settle\n2026-12-08,ESZ26,6000\n2026-12-08,ESH27,6050\n2026-12-11,ESZ26,6030\n2026-12-11,ESH27,6080\n2026-12-14,ESH27,6090\n"
    assert api.post("/api/assets/futures/settlements", json={"text": text}).json()["stored"] == 5
    out = api.get("/api/assets/futures/continuous", params={"product": "ES"}).json()
    assert out["status"] == "OK" and out["points"][0]["adjusted"] == 6050
    assert api.post("/api/assets/futures/settlements", json={"text": "date,contract,settle\nx,ESZ26,1\n"}).status_code == 400
