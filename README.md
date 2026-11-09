# WARN Dashboard

Explore U.S. WARN Act layoff notices, ask questions in plain words, and see
backtested forecasts. Fully static: a scheduled GitHub Action builds JSON data
files, GitHub Pages serves the site, and all analysis (including the optional
on-device language model) runs in the visitor's browser. No server, no paid
API, no account, no tracking.

**Data source:** [WARN Feed](https://github.com/APVentureEngine/warn-act-notices)
(CC BY 4.0, attribution required and given on every page). Economic context:
[BLS public API](https://www.bls.gov/developers/api_faqs.htm) (keyless).
News links: [GDELT DOC API](https://www.gdeltproject.org/) (metadata only).
Optional [FRED](https://fred.stlouisfed.org/docs/api/terms_of_use.html) series
activate only if a free `FRED_API_KEY` secret is configured.

## How it works

```
WARN Feed CSV + BLS + GDELT
        |  daily GitHub Action (ingest/*.py, Python stdlib only)
        v
data/*.json  (validated, dedupe-flagged, forecast, committed to this repo)
        |  GitHub Pages (static)
        v
web/ dashboard: explorer -> chat -> tailored analysis view -> saved views
```

- `ingest/` - pipeline: fetch, validate, dedupe-flag, forecast, build JSON.
  `fetch_econ.py` + `econ_forecast.py` build the layoff outlook: one direct
  model per 1-6 month horizon for national JOLTS layoffs & discharges, from
  lagged layoffs and BLS/DOL economic series (FRED public CSV export, no key).
  Publication lags are enforced, training rows are restricted to targets
  already published at each backtest origin (asserted in code), model choice
  and interval calibration use 2024-2025 only, and 2026 is an untouched final
  test. A learned model is published only where it beats the strongest simple
  baseline. Requires numpy + scikit-learn (installed by the workflow).
- `data/` - published artifacts: `notices.json`, `series.json`,
  `forecasts.json`, `news.json`, `meta.json`.
- `web/` - the static dashboard (no build step, plain ES modules).
- `tests/` - contract tests; a failed test stops the Action before publish.
- `.github/workflows/daily.yml` - runs the pipeline daily and deploys Pages.

## The chat cannot invent numbers

The on-device model (SmolLM2-1.7B-Instruct, Apache-2.0, via Transformers.js,
q4 ONNX from Hugging Face) only translates a question into a whitelisted JSON
query spec `{metric, filters, group_by, time_range}`. Deterministic code
validates the spec and computes every number from the published JSON. Fields
the data does not contain (e.g. visa status - WARN has no H-1B field) get an
explicit "the data doesn't record this" answer. If the model cannot load, the
chat degrades to suggested questions that drive the same engine.

## Honest limits

- The layoff outlook is a research prototype: pseudo-real-time backtests on
  latest-revised series with fixed publication-lag simulation, not as-of
  vintages and not prospectively validated. Where a learned model loses to a
  simple baseline, the baseline is published and labeled as one. No accuracy
  level or false-alarm rate is promised beyond the measured backtests shown
  on the page.

- The WARN Feed files were generated 2026-09-25 and can be stale; the site
  shows the upstream build date and a staleness banner. Free access is the
  vendor's current offer, not a guarantee of future terms or freshness.
- `employees_affected` is missing on a minority of rows; possible duplicates
  are flagged, not dropped. Totals are *announced* positions, not realized
  losses.
- Forward forecasts are withheld: the stale single WARN snapshot cannot
  establish as-of-safe evaluation. Retrospective diagnostics are shown, not
  calibrated forward prediction intervals.
- GDELT matches are by employer name and date window: approximate, links and
  metadata only, no article text.
- On-device model: 1.41 GB weights plus runtime/tokenizer one-time download per visitor browser; WebGPU
  or WASM speed varies by device. Prompts are processed on the device (no
  remote inference), but Hugging Face and GitHub still see download requests.
- GitHub: public repo, standard runners and Pages only (free tier; schedules
  pause after 60 days of repo inactivity; Pages quotas apply). Nothing here
  uses a paid service, and terms can change.

## Local run

```
python ingest/run_all.py      # stdlib only, downloads the WARN snapshot
python -m unittest discover -s tests -v
# serve web/ + data/ together, e.g.:
mkdir -p _site/data && cp -r web/* _site/ && cp data/*.json _site/data/
python -m http.server --directory _site 8000
```

## Prototype status

County, industry and individual visa metrics are unavailable. Current forward
forecasts are withheld. Local AI code is experimental; see the runtime test
notes for what was actually tested. Suggested questions and typed-question parsing are deterministic
keyword matching, not a disguised model; the interpreted query is shown beside
each answer. No historical ALFRED feature join or H-1B employer join is
implemented. Raw snapshots are archived as short-lived Action artifacts, not
claimed as historical vintages.

### Runtime test notes (2026-11-07)

Local Chrome smoke tests passed for state filtering, New York 2025 query
(340 notice rows in this snapshot), H-1B unknown behavior, local saved views,
CSV export and 390px/desktop layout. No model requests occurred before opt-in.
The opt-in q4 browser load reached 83% of the ONNX download during a bounded
65-second test. End-to-end local inference is NOT yet verified. No claim that
the free-form model works on all devices is made.

WARN input contains NUL bytes: normalization removes them and records the
count in validation metadata. Possible-duplicate rules include canonical
employer, state, location, chosen date and count. Flags are not confirmed
duplicates, and all rows remain in totals.

### Runtime test notes (2026-11-07)

Local Chrome smoke tests passed: state filtering, NY 2025 preset (340 notice
rows), H-1B unknown, saved views, CSV export and 390px/desktop layout. No
model requests before opt-in. A bounded 65-second q4 load reached 83% of
the model file download; end-to-end local inference is NOT yet verified.
NUL bytes in the WARN CSV are removed and counted. Possible duplicates
include employer, state, location, chosen date and count; all rows remain.

### Final model verification result

A longer real Chrome browser test crashed during q4 initialization/loading.
Free-form AI is therefore disabled in the visible prototype. The pinned real
SmolLM2 worker code remains in the repo for further development, but no
successful inference or device-compatibility claim is made. Suggested queries
remain visibly deterministic. News fetching is disabled by default after a
rate-limit response. There is no automatic retry against that restriction.

Further bounded browser experiments: 135M on single-thread WASM produced real
responses but failed both structured-query tests. 360M on WASM crashed during
initialization. See [actual model test results](docs/browser-model-tests.md).
Adapter detection is corrected, but no model has passed both runtime and query
contract verification, so free-form AI remains disabled.
