from __future__ import annotations

import pytest

from aipro.env_loader import load_env_file


def test_missing_env_file_is_a_noop(tmp_path) -> None:
    target: dict[str, str] = {}

    assigned = load_env_file(tmp_path / ".env", environ=target)

    assert assigned == 0
    assert target == {}


def test_env_loader_parses_supported_values_and_preserves_existing_values(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        """# comment
AIPRO_MODE=PAPER
export AIPRO_LOG_LEVEL=DEBUG
AIPRO_LABEL='민재 테스트'
AIPRO_MESSAGE="line\\nnext"
EXISTING=from-file
""",
        encoding="utf-8",
    )
    target = {"EXISTING": "injected"}

    assigned = load_env_file(env_file, environ=target)

    assert assigned == 4
    assert target == {
        "AIPRO_MODE": "PAPER",
        "AIPRO_LOG_LEVEL": "DEBUG",
        "AIPRO_LABEL": "민재 테스트",
        "AIPRO_MESSAGE": "line\nnext",
        "EXISTING": "injected",
    }


def test_env_loader_can_explicitly_override_existing_values(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AIPRO_MODE=PAPER\n", encoding="utf-8")
    target = {"AIPRO_MODE": "LIVE"}

    assigned = load_env_file(env_file, environ=target, override=True)

    assert assigned == 1
    assert target["AIPRO_MODE"] == "PAPER"


@pytest.mark.parametrize(
    "contents",
    [
        "NOT_AN_ASSIGNMENT\n",
        "1INVALID=value\n",
        'BROKEN="unterminated\n',
        'BROKEN="invalid\\xescape"\n',
    ],
)
def test_invalid_env_lines_fail_closed(tmp_path, contents: str) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError):
        load_env_file(env_file, environ={})
