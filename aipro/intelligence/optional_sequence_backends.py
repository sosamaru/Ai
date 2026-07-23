"""PAPER-only optional deep-learning backend registry.

The core AiPro process must not import torch or tensorflow at startup.  This
module validates reviewed sequence-model specifications and lazily resolves a
backend only when a research runner explicitly asks for it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib import import_module
from importlib.util import find_spec
import json
from typing import Any, Mapping


_ALLOWED_DOMAINS = {"crypto", "us_stock"}
_ALLOWED_MODELS = {"lstm", "gru", "transformer_encoder"}
_ALLOWED_BACKENDS = {"torch", "tensorflow"}
_ALLOWED_KEYS = {
    "hidden_size",
    "num_layers",
    "dropout",
    "sequence_length",
    "batch_size",
    "epochs",
    "learning_rate",
    "attention_heads",
}


@dataclass(frozen=True)
class SequenceModelSpec:
    name: str
    domain: str
    model_family: str
    backend: str
    feature_names: tuple[str, ...]
    target_name: str
    seed: int = 42
    parameters: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class BackendEvidence:
    backend: str
    available: bool
    module_name: str
    reason: str


@dataclass(frozen=True)
class ValidatedSequenceSpec:
    spec: SequenceModelSpec
    normalized_parameters: Mapping[str, Any]
    fingerprint: str


_BACKEND_MODULES = {"torch": "torch", "tensorflow": "tensorflow"}


def inspect_backend(backend: str) -> BackendEvidence:
    """Report availability without importing the optional package."""
    if backend not in _ALLOWED_BACKENDS:
        raise ValueError(f"unsupported backend: {backend}")
    module_name = _BACKEND_MODULES[backend]
    available = find_spec(module_name) is not None
    return BackendEvidence(
        backend=backend,
        available=available,
        module_name=module_name,
        reason="available" if available else "optional dependency is not installed",
    )


def validate_sequence_spec(spec: SequenceModelSpec) -> ValidatedSequenceSpec:
    if not spec.name.strip():
        raise ValueError("model name is required")
    if spec.domain not in _ALLOWED_DOMAINS:
        raise ValueError("domain must be crypto or us_stock")
    if spec.model_family not in _ALLOWED_MODELS:
        raise ValueError(f"unsupported sequence model: {spec.model_family}")
    if spec.backend not in _ALLOWED_BACKENDS:
        raise ValueError(f"unsupported backend: {spec.backend}")
    if not spec.feature_names or len(set(spec.feature_names)) != len(spec.feature_names):
        raise ValueError("feature names must be non-empty and unique")
    if not spec.target_name.strip():
        raise ValueError("target name is required")
    if spec.seed < 0:
        raise ValueError("seed must be non-negative")

    params = dict(spec.parameters or {})
    unknown = set(params) - _ALLOWED_KEYS
    if unknown:
        raise ValueError(f"unsupported parameters: {sorted(unknown)}")

    normalized = {
        "hidden_size": int(params.get("hidden_size", 64)),
        "num_layers": int(params.get("num_layers", 1)),
        "dropout": float(params.get("dropout", 0.1)),
        "sequence_length": int(params.get("sequence_length", 32)),
        "batch_size": int(params.get("batch_size", 32)),
        "epochs": int(params.get("epochs", 20)),
        "learning_rate": float(params.get("learning_rate", 1e-3)),
        "attention_heads": int(params.get("attention_heads", 4)),
    }
    _validate_bounds(spec.model_family, normalized)

    evidence = {
        "name": spec.name,
        "domain": spec.domain,
        "model_family": spec.model_family,
        "backend": spec.backend,
        "feature_names": list(spec.feature_names),
        "target_name": spec.target_name,
        "seed": spec.seed,
        "parameters": normalized,
    }
    fingerprint = sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ValidatedSequenceSpec(spec=spec, normalized_parameters=normalized, fingerprint=fingerprint)


def load_backend(validated: ValidatedSequenceSpec) -> Any:
    """Lazily import a requested backend after its spec has passed validation."""
    evidence = inspect_backend(validated.spec.backend)
    if not evidence.available:
        raise RuntimeError(evidence.reason)
    return import_module(evidence.module_name)


def public_evidence(validated: ValidatedSequenceSpec) -> Mapping[str, Any]:
    return {
        "spec": asdict(validated.spec),
        "normalized_parameters": dict(validated.normalized_parameters),
        "fingerprint": validated.fingerprint,
        "paper_only": True,
    }


def _validate_bounds(model_family: str, params: Mapping[str, Any]) -> None:
    if not 8 <= params["hidden_size"] <= 512:
        raise ValueError("hidden_size outside reviewed bounds")
    if not 1 <= params["num_layers"] <= 6:
        raise ValueError("num_layers outside reviewed bounds")
    if not 0.0 <= params["dropout"] <= 0.7:
        raise ValueError("dropout outside reviewed bounds")
    if not 4 <= params["sequence_length"] <= 512:
        raise ValueError("sequence_length outside reviewed bounds")
    if not 1 <= params["batch_size"] <= 512:
        raise ValueError("batch_size outside reviewed bounds")
    if not 1 <= params["epochs"] <= 200:
        raise ValueError("epochs outside reviewed bounds")
    if not 1e-6 <= params["learning_rate"] <= 0.1:
        raise ValueError("learning_rate outside reviewed bounds")
    heads = params["attention_heads"]
    if model_family == "transformer_encoder":
        if not 1 <= heads <= 16 or params["hidden_size"] % heads:
            raise ValueError("attention_heads must divide hidden_size")
    elif "attention_heads" in params and heads != 4:
        # Keep the normalized field deterministic but reject an explicit
        # transformer-only override for recurrent families.
        raise ValueError("attention_heads applies only to transformer_encoder")
