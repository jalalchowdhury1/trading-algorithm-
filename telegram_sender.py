"""HTTP-only Telegram sender.

HTML, never Markdown: condition labels are full of `<`, `>` and `_`, and an
unbalanced Markdown token makes Telegram reject the whole message. Every piece
of NUTS text is escaped by nuts_signal before it reaches markup; on any 4xx we
retry once with no parse_mode so a formatting bug can never cost the alert.

Telegram Inbox (19 Oct 2026): the request goes to the health-hub relay first,
which archives it and shows it as a card, with the same body and the same reply.
If the relay is unreachable, slower than 8 s, answers 5xx, 401 (token not on
its allowlist) or 404, the SAME request goes straight to api.telegram.org.
Rollback without a code change: set TELEGRAM_API_BASE=https://api.telegram.org.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

TIMEOUT_S = 20
RELAY_TIMEOUT_S = 8
DIRECT_BASE = "https://api.telegram.org"
RELAY_BASE = "https://jalal-health.vercel.app/api/tg/frontrunners"


def configured() -> bool:
    return bool(os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def _post_to(base: str, payload: dict, timeout: float) -> dict:
    url = f"{base}/bot{os.environ['TELEGRAM_TOKEN']}/sendMessage"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _post(payload: dict) -> dict:
    base = (os.getenv("TELEGRAM_API_BASE") or RELAY_BASE).rstrip("/")
    if base != DIRECT_BASE:
        try:
            return _post_to(base, payload, RELAY_TIMEOUT_S)
        except urllib.error.HTTPError as e:
            # Telegram's own 4xx (bad markup) comes back through the relay unchanged:
            # raise it so send() does its plain-text retry, exactly as before.
            if not (e.code >= 500 or e.code in (401, 404)):
                raise
        except OSError:  # connection refused/reset, DNS, timeout
            pass
    return _post_to(DIRECT_BASE, payload, TIMEOUT_S)


def send(text: str) -> dict:
    payload = {
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        return _post(payload)
    except Exception:
        payload.pop("parse_mode")
        return _post(payload)
