"""Read the NUTS Algo signal and render it for Telegram.

WHY THIS CALLS AN API INSTEAD OF COMPUTING ANYTHING
---------------------------------------------------
This repo used to run its own decision tree. It had drifted so far from NUTS —
the canonical algo — that on 2026-08-24 it reported `BIL (T-Bill ETF)` (cash)
while NUTS was `TQQQ` (3x long Nasdaq). Opposite positions.

They were never the same strategy: RSI window 9 vs 10, different tickers
(IOO/CURE/RETL/LABU/FNGU vs SOXX), different thresholds, and critically this
repo had no FTLT and no BlackSwan tree at all — so "nothing fired" meant "go to
cash" here and "fall through to FTLT" in NUTS.

So the tree logic is gone. This module GETs NUTS's own `/evaluate` endpoint —
the same one that serves the Vercel visualizer — and formats the answer. That
makes agreement structural rather than a thing someone has to maintain.

NUTS is READ-ONLY from here. No force-refresh: its EventBridge cron recomputes
every 30 min in market hours and `/evaluate` is cached <=60 min, so a plain GET
returns exactly what the website shows, at zero cost to NUTS.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import urllib.request

NUTS_API = "https://ju9t7h8903.execute-api.us-east-1.amazonaws.com/evaluate"
TIMEOUT_S = 60

# Plain English for the tickers NUTS can emit, so the message is readable at a
# glance rather than requiring you to remember what LABU is.
MEANING = {
    "TQQQ": "3× long Nasdaq", "UPRO": "3× long S&P", "SOXL": "3× long semis",
    "TECL": "3× long tech", "UVXY": "1.5× long vol", "VIXY": "long vol",
    "BIL": "cash / T-bills", "BND": "bonds", "SQQQ": "3× short Nasdaq",
    "SPXL": "3× long S&P", "TMF": "3× long treasuries", "SH": "short S&P",
    "TLT": "long treasuries", "IEF": "7-10y treasuries", "XLP": "staples",
}


# ── fetching ────────────────────────────────────────────────────────────────

def fetch(url: str = NUTS_API) -> dict:
    """GET the live NUTS evaluation. Raises on any failure — a trading signal
    must never be silently invented."""
    with urllib.request.urlopen(urllib.request.Request(url), timeout=TIMEOUT_S) as r:
        return json.load(r)


# ── the thing we detect changes on ──────────────────────────────────────────

def holding(data: dict) -> str:
    """What NUTS says to actually hold — mirrors the Vercel header exactly.

    If Frontrunners fired it IS the position. Otherwise the position is FTLT's
    call plus the BlackSwan sleeve, which is a standing portfolio component
    whenever Frontrunners is quiet. Tracking only `final_result` would miss a
    BlackSwan flip that changed half the book.
    """
    if data["frontrunners"]["fired"]:
        return str(data["frontrunners"]["result"])
    return f"{data['ftlt']['result']} + {data['blackswan']['result']}"


def changed(data: dict, previous: str | None) -> bool:
    return previous is None or holding(data) != previous


# ── rendering ───────────────────────────────────────────────────────────────

def _esc(s) -> str:
    return html.escape(str(s), quote=False)


def _num(v) -> str:
    if v is None:
        return "?"
    if abs(v) >= 10000:
        return f"{v:,.0f}"
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def plain(result: str) -> str:
    """'BIL/TQQQ' -> '50% BIL (cash / T-bills) + 50% TQQQ (3× long Nasdaq)'."""
    parts = [p.strip() for p in str(result).split("/")]
    if len(parts) == 1:
        m = MEANING.get(parts[0])
        return f"{parts[0]} — {m}" if m else parts[0]
    return "  +  ".join(f"50% {p} ({MEANING.get(p, '?')})" for p in parts)


def condition_line(node: dict) -> str:
    """One condition, unambiguously.

    Shows whether it holds RIGHT NOW, both sides of the comparison, and which
    way it must move to flip. The label alone ("IEF RSI(200) < TLT RSI(200)")
    states the rule but not the answer — and "needs 1.42 more" on a `<`
    condition reads exactly backwards, since it must FALL.

    `threshold` is the right-hand side even for dynamic comparisons: on
    "IEF RSI(200) < TLT RSI(200)" it holds TLT's live RSI.
    """
    holds = bool(node.get("result"))
    gap = abs(node.get("distance") or 0)
    if holds:
        verdict = f"holds by {_num(gap)}"
    else:
        verdict = f"must {'rise' if node.get('operator') == '>' else 'fall'} {_num(gap)}"
    outcome = f" → {_esc(node['outcome'])}" if node.get("outcome") else ""
    return (f"{'✅' if holds else '❌'} {_esc(node['label'])}{outcome}\n"
            f"     <b>{_num(node.get('live_value'))}</b> vs "
            f"{_num(node.get('threshold'))} · {verdict}")


def near_flips(data: dict, limit: int = 3) -> list[dict]:
    """Conditions closest to flipping — what might change the position next.

    Deduped by label: BlackSwan evaluates its NMA and NMB sub-trees
    independently, so the same condition legitimately appears twice.
    """
    seen, scored = set(), []
    for tree in ("frontrunners", "ftlt", "blackswan"):
        for node in data[tree]["nodes"]:
            if not node.get("close_call") or node.get("is_leaf"):
                continue
            if node.get("live_value") is None or node["label"] in seen:
                continue
            seen.add(node["label"])
            scored.append((abs(node.get("distance") or 0), node))
    scored.sort(key=lambda pair: pair[0])
    return [node for _, node in scored[:limit]]


def render(data: dict, previous: str | None) -> str:
    """The Telegram message. Only ever called when the holding changed."""
    now = holding(data)
    source = data["final_source"]
    primary = (data["frontrunners"]["result"] if data["frontrunners"]["fired"]
               else data["ftlt"]["result"])

    # --force-send exists for testing, so previous can equal now. Rendering
    # "X → X" would read as a bug rather than a deliberate test.
    if previous == now:
        header = "<b>📊 NUTS SIGNAL — no change</b>"
    elif previous is None:
        header = "<b>📊 NUTS SIGNAL — first reading</b>"
    else:
        header = "<b>🔄 NUTS SIGNAL CHANGED</b>"

    lines = [header, ""]
    if previous is None or previous == now:
        lines.append(f"<b>{_esc(now)}</b>")
    else:
        lines.append(f"<b>{_esc(previous)}</b>  →  <b>{_esc(now)}</b>")
    lines.append(f"<i>{_esc(plain(primary))}</i>")

    path = [condition_line(n) for n in data[source]["nodes"]
            if n.get("active") and not n.get("is_leaf")]
    if path:
        lines += ["", f"<b>WHY — {_esc(source.upper())}</b>",
                  "<blockquote>" + "\n".join(path) + "</blockquote>"]

    flips = near_flips(data)
    if flips:
        lines += ["", "<b>⚡ NEAREST TO FLIPPING</b>",
                  "<blockquote>" + "\n".join(condition_line(n) for n in flips)
                  + "</blockquote>"]

    unit = data.get("unit_test") or {}
    errors = data.get("download_errors") or []
    try:
        stamp = dt.datetime.fromisoformat(
            data["evaluated_at"]).strftime("%-I:%M %p ET · %-d %b")
    except Exception:
        stamp = str(data.get("evaluated_at", ""))
    footer = f"{'✅' if unit.get('pass') else '🚨 RSI SELF-TEST FAILED —'} " \
             f"{'RSI self-test' if unit.get('pass') else 'DO NOT TRADE'} · {_esc(stamp)}"
    lines += ["", f"<i>{footer}</i>"]
    if errors:
        lines.append(f"<i>⚠️ {len(errors)} data download errors</i>")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Proximity warnings — "tell me BEFORE Frontrunners fires"
#
# NUTS Frontrunners is an exact model of the Composer symphony Jalal actually
# trades (verified 2026-08-24: all 10 conditions, same order, same thresholds,
# same RSI window, same → FTLT fallback). So how close each trigger sits to
# firing is a genuine early warning about real money, and it needs no second
# strategy to compute — NUTS already publishes every distance.
#
# Composer rebalances DAILY, so an intraday warning says what tomorrow's
# rebalance is likely to do.
# ─────────────────────────────────────────────────────────────────────────────

# Closest band first. rank 0 = nearest to firing; QUIET is rank len(BANDS).
BANDS = [(2.0, "IMMINENT", "🔴"), (5.0, "WARNING", "🟠"), (10.0, "WATCH", "🟡")]
QUIET = "QUIET"


def band_of(node: dict) -> str:
    """Which proximity band a condition sits in.

    A condition that has already FIRED is not a warning — that is what the
    CHANGED alert is for. Only conditions that are currently false, and near
    becoming true, are warnings.
    """
    if node.get("result"):
        return QUIET
    distance = abs(node.get("distance") or 0)
    for limit, name, _ in BANDS:
        if distance <= limit:
            return name
    return QUIET


def _rank(band: str) -> int:
    for i, (_, name, _) in enumerate(BANDS):
        if name == band:
            return i
    return len(BANDS)


def _emoji(band: str) -> str:
    for _, name, glyph in BANDS:
        if name == band:
            return glyph
    return "⚪"


def frontrunner_bands(data: dict) -> dict[str, str]:
    """{condition label: band} for every Frontrunners trigger."""
    return {n["label"]: band_of(n)
            for n in data["frontrunners"]["nodes"] if not n.get("is_leaf")}


def escalations(current: dict[str, str], previous: dict[str, str] | None) -> list[tuple]:
    """Conditions that moved CLOSER to firing, or cleared entirely.

    Only crossings are reported. Without this, a trigger parked 8 away would
    alert on all ~16 polls a day — the same noise problem the CHANGED alert
    avoids by tracking state.

    Returns [(label, old_band, new_band, direction)] where direction is
    "closer" or "cleared".
    """
    if previous is None:
        # First run: report anything already inside a band, but never the
        # whole quiet roster.
        return [(label, QUIET, band, "closer")
                for label, band in current.items() if band != QUIET]
    out = []
    for label, band in current.items():
        was = previous.get(label, QUIET)
        if _rank(band) < _rank(was):
            out.append((label, was, band, "closer"))
        elif band == QUIET and was != QUIET:
            out.append((label, was, band, "cleared"))
    return out


def render_warning(data: dict, moves: list[tuple]) -> str:
    """The warning message. Only called when something actually crossed."""
    by_label = {n["label"]: n for n in data["frontrunners"]["nodes"]}
    closer = [m for m in moves if m[3] == "closer"]
    cleared = [m for m in moves if m[3] == "cleared"]

    worst = min((_rank(m[2]) for m in closer), default=len(BANDS))
    head = (f"{_emoji(BANDS[worst][1])} <b>FRONTRUNNERS {BANDS[worst][1]}</b>"
            if closer else "⚪ <b>FRONTRUNNERS — cleared</b>")
    lines = [head, "", "<i>NUTS Frontrunners is the top layer of your Composer "
                      "symphony. This is a heads-up, not a position change.</i>"]

    if closer:
        rows = []
        for label, was, band, _ in sorted(closer, key=lambda m: _rank(m[2])):
            node = by_label[label]
            rows.append(f"{_emoji(band)} {_esc(label)} → {_esc(node.get('outcome') or '')}\n"
                        f"     now <b>{_num(node.get('live_value'))}</b> · "
                        f"{_num(abs(node.get('distance') or 0))} away"
                        + (f" · was {was.lower()}" if was != QUIET else ""))
        lines += ["", "<b>MOVED CLOSER</b>",
                  "<blockquote>" + "\n".join(rows) + "</blockquote>"]

    if cleared:
        rows = [f"⚪ {_esc(label)} · backed off from {was.lower()}"
                for label, was, _, _ in cleared]
        lines += ["", "<b>NO LONGER NEAR</b>",
                  "<blockquote>" + "\n".join(rows) + "</blockquote>"]

    lines += ["", f"<i>current holding: {_esc(holding(data))}</i>"]
    return "\n".join(lines)
