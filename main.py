"""Entrypoint: read NUTS, message only if the holding changed.

Silence is the normal outcome. A message means the position moved — that is the
entire purpose of this bot, so a daily "still TQQQ" heartbeat would be noise.
Liveness is proven by the fleet-health probe instead (see AGENTS.md).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import nuts_signal
import state_manager
import telegram_sender


def run(dry_run: bool = False, force_send: bool = False) -> int:
    try:
        data = nuts_signal.fetch()
    except Exception as exc:
        # Never invent a signal. Fail loudly so the workflow goes red and the
        # fleet-health probe catches it.
        print(f"ERROR: could not reach NUTS: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    unit = data.get("unit_test") or {}
    if not unit.get("pass"):
        # NUTS refuses to trust its own numbers; so do we.
        print(f"ERROR: NUTS RSI unit test FAILED: {unit}", file=sys.stderr)
        return 1

    now = nuts_signal.holding(data)
    previous = state_manager.read_signal()
    print(f"NUTS holding: {now!r}   previous: {previous!r}")

    if not nuts_signal.changed(data, previous) and not force_send:
        print(f"NUTS-SIGNAL OK unchanged={now} date={dt.date.today()}")
        return 0

    message = nuts_signal.render(data, previous)
    if dry_run:
        print(message)
        print("\n[dry-run] not sent, state not written")
        return 0

    telegram_sender.send(message)
    state_manager.write_signal(now)
    print(f"NUTS-SIGNAL CHANGED {previous!r} -> {now!r} date={dt.date.today()}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the message; send nothing, write nothing")
    ap.add_argument("--force-send", action="store_true",
                    help="send even if the holding did not change")
    args = ap.parse_args()
    return run(dry_run=args.dry_run, force_send=args.force_send)


if __name__ == "__main__":
    raise SystemExit(main())
