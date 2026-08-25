# AGENTS.md — trading-algorithm- (NUTS signal watch)

> **Single source of truth for anyone (human or AI) touching this repo.**
> `README.md` is Jalal's human-facing doc — leave it alone unless asked.
>
> **This repo computes NOTHING.** It reads the NUTS Algo's own answer and
> reports changes. If you find yourself adding a threshold, an RSI, or a
> ticker list here, stop — that belongs in NUTS.

---

## 1. What this is

A GitHub Actions job that reads the **NUTS Algo** every 30 minutes during
market hours and messages Telegram **only when something moved**. Two alerts,
both change-only:

| alert | fires when | means |
|---|---|---|
| 🔄 **CHANGED** | the holding moved | Composer will rebalance into this |
| 🟠 **WARNING** | a Frontrunners trigger crossed into a closer band | heads-up, not a position change |

**NUTS Frontrunners is an exact model of the Composer symphony Jalal actually
trades** — verified 2026-08-24 against a screenshot of the live symphony: all
10 conditions, same order, same thresholds, same RSI(10) window, same
`→ FTLT` fallback. That is why NUTS's own per-condition distances are a real
early warning about real money, and why this repo needs no strategy of its
own.

Silence is the normal outcome and the entire point: a message means the
position moved. There is deliberately **no daily heartbeat** — liveness is
proven by the fleet-health probe (§5), not by pinging Jalal's phone.

### Why it no longer computes its own signal

Until 2026-08-24 this repo ran a 720-line hand-coded decision tree. It had
diverged from NUTS so completely that on that date it reported
**`BIL` (cash)** while NUTS said **`TQQQ` (3× long Nasdaq)** — opposite
positions, on a live trading signal.

They were never the same strategy:

| | NUTS | this repo (old) |
|---|---|---|
| RSI window | 10 | 9 |
| Oversold | SOXX/QQQ/SPY < 30 | SOXL/FNGU/TQQQ/TECL/UPRO < 25-28 |
| Extra tickers | — | IOO, CURE, RETL, LABU, FNGU |
| Nothing fires | → **FTLT tree** | → **BIL (cash)** |
| FTLT tree | yes | **absent** |
| BlackSwan tree | yes | **absent** |

The last three rows are why they disagreed on any quiet day. The fix was not
to re-copy the thresholds — that is how the drift happened — but to delete the
local tree and read NUTS's answer.

## 2. Architecture / data flow

```
GitHub Actions cron (:10 and :40, 13-21 UTC, Mon-Fri)
        │
        ├─ nuts_signal.fetch()   GET NUTS /evaluate  ← READ-ONLY, never ?force
        │      https://ju9t7h8903.execute-api.us-east-1.amazonaws.com/evaluate
        │      (the same endpoint that serves nuts-sooty.vercel.app)
        │
        ├─ abort if NUTS's own RSI unit_test did not pass
        ├─ nuts_signal.holding()      frontrunners  OR  ftlt + blackswan
        ├─ compare with trading_state.json
        │        unchanged → print marker, EXIT SILENTLY
        │        changed   → nuts_signal.render() → telegram_sender.send()
        └─ commit trading_state.json back to the repo
```

**NUTS is never modified and never force-refreshed.** Its EventBridge cron
recomputes at :05 and :35 and `/evaluate` is cached ≤60 min, so a plain GET
returns exactly what the website shows, at zero compute cost to NUTS. We poll
at :10/:40 — five minutes behind it — so we read a fresh value rather than
racing the recompute.

## 3. How to run / test

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q         # 47 tests, no network needed

.venv/bin/python main.py --dry-run           # live NUTS read, sends nothing
.venv/bin/python main.py --force-send        # send the SIGNAL even if unchanged
.venv/bin/python main.py --force-warning     # send a WARNING for whatever is near
.venv/bin/python main.py --no-warnings       # signal changes only
.venv/bin/python main.py                     # the real thing

