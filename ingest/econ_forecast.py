"""Learned multi-horizon forecasts of national JOLTS layoffs & discharges.

Target: JTSLDL (BLS JOLTS layoffs and discharges, total nonfarm, SA,
thousands of persons). Predictors: other BLS labor series and DOL/ETA weekly
initial claims, plus lagged values of the target itself. One direct model per
horizon h = 1..6 months.

Honesty rules enforced here (a violation aborts the pipeline):

* Publication-lag simulation. A forecast "issued" at the end of month t uses
  only series values whose reference month is <= t - lag, where lag is 2 for
  JOLTS and 1 for the Employment Situation series and claims. These fixed
  lags are a conservative approximation of the BLS/DOL release calendars
  (JOLTS arrives roughly six weeks after its reference month; employment
  figures early the next month; claims weekly, so a calendar month of claims
  is not fully published until days after it ends). They are not a
  per-release audit of actual publication dates.
* No target lookahead. At origin t the latest known target month is t-2, so
  a training row for issue month s (target s+h) is only used when
  s <= t - h - 2. Asserted for every fit.
* Pseudo-real-time, not vintage. Series are the latest revisions as
  downloaded. BLS revises JOLTS/CES/CPS (annual benchmarking); a true
  as-of-vintage backtest needs ALFRED-style vintage files, which this
  pipeline does not have. Backtest accuracy is therefore an approximation of
  what a real-time forecaster would have seen, usually slightly flattering.
  The output says this next to every accuracy figure.
* Prequential, not fixed-model. Every backtest prediction - including the
  2026 test months - comes from a model refit on everything published by
  that origin, so early-2026 actuals can sit in later-2026 training windows.
  "Untouched 2026" means 2026 played no role in model selection or interval
  calibration, not that a frozen pre-2026 model was tested.
* Ablation. huber_targetonly uses only lagged values of the target (no
  economic inputs) on identical folds, so the incremental value of the
  economic predictors is visible instead of assumed.
* Champion selection and interval calibration use only origins whose target
  month falls in 2024-2025. Target months in 2026 are a final untouched test:
  nothing about 2026 influences model choice, hyperparameters, or intervals.
  2026 interval coverage is therefore genuinely held out.
* Baseline gate. The learned model is published only where its 2024-2025 MAE
  is strictly below the strongest simple baseline (seasonal naive,
  persistence, or 12-month mean - whichever is best). Otherwise the page
  shows the baseline as the forecast and labels the ML result as an
  unreliable diagnostic. A baseline forecast is never presented as ML.
* "Elevated" alerts are an exploratory event definition (predicted or actual
  level above the trailing 60-observed-month 80th percentile, computed
  without lookahead). Counts of true/false positives are published with
  small-sample caveats. This is not calibrated to any user-specified
  false-positive tolerance and no zero-false-positive guarantee is made or
  implied.

Requires numpy and scikit-learn (installed by the workflow; everything else
in this repo is stdlib-only). Fetches are done by fetch_econ.py.
"""
import csv, datetime, json, math, sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import HuberRegressor, Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import DATA, INTER, dump_json, load_json

TARGET = "JTSLDL"
LAGS = {"JTSLDL": 2, "JTSJOL": 2, "JTSHIL": 2, "UNRATE": 1,
        "PAYEMS": 1, "AWHNONAG": 1, "ICSA": 1}
AGENCY = {"JTSLDL": "BLS JOLTS", "JTSJOL": "BLS JOLTS", "JTSHIL": "BLS JOLTS",
          "UNRATE": "BLS CPS", "PAYEMS": "BLS CES", "AWHNONAG": "BLS CES",
          "ICSA": "DOL Employment and Training Administration"}
HORIZONS = (1, 2, 3, 4, 5, 6)
MIN_TRAIN = 120           # rows required before any backtest origin
DIAG_START = "2012-01"    # long-run diagnostic origins (in-sample-era context)
SEL_RANGE = ("2024-01", "2025-12")   # champion selection + interval calibration
TEST_YEAR = "2026"                   # final untouched test
PUBLISH_BACKTEST_FROM = "2023-01"    # origins published to the site
RIDGE_ALPHAS = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0)
ALERT_WINDOW = 60         # trailing observed months for the alert threshold
ALERT_Q = 0.8


