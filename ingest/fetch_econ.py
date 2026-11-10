"""Download the economic series used by the learned JOLTS forecast.

All series are published by BLS/DOL. The six BLS series are fetched directly
from the BLS Public API v2, keyless (batched 10-year windows, the keyless
per-query span limit); this is the first-party publisher NYT/Bloomberg cite.
ICSA (weekly initial claims) is published by DOL ETA as a seasonally adjusted
national series and mirrored by FRED; it is fetched through FRED's public
keyless CSV export (fredgraph.csv). FRED's export is also the per-series
fallback if a BLS API query fails. No API key is required. Each snapshot is
kept under data/snapshots/econ/ so a run is reproducible; the retrieval time
and latest observed month are published with the forecast.

Series and the publication lag the forecast assumes (months, relative to an
end-of-month issue date):
  JTSLDL   JOLTS layoffs & discharges, total nonfarm, SA, thousands  (lag 2)
  JTSJOL   JOLTS job openings, total nonfarm, SA, thousands          (lag 2)
  JTSHIL   JOLTS hires, total nonfarm, SA, thousands                 (lag 2)
  UNRATE   Unemployment rate U-3, SA, %                              (lag 1)
  PAYEMS   Total nonfarm payroll employment, SA, thousands           (lag 1)
  AWHNONAG Average weekly hours, production & nonsupervisory, SA     (lag 1)
  ICSA     Initial unemployment insurance claims, weekly, SA, count  (lag 1)
Lags are conservative approximations of BLS/DOL release calendars: JOLTS is
published roughly six weeks after its reference month; the Employment
Situation series early the following month; claims weekly. Treating claims at
lag 1 keeps the whole feature set honest at an end-of-month issue date.

The values are the latest vintages as downloaded, not historical as-of
vintages; econ_forecast.py carries that caveat in its output. The BLS API
flags preliminary months (JOLTS/CES publish preliminary values for the newest
month(s)); those are included, matching the previous FRED-mirror behavior,
and recorded in econ_fetch.json as preliminary_months.
"""
import csv, datetime, io, json, os, sys, time, urllib.request
from common import DATA, INTER, UA, dump_json

BLS_API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
FREDGRAPH = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"

SERIES = {
    "JTSLDL": ("JOLTS layoffs and discharges, total nonfarm",
               "thousands of persons, monthly, seasonally adjusted", 2),
    "JTSJOL": ("JOLTS job openings, total nonfarm",
               "thousands, monthly, seasonally adjusted", 2),
    "JTSHIL": ("JOLTS hires, total nonfarm",
               "thousands, monthly, seasonally adjusted", 2),
    "UNRATE": ("Unemployment rate (U-3)",
               "percent, monthly, seasonally adjusted", 1),
    "PAYEMS": ("Total nonfarm payroll employment",
               "thousands of persons, monthly, seasonally adjusted", 1),
    "AWHNONAG": ("Average weekly hours, production and nonsupervisory employees, total private",
                 "hours, monthly, seasonally adjusted", 1),
    "ICSA": ("Initial claims for unemployment insurance",
             "count, weekly, seasonally adjusted", 1),
}

# BLS series IDs for the six series fetched from the BLS API. ICSA stays on
# the FRED keyless export of DOL ETA's seasonally adjusted national series.
BLS_ID = {
    "JTSLDL": "JTS000000000000000LDL",
    "JTSJOL": "JTS000000000000000JOL",
    "JTSHIL": "JTS000000000000000HIL",
    "UNRATE": "LNS14000000",
    "PAYEMS": "CES0000000001",
    "AWHNONAG": "CES0500000007",
}
BLS_PAGE = "https://data.bls.gov/timeseries/{}"
FRED_PAGE = "https://fred.stlouisfed.org/series/{}"

# Keyless BLS API allows a 10-year span per query, 25 series per query and
# 25 queries/day; a registered key (BLS_API_KEY env, optional) raises those to
# 20-year spans and 500 queries/day. Only 2000-onward history is fetched:
# econ_forecast trains from JOLTS start (2000-12) and nothing else reads the
# econ snapshots, so 3 keyless windows (2000-2029 span) cover every required
# input and leave room for same-day reruns within the unregistered quota.
# The FRED fallback still fetches full history when the BLS API is missed.
WINDOW_YEARS_KEYLESS = 10
WINDOW_YEARS_KEYED = 20
EARLIEST_YEAR = 2000


def parse_csv(text):
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        if r["observation_date"] and r[list(r)[1]] not in (".", "", None):
            try:
                rows.append((r["observation_date"], float(list(r.values())[1])))
            except ValueError:
                continue
    return rows


