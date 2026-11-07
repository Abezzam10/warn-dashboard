"""BLS public API v2, keyless (keyless limited-access route).
If BLS_API_KEY is configured as an Actions secret it is used, but the pipeline
never requires it. Failure or absence marks the series unavailable - the site
shows that state explicitly instead of synthetic data.
"""
import os, sys, json, urllib.request, datetime
from common import DATA, dump_json, UA

# (series id, label). Unemployment rate + total nonfarm payroll employment.
SERIES = [("LNS14000000", "Unemployment rate (U-3), %"),
          ("CES0000000001", "Total nonfarm payroll employment, thousands")]


def main():
    end = datetime.date.today().year
    body = {"seriesid": [s for s, _ in SERIES], "startyear": str(end - (9 if os.environ.get("BLS_API_KEY") else 2)),
            "endyear": str(end), "catalog": False, "calculations": False,
            "annualaverage": False, "aspects": False}
    key = os.environ.get("BLS_API_KEY")
    if key:
        body["registrationkey"] = key
    req = urllib.request.Request(
        "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        data=json.dumps(body).encode(), headers={**UA, "Content-Type": "application/json"})
    out = {"status": "unavailable", "reason": None, "series": []}
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode())
        if resp.get("status") != "REQUEST_SUCCEEDED":
            out["reason"] = "; ".join(resp.get("message", [])) or resp.get("status")
        else:
            labels = dict(SERIES)
            for s in resp["Results"]["series"]:
                pts = [{"month": f"{d['year']}-{d['period'][1:]}",
                        "value": float(d["value"])}
                       for d in s["data"] if d["period"].startswith("M") and d["period"] != "M13" and d["value"] not in ("-", "", ".")]
                pts.sort(key=lambda p: p["month"])
                out["series"].append({"id": s["seriesID"], "label": labels[s["seriesID"]],
                                      "points": pts})
            out["status"] = "ok"
    except Exception as e:  # noqa: BLE001 - pipeline must degrade, not crash
        out["reason"] = f"{type(e).__name__}: {e}"
    out["retrieved_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out["note"] = ("Latest BLS revisions as retrieved, not vintage data. "
                   "Keyless public API; values may be revised by BLS later.")
    dump_json(out, DATA / "intermediate" / "bls.json")
    print(f"BLS: {out['status']} {out.get('reason') or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
