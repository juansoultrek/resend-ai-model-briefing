from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import resend
from pydantic import SecretStr
from resend.exceptions import NoContentError, ResendError

from ai_model_briefing.email import UNSUBSCRIBE_URL, RenderedEmail
from ai_model_briefing.resend_client import call_with_api_key

BroadcastCreator = Callable[[resend.Broadcasts.CreateParams], resend.Broadcasts.CreateResponse]
BroadcastLister = Callable[[resend.Broadcasts.ListParams | None], resend.Broadcasts.ListResponse]


class DeliveryError(RuntimeError):
    """Raised when a briefing cannot be safely handed to Resend."""


@dataclass(frozen=True, slots=True)
class BroadcastReceipt:
    broadcast_id: str
    sent: bool
    duplicate: bool = False


def find_existing_broadcast(
    *,
    api_key: SecretStr,
    segment_id: UUID,
    delivery_key: str,
    lister: BroadcastLister = resend.Broadcasts.list,
) -> str | None:
    try:
        response = call_with_api_key(api_key, lambda: lister({"limit": 100}))
    except (ResendError, NoContentError, ValueError) as error:
        raise DeliveryError("Resend could not check prior broadcasts") from error

    for broadcast in response.get("data", []):
        if broadcast.get("name") == delivery_key and broadcast.get("segment_id") == str(segment_id):
            broadcast_id = broadcast.get("id", "").strip()
            if broadcast_id:
                return broadcast_id
    return None


def deliver_broadcast(
    email: RenderedEmail,
    *,
    api_key: SecretStr,
    from_address: str,
    segment_id: UUID,
    delivery_key: str,
    send: bool,
    creator: BroadcastCreator = resend.Broadcasts.create,
    lister: BroadcastLister = resend.Broadcasts.list,
) -> BroadcastReceipt:
    if UNSUBSCRIBE_URL not in email.html or UNSUBSCRIBE_URL not in email.text:
        raise DeliveryError("the briefing is missing the Resend unsubscribe link")

    existing_id = find_existing_broadcast(
        api_key=api_key,
        segment_id=segment_id,
        delivery_key=delivery_key,
        lister=lister,
    )
    if existing_id:
        return BroadcastReceipt(existing_id, sent=False, duplicate=True)

    params: resend.Broadcasts.CreateParams = {
        "segment_id": str(segment_id),
        "from": from_address,
        "subject": email.subject,
        "html": email.html,
        "text": email.text,
        "name": delivery_key,
        "send": send,
    }

    try:
        response = call_with_api_key(api_key, lambda: creator(params))
    except (ResendError, NoContentError, ValueError) as error:
        raise DeliveryError("Resend could not create the broadcast") from error

    broadcast_id = response.get("id", "").strip()
    if not broadcast_id:
        raise DeliveryError("Resend returned an invalid broadcast ID")
    return BroadcastReceipt(broadcast_id=broadcast_id, sent=send)
