from ai_model_briefing.briefing import (
    Briefing,
    ImportantSignal,
    ModelRecommendation,
    NewsItem,
)
from ai_model_briefing.email import EMAIL_SUBJECT, UNSUBSCRIBE_URL, render_email

SOURCE_URL = "https://example.com/news/model?edition=1&lang=en"


def make_briefing() -> Briefing:
    return Briefing(
        subject="AI model briefing\r\nInjected header",
        introduction="Today brought <strong>one</strong> release.",
        recommendation=ModelRecommendation(
            model="Model <script>alert(1)</script>",
            provider="Example & Co.",
            why="Useful for <coding>.",
            best_for=["Code & review"],
            tradeoffs=["Price > baseline"],
            evidence_urls=[SOURCE_URL],
        ),
        top_news=[
            NewsItem(
                headline="A <new> model",
                company="Example AI",
                summary="Faster & smaller.",
                why_it_matters="Lower <latency>.",
                evidence_urls=[SOURCE_URL],
            )
        ],
        important_signals=[
            ImportantSignal(
                headline="Efficiency",
                analysis="Smaller models are improving.",
                confidence="medium",
                evidence_urls=[SOURCE_URL],
            )
        ],
    )


def test_renders_escaped_html_and_safe_subject() -> None:
    email = render_email(make_briefing())

    assert email.subject == EMAIL_SUBJECT
    assert "\r" not in email.text
    assert "<script>" not in email.html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in email.html
    assert "Today brought &lt;strong&gt;one&lt;/strong&gt; release." in email.html
    assert "edition=1&amp;lang=en" in email.html


def test_renders_branded_email_layout() -> None:
    email = render_email(make_briefing())

    assert "AI Model Radar" in email.html
    assert "Today's pick" in email.html
    assert "Sent by juansoultrek.com · Built with Resend" in email.html
    assert 'width="600"' in email.html


def test_includes_resend_unsubscribe_placeholder_in_both_formats() -> None:
    email = render_email(make_briefing())

    assert f'href="{UNSUBSCRIBE_URL}"' in email.html
    assert email.text.endswith(UNSUBSCRIBE_URL)


def test_renders_all_briefing_sections_in_plain_text() -> None:
    email = render_email(make_briefing())

    assert "MODEL RECOMMENDATION" in email.text
    assert "TOP NEWS" in email.text
    assert "IMPORTANT SIGNALS" in email.text
    assert SOURCE_URL in email.text
