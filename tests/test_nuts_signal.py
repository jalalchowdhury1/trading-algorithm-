import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import nuts_signal as ns


def node(label, live, threshold, operator, result, **kw):
    base = {"label": label, "live_value": live, "threshold": threshold,
            "operator": operator, "result": result,
            "distance": (live - threshold) if None not in (live, threshold) else 0,
            "close_call": False, "is_leaf": False, "active": False,
            "outcome": None}
    base.update(kw)
    return base


def payload(fr_fired=False, fr_result="→ FTLT", ftlt="TQQQ", bs="BIL/TQQQ",
            source="ftlt", nodes=None):
    n = nodes or [node("SPY vs 200d MA", 763.57, 706.82, ">", True, active=True)]
    return {
        "frontrunners": {"fired": fr_fired, "result": fr_result, "nodes": []},
        "ftlt": {"fired": True, "result": ftlt, "nodes": n},
        "blackswan": {"fired": True, "result": bs, "nodes": []},
        "final_result": ftlt, "final_source": source,
        "unit_test": {"pass": True}, "evaluated_at": "2026-08-24T14:05:39-0400",
        "download_errors": [],
    }


# ── holding: the thing change-detection keys on ─────────────────────────────

def test_holding_is_ftlt_plus_blackswan_when_frontrunners_quiet():
    assert ns.holding(payload()) == "TQQQ + BIL/TQQQ"


def test_holding_is_frontrunners_alone_when_it_fires():
    assert ns.holding(payload(fr_fired=True, fr_result="UVXY")) == "UVXY"


def test_blackswan_flip_counts_as_a_change():
    """A BlackSwan move changes half the book — it must not be silent."""
    before = ns.holding(payload(bs="BIL/TQQQ"))
    after = ns.holding(payload(bs="TQQQ"))
    assert before != after
    assert ns.changed(payload(bs="TQQQ"), before) is True


def test_identical_state_is_not_a_change():
    data = payload()
    assert ns.changed(data, ns.holding(data)) is False


def test_no_previous_state_counts_as_a_change():
    assert ns.changed(payload(), None) is True


# ── condition rendering: the ambiguity Jalal flagged ────────────────────────

def test_true_condition_shows_holds_by():
    line = ns.condition_line(node("QQQ price > QQQ MA(25)", 707.53, 707.27, ">", True))
    assert "✅" in line and "holds by 0.26" in line
    assert "707.53" in line and "707.27" in line


def test_false_greater_than_condition_must_RISE():
    line = ns.condition_line(node("TQQQ RSI(10) > 79", 42.46, 79, ">", False))
    assert "❌" in line and "must rise 36.54" in line


def test_false_less_than_condition_must_FALL_not_rise():
    """`IEF RSI < TLT RSI` is false because IEF is too HIGH. 'needs more' is
    backwards — the original bug Jalal caught."""
    line = ns.condition_line(node("IEF RSI(200) < TLT RSI(200)", 49.55, 48.13, "<", False))
    assert "must fall 1.42" in line
    assert "rise" not in line


def test_condition_shows_both_sides_of_the_comparison():
    line = ns.condition_line(node("IEF RSI(200) < TLT RSI(200)", 49.55, 48.13, "<", False))
    assert "49.55" in line and "48.13" in line


def test_condition_escapes_html_operators():
    line = ns.condition_line(node("A > B & C", 1, 2, ">", False))
    assert "&gt;" in line and "&amp;" in line


# ── near_flips ───────────────────────────────────────────────────────────────

def test_near_flips_dedupes_repeated_blackswan_conditions():
    dup = node("QQQ max_drawdown(10d) > 6", 3.35, 6, ">", False, close_call=True)
    data = payload()
    data["blackswan"]["nodes"] = [dict(dup), dict(dup), dict(dup)]
    assert len(ns.near_flips(data)) == 1


def test_near_flips_sorted_by_closeness():
    data = payload()
    data["blackswan"]["nodes"] = [
        node("far", 10, 20, ">", False, close_call=True),
        node("near", 19, 20, ">", False, close_call=True),
    ]
    assert [n["label"] for n in ns.near_flips(data)] == ["near", "far"]


def test_near_flips_ignores_leaves_and_non_close_calls():
    data = payload()
    data["blackswan"]["nodes"] = [
        node("leaf", 1, 2, ">", True, close_call=True, is_leaf=True),
        node("not close", 1, 99, ">", False, close_call=False),
    ]
    assert ns.near_flips(data) == []


# ── plain English ────────────────────────────────────────────────────────────

def test_plain_expands_a_single_ticker():
    assert ns.plain("TQQQ") == "TQQQ — 3× long Nasdaq"


def test_plain_expands_a_split():
    out = ns.plain("BIL/TQQQ")
    assert "50% BIL" in out and "50% TQQQ" in out


def test_plain_passes_unknown_tickers_through():
    assert ns.plain("WXYZ") == "WXYZ"


# ── full message ─────────────────────────────────────────────────────────────

def test_render_leads_with_the_transition():
    msg = ns.render(payload(), previous="BIL")
    assert "NUTS SIGNAL CHANGED" in msg
    assert "<b>BIL</b>  →  <b>TQQQ + BIL/TQQQ</b>" in msg


def test_render_handles_a_first_ever_reading():
    msg = ns.render(payload(), previous=None)
    assert "first reading" in msg
    assert "→  <b>" not in msg


def test_render_of_a_forced_send_with_no_change_is_not_an_arrow():
    """--force-send exists for testing; 'X → X' would read as a bug."""
    data = payload()
    msg = ns.render(data, previous=ns.holding(data))
    assert "no change" in msg
    assert "→  <b>" not in msg
    assert "CHANGED" not in msg


def test_render_shouts_when_the_rsi_self_test_failed():
    data = payload()
    data["unit_test"] = {"pass": False}
    assert "DO NOT TRADE" in ns.render(data, previous="BIL")


def test_render_flags_download_errors():
    data = payload()
    data["download_errors"] = ["QQQ", "SPY"]
    assert "2 data download errors" in ns.render(data, previous="BIL")


def test_render_fits_one_telegram_message():
    assert len(ns.render(payload(), previous="BIL")) < 4096


def test_render_balances_its_html_tags():
    msg = ns.render(payload(), previous="BIL")
    for tag in ("b", "i", "blockquote"):
        assert msg.count(f"<{tag}>") == msg.count(f"</{tag}>")
