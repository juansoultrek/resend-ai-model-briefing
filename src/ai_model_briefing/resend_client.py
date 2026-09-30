from __future__ import annotations

from collections.abc import Callable
from threading import Lock

import resend
from pydantic import SecretStr

_RESEND_CONFIGURATION_LOCK = Lock()


def call_with_api_key[Result](api_key: SecretStr, operation: Callable[[], Result]) -> Result:
    with _RESEND_CONFIGURATION_LOCK:
        previous_key = resend.api_key
        resend.api_key = api_key.get_secret_value()
        try:
            return operation()
        finally:
            resend.api_key = previous_key