# ---------- month helpers (months as "YYYY-MM" strings) ----------

def mi(m):  # to linear index
    return int(m[:4]) * 12 + int(m[5:7]) - 1


def ms(i):  # to string
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def m_add(m, k):
    return ms(mi(m) + k)


# ---------- data loading ----------

def load_series(sid):
    """Return {month: value}; ICSA weekly values are averaged by month. No
    interpolation anywhere: a value from the future of a backtest origin must
    never leak into it. Missing predictor months are handled at lookup time
    with past-only carry-forward (see features)."""
    path = DATA / "snapshots" / "econ" / f"{sid}.csv"
    rows = list(csv.DictReader(path.open()))
    col = [c for c in rows[0] if c != "observation_date"][0]
    if sid == "ICSA":
        bucket = {}
        for r in rows:
            if r[col] in (".", "", None):
                continue
            bucket.setdefault(r["observation_date"][:7], []).append(float(r[col]))
        return {m: sum(v) / len(v) / 1000.0 for m, v in sorted(bucket.items())}  # thousands/week
    return {r["observation_date"][:7]: float(r[col])
            for r in rows if r[col] not in (".", "", None)}


def source_gaps(d):
    """Missing months strictly inside a series' observed range."""
    if not d:
        return []
    out, i = [], mi(min(d))
    while i <= mi(max(d)):
        if ms(i) not in d:
            out.append(ms(i))
        i += 1
    return out


def gcarry(d, i):
    """Past-only lookup: the value for month i, else the newest EARLIER value
    and how many months back it came from. Never reaches forward, so a month
    published late (or never, like the October 2025 unemployment rate lost to
    the 2025 federal shutdown) cannot leak future information into an origin.
    Returns (value, carry_months); (None, None) if nothing exists yet."""
    j = i
    while j >= mi("1999-01"):
        v = d.get(ms(j))
        if v is not None:
            return v, i - j
        j -= 1
    return None, None


# ---------- feature construction ----------

FEATURE_NAMES = [
    "y_lag0", "y_lag1", "y_mom1", "y_ma6", "y_seas_h",
    "unrate", "unrate_d3", "unrate_d12", "unrate_carried",
    "pay_d1", "pay_d3", "pay_pct12", "pay_carried",
    "awh", "awh_d3", "awh_carried",
    "openings", "openings_d12", "openings_carried",
    "hires", "hires_d3", "hires_carried",
    "claims", "claims_d3", "claims_d12", "claims_carried",
]


def features(S, t, h):
    """Feature vector for a forecast issued in month t for target month t+h.

    Every lookup respects its series' publication lag, then applies past-only
    carry-forward for missing months; a *_carried indicator is 1 when a
    series' level value came from an earlier month than the lag implies.
    Target-side lookups are never carried: a missing target month makes the
    row unavailable. Returns None if any value is unavailable.
    """
    y, jol, hil = S["JTSLDL"], S["JTSJOL"], S["JTSHIL"]
    unr, pay, awh, clm = S["UNRATE"], S["PAYEMS"], S["AWHNONAG"], S["ICSA"]

    def g(d, i):  # target-side: exact month only
        return d.get(ms(i))

    def cdiff(d, a, b):
        (x, _), (z, _) = gcarry(d, a), gcarry(d, b)
        return None if x is None or z is None else x - z

    def cpct(d, a, b):
        (x, _), (z, _) = gcarry(d, a), gcarry(d, b)
        return None if x is None or z in (None, 0) else 100.0 * (x / z - 1.0)

    u, uc = gcarry(unr, t - 1)
    p, pc = gcarry(pay, t - 1)
    w, wc = gcarry(awh, t - 1)
    o, oc = gcarry(jol, t - 2)
    hr, hc = gcarry(hil, t - 2)
    c, cc = gcarry(clm, t - 1)
    vals = [
        g(y, t - 2), g(y, t - 3),
        (g(y, t - 2) - g(y, t - 3)) if g(y, t - 2) is not None and g(y, t - 3) is not None else None,
        _mean([g(y, t - k) for k in range(2, 8)]),
        g(y, t + h - 12),                      # same month last year of the TARGET month
        u, cdiff(unr, t - 1, t - 4), cdiff(unr, t - 1, t - 13), float(bool(uc)),
        cdiff(pay, t - 1, t - 2), cdiff(pay, t - 1, t - 4), cpct(pay, t - 1, t - 13), float(bool(pc)),
        w, cdiff(awh, t - 1, t - 4), float(bool(wc)),
        o, cpct(jol, t - 2, t - 14), float(bool(oc)),
        hr, cdiff(hil, t - 2, t - 5), float(bool(hc)),
        c, cdiff(clm, t - 1, t - 4), cdiff(clm, t - 1, t - 13), float(bool(cc)),
    ]
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals):
        return None
    return vals


