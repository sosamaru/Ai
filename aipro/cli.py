"""Unified, dependency-light AiPro execution and verification commands.

The CLI exists to make local, Windows, VPS, and GitHub Actions execution use the
same commands and the same fail-closed checks. It never enables LIVE mode and it
always preserves the canonical runtime chain through ``run.py``.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from aipro.config import Settings
from aipro.env_loader import load_env_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_PYTHON_MIN = (3, 11)
SUPPORTED_PYTHON_MAX = (3, 13)
REQUIRED_ENTRYPOINTS = ("run.py", "telegram.py", "main.py")
INTEGRATION_TEST_PATHS = (
    "tests/test_application.py",
    "tests/test_application_market_health.py",
    "tests/test_final_integrations.py",
    "tests/test_telegram.py",
    "tests/test_v2_concrete_integrations.py",
    "tests/test_us_dual_portfolio.py",
    "tests/test_us_model_pipeline.py",
    "tests/test_runtime_audit.py",
    "tests/test_adaptive_model_pipeline.py",
    "tests/test_adaptive_runtime.py",
    "tests/test_survival_controls.py",
    "tests/test_market_capture.py",
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: str
    detail: str


class CommandFailure(RuntimeError):
    """Raised when one execution stage returns a non-zero process status."""


def _print_check(result: CheckResult) -> None:
    print(f"[{result.status}] {result.name}: {result.detail}")


def _supported_python() -> bool:
    version = sys.version_info[:2]
    return SUPPORTED_PYTHON_MIN <= version <= SUPPORTED_PYTHON_MAX


def _check_python() -> CheckResult:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if _supported_python():
        return CheckResult("Python", "OK", f"지원 버전 {version}")
    return CheckResult(
        "Python",
        "FAIL",
        f"현재 {version}; Python 3.11~3.13 중 하나가 필요합니다.",
    )


def _check_entrypoints() -> CheckResult:
    missing = [name for name in REQUIRED_ENTRYPOINTS if not (PROJECT_ROOT / name).is_file()]
    if missing:
        return CheckResult("실행 진입점", "FAIL", f"누락: {', '.join(missing)}")
    return CheckResult(
        "실행 진입점",
        "OK",
        "run.py -> telegram.py -> main.py 파일 확인",
    )


def _check_imports() -> CheckResult:
    try:
        for module_name in ("aipro", "main", "telegram", "run"):
            importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - exact provider/import error is environment-specific
        return CheckResult("모듈 import", "FAIL", f"{type(exc).__name__}: {exc}")
    return CheckResult("모듈 import", "OK", "핵심 모듈을 모두 불러왔습니다.")


def _check_environment() -> CheckResult:
    try:
        loaded = load_env_file(PROJECT_ROOT / ".env")
        settings = Settings.from_env()
    except Exception as exc:
        return CheckResult("환경 설정", "FAIL", f"{type(exc).__name__}: {exc}")
    source = f".env {loaded}개 값 로드" if (PROJECT_ROOT / ".env").exists() else ".env 없이 기본값 사용"
    return CheckResult(
        "환경 설정",
        "OK",
        f"{source}; mode={settings.mode}, runtime={settings.runtime}, provider={settings.market_data_provider}",
    )


def _check_runtime_directories() -> CheckResult:
    try:
        settings = Settings.from_env()
        db_directory = (Path(os.getenv("AIPRO_US_DUAL_DB_PATH", "data/us_dual_paper.sqlite3")).parent
                        if settings.runtime == "US_DUAL" else settings.db_path.parent)
        for directory in (db_directory, settings.log_dir):
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=directory, prefix=".aipro-write-", delete=True):
                pass
    except Exception as exc:
        return CheckResult("저장 경로", "FAIL", f"{type(exc).__name__}: {exc}")
    return CheckResult("저장 경로", "OK", "DB 및 로그 경로 쓰기 가능")


def _check_pytest(required: bool) -> CheckResult:
    if importlib.util.find_spec("pytest") is not None:
        return CheckResult("pytest", "OK", "테스트 실행 가능")
    status = "FAIL" if required else "WARN"
    return CheckResult(
        "pytest",
        status,
        '미설치; py -3.12 -m pip install --upgrade "pytest>=8,<10"',
    )


def _check_us_inputs() -> CheckResult:
    """Read-only configuration inspection; never connect to a broker."""
    try:
        if Settings.from_env().runtime != "US_DUAL":
            return CheckResult("미국 주식 입력", "OK", "현재 CRYPTO 프로필")
        from datetime import UTC, datetime
        from aipro.us_stocks.portfolio_market import FileMarketData, instant
        path = os.getenv("AIPRO_US_FRAME_PATH", "").strip()
        if not path:
            return CheckResult("미국 주식 입력", "FAIL", "AIPRO_US_FRAME_PATH가 없습니다. 시세 입력 공급기가 필요합니다.")
        frame = FileMarketData(Path(path)).frame()
        age = (datetime.now(UTC) - instant(frame.as_of_utc)).total_seconds()
        if not 0 <= age <= 60:
            return CheckResult("미국 주식 입력", "FAIL", "시장 입력이 오래되었거나 미래 시점입니다.")
        model_path, pin = os.getenv("AIPRO_US_MODEL_PATH", "").strip(), os.getenv("AIPRO_US_MODEL_SHA256", "").strip()
        if bool(model_path) != bool(pin):
            raise ValueError("model path and fingerprint must both be supplied")
        if model_path:
            from aipro.us_stocks.model_artifact import ArtifactForecastProvider, load_artifact
            from aipro.us_stocks.portfolio_policy import PortfolioPolicy
            artifact = load_artifact(Path(model_path), expected_fingerprint=pin)
            ArtifactForecastProvider(artifact)
            now = datetime.now(UTC)
            if (artifact.payload["policy_fingerprint"] != PortfolioPolicy().fingerprint
                    or not instant(artifact.payload["validation_end_utc"]) < now <= instant(artifact.payload["expires_at_utc"])):
                raise ValueError("model policy or validity interval mismatch")
        return CheckResult("미국 주식 입력", "OK", "현재 프레임 확인; 모델 선택됨" if model_path else "현재 프레임 확인; 미학습 규칙 사용")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return CheckResult("미국 주식 입력", "FAIL", f"입력 또는 모델 설정을 확인하세요 ({type(exc).__name__}).")


def doctor(*, require_pytest: bool = False) -> int:
    """Inspect the local runtime and print actionable failure reasons."""

    print(f"AiPro 진단 경로: {PROJECT_ROOT}")
    checks = (
        _check_python(),
        _check_entrypoints(),
        _check_imports(),
        _check_environment(),
        _check_runtime_directories(),
        _check_us_inputs(),
        _check_pytest(require_pytest),
    )
    for result in checks:
        _print_check(result)
    failures = [result for result in checks if result.status == "FAIL"]
    if failures:
        print(f"진단 실패: {len(failures)}개 필수 항목을 수정해야 합니다.")
        return 1
    print("진단 통과: AiPro 핵심 실행 조건이 준비되었습니다.")
    return 0


def _safe_runtime_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "AIPRO_MODE": "PAPER",
            "AIPRO_RUNTIME": "CRYPTO",
            "AIPRO_PAPER_INTERVAL_SECONDS": "0",
            "AIPRO_LIVE_CONFIRM": "NO",
            "ENABLE_LIVE_TRADING": "0",
            "AIPRO_MARKET_DATA_PROVIDER": "DEMO",
            "AIPRO_TELEGRAM_BOT_TOKEN": "",
            "AIPRO_TELEGRAM_ALLOWED_CHAT_IDS": "",
            "AIPRO_US_MODEL_PATH": "",
            "AIPRO_US_MODEL_SHA256": "",
            "AIPRO_US_ENSEMBLE_PATH": "",
            "AIPRO_US_ENSEMBLE_SHA256": "",
            "AIPRO_US_COHORT_PATH": "",
            "AIPRO_US_COHORT_SHA256": "",
            "AIPRO_US_TRAINING_ARCHIVE": "",
        }
    )
    if extra:
        env.update(extra)
    return env


def _run_stage(
    name: str,
    command: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
) -> int:
    rendered = " ".join(command)
    print(f"\n=== {name} ===")
    print(f"$ {rendered}")
    completed = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        env=dict(env) if env is not None else None,
        check=False,
    )
    if completed.returncode != 0:
        print(f"[FAIL] {name}: 종료 코드 {completed.returncode}")
    else:
        print(f"[OK] {name}")
    return completed.returncode


def run_application() -> int:
    """Run the canonical ``run.py`` entrypoint from the repository root."""

    return _run_stage("AiPro 실행", (sys.executable, str(PROJECT_ROOT / "run.py")))


def compile_repository() -> int:
    return _run_stage(
        "소스 및 테스트 컴파일",
        (
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "run.py",
            "telegram.py",
            "main.py",
            "aipro",
            "tests",
        ),
    )


def smoke_test() -> int:
    """Execute one isolated, deterministic PAPER cycle."""

    with tempfile.TemporaryDirectory(prefix="aipro-smoke-") as temporary:
        temp_root = Path(temporary)
        env = _safe_runtime_env(
            {
                "AIPRO_DB_PATH": str(temp_root / "aipro.db"),
                "AIPRO_LOG_DIR": str(temp_root / "logs"),
            }
        )
        return _run_stage(
            "PAPER 실행 스모크 테스트",
            (sys.executable, str(PROJECT_ROOT / "run.py")),
            env=env,
        )


def _require_pytest() -> bool:
    if importlib.util.find_spec("pytest") is not None:
        return True
    _print_check(_check_pytest(required=True))
    return False


def integration_test() -> int:
    """Run the repository's concrete runtime and integration regression set."""

    if not _require_pytest():
        return 1
    missing = [path for path in INTEGRATION_TEST_PATHS if not (PROJECT_ROOT / path).is_file()]
    if missing:
        print(f"[FAIL] 통합 테스트 파일 누락: {', '.join(missing)}")
        return 1
    return _run_stage(
        "통합 테스트",
        (sys.executable, "-m", "pytest", "-q", "-W", "error", *INTEGRATION_TEST_PATHS),
        env=_safe_runtime_env(),
    )


