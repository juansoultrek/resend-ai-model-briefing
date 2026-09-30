from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import resend
from pydantic import SecretStr
from resend.exceptions import NoContentError, ResendError

from ai_model_briefing.resend_client import call_with_api_key

ContactCreator = Callable[[resend.Contacts.CreateParams], resend.Contacts.CreateContactResponse]
ContactUpdater = Callable[[resend.Contacts.UpdateParams], resend.Contacts.UpdateContactResponse]
EMAIL_PATTERN = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


class SubscriberError(RuntimeError):
    """Raised when a subscriber operation cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class SubscriberReceipt:
    contact_id: str
    email: str
    subscribed: bool


def subscribe(
    email: str,
    *,
    api_key: SecretStr,
    segment_id: UUID,
    consent_confirmed: bool,
    creator: ContactCreator = resend.Contacts.create,
) -> SubscriberReceipt:
    normalized_email = _normalize_email(email)
    if not consent_confirmed:
        raise SubscriberError("subscription requires explicit consent confirmation")

    params: resend.Contacts.CreateParams = {
        "email": normalized_email,
        "unsubscribed": False,
        "segments": [{"id": str(segment_id)}],
    }
    try:
        response = call_with_api_key(api_key, lambda: creator(params))
    except (ResendError, NoContentError, ValueError) as error:
        raise SubscriberError("Resend could not subscribe the contact") from error
    return _receipt(response.get("id", ""), normalized_email, subscribed=True)


def unsubscribe(
    email: str,
    *,
    api_key: SecretStr,
    updater: ContactUpdater = resend.Contacts.update,
) -> SubscriberReceipt:
    normalized_email = _normalize_email(email)
    params: resend.Contacts.UpdateParams = {
        "email": normalized_email,
        "unsubscribed": True,
    }
    try:
        response = call_with_api_key(api_key, lambda: updater(params))
    except (ResendError, NoContentError, ValueError) as error:
        raise SubscriberError("Resend could not unsubscribe the contact") from error
    return _receipt(response.get("id", ""), normalized_email, subscribed=False)


def _normalize_email(value: str) -> str:
    normalized = value.strip()
    if normalized != value or len(normalized) > 254 or not EMAIL_PATTERN.fullmatch(normalized):
        raise SubscriberError("invalid contact email address")
    return normalized


def _receipt(contact_id: str, email: str, *, subscribed: bool) -> SubscriberReceipt:
    normalized_id = contact_id.strip()
    if not normalized_id:
        raise SubscriberError("Resend returned an invalid contact ID")
    return SubscriberReceipt(
        contact_id=normalized_id,
        email=email,
        subscribed=subscribed,
    )
