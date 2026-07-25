import sqlite3

import pytest

from aipro.intelligence.champion_registry import ChampionRegistry
from aipro.intelligence.classical_ml import (
    CandidateFamily,
    CandidateSpec,
    FoldMetrics,
    ModelDomain,
    evaluate_candidate,
)
from aipro.intelligence.model_champion import select_champion


def _decision(name: str, accuracy: float, ev_bps: float, domain=ModelDomain.CRYPTO):
    spec = CandidateSpec(
        name=name,
        family=CandidateFamily.RANDOM_FOREST,
        domain=domain,
        feature_names=("return_1h", "volatility"),
        target_name="forward_return_positive",
        random_seed=42,
        parameters={"n_estimators": 100},
    )
    evaluation = evaluate_candidate(
        spec,
        [FoldMetrics(accuracy, 0.60, 0.58, 0.16, ev_bps, 0.4, 150) for _ in range(3)],
    )
    return select_champion([evaluation], domain)


def test_activate_replace_and_rollback_are_append_only(tmp_path):
    registry = ChampionRegistry(tmp_path / "registry.sqlite3")
    first = registry.activate(_decision("first", 0.60, 10.0), "initial paper champion")
    second = registry.activate(_decision("second", 0.64, 18.0), "better held-out evidence")
    rollback = registry.rollback(ModelDomain.CRYPTO, first.event_id, "drift threshold exceeded")

    assert [item.action for item in registry.history(ModelDomain.CRYPTO)] == [
        "ACTIVATE",
        "REPLACE",
        "ROLLBACK",
    ]
    assert second.previous_event_id == first.event_id
    assert rollback.previous_event_id == second.event_id
    assert registry.current(ModelDomain.CRYPTO).candidate_name == "first"
    assert registry.verify_chain(ModelDomain.CRYPTO) is True


def test_crypto_and_us_stock_histories_are_isolated(tmp_path):
    registry = ChampionRegistry(tmp_path / "registry.sqlite3")
    registry.activate(_decision("crypto", 0.60, 10.0), "crypto evidence")
    registry.activate(
        _decision("stock", 0.60, 10.0, ModelDomain.US_STOCK),
        "stock evidence",
    )

    assert registry.current(ModelDomain.CRYPTO).candidate_name == "crypto"
    assert registry.current(ModelDomain.US_STOCK).candidate_name == "stock"
    assert len(registry.history(ModelDomain.CRYPTO)) == 1
    assert len(registry.history(ModelDomain.US_STOCK)) == 1


def test_rejected_decision_cannot_be_activated(tmp_path):
    registry = ChampionRegistry(tmp_path / "registry.sqlite3")
    spec = CandidateSpec(
        "bad",
        CandidateFamily.RANDOM_FOREST,
        ModelDomain.CRYPTO,
        ("x",),
        "y",
        1,
        {},
    )
    rejected = evaluate_candidate(
        spec,
        [FoldMetrics(0.40, 0.40, 0.40, 0.40, -2.0, 0.4, 150) for _ in range(3)],
    )
    decision = select_champion([rejected], ModelDomain.CRYPTO)

    with pytest.raises(ValueError, match="approved"):
        registry.activate(decision, "must fail")


def test_duplicate_activation_is_rejected(tmp_path):
    registry = ChampionRegistry(tmp_path / "registry.sqlite3")
    decision = _decision("same", 0.60, 10.0)
    registry.activate(decision, "initial")

    with pytest.raises(ValueError, match="already"):
        registry.activate(decision, "duplicate")


def test_update_and_delete_are_blocked_by_database_triggers(tmp_path):
    path = tmp_path / "registry.sqlite3"
    registry = ChampionRegistry(path)
    event = registry.activate(_decision("first", 0.60, 10.0), "initial")

    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE champion_events SET reason = 'tampered' WHERE event_id = ?",
                (event.event_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM champion_events WHERE event_id = ?", (event.event_id,)
            )


def test_deactivate_removes_current_without_deleting_history(tmp_path):
    registry = ChampionRegistry(tmp_path / "registry.sqlite3")
    activated = registry.activate(_decision("first", 0.60, 10.0), "initial")
    deactivated = registry.deactivate(ModelDomain.CRYPTO, "manual paper stop")

    assert deactivated.previous_event_id == activated.event_id
    assert registry.current(ModelDomain.CRYPTO) is None
    assert len(registry.history(ModelDomain.CRYPTO)) == 2
    assert registry.verify_chain(ModelDomain.CRYPTO) is True


def test_rollback_domain_mismatch_fails_closed(tmp_path):
    registry = ChampionRegistry(tmp_path / "registry.sqlite3")
    crypto = registry.activate(_decision("crypto", 0.60, 10.0), "crypto")

    with pytest.raises(ValueError, match="domain mismatch"):
        registry.rollback(ModelDomain.US_STOCK, crypto.event_id, "invalid")
