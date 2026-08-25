"""Proximity warnings: fire on crossings only, never on every poll."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import nuts_signal as ns
from tests.test_nuts_signal import node, payload


def fr(*nodes):
    data = payload()
    data["frontrunners"]["nodes"] = list(nodes)
    return data


# ── band_of ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("distance,expected", [
    (0.5, "IMMINENT"), (2.0, "IMMINENT"),
    (2.1, "WARNING"), (5.0, "WARNING"),
    (5.1, "WATCH"), (10.0, "WATCH"),
    (10.1, ns.QUIET), (35.0, ns.QUIET),
])
def test_band_boundaries(distance, expected):
    n = node("SPY RSI(10) > 80", 80 - distance, 80, ">", False)
    assert ns.band_of(n) == expected


def test_a_fired_condition_is_not_a_warning():
    """It already fired — that is the CHANGED alert's job, not a heads-up."""
    n = node("SPY RSI(10) > 80", 81, 80, ">", True)
    assert ns.band_of(n) == ns.QUIET


# ── escalations: the anti-noise rule ─────────────────────────────────────────

def test_first_run_reports_only_what_is_already_near():
    current = {"a": "WATCH", "b": ns.QUIET, "c": "IMMINENT"}
    got = ns.escalations(current, None)
    assert {m[0] for m in got} == {"a", "c"}


def test_staying_in_the_same_band_is_silent():
    """A trigger parked at 8 away must not alert on all 16 polls a day."""
    bands = {"a": "WATCH"}
    assert ns.escalations(bands, bands) == []


def test_moving_closer_alerts():
    got = ns.escalations({"a": "WARNING"}, {"a": "WATCH"})
    assert got == [("a", "WATCH", "WARNING", "closer")]


def test_moving_further_away_but_still_near_is_silent():
    """Backing off WARNING -> WATCH is not urgent; only 'cleared' is worth a ping."""
    assert ns.escalations({"a": "WATCH"}, {"a": "WARNING"}) == []


def test_clearing_completely_alerts_once():
    got = ns.escalations({"a": ns.QUIET}, {"a": "WARNING"})
    assert got == [("a", "WARNING", ns.QUIET, "cleared")]


def test_staying_quiet_is_silent():
    assert ns.escalations({"a": ns.QUIET}, {"a": ns.QUIET}) == []


def test_jumping_two_bands_reports_the_new_band():
    got = ns.escalations({"a": "IMMINENT"}, {"a": "WATCH"})
    assert got == [("a", "WATCH", "IMMINENT", "closer")]


# ── frontrunner_bands ────────────────────────────────────────────────────────

def test_frontrunner_bands_skips_leaves():
    data = fr(node("cond", 75, 80, ">", False),
              node("→ UVXY", None, None, ">", True, is_leaf=True))
    assert list(ns.frontrunner_bands(data)) == ["cond"]


def test_frontrunner_bands_covers_every_condition():
    data = fr(node("a", 75, 80, ">", False), node("b", 40, 30, "<", False))
    assert set(ns.frontrunner_bands(data)) == {"a", "b"}


# ── render_warning ───────────────────────────────────────────────────────────

def test_warning_names_the_worst_band_in_the_header():
    data = fr(node("SPY RSI(10) > 80", 79, 80, ">", False, outcome="UVXY"))
    msg = ns.render_warning(data, [("SPY RSI(10) > 80", "WATCH", "IMMINENT", "closer")])
    assert "FRONTRUNNERS IMMINENT" in msg


def test_warning_says_it_is_not_a_position_change():
    data = fr(node("SPY RSI(10) > 80", 75, 80, ">", False, outcome="UVXY"))
    msg = ns.render_warning(data, [("SPY RSI(10) > 80", ns.QUIET, "WATCH", "closer")])
    assert "not a position change" in msg
    assert "current holding" in msg


def test_warning_shows_value_distance_and_outcome():
    data = fr(node("SOXX RSI(10) < 30", 37.97, 30, "<", False, outcome="SOXL"))
    msg = ns.render_warning(data, [("SOXX RSI(10) < 30", ns.QUIET, "WATCH", "closer")])
    assert "37.97" in msg and "7.97" in msg and "SOXL" in msg


def test_cleared_only_renders_the_cleared_section():
    data = fr(node("SPY RSI(10) > 80", 40, 80, ">", False, outcome="UVXY"))
    msg = ns.render_warning(data, [("SPY RSI(10) > 80", "WATCH", ns.QUIET, "cleared")])
    assert "cleared" in msg.lower()
    assert "MOVED CLOSER" not in msg


def test_warning_escapes_html_and_balances_tags():
    data = fr(node("A > B & C", 79, 80, ">", False, outcome="X"))
    msg = ns.render_warning(data, [("A > B & C", ns.QUIET, "IMMINENT", "closer")])
    assert "&gt;" in msg and "&amp;" in msg
    for tag in ("b", "i", "blockquote"):
        assert msg.count(f"<{tag}>") == msg.count(f"</{tag}>")


def test_warning_fits_one_telegram_message():
    nodes = [node(f"T{i} RSI(10) > 80", 79, 80, ">", False, outcome="UVXY")
             for i in range(10)]
    data = fr(*nodes)
    moves = [(n["label"], ns.QUIET, "IMMINENT", "closer") for n in nodes]
    assert len(ns.render_warning(data, moves)) < 4096
