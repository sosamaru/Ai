from unittest.mock import patch

import pytest

from aipro.intelligence.optional_sequence_backends import (
    SequenceModelSpec,
    inspect_backend,
    load_backend,
    public_evidence,
    validate_sequence_spec,
)


def _spec(**changes):
    values = {
        "name": "crypto_lstm_v1",
        "domain": "crypto",
        "model_family": "lstm",
        "backend": "torch",
        "feature_names": ("return_1h", "volatility_24h"),
        "target_name": "forward_return",
        "seed": 7,
        "parameters": {"hidden_size": 64, "epochs": 10},
    }
    values.update(changes)
    return SequenceModelSpec(**values)


def test_validation_is_deterministic():
    first = validate_sequence_spec(_spec())
    second = validate_sequence_spec(_spec())
    assert first.fingerprint == second.fingerprint
    assert first.normalized_parameters == second.normalized_parameters


def test_domain_is_strictly_limited():
    with pytest.raises(ValueError, match="domain"):
        validate_sequence_spec(_spec(domain="combined"))


def test_unknown_parameters_fail_closed():
    with pytest.raises(ValueError, match="unsupported parameters"):
        validate_sequence_spec(_spec(parameters={"hidden_size": 64, "shell": True}))


def test_transformer_heads_must_divide_hidden_size():
    with pytest.raises(ValueError, match="divide"):
        validate_sequence_spec(
            _spec(
                model_family="transformer_encoder",
                parameters={"hidden_size": 62, "attention_heads": 4},
            )
        )


def test_recurrent_model_rejects_attention_override():
    with pytest.raises(ValueError, match="transformer_encoder"):
        validate_sequence_spec(_spec(parameters={"attention_heads": 8}))


def test_excessive_training_budget_is_rejected():
    with pytest.raises(ValueError, match="epochs"):
        validate_sequence_spec(_spec(parameters={"epochs": 201}))


def test_availability_check_does_not_import_backend():
    with patch("aipro.intelligence.optional_sequence_backends.find_spec", return_value=None), patch(
        "aipro.intelligence.optional_sequence_backends.import_module"
    ) as importer:
        evidence = inspect_backend("torch")
    assert not evidence.available
    importer.assert_not_called()


def test_missing_backend_fails_explicitly():
    validated = validate_sequence_spec(_spec())
    with patch("aipro.intelligence.optional_sequence_backends.find_spec", return_value=None):
        with pytest.raises(RuntimeError, match="not installed"):
            load_backend(validated)


def test_public_evidence_is_paper_only():
    evidence = public_evidence(validate_sequence_spec(_spec()))
    assert evidence["paper_only"] is True
    assert len(evidence["fingerprint"]) == 64