def fetch_bls():
    """Return {sid: {month: (value, preliminary)}} from the BLS API, batched
    by 10-year window. Raises on transport/API failure (caller falls back)."""
    key = os.environ.get("BLS_API_KEY")
    span = WINDOW_YEARS_KEYED if key else WINDOW_YEARS_KEYLESS
    end_year = datetime.date.today().year
    windows = [(y, min(y + span - 1, end_year))
               for y in range(EARLIEST_YEAR, end_year + 1, span)]
    inv = {v: k for k, v in BLS_ID.items()}
    out = {sid: {} for sid in BLS_ID}
    raw_windows = []
    for i, (y0, y1) in enumerate(windows):
        body = {"seriesid": list(BLS_ID.values()), "startyear": str(y0),
                "endyear": str(y1), "catalog": False, "calculations": False,
                "annualaverage": False, "aspects": False}
        if key:
            body["registrationkey"] = key
        req = urllib.request.Request(
            BLS_API, data=json.dumps(body).encode(),
            headers={**UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode())
        if resp.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS API {y0}-{y1}: "
                               + "; ".join(resp.get("message", [])))
        raw_windows.append({"window": [y0, y1], "response": resp})
        for s in resp["Results"]["series"]:
            sid = inv[s["seriesID"]]
            for item in s["data"]:
                if item["period"].startswith("M") and item["period"] != "M13":
                    if item["value"] in ("-", ".", ""):
                        continue
                    prelim = any(fn.get("code") == "P"
                                 for fn in item.get("footnotes", []))
                    out[sid][f"{item['year']}-{item['period'][1:]}"] = (
                        float(item["value"]), prelim)
        if i < len(windows) - 1:
            time.sleep(1)  # polite pacing within the unregistered daily limit
    dump_json({"retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "windows": raw_windows}, INTER / "bls_windows.json")
    return out


def fetch_fred(sid):
    req = urllib.request.Request(FREDGRAPH.format(sid), headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        text = r.read().decode()
    return parse_csv(text), text


def main():
    snap = DATA / "snapshots" / "econ"
    snap.mkdir(parents=True, exist_ok=True)
    retrieved = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out = {"retrieved_at": retrieved,
           "export": ("BLS Public API v2, keyless (batched 10-year windows); "
                      "ICSA via FRED public CSV (fredgraph.csv) of the DOL ETA "
                      "seasonally adjusted series; FRED CSV is the per-series fallback"),
           "series": {}}
    failed = []
    try:
        bls = fetch_bls()
    except Exception as e:  # noqa: BLE001 - fall back to FRED for all BLS series
        print(f"BLS API failed ({type(e).__name__}: {e}); falling back to FRED for all BLS series")
        bls = {sid: {} for sid in BLS_ID}
    for sid, (label, units, lag) in SERIES.items():
        try:
            rows = [(f"{m}-01", v) for m, (v, _p) in sorted(bls.get(sid, {}).items())]
            source = None
            if len(rows) >= 24:
                source = "BLS Public API v2 (keyless)"
                text = "observation_date,{}\n".format(sid) + "".join(
                    f"{d},{v}\n" for d, v in rows)
                out["series"][sid] = {
                    "label": label, "units": units, "lag_months": lag,
                    "source": source, "url": BLS_API,
                    "series_page": BLS_PAGE.format(BLS_ID[sid]),
                    "preliminary_months": sorted(m for m, (_v, p) in bls[sid].items() if p),
                    "first": rows[0][0], "latest": rows[-1][0], "n": len(rows)}
            else:
                rows, text = fetch_fred(sid)
                if len(rows) < 24:
                    raise ValueError(f"only {len(rows)} observations")
                source = ("FRED public CSV (fredgraph.csv)"
                          if sid not in BLS_ID else
                          "FRED public CSV (fredgraph.csv), fallback after BLS API miss")
                out["series"][sid] = {
                    "label": label, "units": units, "lag_months": lag,
                    "source": source, "url": FREDGRAPH.format(sid),
                    "series_page": FRED_PAGE.format(sid),
                    "first": rows[0][0], "latest": rows[-1][0], "n": len(rows)}
            (snap / f"{sid}.csv").write_text(text)
            print(f"{sid} [{source}]: {rows[0][0]} .. {rows[-1][0]} ({len(rows)} obs)")
        except Exception as e:  # noqa: BLE001 - report, then fail the run below
            failed.append(f"{sid}: {type(e).__name__}: {e}")
            print(f"FAILED {sid}: {e}")
    out["failed"] = failed
    dump_json(out, INTER / "econ_fetch.json")
    if failed:
        print("econ fetch incomplete - aborting pipeline before publish")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