def _mean(vs):
    return None if any(v is None for v in vs) else sum(vs) / len(vs)


def _diff(d, a, b):
    x, y = d.get(ms(a)), d.get(ms(b))
    return None if x is None or y is None else x - y


def _pct(d, a, b):
    x, y = d.get(ms(a)), d.get(ms(b))
    return None if x is None or y is None or y == 0 else 100.0 * (x / y - 1.0)


# ---------- genuine leakage tests ----------

class _Rec(dict):
    """dict that records every month looked up, per series."""
    def __init__(self, d, log, sid):
        super().__init__(d)
        self._log, self._sid = log, sid

    def get(self, k, default=None):
        self._log.append((self._sid, k))
        return super().get(k, default)


def lineage_check(S, t, h):
    """Every month a feature lookup touches must satisfy its series' lag."""
    log = []
    Srec = {sid: _Rec(d, log, sid) for sid, d in S.items()}
    features(Srec, t, h)
    for sid, m in log:
        assert mi(m) <= t - LAGS[sid], (
            f"lineage violation: {sid} looked up {m} at origin {ms(t)} (lag {LAGS[sid]})")


def _origin_preds(S, t, h):
    """Refit every model exactly as the backtest does and return predictions."""
    y = S[TARGET]
    s_max = t - h - 2
    rows_tr = []
    s = mi("2002-01")
    while s <= s_max:
        f_s = features(S, s, h)
        tgt = y.get(ms(s + h))
        if f_s is not None and tgt is not None:
            rows_tr.append((f_s, tgt, baseline_preds(y, s, h)["ma12"]))
        s += 1
    f = features(S, t, h)
    if f is None or len(rows_tr) < MIN_TRAIN:
        return None
    X = np.array([r[0] for r in rows_tr])
    yv = np.array([r[1] for r in rows_tr])
    base_tr = np.array([r[2] if r[2] is not None else np.nan for r in rows_tr])
    preds = {name: float(ftr(X, yv, **({"gap": h + 2} if ftr is fit_ridge else {})).predict(np.array([f]))[0])
             for name, ftr in MODEL_FITTERS.items()}
    base_t = baseline_preds(y, t, h)["ma12"]
    ok = base_t is not None and not np.isnan(base_tr).any()
    for name, ftr in RESIDUAL_MODELS.items():
        preds[name] = None if not ok else float(base_t + ftr(X, yv - base_tr, gap=h + 2).predict(np.array([f]))[0])
    for name, ftr in TARGETONLY_MODELS.items():
        preds[name] = float(ftr(X[:, :TARGET_ONLY_COLS], yv).predict(np.array([f])[:, :TARGET_ONLY_COLS])[0])
    for name, val in baseline_preds(y, t, h).items():
        preds[name] = val
    return preds


def perturbation_check(S, t, h):
    """Multiply every observation newer than its series' cutoff at origin t
    by a large factor. Features and every model's prediction must be
    bit-identical; any change proves future data reached the origin."""
    before = _origin_preds(S, t, h)
    if before is None:
        return
    S2 = {sid: dict(d) for sid, d in S.items()}
    for sid, d in S2.items():
        for m in list(d):
            if mi(m) > t - LAGS[sid]:
                d[m] = d[m] * 3.7 + 12345.0
    after = _origin_preds(S2, t, h)
    lineage_check(S, t, h)
    assert after == before, f"future-influence leak at origin {ms(t)} h={h}"


