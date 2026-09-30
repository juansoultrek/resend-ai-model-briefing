from uuid import uuid4

import pytest

from ai_model_briefing.cli import main


def test_help_exits_successfully(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--help"])

    assert error.value.code == 0
    assert "deliver them with Resend" in capsys.readouterr().out


def test_empty_command_exits_successfully() -> None:
    assert main([]) == 0


def test_check_reports_safe_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    segment_id = uuid4()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("RESEND_API_KEY", "re_secret-value")
    monkeypatch.setenv("RESEND_FROM", "Briefing <briefing@example.com>")
    monkeypatch.setenv("RESEND_SEGMENT_ID", str(segment_id))

    assert main(["check"]) == 0

    output = capsys.readouterr().out
    assert "Configuration is valid" in output
    assert "test-model" in output
    assert str(segment_id) in output
    assert "sk-secret-value" not in output
    assert "re_secret-value" not in output


def test_check_reports_missing_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("OPENAI_API_KEY", "RESEND_API_KEY", "RESEND_FROM", "RESEND_SEGMENT_ID"):
        monkeypatch.delenv(name, raising=False)

    assert main(["check"]) == 2
    assert "Configuration is invalid" in capsys.readouterr().err


def test_check_rejects_header_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    monkeypatch.setenv("RESEND_API_KEY", "re_secret-value")
    monkeypatch.setenv("RESEND_FROM", "briefing@example.com\nBcc: attacker@example.com")
    monkeypatch.setenv("RESEND_SEGMENT_ID", str(uuid4()))

    assert main(["check"]) == 2
