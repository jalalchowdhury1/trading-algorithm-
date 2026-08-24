"""The last holding we told Jalal about.

Committed back to the repo by the workflow, the hedgelab pattern — a GitHub
Actions runner keeps no state of its own.

The S3 path is GONE. Until 2026-08-06 this repo ran on BOTH GitHub Actions and
AWS Lambda with two independent state stores, which diverged and double-alerted
every morning. GitHub Actions is the single canonical runner; a second store is
how you get a second answer.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib

STATE_PATH = pathlib.Path(__file__).with_name("trading_state.json")


def read_signal(path: pathlib.Path = STATE_PATH) -> str | None:
    """The last holding we sent, or None if we have never sent one.

    A missing or unreadable file reads as None, which renders as a "first
    reading" message rather than a bogus change. Corrupt state must not
    fabricate a transition that never happened.
    """
    try:
        value = json.loads(pathlib.Path(path).read_text()).get("holding")
    except Exception:
        return None
    return value if isinstance(value, str) and value.strip() else None


def write_signal(holding: str, path: pathlib.Path = STATE_PATH) -> None:
    pathlib.Path(path).write_text(json.dumps({
        "holding": holding,
        "sent_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "NUTS /evaluate",
    }, indent=2) + "\n")