def selftest(S):
    """Lineage + future-perturbation proof over a spread of origins."""
    origins = ("2015-06", "2020-04", "2024-06", "2025-12", "2026-06")
    for m in origins:
        for h in (1, 3, 6):
            perturbation_check(S, mi(m), h)
    print(f"leakage self-test passed ({len(origins)} origins x 3 horizons: "
          "lookup lineage + future perturbation)")


# ---------- models ----------

def fit_ridge(X, yv, gap=0):
    """Ridge with alpha chosen by past-only inner CV on the training rows.
    gap=h+2 keeps each inner validation fold's labels outside the horizon +
    publication delay of the inner training cutoff, matching the outer rule."""
    best_alpha, best_mae = RIDGE_ALPHAS[0], float("inf")
    n = len(yv)
    splits = list(TimeSeriesSplit(n_splits=3, gap=gap).split(X)) if n >= 40 + gap else []
    for alpha in RIDGE_ALPHAS:
        if splits:
            errs = []
            for tr, va in splits:
                m = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
                m.fit(X[tr], yv[tr])
                errs.append(np.mean(np.abs(m.predict(X[va]) - yv[va])))
            score = float(np.mean(errs))
        else:
            m = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
            m.fit(X, yv)
            score = float(np.mean(np.abs(m.predict(X) - yv)))
        if score < best_mae:
            best_mae, best_alpha = score, alpha
    model = make_pipeline(StandardScaler(), Ridge(alpha=best_alpha))
    model.fit(X, yv)
    model.alpha_ = best_alpha
    return model


def fit_huber(X, yv):
    """Robust linear model: squared-loss ridge is poisoned by the COVID-19
    outlier months that sit in every training window. Huber limits their pull.
    Fixed hyperparameters - nothing tuned on selection or test origins."""
    m = make_pipeline(StandardScaler(), HuberRegressor(max_iter=400))
    m.fit(X, yv)
    return m


def fit_gbt(X, yv):
    m = HistGradientBoostingRegressor(max_depth=3, max_iter=200,
                                      learning_rate=0.06,
                                      l2_regularization=1.0,
                                      random_state=7)
    m.fit(X, yv)
    return m


MODEL_FITTERS = {"ridge": fit_ridge, "huber": fit_huber, "gbt": fit_gbt}

# residual_ridge learns the deviation of the target from the 12-month mean
# baseline; with no economic signal it degrades gracefully to that baseline.
RESIDUAL_MODELS = {"residual_ridge": fit_ridge}
# Ablation: same Huber estimator on target-lag features only (first five
# columns), no economic inputs, identical folds - measures what the economic
# predictors add over a learned target-only model.
TARGET_ONLY_COLS = 5
TARGETONLY_MODELS = {"huber_targetonly": fit_huber}
ML_MODELS = tuple(MODEL_FITTERS) + tuple(RESIDUAL_MODELS) + tuple(TARGETONLY_MODELS)


def baseline_preds(y, t, h):
    """Simple forecasts for issue t, target t+h. All use only observed months."""
    seas = y.get(ms(t + h - 12))
    pers = y.get(ms(t - 2))
    ma_vals = [y.get(ms(t - k)) for k in range(2, 14)]
    ma12 = None if any(v is None for v in ma_vals) else sum(ma_vals) / 12.0
    return {"seasonal_naive": seas, "persistence": pers, "ma12": ma12}


BASELINES = ("seasonal_naive", "persistence", "ma12")
ALL_MODELS = ML_MODELS + BASELINES


# ---------- backtest engine ----------

