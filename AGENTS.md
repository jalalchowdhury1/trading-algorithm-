# AGENTS.md — Trading Algorithm (VIX / RSI Signal Bot)

> **This is the single source of truth for anyone (human or AI) touching this repo.**
> Read it fully before changing code, deploying, or "fixing" anything. It replaces the
> old AWS guides (`AWS_SETUP.md`, `LAMBDA_LAYERS.md`, `AWS_TROUBLESHOOTING.md`), which were
> point-in-time, mutually contradictory, and have been **deleted** — all their still-true
> content is folded in below. `README.md` is kept as the human/GitHub landing page (but note
> it has its own drift — see §Gotchas). If something here is wrong, fix *this* file.

---

## 1. What this is

A small Python script that, on a schedule during US market hours, downloads ETF prices from
Yahoo Finance, computes a custom **SMA-based RSI** for 16 tickers, walks a hard-coded
**decision tree** to produce one **trading signal** (a VIX/leveraged-ETF allocation string),
and sends it to **Telegram** — but only when the signal is new or it's the first run of the
day (dedup logic). State (last signal + date) persists between runs.

There are **two deployment paths from the same code**, selected at runtime by the presence of
the `AWS_LAMBDA_FUNCTION_NAME` env var:

1. **GitHub Actions (the path actually running today).** `.github/workflows/trading_alert.yml`
   runs `python3 main.py` on a schedule, then **commits `trading_state.json` back to `main`**
   (`[skip ci]`). The git history is wall-to-wall "Update trading signal state [skip ci]"
   commits — that is this path. State lives in the **committed `trading_state.json` file**.
   Telegram secrets are GitHub Actions secrets.
2. **AWS Lambda (built, documented, manually deployed via console).** `lambda_function.py:lambda_handler`
   calls the same `main()`. When running in Lambda, `state_manager.py` detects
   `AWS_LAMBDA_FUNCTION_NAME` and reads/writes state to **S3** instead of the local file.
   EventBridge schedules invoke it. There is **no CI that deploys the Lambda** — deploys are
   manual (`deploy_to_lambda.sh` builds a zip; the console uploads it). Whether the Lambda is
   currently enabled is owner-side AWS state, not visible in the repo; the live, observable
   path is GitHub Actions.

**Language/stack:** Python (workflow pins **3.9**; AWS docs historically mentioned 3.10/3.11 —
see §Gotchas). Deps: `yfinance, pandas, numpy, pytz, requests, boto3` (`requirements.txt`).
No tests framework, no build step — `main.py` is the entry point.

---

## 2. Architecture / data flow

```
                 schedule (GitHub Actions cron, UTC)           schedule (EventBridge, ET)
                            │                                            │
                            ▼                                            ▼
   market_hours.py (exit 0 if open) ── gate                    lambda_function.lambda_handler
                            │ (Actions only)                            │
                            ▼                                            ▼
                          main.main()  ◀───────── same code path ───────┘
                            │
   1. download_data()   → yfinance.download() for 16 TICKERS, ~120 calendar days
   2. calculate_all_rsi() → SMA-RSI(9) for all; RSI(50)+RSI(60) for VIXY  → rsi_cache
   3. execute_logic()   → walk logic_tree (start node 1) → final_decision + decision_path
        └─ node 35 true → execute_special_logic_35() (bottom-2 RSI of SOXL/TECL/TQQQ/FNGU)
   4. should_notify(signal, last_state) → notify if first-ever / new day / signal changed
   5. if notify & creds → format_telegram_report() → send_telegram_message() (Telegram API)
   6. write_state(signal, notified)
        ├─ NOT Lambda → local file trading_state.json  (Actions then git-commits it)
        └─ IN Lambda  → S3  s3://$STATE_BUCKET_NAME/trading_state.json
```

`read_state`/`write_state` (in `state_manager.py`) are the only branch on environment.
Everything else runs identically in both paths.

---

## 3. How to run / deploy / test

