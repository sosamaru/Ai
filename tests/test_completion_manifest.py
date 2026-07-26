from pathlib import Path

import pytest

from aipro.research.completion_manifest import (
    ClaimSpec,
    ClaimStatus,
    OperationalStatus,
    build_completion_manifest,
    render_manifest_markdown,
)


ROOT = Path(__file__).resolve().parents[1]


def test_default_manifest_matches_repository_code_tests_docs_and_roadmap():
    manifest = build_completion_manifest(ROOT)
    rendered = render_manifest_markdown(manifest)
    assert manifest.development_complete, rendered
    assert not manifest.operational_complete
    assert manifest.paper_only
    assert not manifest.grants_execution_authority
    assert all(claim.status is ClaimStatus.COMPLETE for claim in manifest.claims), rendered
    assert all(
        requirement.status is OperationalStatus.EXTERNAL_EVIDENCE_REQUIRED
        for requirement in manifest.operational_requirements
    )
    assert len(manifest.fingerprint) == 64


def test_manifest_and_markdown_are_deterministic():
    first = build_completion_manifest(ROOT)
    second = build_completion_manifest(ROOT)
    assert first.fingerprint == second.fingerprint
    assert render_manifest_markdown(first) == render_manifest_markdown(second)
    rendered = render_manifest_markdown(first)
    assert "Development complete: **true**" in rendered, rendered
    assert "Operational evidence complete: **false**" in rendered
    assert "external_evidence_required" in rendered


def test_missing_path_or_roadmap_marker_makes_claim_incomplete(tmp_path: Path):
    (tmp_path / "PROJECT_ROADMAP.md").write_text("known marker", encoding="utf-8")
    (tmp_path / "code.py").write_text("print('ok')", encoding="utf-8")
    claim = ClaimSpec(
        claim_id="sample",
        description="Sample claim.",
        code_paths=("code.py",),
        test_paths=("tests/test_code.py",),
        documentation_paths=("docs/code.md",),
        roadmap_markers=("missing marker",),
    )
    manifest = build_completion_manifest(tmp_path, claims=(claim,))
    evidence = manifest.claims[0]
    assert evidence.status is ClaimStatus.INCOMPLETE
    assert evidence.missing_roadmap_markers == ("missing marker",)
    assert not manifest.development_complete


def test_repository_paths_fail_closed_on_escape_attempts():
    with pytest.raises(ValueError, match="unsafe"):
        ClaimSpec(
            claim_id="unsafe",
            description="Unsafe path.",
            code_paths=("../secret",),
            test_paths=("tests/test_safe.py",),
            documentation_paths=("docs/safe.md",),
            roadmap_markers=("safe",),
        )


def test_duplicate_claim_ids_are_rejected(tmp_path: Path):
    (tmp_path / "PROJECT_ROADMAP.md").write_text("marker", encoding="utf-8")
    for name in ("code.py", "test.py", "doc.md"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    claim = ClaimSpec(
        claim_id="duplicate",
        description="Duplicate claim.",
        code_paths=("code.py",),
        test_paths=("test.py",),
        documentation_paths=("doc.md",),
        roadmap_markers=("marker",),
    )
    with pytest.raises(ValueError, match="unique"):
        build_completion_manifest(tmp_path, claims=(claim, claim))