def full_test() -> int:
    if not _require_pytest():
        return 1
    return _run_stage(
        "전체 회귀 테스트",
        (sys.executable, "-m", "pytest", "-q", "-W", "error"),
        env=_safe_runtime_env(),
    )


def run_all_checks() -> int:
    """Run the same complete verification sequence locally and in CI."""

    stages: Iterable[tuple[str, callable]] = (
        ("환경 진단", lambda: doctor(require_pytest=True)),
        ("컴파일", compile_repository),
        ("스모크 테스트", smoke_test),
        ("통합 테스트", integration_test),
        ("전체 테스트", full_test),
    )
    for stage_name, stage in stages:
        result = stage()
        if result != 0:
            print(f"\n전체 검증 중단: {stage_name} 단계 실패")
            return result
    print("\n전체 검증 통과: 진단, 컴파일, PAPER 실행, 통합 테스트, 전체 테스트 성공")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m aipro",
        description="AiPro 실행, 진단, 스모크 테스트 및 통합 테스트 도구",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="실행 환경과 설정 오류를 진단합니다.")
    doctor_parser.add_argument(
        "--require-pytest",
        action="store_true",
        help="pytest 미설치를 경고가 아닌 실패로 처리합니다.",
    )
    subparsers.add_parser("run", help="run.py 진입점으로 AiPro를 실행합니다.")
    subparsers.add_parser("compile", help="전체 Python 소스와 테스트를 컴파일합니다.")
    subparsers.add_parser("smoke", help="격리된 PAPER 실행 스모크 테스트를 수행합니다.")
    subparsers.add_parser("integration", help="핵심 통합 테스트 묶음을 수행합니다.")
    subparsers.add_parser("test", help="전체 회귀 테스트를 수행합니다.")
    subparsers.add_parser("all", help="진단부터 전체 테스트까지 순서대로 수행합니다.")
    demo = subparsers.add_parser("portfolio-demo", help="100만 원 미국 주식 분리 운용 합성 데모를 실행합니다.")
    demo.add_argument("--output", type=Path, help="선택적 JSON 보고서 경로")
    replay_parser = subparsers.add_parser("portfolio-replay", help="시점별 JSONL 시장 입력을 순서대로 재생합니다.")
    replay_parser.add_argument("input", type=Path)
    replay_parser.add_argument("--output", type=Path, required=True)
    replay_parser.add_argument("--model", type=Path, help="선택적 JSON 연구 모델")
    replay_parser.add_argument("--model-sha256", help="선택한 모델의 고정 SHA-256")
    replay_parser.add_argument("--allow-synthetic-model", action="store_true", help="합성 모델을 합성 재생에만 사용")
    trainer = subparsers.add_parser("model-train", help="보관된 US 프레임으로 CPU 모델 학습·독립 평가·JSON 저장")
    trainer.add_argument("input", type=Path)
    trainer.add_argument("--symbol", required=True)
    trainer.add_argument("--output-dir", type=Path, required=True)
    trainer.add_argument("--horizon-seconds", type=int, default=300)
    trainer.add_argument("--experiment-id", required=True)
    trainer.add_argument("--ledger", type=Path, default=Path("data/research_experiments.sqlite3"))
    trainer.add_argument("--calibration", choices=("sigmoid", "isotonic", "none"), default="sigmoid")
    inspector = subparsers.add_parser("model-inspect", help="JSON 모델의 출처·검증·적용 범위를 확인")
    inspector.add_argument("input", type=Path)
    retrainer = subparsers.add_parser("model-retrain-worker", help="자동 등록된 후보 학습 작업 하나를 별도 프로세스에서 처리")
    retrainer.add_argument("--queue", type=Path, required=True)
    exporter = subparsers.add_parser("market-export", help="기록된 실제 시점의 프레임을 동일 재생/학습 형식으로 내보냅니다.")
    exporter.add_argument("archive", type=Path)
    exporter.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "market-export":
        from aipro.us_stocks.market_capture import FrameArchive
        try:
            if not args.archive.is_file():
                raise ValueError("capture archive does not exist")
            count = FrameArchive(args.archive).export(args.output)
            print(f"Exported {count} prospective frames; provider identity and LIVE readiness not established")
            return 0 if count else 1
        except (OSError, ValueError) as exc:
            print(f"[FAIL] market export: {type(exc).__name__}")
            return 1
    if args.command == "model-retrain-worker":
        import json
        from aipro.research.retraining_queue import RetrainingQueue
        result = RetrainingQueue(args.queue).run_next()
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result["phase"] == "FAILED" else 0
    if args.command in {"model-train", "model-inspect"}:
        try:
            if args.command == "model-train":
                from aipro.us_stocks.model_training import train_from_archive
                return train_from_archive(args.input, symbol=args.symbol, output_dir=args.output_dir,
                                          horizon_seconds=args.horizon_seconds, experiment_id=args.experiment_id,
                                          ledger_path=args.ledger, calibration_method=None if args.calibration == "none" else args.calibration)
            import json
            from aipro.us_stocks.model_artifact import load_artifact
            artifact = load_artifact(args.input)
            print(json.dumps({"model_id": artifact.model_id, **{key: artifact.payload[key] for key in
                ("symbol", "qualified", "synthetic", "blockers", "validation", "training_end_utc",
                 "validation_end_utc", "expires_at_utc", "paper_only", "live_ready")}}, ensure_ascii=False, indent=2))
            return 0
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print(f"[FAIL] model command: {type(exc).__name__}: {exc}")
            return 1
    if args.command in {"portfolio-demo", "portfolio-replay"}:
        import json
        from aipro.us_stocks.portfolio_replay import load_jsonl, replay, run_demo
        if args.command == "portfolio-demo":
            return run_demo(args.output)
        forecaster = None
        if bool(args.model) != bool(args.model_sha256):
            raise ValueError("replay model path and pinned SHA-256 must both be provided")
        if args.model:
            from aipro.us_stocks.model_artifact import ArtifactForecastProvider, load_artifact
            forecaster = ArtifactForecastProvider(load_artifact(args.model, expected_fingerprint=args.model_sha256),
                                                  allow_synthetic=args.allow_synthetic_model)
        report = replay(load_jsonl(args.input), forecaster=forecaster)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"PAPER 재생 보고서: {args.output}; 실제 수익성/실거래 준비 검증 아님")
        return 1 if report["blocked_frames"] else 0
    commands = {
        "doctor": lambda: doctor(require_pytest=args.require_pytest),
        "run": run_application,
        "compile": compile_repository,
        "smoke": smoke_test,
        "integration": integration_test,
        "test": full_test,
        "all": run_all_checks,
    }
    return int(commands[args.command]())


__all__ = [
    "INTEGRATION_TEST_PATHS",
    "PROJECT_ROOT",
    "build_parser",
    "doctor",
    "main",
    "run_all_checks",
]