### Run locally
```bash
python3 -m pip install --user -r requirements.txt
python3 main.py            # prints all steps; no Telegram unless creds set
```
Telegram is optional locally: if `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are unset the
script still runs and prints the signal, just skips the send. To enable it, export both (or
put them in a `.env` — but nothing in this repo loads `.env`; you must `export` them or use a
tool like `direnv`/`dotenv` yourself).

```bash
python3 market_hours.py    # exit 0 = market open, exit 1 = closed (the Actions gate)
```

### Tests / verification
There is **no test runner**. The only verification is a built-in unit test that `main()`
runs first: `test_rsi_calculation()` computes RSI(9) for the hard-coded series
`[100,102,101,103,102,104,105,103,106,107]` and should print **73.3333** (verified). It only
prints — it does not assert/fail — so a wrong value won't stop execution; eyeball it.

### Environment variables (NEVER commit values — repo is public)
| Var | Used by | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `main.py` send | required to actually send; GitHub Actions secret / Lambda env var |
| `TELEGRAM_CHAT_ID` | `main.py` send | numeric chat id |
| `STATE_BUCKET_NAME` | `state_manager.py` (Lambda only) | S3 bucket for state; defaults to `trading-algorithm-state` if unset, but the owner's actual bucket is `trading-algorithm-state-jalal` |
| `AWS_LAMBDA_FUNCTION_NAME` | set automatically by AWS | presence flips state storage to S3 and the report "source" badge to "AWS Lambda" |

> Older docs hard-coded a real bot token / chat id (`8488869990:…` / `7956935476`) in
> `AWS_SETUP.md` and `AWS_TROUBLESHOOTING.md`. Those docs are deleted. **If that token was
> ever pushed publicly, rotate it.** Never re-introduce literal secrets — env vars / GitHub
> secrets only.

### Deploy — GitHub Actions (the live path)
Nothing to do beyond pushing to `main`; the workflow self-schedules. Secrets:
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` under repo Settings ▸ Secrets and variables ▸ Actions.
The workflow needs `contents: write` (already set) to push the state commit, and checks out
with `fetch-depth: 0` + `GITHUB_TOKEN` so the push works. Manual run: Actions ▸ **Trading
Algorithm Every 30min** ▸ Run workflow.

**Actual schedule (from `trading_alert.yml`, cron is UTC):**
- `35 13-14 * * 1-5` — 9:35 AM ET first run (13:35 UTC in EDT, 14:35 UTC in EST; the workflow
  fires at *both* 13:35 and 14:35, and `market_hours.py` gates out the wrong one).
- `0,30 14-21 * * 1-5` — every 30 min, hours 14–21 UTC (covers 10:00 AM–4:00 PM ET across
  EST/EDT). So it runs **every 30 minutes**, not "every hour" (README is wrong — see §Gotchas).

### Deploy — AWS Lambda (manual; no CI does this)
Reference setup, distilled from the deleted AWS docs. Treat as the owner's known-good recipe;
verify against the live console before trusting any specific value (the old docs disagreed
with each other on runtime and cron).

- **Function:** `trading-algorithm`, `us-east-1`, x86_64, handler `lambda_function.lambda_handler`,
  timeout 120 s (bump to 180 s if it times out), memory 512 MB.
- **Runtime:** the old docs variously said 3.9 / 3.10 / 3.11. **The Lambda runtime and the
  dependency layer's Python version MUST match exactly**, or you get
  `Runtime.ImportModuleError`. Pick one (e.g. 3.11) and build the layer for it.
- **Env vars:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `STATE_BUCKET_NAME` (=`trading-algorithm-state-jalal`).
- **State:** S3 bucket `trading-algorithm-state-jalal` (us-east-1, private), key `trading_state.json`.
- **IAM:** execution role needs CloudWatch Logs (default) + an inline S3 policy
  (`TradingAlgorithmS3Access`) granting `s3:GetObject`/`s3:PutObject` on
  `arn:aws:s3:::trading-algorithm-state-jalal/*`.
