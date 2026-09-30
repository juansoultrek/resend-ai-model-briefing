from __future__ import annotations

from dataclasses import dataclass
from html import escape

from ai_model_briefing.briefing import Briefing, ImportantSignal, NewsItem

UNSUBSCRIBE_URL = "{{{RESEND_UNSUBSCRIBE_URL}}}"


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def render_email(briefing: Briefing) -> RenderedEmail:
    subject = " ".join(briefing.subject.split())[:150]
    html_sections = [
        _html_paragraph(briefing.introduction, css_class="introduction"),
        "<h2>Model recommendation</h2>",
        _html_recommendation(briefing),
        "<h2>Top news</h2>",
        *(_html_news_item(item, index) for index, item in enumerate(briefing.top_news, 1)),
    ]
    if briefing.important_signals:
        html_sections.extend(
            [
                "<h2>Important signals</h2>",
                *(_html_signal(signal) for signal in briefing.important_signals),
            ]
        )
    html_sections.append(f'<p class="footer"><a href="{UNSUBSCRIBE_URL}">Unsubscribe</a></p>')

    html = _html_document(subject, "".join(html_sections))
    text = _text_email(briefing, subject)
    return RenderedEmail(subject=subject, html=html, text=text)


def _html_document(subject: str, content: str) -> str:
    safe_subject = escape(subject)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_subject}</title>
</head>
<body style="margin:0;background:#f4f4f5;color:#18181b;font-family:Arial,sans-serif">
  <main style="max-width:680px;margin:0 auto;padding:32px 20px">
    <div style="background:#ffffff;border:1px solid #e4e4e7;border-radius:12px;padding:32px">
      <h1 style="margin-top:0">{safe_subject}</h1>
      {content}
    </div>
  </main>
</body>
</html>"""


def _html_recommendation(briefing: Briefing) -> str:
    recommendation = briefing.recommendation
    return "".join(
        [
            f"<h3>{escape(recommendation.model)} — {escape(recommendation.provider)}</h3>",
            _html_paragraph(recommendation.why),
            "<h4>Best for</h4>",
            _html_list(recommendation.best_for),
            "<h4>Tradeoffs</h4>",
            _html_list(recommendation.tradeoffs),
            _html_sources(recommendation.evidence_urls),
        ]
    )


def _html_news_item(item: NewsItem, index: int) -> str:
    return "".join(
        [
            f"<h3>{index}. {escape(item.headline)}</h3>",
            f"<p><strong>{escape(item.company)}</strong></p>",
            _html_paragraph(item.summary),
            f"<p><strong>Why it matters:</strong> {escape(item.why_it_matters)}</p>",
            _html_sources(item.evidence_urls),
        ]
    )


def _html_signal(signal: ImportantSignal) -> str:
    return "".join(
        [
            f"<h3>{escape(signal.headline)}</h3>",
            _html_paragraph(signal.analysis),
            f"<p><strong>Confidence:</strong> {escape(signal.confidence.title())}</p>",
            _html_sources(signal.evidence_urls),
        ]
    )


def _html_paragraph(value: str, *, css_class: str = "") -> str:
    class_attribute = f' class="{css_class}"' if css_class else ""
    return f"<p{class_attribute}>{escape(value)}</p>"


def _html_list(values: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(value)}</li>" for value in values) + "</ul>"


def _html_sources(urls: list[str]) -> str:
    links = " · ".join(
        f'<a href="{escape(url, quote=True)}">Source {index}</a>'
        for index, url in enumerate(urls, 1)
    )
    return f"<p>{links}</p>"


def _text_email(briefing: Briefing, subject: str) -> str:
    recommendation = briefing.recommendation
    lines = [
        subject,
        "",
        briefing.introduction,
        "",
        "MODEL RECOMMENDATION",
        f"{recommendation.model} — {recommendation.provider}",
        recommendation.why,
        "Best for: " + "; ".join(recommendation.best_for),
        "Tradeoffs: " + "; ".join(recommendation.tradeoffs),
        "Sources: " + " ".join(recommendation.evidence_urls),
        "",
        "TOP NEWS",
    ]
    for index, item in enumerate(briefing.top_news, 1):
        lines.extend(
            [
                f"{index}. {item.headline} — {item.company}",
                item.summary,
                f"Why it matters: {item.why_it_matters}",
                "Sources: " + " ".join(item.evidence_urls),
                "",
            ]
        )
    if briefing.important_signals:
        lines.append("IMPORTANT SIGNALS")
        for signal in briefing.important_signals:
            lines.extend(
                [
                    signal.headline,
                    signal.analysis,
                    f"Confidence: {signal.confidence.title()}",
                    "Sources: " + " ".join(signal.evidence_urls),
                    "",
                ]
            )
    lines.extend(["Unsubscribe:", UNSUBSCRIBE_URL])
    return "\n".join(lines)
