"""Asset classes come from the capability registry. Nothing unsupported is offered or invented."""
import yaml
from fastapi.testclient import TestClient

from candleisgreen.api.app import create_app
from candleisgreen.core.capabilities import load_capabilities
from candleisgreen.core.config import load_config
from tests.phase1_env import ROOT, EXEC_NOW


def test_every_facet_names_a_real_capability():
    caps = load_capabilities()
    for a in yaml.safe_load((ROOT / "config" / "asset_classes.yaml").read_text())["asset_classes"]:
        for name in [a["research"], a["history"], a["paper_execution"], *a.get("extra", [])]:
            caps.get(name)  # raises for an unknown name


def test_only_stocks_can_be_paper_traded(tmp_path):
    api = TestClient(create_app(tmp_path, "http://127.0.0.1:9", load_config(), clock=lambda: EXEC_NOW))
    rows = {a["id"]: a for a in api.get("/api/asset-classes").json()["asset_classes"]}
    assert set(rows) == {"stocks_etfs", "options", "futures", "forex", "crypto"}
    assert rows["stocks_etfs"]["summary"] == "Paper trading" and rows["stocks_etfs"]["paper_execution"]["usable"]
    for k in ("options", "futures", "forex", "crypto"):
        assert not rows[k]["paper_execution"]["usable"]
        assert rows[k]["paper_execution"]["label"].startswith("NOT AVAILABLE")
    assert rows["forex"]["summary"] == "Research only"
    assert rows["options"]["summary"] == rows["futures"]["summary"] == rows["crypto"]["summary"] == "No usable data"