- **Schedules (EventBridge Scheduler, timezone America/New_York):**
  `trading-algorithm-935am` = `35 9 ? * MON-FRI *`;
  `trading-algorithm-every30min` = `0,30 10-16 ? * MON-FRI *`.
  (Note: AWS_SETUP.md instead described UTC crons `35 13,14 …` / `0,30 14-21 …` on the default
  bus — same intent, different bus/timezone. The America/New_York scheduler form in
  AWS_TROUBLESHOOTING.md is the more recent, cleaner one.)

**Build the deployment package** (`deploy_to_lambda.sh` does steps 1–3, then you upload via
console or `aws lambda update-function-code`):
```bash
./deploy_to_lambda.sh   # installs deps with --platform manylinux2014_x86_64 --only-binary=:all:,
                        # copies main.py / lambda_function.py / state_manager.py / market_hours.py,
                        # zips to lambda_deployment.zip
```
For a **dependency layer** instead of a fat zip (build in AWS CloudShell or Docker, NOT on a
Mac — see §Gotchas). The published layer is named **`trading-dependencies`** (compatible
runtime Python 3.10 historically; match it to whatever runtime you pick). Its actual contents
per the old AWS_TROUBLESHOOTING doc are **`yfinance pandas numpy pytz requests beautifulsoup4
html5lib`** — `beautifulsoup4`/`html5lib` are yfinance transitive deps, so the bare
`yfinance pandas numpy pytz requests` install below pulls them in, but if you build with
`--only-binary=:all:` and a dep is missing, add them explicitly:
```bash
pip install --platform manylinux2014_x86_64 --target python \
    --implementation cp --python-version 3.11 --only-binary=:all: --upgrade \
    yfinance pandas numpy pytz requests        # bs4/html5lib come in transitively
zip -r trading-dependencies-layer.zip python
aws s3 cp trading-dependencies-layer.zip s3://trading-algorithm-state-jalal/
# then publish-layer-version --layer-name trading-dependencies + attach to the function
```
The attached layer shows up in the console as **`trading-dependencies`**; manage versions with
`aws lambda list-layer-versions --layer-name trading-dependencies` and
`aws lambda delete-layer-version --layer-name trading-dependencies --version-number N`.

**Alternative dependency strategies (from the deleted LAMBDA_LAYERS.md, kept as fallbacks; the
custom `trading-dependencies` layer above is the path the more-recent troubleshooting doc
actually uses):**
- **AWS-managed pandas layer (public ARN).** Instead of building pandas/numpy yourself, attach
  AWS's SDK-for-pandas layer (gives pandas, numpy, boto3, requests), then only build a small
  custom layer for `yfinance`/`pytz`. For us-east-1 / Python 3.11:
  `arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python311:15`
  (us-west-2: `arn:aws:lambda:us-west-2:336392948345:layer:AWSSDKPandas-Python311:15`;
  eu-west-1: `arn:aws:lambda:eu-west-1:336392948345:layer:AWSSDKPandas-Python311:15`).
  The region in the ARN MUST match the function's region.
- **`/tmp` runtime pip-install hack.** Last resort: `pip install yfinance pytz -t /tmp` at the
  top of `lambda_function.py` and `sys.path.insert(0, '/tmp')`. Simple, no layer setup, but adds
  ~2 s to every cold start — avoid for the scheduled prod path.
Update existing function code via CLI:
```bash
aws lambda update-function-code --function-name trading-algorithm \
  --zip-file fileb://lambda_deployment.zip --region us-east-1
```
Useful checks:
```bash
aws lambda invoke --function-name trading-algorithm --region us-east-1 output.json && cat output.json
aws logs tail /aws/lambda/trading-algorithm --follow --region us-east-1
aws s3 cp s3://trading-algorithm-state-jalal/trading_state.json - | python -m json.tool
aws scheduler list-schedules --region us-east-1 | grep trading
```

---

## 4. Gotchas / hard rules

- **The two deploy paths can double-fire and double-state.** GitHub Actions and AWS Lambda run
  the *same* algorithm on overlapping schedules. If both are enabled you get duplicate Telegram
  alerts AND two independent state stores (git file vs S3) that won't agree — so `should_notify`
  dedup is per-store, meaning each path notifies on its own first-of-day. The deleted AWS_SETUP
  "Next Steps" said to **disable the GitHub Actions workflow once Lambda is live** to avoid
  duplicates. The live git history shows the *Actions* path is the one running. Before enabling
  Lambda, decide which path owns the schedule and disable the other.