def run_backtest(S, t0, t1):  # noqa: C901 - the rolling origin loop is the core

    """Rolling-origin backtest for origins t0..t1 (inclusive, linear indices).

    Returns {h: [ {origin, target, actual, preds{model:val}, threshold} ]}.
    Training per origin uses only rows whose target was published by then.
    """
    y = S[TARGET]
    out = {h: [] for h in HORIZONS}
    for t in range(t0, t1 + 1):
        for h in HORIZONS:
            actual = y.get(ms(t + h))
            if actual is None:
                continue
            # training rows: issue s, target s+h published by end of t
            s_max = t - h - 2
            rows_tr = []  # (issue, features, target, ma12 baseline)
            s = mi("2002-01")
            while s <= s_max:
                f_s = features(S, s, h)
                tgt = y.get(ms(s + h))
                if f_s is not None and tgt is not None:
                    rows_tr.append((s, f_s, tgt, baseline_preds(y, s, h)["ma12"]))
                s += 1
            assert not rows_tr or ms(s_max + h) <= ms(t - 2), "target lookahead in training slice"
            if len(rows_tr) < MIN_TRAIN:
                continue
            f = features(S, t, h)
            if f is None:
                continue
            X = np.array([r[1] for r in rows_tr])
            yv = np.array([r[2] for r in rows_tr])
            base_tr = np.array([r[3] if r[3] is not None else np.nan for r in rows_tr])
            preds = {}
            for name, fitter in MODEL_FITTERS.items():
                kw = {"gap": h + 2} if fitter is fit_ridge else {}
                preds[name] = float(fitter(X, yv, **kw).predict(np.array([f]))[0])
            # residual model: learn y - ma12 over the same training rows
            base_t = baseline_preds(y, t, h)["ma12"]
            ok = base_t is not None and not np.isnan(base_tr).any()
            for name, fitter in RESIDUAL_MODELS.items():
                preds[name] = (None if not ok else
                               float(base_t + fitter(X, yv - base_tr, gap=h + 2).predict(np.array([f]))[0]))
            for name, fitter in TARGETONLY_MODELS.items():
                preds[name] = float(fitter(X[:, :TARGET_ONLY_COLS], yv)
                                    .predict(np.array([f])[:, :TARGET_ONLY_COLS])[0])
            for name, val in baseline_preds(y, t, h).items():
                preds[name] = None if val is None else float(val)
            hist = [y.get(ms(t - k)) for k in range(2, 2 + ALERT_WINDOW)]
            hist = [v for v in hist if v is not None]
            thr = float(np.quantile(hist, ALERT_Q)) if len(hist) >= 48 else None
            out[h].append({"origin": ms(t), "target": ms(t + h), "actual": actual,
                           "preds": preds, "threshold": thr})
    return out


# ---------- metrics ----------

def era_of(target_month):
    if SEL_RANGE[0] <= target_month <= SEL_RANGE[1]:
        return "selection_2024_2025"
    if target_month.startswith(TEST_YEAR):
        return "test_2026"
    return "diagnostic_pre2024"


def summarize(rows, models):
    """MAE/RMSE per model per era, plus 2024/2025 pooled by year."""
    eras = {}
    for row in rows:
        e = era_of(row["target"])
        eras.setdefault(e, []).append(row)
        if e == "selection_2024_2025":
            eras.setdefault(f"sel_{row['target'][:4]}", []).append(row)
    out = {}
    for era, rs in sorted(eras.items()):
        out[era] = {"n_origins": len(rs), "models": {}}
        for m in models:
            es = [r["actual"] - r["preds"][m] for r in rs if r["preds"].get(m) is not None]
            if not es:
                continue
            out[era]["models"][m] = {
                "n": len(es),
                "mae": round(float(np.mean(np.abs(es))), 1),
                "rmse": round(float(np.sqrt(np.mean(np.square(es)))), 1)}
    return out


