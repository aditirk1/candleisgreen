"""Spec v3.2 decisions Q3, Q4, Q9, Q10 and Q12."""
import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from candleisgreen.core.licenses import LicenseNotPermittedError, load_licenses
from candleisgreen.core.schemas import CalibrationStatus, Forecast, RecordType
from candleisgreen.core.timeutil import in_local_window

UTC = timezone.utc
AS_OF = datetime(2026, 11, 13, 21, 30, tzinfo=UTC)


def _forecast(**kw):
    base = dict(
        model_id="m", model_version="1", asset_id="a", issued_at=AS_OF, as_of=AS_OF,
        target_definition="t", target_start=AS_OF, target_end=AS_OF + timedelta(days=5),
        signal_strength=1.0, training_cutoff=AS_OF, data_snapshot_id="snap", feature_snapshot_id="feat",
        calibration_status=CalibrationStatus.SIGNAL_STRENGTH_ONLY, eligible_for_orders=False,
    )
    base.update(kw)
    return Forecast(**base)


# Q9: retrospective reconstructions stay apart from prospective forecasts -------------------

def test_late_forecast_cannot_be_labeled_prospective():
    with pytest.raises(ValidationError):
        _forecast(issued_at=AS_OF + timedelta(days=30))
    retro = _forecast(issued_at=AS_OF + timedelta(days=30), record_type=RecordType.RETROSPECTIVE)
    assert retro.record_type is RecordType.RETROSPECTIVE


def test_retrospective_forecast_can_never_trade():
    with pytest.raises(ValidationError):
        _forecast(issued_at=AS_OF + timedelta(days=30), record_type=RecordType.RETROSPECTIVE,
                  eligible_for_orders=True)


def test_record_type_changes_the_forecast_id():
    a = _forecast(issued_at=AS_OF + timedelta(days=1), target_start=AS_OF + timedelta(days=2),
                  target_end=AS_OF + timedelta(days=7))
    b = _forecast(issued_at=AS_OF + timedelta(days=1), target_start=AS_OF + timedelta(days=2),
                  target_end=AS_OF + timedelta(days=7), record_type=RecordType.RETROSPECTIVE)
    assert a.forecast_id != b.forecast_id


# Q3: license tags travel with data and block unverified trading use ---------------------

def test_noncommercial_data_is_research_only_until_checked():
    reg = load_licenses()
    reg.assert_use(["cc_by_nc_4_0"], "research")
    with pytest.raises(LicenseNotPermittedError, match="unverified"):
        reg.assert_use(["cc_by_nc_4_0"], "paper_trading")
    with pytest.raises(LicenseNotPermittedError, match="not in config"):
        reg.assert_use(["mystery_license"], "research")
    with pytest.raises(LicenseNotPermittedError, match="no license"):
        reg.assert_use([], "paper_trading")


def test_a_jkp_derived_forecast_cannot_become_an_order():
    from candleisgreen.core.schemas import Venue
    from candleisgreen.models import fixture_baseline
    from candleisgreen.pipeline import build_intent

    fc = _forecast(model_id="jkp_study", eligible_for_orders=True, data_licenses=("cc_by_nc_4_0", "synthetic"))
    with pytest.raises(LicenseNotPermittedError):
        build_intent(fc, 10.0, "2026-11-16", Venue.SIMULATION, 51.0)
    assert fixture_baseline.MODEL_ID != "jkp_study"


# Q4: the execution window ------------------------------------------------------------------

def test_execution_window_in_both_seasons():
    tz = "America/New_York"
    assert in_local_window(datetime(2026, 11, 16, 14, 40, tzinfo=UTC), "09:35", "10:30", tz)  # 09:40 EST
    assert not in_local_window(datetime(2026, 11, 16, 14, 30, tzinfo=UTC), "09:35", "10:30", tz)  # 09:30 EST
    assert in_local_window(datetime(2026, 7, 1, 13, 40, tzinfo=UTC), "09:35", "10:30", tz)  # 09:40 EDT
    assert not in_local_window(datetime(2026, 7, 1, 14, 30, tzinfo=UTC), "09:35", "10:30", tz)  # 10:30 EDT


