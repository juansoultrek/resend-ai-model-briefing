from datetime import UTC, datetime
from uuid import uuid4

import pytest

import ai_model_briefing.cli as cli
from ai_model_briefing.collector import CollectionIssue, CollectionResult
from ai_model_briefing.delivery import BroadcastReceipt
from ai_model_briefing.email import RenderedEmail
from ai_model_briefing.parsers import ParsedArticle


def make_collection(*, with_issue: bool = False) -> CollectionResult:
    issues = (CollectionIssue("example-ai", "listing_fetch"),) if with_issue else ()
    return CollectionResult(
        articles=(
            ParsedArticle(
                source_id="example-ai",
                company="Example AI",
                title="Example Model",
                url="https://example.com/news/model",
                published_at=datetime(2026, 9, 30, 10, tzinfo=UTC),
                summary="A model release.",
            ),
        ),
        issues=issues,
    )


def test_help_exits_successfully(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["--help"])

    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "deliver them with Resend" in output
    assert "preview" in output
    assert "run" in output


def test_empty_command_exits_successfully() -> None:
    assert cli.main([]) == 0


def test_check_reports_safe_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    segment_id = uuid4()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("RESEND_API_KEY", "re_secret-value")
    monkeypatch.setenv("RESEND_FROM", "Briefing <briefing@example.com>")
    monkeypatch.setenv("RESEND_SEGMENT_ID", str(segment_id))

    assert cli.main(["check"]) == 0

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

    assert cli.main(["check"]) == 2
    assert "Configuration is invalid" in capsys.readouterr().err


def test_check_rejects_header_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    monkeypatch.setenv("RESEND_API_KEY", "re_secret-value")
    monkeypatch.setenv("RESEND_FROM", "briefing@example.com\nBcc: attacker@example.com")
    monkeypatch.setenv("RESEND_SEGMENT_ID", str(uuid4()))

    assert cli.main(["check"]) == 2


def test_preview_generates_local_html_without_resend_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    for name in ("RESEND_API_KEY", "RESEND_FROM", "RESEND_SEGMENT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "collect_recent_articles", lambda catalog, mode: make_collection())
    monkeypatch.setattr(cli, "generate_briefing", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        cli,
        "render_email",
        lambda briefing: RenderedEmail("Preview", "<p>Safe preview</p>", "Safe preview"),
    )
    output_path = tmp_path / "preview.html"

    assert cli.main(["preview", "--output", str(output_path)]) == 0

    assert output_path.read_text(encoding="utf-8") == "<p>Safe preview</p>"
    assert output_path.stat().st_mode & 0o777 == 0o600
    output = capsys.readouterr().out
    assert str(output_path) in output
    assert "sk-secret-value" not in output


def test_run_sends_generated_broadcast(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    segment_id = uuid4()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    monkeypatch.setenv("RESEND_API_KEY", "re_secret-value")
    monkeypatch.setenv("RESEND_FROM", "Briefing <briefing@example.com>")
    monkeypatch.setenv("RESEND_SEGMENT_ID", str(segment_id))
    monkeypatch.setattr(
        cli, "collect_recent_articles", lambda catalog, mode: make_collection(with_issue=True)
    )
    monkeypatch.setattr(cli, "generate_briefing", lambda *args, **kwargs: object())
    email = RenderedEmail("Briefing", "<p>Briefing</p>", "Briefing")
    monkeypatch.setattr(cli, "render_email", lambda briefing: email)

    def deliver(rendered_email, **kwargs):
        assert rendered_email is email
        assert kwargs["send"] is True
        assert kwargs["segment_id"] == segment_id
        return BroadcastReceipt("broadcast-id", sent=True)

    monkeypatch.setattr(cli, "deliver_broadcast", deliver)

    assert cli.main(["run"]) == 0

    captured = capsys.readouterr()
    assert "Broadcast sent: broadcast-id" in captured.out
    assert "example-ai failed during listing_fetch" in captured.err
    assert "sk-secret-value" not in captured.out + captured.err
    assert "re_secret-value" not in captured.out + captured.err
