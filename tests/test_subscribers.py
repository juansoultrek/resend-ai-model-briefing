from uuid import UUID

import pytest
import resend
from pydantic import SecretStr

from ai_model_briefing.subscribers import SubscriberError, subscribe, unsubscribe

SEGMENT_ID = UUID("78261eea-8f8b-4381-83c6-79fa7120f1cf")
CONTACT_ID = "479e3145-dd38-476b-932c-529ceb705947"


def test_subscribes_contact_to_segment_with_confirmed_consent() -> None:
    captured: dict[str, object] = {}

    def creator(params: resend.Contacts.CreateParams) -> resend.Contacts.CreateContactResponse:
        assert resend.api_key == "re_test"
        captured.update(params)
        return {"object": "contact", "id": CONTACT_ID}

    receipt = subscribe(
        "reader@example.com",
        api_key=SecretStr("re_test"),
        segment_id=SEGMENT_ID,
        consent_confirmed=True,
        creator=creator,
    )

    assert receipt.subscribed is True
    assert captured == {
        "email": "reader@example.com",
        "unsubscribed": False,
        "segments": [{"id": str(SEGMENT_ID)}],
    }


def test_requires_explicit_consent() -> None:
    with pytest.raises(SubscriberError, match="explicit consent"):
        subscribe(
            "reader@example.com",
            api_key=SecretStr("re_test"),
            segment_id=SEGMENT_ID,
            consent_confirmed=False,
        )


def test_unsubscribes_contact_globally() -> None:
    captured: dict[str, object] = {}

    def updater(params: resend.Contacts.UpdateParams) -> resend.Contacts.UpdateContactResponse:
        captured.update(params)
        return {"object": "contact", "id": CONTACT_ID}

    receipt = unsubscribe(
        "reader@example.com",
        api_key=SecretStr("re_test"),
        updater=updater,
    )

    assert receipt.subscribed is False
    assert captured == {"email": "reader@example.com", "unsubscribed": True}


@pytest.mark.parametrize(
    "email",
    [
        " reader@example.com",
        "reader@example.com\nBcc: attacker@example.com",
        "not-an-email",
        "reader@example",
    ],
)
def test_rejects_invalid_email(email: str) -> None:
    with pytest.raises(SubscriberError, match="invalid contact email"):
        unsubscribe(email, api_key=SecretStr("re_test"))


def test_restores_resend_key_after_contact_error() -> None:
    def creator(params: resend.Contacts.CreateParams) -> resend.Contacts.CreateContactResponse:
        raise ValueError("sensitive provider details")

    original_key = resend.api_key
    with pytest.raises(SubscriberError, match="could not subscribe"):
        subscribe(
            "reader@example.com",
            api_key=SecretStr("re_test"),
            segment_id=SEGMENT_ID,
            consent_confirmed=True,
            creator=creator,
        )
    assert resend.api_key == original_key
