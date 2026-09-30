from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from uuid import UUID

import resend
from pydantic import SecretStr
from resend.exceptions import NoContentError, ResendError

from ai_model_briefing.email import UNSUBSCRIBE_URL, RenderedEmail

BroadcastCreator = Callable[[resend.Broadcasts.CreateParams], resend.Broadcasts.CreateResponse]
_RESEND_CONFIGURATION_LOCK = Lock()


class DeliveryError(RuntimeError):
    """Raised when a briefing cannot be safely handed to Resend."""


@dataclass(frozen=True, slots=True)
class BroadcastReceipt:
    broadcast_id: str
    sent: bool


def deliver_broadcast(
    email: RenderedEmail,
    *,
    api_key: SecretStr,
    from_address: str,
    segment_id: UUID,
    send: bool,
    creator: BroadcastCreator = resend.Broadcasts.create,
) -> BroadcastReceipt:
    if UNSUBSCRIBE_URL not in email.html or UNSUBSCRIBE_URL not in email.text:
        raise DeliveryError("the briefing is missing the Resend unsubscribe link")

    params: resend.Broadcasts.CreateParams = {
        "segment_id": str(segment_id),
        "from": from_address,
        "subject": email.subject,
        "html": email.html,
        "text": email.text,
        "name": email.subject[:70],
        "send": send,
    }

    try:
        response = _create_with_scoped_api_key(api_key, params, creator)
    except (ResendError, NoContentError, ValueError) as error:
        raise DeliveryError("Resend could not create the broadcast") from error

    broadcast_id = response.get("id", "").strip()
    if not broadcast_id:
        raise DeliveryError("Resend returned an invalid broadcast ID")
    return BroadcastReceipt(broadcast_id=broadcast_id, sent=send)


def _create_with_scoped_api_key(
    api_key: SecretStr,
    params: resend.Broadcasts.CreateParams,
    creator: BroadcastCreator,
) -> resend.Broadcasts.CreateResponse:
    with _RESEND_CONFIGURATION_LOCK:
        previous_key = resend.api_key
        resend.api_key = api_key.get_secret_value()
        try:
            return creator(params)
        finally:
            resend.api_key = previous_key
