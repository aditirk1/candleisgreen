"""Clinical trials for the research-only biotech universe: forward snapshots, exact sponsor match, events."""
import json
from datetime import datetime, timedelta, timezone

from candleisgreen.core.config import load_config
from candleisgreen.data.instruments import InstrumentMaster
from candleisgreen.data.pit_store import PointInTimeStore
from candleisgreen.global_research import TRIALS_FIXTURES
from candleisgreen.sources import trials

UTC = timezone.utc
T1 = datetime(2026, 11, 20, 2, tzinfo=UTC)


def _setup(tmp_path, sic=2834):
    store = PointInTimeStore(tmp_path / "pit.duckdb")
    master = InstrumentMaster(store.connection)
    iid = master.map_issuer("0009999999", "EXGN", T1 - timedelta(days=30))
    master.add_classification(iid, "0009999999", sic, "Hlth", "mapped", T1 - timedelta(days=30), None, "ff12-test")
    master.add_entity_name(iid, "EXAMPLEGEN THERAPEUTICS, INC.", "sec_submissions", T1 - timedelta(days=30))
    return store, master, iid


def _record(store, master, now, transport=None):
    cfg = load_config()
    return trials.record(store.connection, transport or trials.FixtureTrialsTransport(TRIALS_FIXTURES), master,
                         tuple(cfg.universe.research_universes["biotech"].sic_codes), cfg.sources.trials, now)


def test_normalize_drops_case_punctuation_and_legal_suffixes():
    assert trials.normalize("Examplegen Therapeutics, Inc.") == trials.normalize("EXAMPLEGEN THERAPEUTICS INC") == "examplegen therapeutics"
    assert trials.normalize("Examplegen Therapeutics Foundation") != "examplegen therapeutics"


def test_only_exact_lead_sponsor_matches_are_linked_and_pages_are_followed(tmp_path):
    store, master, iid = _setup(tmp_path)
    cfg = load_config().sources.trials
    rows = trials.fetch(trials.FixtureTrialsTransport(TRIALS_FIXTURES), "Examplegen Therapeutics, Inc.", page_size=1)
    assert sorted(trials.flatten(s)["nct_id"] for s in rows) == ["NCT90000001", "NCT90000002"]
    out = _record(store, master, T1)
    assert out == {"companies": 1, "trials_seen": 2, "snapshots_added": 2}
    assert _record(store, master, T1 + timedelta(days=1))["snapshots_added"] == 0  # unchanged content is not stored again
    assert {r["instrument_id"] for r in trials.as_of(store.connection, T1 + timedelta(days=2))} == {iid}
    assert cfg.page_size == 1000
    store.close()


def test_non_biotech_names_are_not_queried(tmp_path):
    store, master, _ = _setup(tmp_path, sic=3571)
    assert _record(store, master, T1) == {"companies": 0, "trials_seen": 0, "snapshots_added": 0}
    store.close()


def test_changes_become_events_and_reads_are_as_known_then(tmp_path):
    store, master, _ = _setup(tmp_path)
    _record(store, master, T1)
    changed = json.loads((TRIALS_FIXTURES / "examplegen_therapeutics.json").read_text())
    st = changed["studies"][0]["protocolSection"]["statusModule"]
    st["overallStatus"], st["primaryCompletionDateStruct"] = "COMPLETED", {"date": "2026-11-18", "type": "ACTUAL"}
    tmp_dir = tmp_path / "fx"
    tmp_dir.mkdir()
    (tmp_dir / "examplegen_therapeutics.json").write_text(json.dumps(changed))
    t2 = T1 + timedelta(days=7)
    assert _record(store, master, t2, trials.FixtureTrialsTransport(tmp_dir))["snapshots_added"] == 1
    ev = trials.events(store.connection, T1, t2)
    assert {(e["field"], e["before"], e["after"]) for e in ev} >= {
        ("overall_status", "ACTIVE_NOT_RECRUITING", "COMPLETED"), ("primary_completion", "2027-03", "2026-11-18"),
        ("primary_completion_type", "ESTIMATED", "ACTUAL")}
    before = {r["nct_id"]: r for r in trials.as_of(store.connection, t2)}
    after = {r["nct_id"]: r for r in trials.as_of(store.connection, t2 + timedelta(seconds=1))}
    assert before["NCT90000001"]["overall_status"] == "ACTIVE_NOT_RECRUITING"
    assert after["NCT90000001"]["overall_status"] == "COMPLETED"
    # Reverting to earlier content is recorded too.
    assert _record(store, master, t2 + timedelta(days=7))["snapshots_added"] == 1
    store.close()


def test_trial_data_cannot_feed_a_paper_order():
    import pytest

    from candleisgreen.core.licenses import LicenseNotPermittedError, load_licenses

    lic = load_licenses()
    lic.assert_use(["clinicaltrials_gov"], "research")
    with pytest.raises(LicenseNotPermittedError):
        lic.assert_use(["clinicaltrials_gov"], "paper_trading")