- **README is stale on cadence and structure.** README says "runs every hour"/"hourly" and
  lists the workflow as "Trading Algorithm Hourly" and the project structure as just
  `main.py / README.md / requirements.txt`. Reality: the workflow is named **"Trading
  Algorithm Every 30min"**, runs **every 30 minutes**, and the repo also contains
  `lambda_function.py`, `state_manager.py`, `market_hours.py`, the AWS scripts, etc. Trust this
  file / the code over README on schedule and layout. (README is intentionally left in place as
  the GitHub landing page; don't rely on it for ops detail.)
- **`market_hours.py` only gates the GitHub Actions path.** It's a separate workflow step
  (`continue-on-error: true`) and the algorithm step is `if: market_check.outcome == 'success'`.
  The Lambda path does NOT call `market_hours.py` — EventBridge crons are the only gate there,
  so the Lambda will happily run on a market holiday (weekday, market closed) and yfinance will
  just return the prior day's data. `market_hours.py` uses `US/Eastern`; the rest of the code
  uses `America/New_York` (same zone, two spellings).
- **Never build Lambda native deps on a Mac.** numpy/pandas Mac wheels crash on Lambda's Linux
  with `Runtime.ImportModuleError`. Always build with `--platform manylinux2014_x86_64
  --only-binary=:all:` (and `--python-version`/`--implementation cp` matching the runtime), in
  CloudShell/Docker. Note `deploy_to_lambda.sh` passes `--platform/--only-binary` but **omits
  `--python-version`/`--implementation`**, so on some pip/Python combos it can still resolve to
  the local interpreter version — prefer the explicit layer command above for anything that
  must match a specific Lambda runtime.
- **Lambda runtime ⇄ dependency Python version must match.** A 3.11 runtime with a 3.10 layer
  (or vice-versa) is the #1 historical failure (`No module named 'yfinance'` /
  `Unable to import module 'lambda_function'`). Fix by aligning one to the other.
- **The committed `trading_state.json` is live data, not a fixture.** The Actions path reads and
  rewrites it every run and commits it. Don't hand-edit it to "reset" without understanding
  you'll change tomorrow's first-run dedup. (`.gitignore` ignores Lambda build artifacts
  `lambda_package/`, `lambda_deployment*.zip`, `trading-dependencies-layer.zip`, `output.json`,
  `.env` — keep build junk out of git.)
- **Decision tree has intentional gaps.** `logic_tree` in `execute_logic()` is keyed by node id
  but **ids 7, 11, 14, 15, 20, 21, 26, 27, 30, 31 do not exist** — they were pruned/renumbered
  from the original Google-Sheet tree. Traversal only follows `true`/`false` pointers, so the
  gaps are harmless; do not "fill them in" assuming a bug.
- **RSI is SMA-based, deliberately.** `calculate_rsi_sma` uses a *simple* moving average of
  ups/downs over the last `window` diffs (to match the owner's Google Sheet), NOT the standard
  Wilder/EMA RSI. Don't "correct" it to EMA. `avg_down == 0` → RSI forced to `100.0`.
- **yfinance multi-index handling.** `yf.download` may return MultiIndex columns; the code
  guards with `isinstance(df.columns, pd.MultiIndex)` and takes `df['Close'].iloc[:, 0]`. Keep
  that guard if you touch data extraction. A ticker with `<60` rows is treated as a failure and
  `download_data()` calls `exit(1)` (hard stop) — one bad ticker aborts the whole run.
- **`get_rsi` returns 0 for a missing key**, so a never-downloaded ticker reads as RSI 0, which
  in a `< threshold` comparison would look "extremely oversold." Since `download_data()` aborts
  on any failure, this normally can't happen — but if you relax that abort, RSI-0 fallbacks
  could silently flip the tree to a buy signal.
- **Telegram send is best-effort plain text.** `send_telegram_message` posts plain `text` (no
  `parse_mode`), so the emoji/box-drawing report is fine; there's no Markdown to break and no
  >4096-char chunking — the report is short, but if you make it long, Telegram will 400.
- **`requirements.txt` uses `>=` ranges**, including `boto3` (already in the Lambda runtime).
  yfinance's pin is `yfinance>=1.1.0` (older yfinance versions used a different major scheme;
  this just means "any reasonably recent yfinance"). Yahoo's unofficial endpoints break/change
  periodically — a sudden empty-data failure is usually yfinance/Yahoo, not this code.

