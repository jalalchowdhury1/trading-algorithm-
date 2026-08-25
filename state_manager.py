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


def read_bands(path: pathlib.Path = STATE_PATH) -> dict | None:
    """Last known proximity band per Frontrunners condition.

    None (not {}) when we have never recorded any — `escalations` treats those
    differently: None means "first run, report what is already near", whereas
    {} would mean "everything was quiet", inventing crossings that never
    happened.
    """
    try:
        bands = json.loads(pathlib.Path(path).read_text()).get("bands")
    except Exception:
        return None
    return bands if isinstance(bands, dict) and bands else None


def write_state(holding: str, bands: dict | None = None,
                path: pathlib.Path = STATE_PATH) -> None:
    path = pathlib.Path(path)
    try:
        existing = json.loads(path.read_text())
    except Exception:
        existing = {}
    existing.update({
        "holding": holding,
        "sent_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "NUTS /evaluate",
    })
    if bands is not None:
        existing["bands"] = bands
    path.write_text(json.dumps(existing, indent=2) + "\n")


def write_signal(holding: str, path: pathlib.Path = STATE_PATH) -> None:
    write_state(holding, path=path)
