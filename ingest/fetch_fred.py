"""Optional FRED/ALFRED series. Requires a free FRED_API_KEY in Actions
secrets; without it the series are marked unavailable and the site says so.
No key is invented and no signup is performed by this pipeline.
"""
import os, sys, datetime
from common import DATA, dump_json, fetch_json

SERIES = [("UNRATE", "Unemployment rate, %"), ("PAYEMS", "Nonfarm payrolls, thousands")]


def main():
    out = {"status": "unavailable", "reason": "no FRED_API_KEY secret configured",
           "series": [], "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "note": "FRED terms vary per series; check each series before reuse."}
    key = os.environ.get("FRED_API_KEY")
    if key:
        try:
            for sid, label in SERIES:
                j = fetch_json("https://api.stlouisfed.org/fred/series/observations"
                               f"?series_id={sid}&api_key={key}&file_type=json"
                               "&sort_order=desc&limit=120")
                pts = [{"month": o["date"][:7], "value": float(o["value"])}
                       for o in j.get("observations", []) if o["value"] != "."]
                pts.sort(key=lambda p: p["month"])
                # realtime_start/end document the vintage window for leakage control
                out["series"].append({"id": sid, "label": label, "points": pts,
                                      "realtime_start": j.get("realtime_start"),
                                      "realtime_end": j.get("realtime_end")})
            out["status"] = "ok" if out["series"] else "unavailable"
            out["reason"] = None if out["series"] else "empty response"
        except Exception as e:  # noqa: BLE001
            out["reason"] = type(e).__name__  # never publish an exception URL containing the key
    dump_json(out, DATA / "intermediate" / "fred.json")
    print(f"FRED: {out['status']} {out.get('reason') or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
