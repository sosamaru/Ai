"""Deterministic repository completion manifest for AiPro.

The manifest compares reviewed development claims with repository code, tests,
documentation, and roadmap markers. Operational evidence that requires real elapsed
time or external credentials is never inferred from source files.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping, Sequence


def _validate_relative_path(value: str) -> None:
    path = Path(value)
    if not value.strip() or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe repository path: {value!r}")


def _fingerprint(payload: Mapping[str, object]) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


class ClaimStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class OperationalStatus(StrEnum):
    EXTERNAL_EVIDENCE_REQUIRED = "external_evidence_required"


@dataclass(frozen=True, slots=True)
class ClaimSpec:
    claim_id: str
    description: str
    code_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    documentation_paths: tuple[str, ...]
    roadmap_markers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.claim_id.strip() or not self.description.strip():
            raise ValueError("claim_id and description are required")
        paths = self.code_paths + self.test_paths + self.documentation_paths
        if not paths:
            raise ValueError("a development claim must reference repository paths")
        for value in paths:
            _validate_relative_path(value)
        if not self.roadmap_markers or any(not marker.strip() for marker in self.roadmap_markers):
            raise ValueError("roadmap_markers must be non-empty")


@dataclass(frozen=True, slots=True)
class FileEvidence:
    path: str
    exists: bool
    size_bytes: int | None
    sha256: str | None


@dataclass(frozen=True, slots=True)
class ClaimEvidence:
    claim_id: str
    description: str
    status: ClaimStatus
    code: tuple[FileEvidence, ...]
    tests: tuple[FileEvidence, ...]
    documentation: tuple[FileEvidence, ...]
    roadmap_markers: tuple[str, ...]
    missing_roadmap_markers: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class OperationalRequirement:
    requirement_id: str
    description: str
    status: OperationalStatus = OperationalStatus.EXTERNAL_EVIDENCE_REQUIRED


@dataclass(frozen=True, slots=True)
class CompletionManifest:
    repository_root: str
    roadmap_path: str
    claims: tuple[ClaimEvidence, ...]
    operational_requirements: tuple[OperationalRequirement, ...]
    development_complete: bool
    operational_complete: bool
    limitations: tuple[str, ...]
    fingerprint: str
    paper_only: bool = True
    grants_execution_authority: bool = False


DEFAULT_CLAIMS: tuple[ClaimSpec, ...] = (
    ClaimSpec(
        claim_id="architecture_contract",
        description="Preserve run.py -> telegram.py -> main.py -> TradingApplication.",
        code_paths=("run.py", "telegram.py", "main.py"),
        test_paths=("tests/test_application.py",),
        documentation_paths=("README.md",),
        roadmap_markers=("run.py -> telegram.py -> main.py -> TradingApplication",),
    ),
    ClaimSpec(
        claim_id="purged_model_training",
        description="Provide leakage-safe logistic, boosting, and sequence PAPER training.",
        code_paths=(
            "aipro/research/purged_walk_forward.py",
            "aipro/research/purged_training_runner.py",
            "aipro/research/purged_boosting_runner.py",
            "aipro/research/purged_sequence_runner.py",
        ),
        test_paths=(
            "tests/test_purged_walk_forward.py",
            "tests/test_purged_training_runner.py",
            "tests/test_purged_boosting_runner.py",
            "tests/test_purged_sequence_runner.py",
        ),
        documentation_paths=(
            "docs/PURGED_WALK_FORWARD.md",
            "docs/PURGED_PAPER_TRAINING_RUNNER.md",
            "docs/PURGED_BOOSTING_TRAINING.md",
            "docs/PURGED_SEQUENCE_TRAINING.md",
        ),
        roadmap_markers=(
            "Purged walk-forward validation",
            "Bounded lazy XGBoost, LightGBM, and CatBoost training adapters",
            "Bounded lazy PyTorch and TensorFlow LSTM, GRU, and Transformer-encoder training adapters",
        ),
    ),
    ClaimSpec(
        claim_id="paper_model_governance",
        description="Keep champion selection, registry, monitoring, approvals, and commands fail closed.",
        code_paths=(
            "aipro/intelligence/model_champion.py",
            "aipro/intelligence/champion_registry.py",
            "aipro/intelligence/challenger_monitor.py",
            "aipro/intelligence/governance_approval.py",
            "aipro/intelligence/governance_command.py",
        ),
        test_paths=(
            "tests/test_model_champion.py",
            "tests/test_champion_registry.py",
            "tests/test_challenger_monitor.py",
            "tests/test_governance_approval.py",
            "tests/test_governance_command.py",
        ),
        documentation_paths=(
            "docs/MODEL_CHAMPION_GOVERNANCE.md",
            "docs/PAPER_CHAMPION_REGISTRY.md",
            "docs/PAPER_CHALLENGER_MONITORING.md",
            "docs/PAPER_GOVERNANCE_APPROVALS.md",
            "docs/PAPER_GOVERNANCE_COMMAND_BOUNDARY.md",
        ),
        roadmap_markers=(
            "Fail-closed PAPER champion selection",
            "Immutable SQLite PAPER champion registry",
            "Immutable PAPER operator-review approval ledger",
        ),
    ),
    ClaimSpec(
        claim_id="paper_strategy_validation",
        description="Validate domain-isolated PAPER strategies with EV, sizing, and execution costs.",
        code_paths=("aipro/intelligence/paper_strategy_validation.py",),
        test_paths=("tests/test_paper_strategy_validation.py",),
        documentation_paths=("docs/PAPER_STRATEGY_VALIDATION.md",),
        roadmap_markers=("End-to-end domain-isolated PAPER strategy validation",),
    ),
    ClaimSpec(
        claim_id="sec_filing_intelligence",
        description="Normalize SEC events, filing text, XBRL facts, materiality, and historical outcomes.",
        code_paths=(
            "aipro/intelligence/sec_edgar.py",
            "aipro/intelligence/sec_filing_analysis.py",
        ),
        test_paths=(
            "tests/test_sec_edgar.py",
            "tests/test_sec_filing_analysis.py",
        ),
        documentation_paths=(
            "docs/SEC_EDGAR_INTELLIGENCE.md",
            "docs/SEC_FILING_MATERIALITY_OUTCOMES.md",
        ),
        roadmap_markers=(
            "SEC EDGAR filing events",
            "SEC Company Facts extraction",
            "Historical filing outcome evaluation",
        ),
    ),
    ClaimSpec(
        claim_id="ci_and_safety_boundary",
        description="Keep dependency-free CI and explicit secret/LIVE safety documentation.",
        code_paths=(".github/workflows/tests.yml",),
        test_paths=("tests/test_config.py",),
        documentation_paths=("SECURITY.md", ".env.example"),
        roadmap_markers=(
            "PAPER defaults",
            "Real Upbit order creation remains absent",
        ),
    ),
)


DEFAULT_OPERATIONAL_REQUIREMENTS: tuple[OperationalRequirement, ...] = (
    OperationalRequirement("smtp_delivery", "Configure and verify dedicated SMTP delivery."),
    OperationalRequirement("totp_enrollment", "Enroll TOTP and store recovery material offline."),
    OperationalRequirement(
        "alpaca_paper_30_days",
        "Run actual Alpaca PAPER credentials for at least 30 calendar days.",
    ),
    OperationalRequirement(
        "domain_sessions",
        "Collect independent crypto and U.S.-stock sessions and orders while readiness gates pass.",
    ),
    OperationalRequirement(
        "upbit_supervised_preflight",
        "Run supervised Upbit inspection and test-order preflight with real order creation disabled.",
    ),
    OperationalRequirement(
        "live_readiness_decision",
        "Produce a separate live-readiness decision from immutable evidence.",
    ),
)


DEFAULT_LIMITATIONS: tuple[str, ...] = (
    "No profitability guarantee is permitted.",
    "Real Upbit order creation remains absent.",
    "Alpaca remains PAPER-domain only.",
    "Optional deep-learning packages are not installed in core CI.",
    "Filing materiality is a deterministic research heuristic, not a recommendation.",
    "Operational evidence cannot be completed by repository inspection alone.",
)


def build_completion_manifest(
    repository_root: str | Path,
    *,
    roadmap_path: str = "PROJECT_ROADMAP.md",
    claims: Sequence[ClaimSpec] = DEFAULT_CLAIMS,
    operational_requirements: Sequence[OperationalRequirement] = DEFAULT_OPERATIONAL_REQUIREMENTS,
    limitations: Sequence[str] = DEFAULT_LIMITATIONS,
) -> CompletionManifest:
    root = Path(repository_root).resolve()
    if not root.is_dir():
        raise ValueError("repository_root must be an existing directory")
    _validate_relative_path(roadmap_path)
    roadmap_file = root / roadmap_path
    if not roadmap_file.is_file():
        raise ValueError("roadmap file is missing")
    roadmap_text = roadmap_file.read_text(encoding="utf-8")

    claim_items = tuple(claims)
    if not claim_items:
        raise ValueError("claims cannot be empty")
    claim_ids = [claim.claim_id for claim in claim_items]
    if len(set(claim_ids)) != len(claim_ids):
        raise ValueError("claim IDs must be unique")

    evidence = tuple(_evaluate_claim(root, roadmap_text, claim) for claim in claim_items)
    operations = tuple(operational_requirements)
    operation_ids = [item.requirement_id for item in operations]
    if len(set(operation_ids)) != len(operation_ids):
        raise ValueError("operational requirement IDs must be unique")
    normalized_limitations = tuple(item.strip() for item in limitations if item.strip())
    development_complete = all(item.status is ClaimStatus.COMPLETE for item in evidence)
    operational_complete = bool(operations) and all(
        item.status is not OperationalStatus.EXTERNAL_EVIDENCE_REQUIRED for item in operations
    )
    payload = {
        "roadmap_path": roadmap_path,
        "roadmap_sha256": _hash_file(roadmap_file),
        "claims": [
            {"claim_id": item.claim_id, "status": item.status.value, "fingerprint": item.fingerprint}
            for item in evidence
        ],
        "operational_requirements": [asdict(item) for item in operations],
        "development_complete": development_complete,
        "operational_complete": operational_complete,
        "limitations": normalized_limitations,
        "paper_only": True,
        "grants_execution_authority": False,
    }
    return CompletionManifest(
        repository_root=str(root),
        roadmap_path=roadmap_path,
        claims=evidence,
        operational_requirements=operations,
        development_complete=development_complete,
        operational_complete=operational_complete,
        limitations=normalized_limitations,
        fingerprint=_fingerprint(payload),
    )


def render_manifest_markdown(manifest: CompletionManifest) -> str:
    lines = [
        "# AiPro Completion Manifest",
        "",
        f"- Development complete: **{str(manifest.development_complete).lower()}**",
        f"- Operational evidence complete: **{str(manifest.operational_complete).lower()}**",
        f"- PAPER-only: **{str(manifest.paper_only).lower()}**",
        f"- Grants execution authority: **{str(manifest.grants_execution_authority).lower()}**",
        f"- Manifest fingerprint: `{manifest.fingerprint}`",
        "",
        "## Development claims",
        "",
    ]
    for claim in manifest.claims:
        lines.append(f"- **{claim.claim_id}** — `{claim.status.value}` — {claim.description}")
        missing = tuple(
            item.path
            for group in (claim.code, claim.tests, claim.documentation)
            for item in group
            if not item.exists
        )
        if missing:
            lines.append(f"  - Missing paths: {', '.join(missing)}")
        if claim.missing_roadmap_markers:
            lines.append(
                "  - Missing roadmap markers: " + ", ".join(claim.missing_roadmap_markers)
            )
    lines.extend(["", "## Operational evidence still required", ""])
    for item in manifest.operational_requirements:
        lines.append(f"- **{item.requirement_id}** — `{item.status.value}` — {item.description}")
    lines.extend(["", "## Known limitations", ""])
    lines.extend(f"- {item}" for item in manifest.limitations)
    lines.append("")
    return "\n".join(lines)


def _evaluate_claim(root: Path, roadmap_text: str, claim: ClaimSpec) -> ClaimEvidence:
    code = tuple(_file_evidence(root, path) for path in claim.code_paths)
    tests = tuple(_file_evidence(root, path) for path in claim.test_paths)
    documentation = tuple(_file_evidence(root, path) for path in claim.documentation_paths)
    missing_markers = tuple(
        marker for marker in claim.roadmap_markers if marker not in roadmap_text
    )
    complete = all(
        item.exists
        for group in (code, tests, documentation)
        for item in group
    ) and not missing_markers
    payload = {
        "claim_id": claim.claim_id,
        "description": claim.description,
        "status": ClaimStatus.COMPLETE.value if complete else ClaimStatus.INCOMPLETE.value,
        "code": [asdict(item) for item in code],
        "tests": [asdict(item) for item in tests],
        "documentation": [asdict(item) for item in documentation],
        "roadmap_markers": claim.roadmap_markers,
        "missing_roadmap_markers": missing_markers,
    }
    return ClaimEvidence(
        claim_id=claim.claim_id,
        description=claim.description,
        status=ClaimStatus.COMPLETE if complete else ClaimStatus.INCOMPLETE,
        code=code,
        tests=tests,
        documentation=documentation,
        roadmap_markers=claim.roadmap_markers,
        missing_roadmap_markers=missing_markers,
        fingerprint=_fingerprint(payload),
    )


def _file_evidence(root: Path, relative_path: str) -> FileEvidence:
    _validate_relative_path(relative_path)
    path = root / relative_path
    exists = path.is_file()
    return FileEvidence(
        path=relative_path,
        exists=exists,
        size_bytes=path.stat().st_size if exists else None,
        sha256=_hash_file(path) if exists else None,
    )


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "ClaimEvidence",
    "ClaimSpec",
    "ClaimStatus",
    "CompletionManifest",
    "DEFAULT_CLAIMS",
    "DEFAULT_LIMITATIONS",
    "DEFAULT_OPERATIONAL_REQUIREMENTS",
    "FileEvidence",
    "OperationalRequirement",
    "OperationalStatus",
    "build_completion_manifest",
    "render_manifest_markdown",
]