# same two switches from the Actions UI / CLI:
gh workflow run trading_alert.yml --repo jalalchowdhury1/trading-algorithm- -f force_warning=true
```

No third-party dependencies: stdlib `urllib` for both NUTS and Telegram.

## 4. Secrets & env

| var | notes |
|---|---|
| `TELEGRAM_BOT_TOKEN` | repo secret. **Note the name** — the workflow maps it to `TELEGRAM_TOKEN` in `env:`. Do not rename one without the other. |
| `TELEGRAM_CHAT_ID` | repo secret |

## 4b. Proximity warnings

Bands, on `abs(distance)` from a Frontrunners trigger's threshold:

| band | distance | glyph |
|---|---|---|
| IMMINENT | ≤ 2 | 🔴 |
| WARNING | ≤ 5 | 🟠 |
| WATCH | ≤ 10 | 🟡 |
| QUIET | > 10 | — |

**Alerts fire on a CROSSING, never on a level.** A trigger parked 8 away would
otherwise ping on all ~16 polls a day. `escalations()` reports a condition only
when it moves to a closer band, or when it clears to QUIET entirely. Backing
off WARNING → WATCH is deliberately silent: still near, not news.

**A condition that has already FIRED is never a warning** — that is the CHANGED
alert's job. `band_of()` returns QUIET for `result: true`.

`state_manager.read_bands()` returns **None**, not `{}`, when nothing was ever
recorded. `escalations()` treats None as "first run, report what is already
near"; `{}` would mean "everything was quiet", inventing crossings that never
happened.

## 5. Gotchas / hard rules

1. **Never re-implement NUTS's maths here.** The whole point of this rewrite is
   that there is exactly one copy of the strategy. NUTS's own AGENTS.md warns:
   *never change the RSI/MA math without re-deriving the unit test by hand.*
   Owning a second copy is how BIL-vs-TQQQ happened.

2. **`holding()` is `ftlt + blackswan`, not `final_result`.** BlackSwan is a
   standing portfolio component whenever Frontrunners is quiet, so tracking
   only the headline signal would miss a BlackSwan flip that changed half the
   book. This mirrors what the Vercel header shows.

3. **A failed NUTS unit test aborts the run.** If NUTS will not trust its own
   RSI, neither do we — `main.py` exits 1 before sending anything. The message
   renderer also shouts `DO NOT TRADE` if it is ever reached with a failed test.

4. **Never invent a signal.** An unreachable NUTS exits 1 and goes red. There
   is no stale-value fallback: a stale trading signal presented as current is
   worse than no signal.

5. **Condition lines must show both sides and the direction.** A label alone
   ("IEF RSI(200) < TLT RSI(200)") states the rule but not the answer, and
   "needs 1.42 more" on a `<` condition reads exactly backwards — it must
   *fall*. `condition_line` renders
   `49.55 vs 48.13 · must fall 1.42`; three tests pin this.

6. **No AWS Lambda path.** It existed until 2026-08-06 and ran *alongside*
   Actions with a separate S3 state store, double-alerting every morning and
   diverging (S3 recomputed on after-hours data because `lambda_handler` never
   gated on market hours). `lambda_function.py` and `deploy_to_lambda.sh` are
   deleted. **Do not reintroduce a second runner.**

7. **`--force-warning` and `--dry-run` must never satisfy the fleet probe.**
   The marker `NUTS-SIGNAL OK unchanged=` / `NUTS-SIGNAL CHANGED ` prints only
   when the run reached NUTS AND its RSI unit test passed. `--dry-run` prints
   nothing and writes nothing. Seven tests in `tests/test_marker.py` pin this,
   because `force_warning` is a workflow_dispatch input — without the rule, a
   manual test would paint the row green while the cron was dead.

8. **Silence is not health.** Because the bot only speaks on change, a dead job
   looks exactly like a quiet market from Telegram. The fleet-health probe
   (`github-notion-sync/fleet_health.py`, entry
   "trading-algorithm- (30-min signal)") is the only liveness signal, and it
   greps for `NUTS-SIGNAL OK unchanged=` **or** `NUTS-SIGNAL CHANGED `. Neither
   can print unless the NUTS fetch succeeded and the unit test passed.

## 6. State / known issues

- `trading_state.json` holds only `{holding, sent_at, source}`. A corrupt or
  missing file reads as `None`, which renders as a "first reading" message
  rather than fabricating a transition.
- **The n8n "Daily RSI" workflow must be deactivated** — it is a third copy of
  a trading signal and will contradict this one.
- Old `market_hours.py` is retained but the cron window now does the gating.

## 7. File map

```
main.py              orchestration: fetch → compare → send-or-be-silent
nuts_signal.py       NUTS client, holding(), change detection, rendering,
                     proximity bands + escalations + render_warning
state_manager.py     last-sent holding, committed back by the workflow
telegram_sender.py   HTML sender with a no-parse_mode retry
market_hours.py      legacy ET market-hours helper
tests/               47 tests, fully offline (test_marker.py + test_warnings.py)
.github/workflows/trading_alert.yml
```
