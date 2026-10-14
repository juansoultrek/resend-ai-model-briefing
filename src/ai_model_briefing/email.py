# ruff: noqa: E501
from __future__ import annotations

from dataclasses import dataclass
from html import escape

from ai_model_briefing.briefing import Briefing, ImportantSignal, NewsItem

# Inline email styles are intentionally kept intact for broad client compatibility.

UNSUBSCRIBE_URL = "{{{RESEND_UNSUBSCRIBE_URL}}}"
EMAIL_SUBJECT = "🤖 AI Daily Briefing ✨"


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def render_email(briefing: Briefing) -> RenderedEmail:
    subject = EMAIL_SUBJECT
    html_sections = [
        _html_paragraph(briefing.introduction, css_class="introduction"),
        _html_section_heading("Model recommendation", "7c3aed"),
        _html_recommendation(briefing),
        _html_section_heading("Top news", "2563eb"),
        *(_html_news_item(item, index) for index, item in enumerate(briefing.top_news, 1)),
    ]
    if briefing.important_signals:
        html_sections.extend(
            [
                _html_section_heading("Important signals", "059669"),
                *(_html_signal(signal) for signal in briefing.important_signals),
            ]
        )

    html = _html_document(subject, "".join(html_sections))
    text = _text_email(briefing, subject)
    return RenderedEmail(subject=subject, html=html, text=text)


def _html_document(subject: str, content: str) -> str:
    safe_subject = escape(subject)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{safe_subject}</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" role="presentation" style="background:#f3f4f6;padding:24px 12px;">
    <tr>
      <td align="center">
        <table border="0" cellpadding="0" cellspacing="0" width="600" role="presentation" style="max-width:600px;background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
          <tr>
            <td style="padding:28px 32px 22px 32px;border-bottom:1px solid #f3f4f6;">
              <p style="margin:0;color:#7c3aed;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;">AI Model Radar</p>
              <h1 style="margin:7px 0 0 0;color:#111827;font-size:24px;line-height:1.25;font-weight:750;">{safe_subject}</h1>
              <p style="margin:8px 0 0 0;color:#6b7280;font-size:13px;line-height:1.5;">The model releases and signals worth knowing today.</p>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 32px 8px 32px;color:#374151;font-size:14px;line-height:1.65;">
              {content}
            </td>
          </tr>
          <tr>
            <td style="padding:24px 32px 28px 32px;border-top:1px solid #f3f4f6;background:#fafafa;">
              <p style="margin:0 0 12px 0;color:#6b7280;font-size:12px;line-height:1.5;">You're receiving this because you subscribed to AI Daily Briefing.</p>
              <p style="margin:0 0 14px 0;color:#9ca3af;font-size:12px;line-height:1.5;"><a href="{UNSUBSCRIBE_URL}" style="color:#6b7280;">Unsubscribe</a></p>
              <p style="margin:0;color:#9ca3af;font-size:11px;line-height:1.5;">Sent by juansoultrek.com · Built with Resend</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _html_recommendation(briefing: Briefing) -> str:
    recommendation = briefing.recommendation
    return "".join(
        [
            '<div style="margin:0 0 28px 0;border:1px solid #ddd6fe;border-radius:10px;overflow:hidden;">',
            '<div style="padding:18px 20px;background:#f5f3ff;border-bottom:1px solid #ddd6fe;">',
            '<span style="display:inline-block;background:#7c3aed;color:#ffffff;font-size:10px;font-weight:700;letter-spacing:0.06em;padding:3px 8px;border-radius:4px;text-transform:uppercase;">Today\'s pick</span>',
            f'<h3 style="margin:10px 0 3px 0;color:#111827;font-size:18px;line-height:1.35;">{escape(recommendation.model)}</h3>',
            f'<p style="margin:0;color:#6b7280;font-size:12px;">{escape(recommendation.provider)}</p>',
            "</div>",
            '<div style="padding:18px 20px;">',
            _html_paragraph(recommendation.why),
            '<h4 style="margin:18px 0 8px 0;color:#111827;font-size:13px;">Best for</h4>',
            _html_list(recommendation.best_for),
            '<h4 style="margin:18px 0 8px 0;color:#111827;font-size:13px;">Tradeoffs</h4>',
            _html_list(recommendation.tradeoffs),
            _html_sources(recommendation.evidence_urls),
            "</div></div>",
        ]
    )


def _html_news_item(item: NewsItem, index: int) -> str:
    return "".join(
        [
            '<div style="margin:0 0 18px 0;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;">',
            '<div style="padding:16px 20px;background:#f9fafb;border-bottom:1px solid #e5e7eb;">',
            f'<span style="display:inline-block;background:#2563eb;color:#ffffff;font-size:10px;font-weight:700;letter-spacing:0.06em;padding:3px 8px;border-radius:4px;">#{index}</span>',
            f'<span style="color:#6b7280;font-size:12px;margin-left:8px;">{escape(item.company)}</span>',
            f'<h3 style="margin:10px 0 0 0;color:#111827;font-size:16px;line-height:1.4;">{escape(item.headline)}</h3>',
            "</div>",
            '<div style="padding:16px 20px;">',
            _html_paragraph(item.summary),
            f'<p style="margin:12px 0;color:#374151;font-size:14px;line-height:1.55;"><strong style="color:#111827;">Why it matters:</strong> {escape(item.why_it_matters)}</p>',
            _html_sources(item.evidence_urls),
            "</div></div>",
        ]
    )


def _html_signal(signal: ImportantSignal) -> str:
    return "".join(
        [
            '<div style="margin:0 0 18px 0;padding:18px 20px;border-left:4px solid #059669;background:#ecfdf5;border-radius:0 10px 10px 0;">',
            f'<h3 style="margin:0 0 8px 0;color:#111827;font-size:16px;line-height:1.4;">{escape(signal.headline)}</h3>',
            _html_paragraph(signal.analysis),
            f'<p style="margin:12px 0;color:#374151;font-size:13px;"><strong style="color:#111827;">Confidence:</strong> {escape(signal.confidence.title())}</p>',
            _html_sources(signal.evidence_urls),
            "</div>",
        ]
    )


def _html_paragraph(value: str, *, css_class: str = "") -> str:
    class_attribute = f' class="{css_class}"' if css_class else ""
    return f'<p{class_attribute} style="margin:0 0 12px 0;color:#374151;font-size:14px;line-height:1.65;">{escape(value)}</p>'


def _html_list(values: list[str]) -> str:
    return (
        '<ul style="margin:0;padding-left:20px;color:#374151;font-size:14px;line-height:1.65;">'
        + "".join(f"<li>{escape(value)}</li>" for value in values)
        + "</ul>"
    )


def _html_sources(urls: list[str]) -> str:
    links = " · ".join(
        f'<a href="{escape(url, quote=True)}" style="color:#4f46e5;font-weight:600;text-decoration:none;">Source {index}</a>'
        for index, url in enumerate(urls, 1)
    )
    return f'<p style="margin:14px 0 0 0;font-size:12px;line-height:1.5;">{links}</p>'


def _html_section_heading(title: str, accent: str) -> str:
    return (
        '<table border="0" cellpadding="0" cellspacing="0" width="100%" role="presentation" '
        'style="margin:24px 0 14px 0;"><tr>'
        f'<td style="width:4px;background:#{accent};border-radius:2px;">&nbsp;</td>'
        f'<td style="padding-left:12px;"><h2 style="margin:0;color:#111827;font-size:18px;font-weight:700;">{escape(title)}</h2></td>'
        "</tr></table>"
    )


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