def test_order_outside_the_window_is_blocked_end_to_end(tmp_path):
    import json

    from candleisgreen.pipeline import run_offline_event
    from tests.conftest import FIXTURE

    payload = json.loads(FIXTURE.read_text())
    payload["execution"]["now"] = "2026-11-16T16:00:00Z"  # 11:00 ET
    payload["execution"]["quote"]["quote_time"] = "2026-11-16T15:59:58Z"
    path = tmp_path / "late.json"
    path.write_text(json.dumps(payload))
    result = run_offline_event(path, tmp_path / "run")
    assert result["risk_verdict"] == "blocked" and result["fill_ids"] == []
    assert any("execution window" in r for r in result["risk_reasons"])


def test_delayed_consolidated_quote_blocks_end_to_end(tmp_path):
    import json

    from candleisgreen.pipeline import run_offline_event
    from tests.conftest import FIXTURE

    payload = json.loads(FIXTURE.read_text())
    payload["execution"]["quote"]["feed"] = "sip_delayed"
    path = tmp_path / "delayed.json"
    path.write_text(json.dumps(payload))
    result = run_offline_event(path, tmp_path / "run")
    assert result["risk_verdict"] == "blocked"
    assert any("not execution grade" in r for r in result["risk_reasons"])


# Q10: unknown classifications cannot evade a cap -------------------------------------------

def test_unknown_sectors_share_one_capped_bucket():
    from candleisgreen.composite import optimizer

    groups = optimizer._groups(["tech", None, "", "  ", "UNKNOWN", "tech"])
    sizes = sorted(len(g) for g in groups)
    assert sizes == [2, 4]  # four unknowns pooled into one group


def test_optimizer_caps_the_unknown_bucket():
    from candleisgreen.composite import optimizer, riskmodel
    from candleisgreen.core.config import load_config

    cfg = load_config()
    rng = np.random.default_rng(40)
    n = 30
    daily = rng.normal(0, 0.01, (300, 1)) * rng.uniform(0.5, 1.5, n) + rng.normal(0, 0.015, (300, n))
    model = riskmodel.fit(daily, cfg.composite.optimizer)
    alpha = np.full(n, 0.001)
    alpha[:12] = 0.05  # strong alpha on the names with no sector
    sectors = [None] * 12 + [f"s{i % 6}" for i in range(18)]
    inputs = optimizer.OptimizerInputs(alpha, model, np.zeros(n), np.full(n, 0.0005), daily.std(axis=0),
                                       np.full(n, 5e7), 1e5, sectors, [f"c{i}" for i in range(n)])
    res = optimizer.solve(inputs, cfg.risk.hard_limits, cfg.composite.optimizer)
    assert res.weights[:12].sum() <= cfg.composite.optimizer.sector_cap + 1e-7


# Q12: module boundaries --------------------------------------------------------------------

PKG = Path(__file__).resolve().parents[1] / "candleisgreen"
FORBIDDEN = {
    "composite": {"broker", "pipeline"},
    "models": {"broker", "pipeline"},
    "research": {"broker", "pipeline"},
    "risk": {"broker", "composite", "models", "research", "pipeline"},
    "data": {"broker", "composite", "models", "risk", "pipeline"},
    "core": {"broker", "composite", "models", "research", "risk", "data", "sources", "pipeline"},
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level >= 2 and node.module:
                out.add(node.module.split(".")[0])
            elif node.level == 0 and node.module and node.module.startswith("candleisgreen."):
                out.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("candleisgreen."):
                    out.add(alias.name.split(".")[1])
    return out


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_module_boundaries_hold(package):
    for path in (PKG / package).rglob("*.py"):
        bad = _imports(path) & FORBIDDEN[package]
        assert not bad, f"{path.relative_to(PKG)} imports {bad}"
