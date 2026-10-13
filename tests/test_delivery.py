from __future__ import annotations

from uuid import UUID

import pytest
import resend
from pydantic import SecretStr
from resend.exceptions import ResendError

from ai_model_briefing.delivery import DeliveryError, deliver_broadcast
from ai_model_briefing.email import UNSUBSCRIBE_URL, RenderedEmail

SEGMENT_ID = UUID("78261eea-8f8b-4381-83c6-79fa7120f1cf")
BROADCAST_ID = "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"


def make_email(*, include_unsubscribe: bool = True) -> RenderedEmail:
    footer = UNSUBSCRIBE_URL if include_unsubscribe else ""
    return RenderedEmail(
        subject="AI model briefing",
        html=f'<p>Briefing</p><a href="{footer}">Unsubscribe</a>',
        text=f"Briefing\nUnsubscribe: {footer}",
    )


def empty_lister(
    params: resend.Broadcasts.ListParams | None = None,
) -> resend.Broadcasts.ListResponse:
    return {"object": "list", "data": [], "has_more": False}


def test_creates_and_sends_broadcast_with_scoped_api_key() -> None:
    captured: dict[str, object] = {}

    def creator(params: resend.Broadcasts.CreateParams) -> resend.Broadcasts.CreateResponse:
        assert resend.api_key == "re_test"
        captured.update(params)
        return {"id": BROADCAST_ID}

    original_key = resend.api_key
    receipt = deliver_broadcast(
        make_email(),
        api_key=SecretStr("re_test"),
        from_address="Briefing <briefing@example.com>",
        segment_id=SEGMENT_ID,
        delivery_key="ai-model-briefing:daily:2026-09-30",
        send=True,
        creator=creator,
        lister=empty_lister,
    )

    assert receipt.broadcast_id == BROADCAST_ID
    assert receipt.sent is True
    assert captured["segment_id"] == str(SEGMENT_ID)
    assert captured["send"] is True
    assert captured["name"] == "ai-model-briefing:daily:2026-09-30"
    assert UNSUBSCRIBE_URL in str(captured["html"])
    assert resend.api_key == original_key


def test_can_create_a_draft() -> None:
    def creator(params: resend.Broadcasts.CreateParams) -> resend.Broadcasts.CreateResponse:
        assert params["send"] is False
        return {"id": BROADCAST_ID}

    receipt = deliver_broadcast(
        make_email(),
        api_key=SecretStr("re_test"),
        from_address="briefing@example.com",
        segment_id=SEGMENT_ID,
        delivery_key="ai-model-briefing:daily:2026-09-30",
        send=False,
        creator=creator,
        lister=empty_lister,
    )

    assert receipt.sent is False


def test_rejects_email_without_unsubscribe_link() -> None:
    with pytest.raises(DeliveryError, match="unsubscribe link"):
        deliver_broadcast(
            make_email(include_unsubscribe=False),
            api_key=SecretStr("re_test"),
            from_address="briefing@example.com",
            segment_id=SEGMENT_ID,
            delivery_key="ai-model-briefing:daily:2026-09-30",
            send=True,
            lister=empty_lister,
        )


def test_wraps_resend_errors_and_restores_api_key() -> None:
    def creator(params: resend.Broadcasts.CreateParams) -> resend.Broadcasts.CreateResponse:
        raise ResendError(500, "application_error", "sensitive details", "retry")

    original_key = resend.api_key
    with pytest.raises(DeliveryError, match="could not create"):
        deliver_broadcast(
            make_email(),
            api_key=SecretStr("re_test"),
            from_address="briefing@example.com",
            segment_id=SEGMENT_ID,
            delivery_key="ai-model-briefing:daily:2026-09-30",
            send=True,
            creator=creator,
            lister=empty_lister,
        )
    assert resend.api_key == original_key


def test_rejects_empty_broadcast_id() -> None:
    def creator(params: resend.Broadcasts.CreateParams) -> resend.Broadcasts.CreateResponse:
        return {"id": ""}

    with pytest.raises(DeliveryError, match="invalid broadcast ID"):
        deliver_broadcast(
            make_email(),
            api_key=SecretStr("re_test"),
            from_address="briefing@example.com",
            segment_id=SEGMENT_ID,
            delivery_key="ai-model-briefing:daily:2026-09-30",
            send=True,
            creator=creator,
            lister=empty_lister,
        )


def test_skips_a_duplicate_broadcast() -> None:
    def lister(
        params: resend.Broadcasts.ListParams | None = None,
    ) -> resend.Broadcasts.ListResponse:
        return {
            "object": "list",
            "data": [
                {
                    "id": BROADCAST_ID,
                    "name": "ai-model-briefing:daily:2026-09-30",
                    "segment_id": str(SEGMENT_ID),
                }
            ],
            "has_more": False,
        }  # type: ignore[return-value]

    receipt = deliver_broadcast(
        make_email(),
        api_key=SecretStr("re_test"),
        from_address="briefing@example.com",
        segment_id=SEGMENT_ID,
        delivery_key="ai-model-briefing:daily:2026-09-30",
        send=True,
        creator=lambda params: pytest.fail("duplicate broadcast must not be created"),
        lister=lister,
    )

    assert receipt.broadcast_id == BROADCAST_ID
    assert receipt.sent is False
    assert receipt.duplicate is True
