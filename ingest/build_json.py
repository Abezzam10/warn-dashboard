"""Assemble the published data artifacts the static site reads."""
import sys, datetime
from common import DATA, dump_json, load_json

SCHEMA_VERSION = 1


def main():
    validated = load_json(DATA / "intermediate" / "validated.json")
    fetch_meta = load_json(DATA / "intermediate" / "warn_fetch.json")
    forecasts = load_json(DATA / "intermediate" / "forecasts.json")
    bls = load_json(DATA / "intermediate" / "bls.json", {"status": "unavailable"})
    fred = load_json(DATA / "intermediate" / "fred.json", {"status": "unavailable"})
    gdelt = load_json(DATA / "intermediate" / "gdelt.json",
                      {"articles": [], "matched_at": None, "errors": []})
    notices = validated["notices"]
    month_cap = (fetch_meta.get("coverage_generated_at") or "")[:7]

    # series.json: monthly rollups + economic context
    nat, by_state, by_type = {}, {}, {}
    states_by_month = {}
    for n in notices:
        month = (n["notice_date"] or n["effective_date"] or "")[:7]
        if not month or month > month_cap:
            continue
        for agg, key in ((nat, "all"), (by_state, n["state"]),
                         (by_type, n["notice_type"] or "unknown")):
            a = agg.setdefault(key, {}).setdefault(
                month, {"month": month, "notices": 0, "workers_announced_sum": 0,
                        "workers_missing_count": 0})
            a["notices"] += 1
            a["workers_announced_sum"] += n["workers_announced"] or 0
            a["workers_missing_count"] += 1 if n["workers_missing"] else 0
        states_by_month.setdefault(month, set()).add(n["state"])

    def flat(agg):
        return {k: [a[m] for m in sorted(a)] for k, a in agg.items()}

    series = {"schema_version": SCHEMA_VERSION, "month_cap": month_cap,
              "national": flat(nat)["all"],
              "by_state": flat(by_state), "by_notice_type": flat(by_type),
              "states_reporting_by_month": {m: sorted(s) for m, s in sorted(states_by_month.items())},
              "economic_context": {
                  "bls": bls, "fred": fred,
                  "note": "Context series sit beside WARN data; no causal claim is made."}}

    run_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    gen = fetch_meta.get("coverage_generated_at")
    stale_days = None
    if gen:
        try:
            g = datetime.datetime.fromisoformat(gen.replace("Z", "+00:00"))
            stale_days = (datetime.datetime.now(datetime.timezone.utc) - g).days
        except ValueError:
            pass
    meta = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_run_at": run_at,
        "upstream": {"name": "WARN Feed (APVentureEngine/warn-act-notices)",
                     "license": "CC BY 4.0",
                     "url": "https://github.com/APVentureEngine/warn-act-notices",
                     "data_url": "https://approjects-warn-act-notices.static.hf.space",
                     "generated_at": gen, "stale_days": stale_days,
                     "csv_sha256": fetch_meta.get("csv_sha256"),
                     "coverage": fetch_meta.get("coverage")},
        "row_counts": {"notices": len(notices),
                       "workers_missing": validated["validation"]["workers_missing"],
                       "workers_missing_pct": validated["validation"]["workers_missing_pct"],
                       "possible_duplicates": validated["validation"]["possible_duplicates"]},
        "validation": validated["validation"],
        "known_gaps": ["WARN notices carry no visa/H-1B field",
                       "no county FIPS or per-row source URL in the feed",
                       "announced positions, not realized job losses",
                       "feed can be stale; see upstream.generated_at"]}

    dump_json({"schema_version": SCHEMA_VERSION, "notices": notices}, DATA / "notices.json")
    dump_json(series, DATA / "series.json")
    dump_json({"schema_version": SCHEMA_VERSION, **forecasts}, DATA / "forecasts.json")
    dump_json({"schema_version": SCHEMA_VERSION, **{k: v for k, v in gdelt.items()}},
              DATA / "news.json")
    p = dump_json(meta, DATA / "meta.json")
    size_mb = round((DATA / "notices.json").stat().st_size / 1e6, 1)
    print(f"build: {len(notices)} notices ({size_mb} MB), upstream stale_days={stale_days}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