---

## 5. Known issues / open items (owner action)

- **Secret rotation:** the previously-committed Telegram bot token (`8488869990:…`) and chat id
  lived in the now-deleted AWS docs. If the repo was ever public with those, rotate the token.
- **Pick one scheduler:** confirm whether AWS Lambda is still enabled. If it is, disable the
  GitHub Actions workflow (or vice-versa) to stop duplicate alerts / divergent state. The
  observable truth right now: GitHub Actions is running (state commits in git log).
- **README cleanup:** README claims "hourly" and an outdated file list; left untouched per
  policy, but it should eventually be corrected to "every 30 min" + the real structure.
- **No real test/CI for the algorithm** beyond the eyeball RSI print and `market_hours` gate.
- **Lambda config is hand-managed in the console** — there is no SAM/Terraform/CI for it, so
  schedules, env vars, runtime, memory/timeout and the layer can drift from anything written
  here. Verify live before trusting a value.

---

## 6. File / module map

- `main.py` — the whole algorithm: `TICKERS` (16 ETFs), `calculate_rsi_sma`, `download_data`,
  `calculate_all_rsi`, `execute_logic` (the `logic_tree`), `execute_special_logic_35`
  (bottom-2 RSI of SOXL/TECL/TQQQ/FNGU), `should_notify` (dedup), `format_telegram_report`,
  `send_telegram_message`, `main()`. Run with `python3 main.py`.
- `lambda_function.py` — AWS entry `lambda_handler(event, context)` → calls `main.main()`,
  returns `{statusCode, body}`. Handler string: `lambda_function.lambda_handler`.
- `state_manager.py` — `read_state`/`write_state`; branches on `AWS_LAMBDA_FUNCTION_NAME`
  (local file `trading_state.json` vs S3 `s3://$STATE_BUCKET_NAME/trading_state.json`).
- `market_hours.py` — `is_market_open()`; CLI exits 0 (open) / 1 (closed). The Actions gate.
- `trading_state.json` — **live** committed state (`signal`, `date`, `timestamp`, `notified`)
  for the GitHub Actions path. Not a fixture.
- `requirements.txt` — `yfinance, pandas, numpy, pytz, requests, boto3` (all `>=`).
- `deploy_to_lambda.sh` — builds `lambda_deployment.zip` (deps + the 4 `.py` files) for manual
  Lambda upload. Does NOT deploy by itself.
- `.github/workflows/trading_alert.yml` — "Trading Algorithm Every 30min": cron (UTC) →
  setup-python 3.9 → install → `market_hours.py` gate → `main.py` → commit & push
  `trading_state.json` `[skip ci]`. Needs `contents: write`.
- `README.md` — human landing page (kept; stale on cadence/structure — see §4/§5).
- *(deleted)* `AWS_SETUP.md`, `LAMBDA_LAYERS.md`, `AWS_TROUBLESHOOTING.md` — their content is
  consolidated above.

### The signal vocabulary (possible `final_decision` outputs)
`1.5x VIX Group (VXX, UVIX)` · `VIX Blend (VXX=0.45, VIXM=0.2, UVIX=0.35)` · `1x VIX (VIXY)` ·
`LABD` (inverse biotech) · `SOXL` / `FNGU` / `TECL` / `UPRO` (single leveraged longs) ·
`Buy <T1> and <T2> (Bottom 2 RSIs: …)` (node-35 special logic) · `BIL (T-Bill ETF)` (cash/risk-off,
the default leaf). Report emoji is chosen in `format_telegram_report` from the signal text.
