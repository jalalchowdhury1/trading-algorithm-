"""HTTP-only Telegram sender.

HTML, never Markdown: condition labels are full of `<`, `>` and `_`, and an
unbalanced Markdown token makes Telegram reject the whole message. Every piece
of NUTS text is escaped by nuts_signal before it reaches markup; on any 4xx we
retry once with no parse_mode so a formatting bug can never cost the alert.
"""
from __future__ import annotations

import json
import os
import urllib.request

TIMEOUT_S = 20


def configured() -> bool:
    return bool(os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def _post(payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/sendMessage"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.load(r)


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