def alert_stats(rows, pred_key):
    out = {}
    for row in rows:
        thr = row["threshold"]
        if thr is None or row["preds"].get(pred_key) is None:
            continue
        year = row["target"][:4]
        a = out.setdefault(year, {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
        pa, aa = row["preds"][pred_key] > thr, row["actual"] > thr
        a["tp" if pa and aa else "fp" if pa else "fn" if aa else "tn"] += 1
    for year, a in out.items():
        p = a["tp"] / (a["tp"] + a["fp"]) if a["tp"] + a["fp"] else None
        r = a["tp"] / (a["tp"] + a["fn"]) if a["tp"] + a["fn"] else None
        a.update({"precision": None if p is None else round(p, 2),
                  "recall": None if r is None else round(r, 2),
                  "elevated_share": round((a["tp"] + a["fn"]) / max(1, sum(a[k] for k in ("tp", "fp", "fn", "tn"))), 2)})
    return out


def coverage(rows, pred_key, q10, q90):
    hits = tot = 0
    for row in rows:
        p = row["preds"].get(pred_key)
        if p is None:
            continue
        tot += 1
        hits += (p + q10) <= row["actual"] <= (p + q90)
    return {"n": tot, "coverage_80": None if not tot else round(hits / tot, 2)}


# ---------- main ----------

def main():
    fetch_meta = load_json(INTER / "econ_fetch.json")
    if not fetch_meta or fetch_meta.get("failed"):
        print("econ_forecast: fetch metadata missing or incomplete")
        return 1
    S = {sid: load_series(sid) for sid in LAGS}
    y = S[TARGET]
    gaps = {sid: source_gaps(d) for sid, d in S.items() if source_gaps(d)}

    run_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # Live issue month: the newest t whose full feature set is actually
    # published as of the retrieval timestamp (lag rule applied to the latest
    # observed month per series). This is an as-of-today issue, not an
    # end-of-month simulation: no future input is assumed.
    t_live = min(mi(max(d)) + LAGS[sid] for sid, d in S.items())
    t0 = mi(DIAG_START)
    selftest(S)  # aborts the pipeline on any future-influence leak
    bt = run_backtest(S, t0, min(t_live, mi(max(y)) - 1))

    result = {
        "schema_version": 1,
        "generated_at": run_at,
        "issue_month": ms(t_live),
        "issue_semantics": ("Forecasts use the latest-revised values the fixed lag rule "
                            "expects to be published as of the retrieval date; issue month "
                            "is the latest month for which that rule yields a complete "
                            "feature set. Individual release dates are not audited per "
                            "origin (spot-checked against the BLS calendar at build time). "
                            "Backtest origins simulate the same rule at past month-ends."),
        "target": {"series": TARGET, "agency": AGENCY[TARGET],
                   "name": fetch_meta["series"][TARGET]["label"],
                   "units": fetch_meta["series"][TARGET]["units"],
                   "definition": "Includes firings and other discharges, not only "
                                 "layoffs for economic weakness. A JOLTS measure, "
                                 "not WARN notices and not a count of people.",
                   "latest_observed_month": max(y)},
        "horizons": {},
        "evaluation": {
            "design": "Expanding-window rolling-origin backtest; direct model per horizon.",
            "selection_era": list(SEL_RANGE),
            "final_test_era": "2026 target months (untouched by selection/calibration)",
            "diagnostic_era": f"{DIAG_START}..2023 origins (context only, overlaps training)",
            "min_train_months": MIN_TRAIN,
            "pseudo_real_time": True,
            "caveats": [
                "Latest-revised data, not historical vintages: BLS revises these series "
                "(annual JOLTS/CES benchmarking). Backtest accuracy approximates and "
                "usually flatters real-time performance.",
                "Fixed publication lags (JOLTS 2 months, others 1) approximate the "
                "release calendar; actual release dates vary. Claims are weekly; a "
                "calendar month of claims is not fully published until days after it ends.",
                "Claims (ICSA) are seasonally adjusted weekly counts averaged into "
                "calendar months; the week-to-month mapping is approximate.",
                "Prequential evaluation, not a fixed-model test: every prediction, "
                "including 2026 test months, comes from a model refit on everything "
                "published by that origin. 'Untouched 2026' means 2026 played no role "
                "in model selection or interval calibration only.",
                "Roughly 24 selection and up to 9 final-test origins per horizon: "
                "per-year scores have wide sampling error.",
                "Elevated-alert evaluation is exploratory and historical only, not "
                "calibrated to a required false-positive rate; no zero-false-positive "
                "guarantee is possible or made. It is not a risk recommendation.",
                "Intervals are residual bands calibrated on 2024-2025 selection origins "
                "of the published model. Selection-era coverage is in-calibration "
                "(optimistic); 2026 coverage is held out. Where held-out coverage falls "
                "well short of the nominal 80%, the band ran too narrow and is labeled so.",
                "huber_targetonly is an exploratory ablation using only lagged target "
                "values on identical folds. Full-model improvements over it on the "
                "2024-2025 selection era and on 2026 are reported descriptively; with "
                "~24 selection and ~9 test origins, the incremental value of the "
                "economic predictors carries wide uncertainty, and no causal feature "
                "importance is claimed.",
                "Leakage tests validate the cutoff logic on the latest data snapshot "
                "only; they cannot prove what was actually available historically - "
                "the vintage caveat stands.",
                "Forecasts describe this JOLTS measure only. They are not causal claims "
                "about the economy and not WARN notice predictions.",
            ] + ([f"Source gaps handled by past-only carry-forward with a missingness "
                  f"indicator (never the target, never reaching forward): "
                  + "; ".join(f"{sid} {m}" for sid, m in gaps.items())] if gaps else []),
        },
        "source_gaps": gaps,
        "gap_notes": {"UNRATE": {"2025-10": "Never published: the 2025 federal government "
                                             "shutdown halted CPS collection and BLS cancelled "
                                             "the October 2025 household report."}},
    }

    for h in HORIZONS:
        rows = bt[h]
        sel = [r for r in rows if era_of(r["target"]) == "selection_2024_2025"]
        test = [r for r in rows if era_of(r["target"]) == "test_2026"]
        diag = [r for r in rows if era_of(r["target"]) == "diagnostic_pre2024"]
        metrics = summarize(rows, ALL_MODELS)

        def sel_mae(m):
            d = metrics.get("selection_2024_2025", {}).get("models", {}).get(m)
            return d["mae"] if d else None

        base_best = min((b for b in BASELINES if sel_mae(b) is not None),
                        key=lambda b: sel_mae(b), default=None)
        ml_scores = {m: sel_mae(m) for m in ML_MODELS if sel_mae(m) is not None}
        ml_best = min(ml_scores, key=ml_scores.get) if ml_scores else None
        gate = (ml_best is not None and base_best is not None
                and sel_mae(ml_best) < sel_mae(base_best))
        published = ml_best if gate else base_best
        status = "ok" if gate else "no_ml_beat"

        # intervals from selection-era residuals of the PUBLISHED model only
        res = sorted(r["actual"] - r["preds"][published] for r in sel
                     if r["preds"].get(published) is not None)
        q10 = float(np.quantile(res, 0.1)) if len(res) >= 20 else None
        q90 = float(np.quantile(res, 0.9)) if len(res) >= 20 else None

        # live forecast: retrain published model on all rows published by t_live
        s_max = t_live - h - 2
        rows_tr = []
        s = mi("2002-01")
        while s <= s_max:
            f_s = features(S, s, h)
            tgt = y.get(ms(s + h))
            if f_s is not None and tgt is not None:
                rows_tr.append((f_s, tgt, baseline_preds(y, s, h)["ma12"]))
            s += 1
        X = np.array([r[0] for r in rows_tr])
        yv = np.array([r[1] for r in rows_tr])
        base_tr = np.array([r[2] if r[2] is not None else np.nan for r in rows_tr])
        live = None
        f_live = features(S, t_live, h)
        if f_live is not None and len(yv) >= MIN_TRAIN:
            if published in MODEL_FITTERS:
                ftr = MODEL_FITTERS[published]
                mdl = ftr(X, yv, **({"gap": h + 2} if ftr is fit_ridge else {}))
                point = float(mdl.predict(np.array([f_live]))[0])
            elif published in RESIDUAL_MODELS:
                base_t = baseline_preds(y, t_live, h)["ma12"]
                if base_t is None or np.isnan(base_tr).any():
                    point = None
                else:
                    rm = RESIDUAL_MODELS[published](X, yv - base_tr, gap=h + 2)
                    point = float(base_t + rm.predict(np.array([f_live]))[0])
            elif published in TARGETONLY_MODELS:
                mdl = TARGETONLY_MODELS[published](X[:, :TARGET_ONLY_COLS], yv)
                point = float(mdl.predict(np.array([f_live])[:, :TARGET_ONLY_COLS])[0])
            else:
                point = baseline_preds(y, t_live, h)[published]
            if point is not None:
                live = {"target_month": ms(t_live + h), "point": round(point),
                        "lower_80": None if q10 is None else round(max(0.0, point + q10)),
                        "upper_80": None if q90 is None else round(max(0.0, point + q90)),
                        "n_train": len(yv), "trained_through_issue": ms(s_max),
                        "model": published}

        tst = metrics.get("test_2026", {}).get("models", {})
        holdout = {"published_mae": tst.get(published, {}).get("mae"),
                   "strongest_baseline": base_best,
                   "strongest_baseline_mae": tst.get(base_best, {}).get("mae") if base_best else None,
                   "n": metrics.get("test_2026", {}).get("n_origins", 0)}
        holdout["held_up"] = (None if holdout["published_mae"] is None
                              or holdout["strongest_baseline_mae"] is None
                              else holdout["published_mae"] <= holdout["strongest_baseline_mae"])
        result["horizons"][str(h)] = {
            "status": status,
            "holdout_2026": holdout,
            "published_model": published,
            "published_model_kind": "machine_learning" if published in ML_MODELS else "simple_baseline",
            "ml_candidates": ml_scores,
            "strongest_baseline": {"name": base_best,
                                   "selection_mae": sel_mae(base_best) if base_best else None},
            "gate": ("Published because the learned model beat the strongest baseline on "
                     "2024-2025 selection origins." if gate else
                     "Learned models did not beat the strongest simple baseline on "
                     "2024-2025 selection origins, so the published forecast is the "
                     "baseline and ML scores are shown as unreliable diagnostics."),
            "live": live,
            "metrics": metrics,
            "interval": {"method": "10th/90th percentile of selection-era (2024-2025) "
                                   "out-of-sample residuals of the published model",
                         "q10": None if q10 is None else round(q10, 1),
                         "q90": None if q90 is None else round(q90, 1),
                         "selection_coverage": coverage(sel, published, q10 or 0, q90 or 0),
                         "test_2026_coverage": coverage(test, published, q10 or 0, q90 or 0)},
            "alerts": {"rule": f"Predicted or actual level above trailing {ALERT_WINDOW}-month "
                               f"{int(ALERT_Q * 100)}th percentile (no lookahead)",
                       "by_year": alert_stats(sel + test, published),
                       "note": "Exploratory event definition; not calibrated to a required "
                               "false-positive rate. Counts are small."},
            "backtest": [{"origin": r["origin"], "target": r["target"],
                          "actual": r["actual"], "preds": r["preds"],
                          "threshold": r["threshold"]}
                         for r in rows if r["origin"] >= PUBLISH_BACKTEST_FROM],
            "counts": {"selection_origins": len(sel), "test_2026_origins": len(test),
                       "diagnostic_origins": len(diag)},
        }

    result["sources"] = [
        {"id": sid, "agency": AGENCY[sid], **fetch_meta["series"][sid]} for sid in LAGS]
    dump_json(result, INTER / "econ_forecast.json")

    # console digest
    for h in HORIZONS:
        hz = result["horizons"][str(h)]
        sel_m = hz["metrics"].get("selection_2024_2025", {}).get("models", {})
        tst_m = hz["metrics"].get("test_2026", {}).get("models", {})
        print(f"h={h} status={hz['status']} published={hz['published_model']} "
              f"selMAE={ {m: v['mae'] for m, v in sel_m.items()} } "
              f"test2026MAE={ {m: v['mae'] for m, v in tst_m.items()} } "
              f"cov2026={hz['interval']['test_2026_coverage']}")
    print(f"issue_month={result['issue_month']} target_latest={result['target']['latest_observed_month']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
