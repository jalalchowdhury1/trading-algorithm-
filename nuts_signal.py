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

    lines = ["<b>🔄 NUTS SIGNAL CHANGED</b>", ""]
    if previous is None:
        lines.append(f"<b>{_esc(now)}</b>")
        lines.append("<i>first reading — nothing to compare against</i>")
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
