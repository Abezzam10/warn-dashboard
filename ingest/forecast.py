"""Classical, backtested forecasts for monthly WARN activity. No LLM involved.

Candidates: seasonal-naive (value 12 months back) and seasonal-naive + drift.
A rolling-origin backtest scores both by MAE at 1/3/6-month horizons; a
forecast is published only if the challenger beats seasonal-naive. Prediction
intervals come from the backtest error distribution. Every figure carries the
training cutoff so nothing dated after it can leak in.
"""
import sys, statistics, datetime
from common import DATA, dump_json, load_json

HORIZONS = (1, 3, 6)
MIN_MONTHS = 36
BACKTEST_ORIGINS = 12


def monthly_series(notices, month_cap, key=None):
    agg = {}
    for n in notices:
        if key and key(n) is None:
            continue
        month = (n["notice_date"] or n["effective_date"] or "")[:7]
        if not month or month > month_cap:
            continue
        k = key(n) if key else "all"
        a = agg.setdefault(k, {}).setdefault(month, {"notices": 0, "workers": 0})
        a["notices"] += 1
        a["workers"] += n["workers_announced"] or 0
    return agg


def contiguous(agg, field):
    """Return ordered (months, values) filling gaps with zeros."""
    if not agg:
        return [], []
    months = sorted(agg)
    start = [int(months[0][:4]), int(months[0][5:7])]
    end = [int(months[-1][:4]), int(months[-1][5:7])]
    out_m, out_v = [], []
    y, m = start
    while (y, m) <= tuple(end):
        key = f"{y:04d}-{m:02d}"
        out_m.append(key)
        out_v.append(agg.get(key, {}).get(field, 0))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out_m, out_v


def fc_seasonal(train, h):
    return train[-12 + (h - 1)] if len(train) >= 12 else None


def fc_drift(train, h):
    base = fc_seasonal(train, h)
    if base is None:
        return None
    recent = train[-13:]
    drift = (recent[-1] - recent[0]) / 12.0
    return max(0.0, base + h * drift)


MODELS = {"seasonal_naive": fc_seasonal, "seasonal_naive_drift": fc_drift}


def backtest(values):
    """Rolling-origin errors per model per horizon."""
    errors = {name: {h: [] for h in HORIZONS} for name in MODELS}
    origins = range(max(13, len(values) - BACKTEST_ORIGINS - max(HORIZONS) + 1),
                    len(values) - max(HORIZONS) + 1)
    n = 0
    for t in origins:
        train = values[:t]
        if len(train) < 12:
            continue
        n += 1
        for name, fn in MODELS.items():
            for h in HORIZONS:
                if t + h - 1 < len(values):
                    pred = fn(train, h)
                    if pred is not None:
                        errors[name][h].append(values[t + h - 1] - pred)
    return errors, n


def mae(errs):
    return statistics.mean(abs(e) for e in errs) if errs else None


def quantile(sorted_vals, q):
    if not sorted_vals:
        return None
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def forecast_one(months, values):
    if len(values) < MIN_MONTHS:
        return {"status": "insufficient_history", "months_available": len(values)}
    errors, n_origins = backtest(values)
    if n_origins < 4:
        return {"status": "insufficient_history", "months_available": len(values)}
    mae_sn = mae(errors["seasonal_naive"][1])
    mae_alt = mae(errors["seasonal_naive_drift"][1])
    scores = {name: {f"h{h}": {"mae": (round(mae(errors[name][h]), 2)
                                    if mae(errors[name][h]) is not None else None),
                              "n": len(errors[name][h])} for h in HORIZONS}
              for name in MODELS}
    if mae_alt is None or mae_sn is None or mae_alt >= mae_sn:
        return {"status": "below_baseline",
                "note": "Challenger did not beat the seasonal-naive baseline on "
                        "rolling backtests; forecast withheld by design.",
                "backtest_scores": scores, "trained_on": months[-1]}
    last = months[-1]
    y, m = int(last[:4]), int(last[5:7])
    points = []
    for h in HORIZONS:
        pred = fc_drift(values, h)
        errs = sorted(errors["seasonal_naive_drift"][h])
        radius = quantile(sorted(abs(e) for e in errs), 0.8)
        lo_e, hi_e = -radius, radius
        hh, mm = y, m + h
        while mm > 12:
            hh, mm = hh + 1, mm - 12
        inside = [e for e in errors["seasonal_naive_drift"][h]
                  if lo_e is not None and lo_e <= e <= hi_e]
        points.append({
            "horizon_months": h, "month": f"{hh:04d}-{mm:02d}",
            "point": round(pred, 1),
            "lower_80": round(max(0.0, pred + lo_e), 1) if lo_e is not None else None,
            "upper_80": round(max(0.0, pred + hi_e), 1) if hi_e is not None else None,
            "interval_coverage_80": (round(len(inside) / len(errs), 2) if errs else None)})
    return {"status": "ok", "model": "seasonal_naive_drift",
            "baseline": "seasonal_naive", "trained_on": last,
            "backtest_origins": n_origins, "backtest_scores": scores,
            "points": points,
            "note": "Announced notices/workers, not realized job losses. Simple "
                    "classical model; accuracy is measured, not promised."}


def main():
    validated = load_json(DATA / "intermediate" / "validated.json")
    fetch_meta = load_json(DATA / "intermediate" / "warn_fetch.json")
    notices = validated["notices"]
    gen = datetime.date.fromisoformat(fetch_meta["coverage_generated_at"][:10])
    month_cap = (gen.replace(day=1) - datetime.timedelta(days=1)).isoformat()[:7]
    nat = monthly_series(notices, month_cap)["all"]

    def pack(field):
        months, values = contiguous(nat, field)
        r = forecast_one(months, values)
        r["history"] = [{"month": m, "value": v} for m, v in zip(months, values)]
        return r

    out = {"month_cap": month_cap, "evaluation_type": "Retrospective latest-snapshot backtest, NOT as-of/vintage-safe. Revised/backfilled WARN rows may leak into historical tests. Intervals are in-sample residual bands, not independently calibrated coverage.",
           "national": {"notices": pack("notices"), "workers": pack("workers")},
           "states": {}}
    by_state = monthly_series(notices, month_cap, key=lambda n: n["state"])
    top_states = sorted(by_state, key=lambda s: -sum(a["notices"] for a in by_state[s].values()))[:10]
    for st in top_states:
        months, values = contiguous(by_state[st], "notices")
        r = forecast_one(months, values)
        r["history"] = [{"month": m, "value": v} for m, v in zip(months, values)]
        out["states"][st] = {"notices": r}
    for r in list(out["national"].values()) + [v["notices"] for v in out["states"].values()]:
        r["experimental_status"] = r["status"]
        r["status"] = "withheld"
        r.pop("points", None)
        r["note"] = "Forecast withheld: stale upstream and no historical as-of snapshots. Retrospective scores are diagnostic only, not a validated forward forecast."
    dump_json(out, DATA / "intermediate" / "forecasts.json")
    print(f"forecast: national notices status={out['national']['notices']['status']}, "
          f"states evaluated={len(out['states'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
