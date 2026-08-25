"""Entrypoint: read NUTS, message only when something actually moved.

Two kinds of alert, both change-only:

  🔄 CHANGED  — the holding moved. Composer will rebalance into this.
  🟠 WARNING  — a Frontrunners trigger crossed into a closer band. A heads-up
                that the position may move, not that it has.

Silence is the normal outcome, so a daily "still TQQQ" heartbeat would be
noise. Liveness is proven by the fleet-health probe instead (see AGENTS.md).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import nuts_signal
import state_manager
import telegram_sender


def run(dry_run: bool = False, force_send: bool = False,
        no_warnings: bool = False) -> int:
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
    bands_now = nuts_signal.frontrunner_bands(data)
    bands_was = state_manager.read_bands()
    moves = [] if no_warnings else nuts_signal.escalations(bands_now, bands_was)

    print(f"NUTS holding: {now!r}   previous: {previous!r}")
    near = {k: v for k, v in bands_now.items() if v != nuts_signal.QUIET}
    print(f"near-firing: {near or 'none'}")

    position_moved = nuts_signal.changed(data, previous) or force_send
    if not position_moved and not moves:
        print(f"NUTS-SIGNAL OK unchanged={now} date={dt.date.today()}")
        return 0

    messages = []
    if position_moved:
        messages.append(("signal", nuts_signal.render(data, previous)))
    if moves:
        messages.append(("warning", nuts_signal.render_warning(data, moves)))

    if dry_run:
        for kind, text in messages:
            print(f"\n===== {kind.upper()} =====\n{text}")
        print("\n[dry-run] nothing sent, state not written")
        return 0

    for _, text in messages:
        telegram_sender.send(text)
    state_manager.write_state(now, bands=bands_now)

    if position_moved:
        print(f"NUTS-SIGNAL CHANGED {previous!r} -> {now!r} date={dt.date.today()}")
    else:
        # Still a marker the fleet probe accepts: the run reached NUTS, passed
        # its unit test, and did real work.
        print(f"NUTS-SIGNAL OK unchanged={now} date={dt.date.today()} "
              f"warnings={len(moves)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the messages; send nothing, write nothing")
    ap.add_argument("--force-send", action="store_true",
                    help="send the signal even if the holding did not change")
    ap.add_argument("--no-warnings", action="store_true",
                    help="suppress proximity warnings (signal changes only)")
    args = ap.parse_args()
    return run(dry_run=args.dry_run, force_send=args.force_send,
               no_warnings=args.no_warnings)


if __name__ == "__main__":
    raise SystemExit(main())
