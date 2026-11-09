"""Download the economic series used by the learned JOLTS forecast.

All series are published by BLS/DOL and mirrored by FRED. They are fetched
through FRED's public keyless CSV export (fredgraph.csv) because
download.bls.gov flat files refuse automated downloads from some runners.
No API key is required. Each snapshot is kept under data/snapshots/econ/ so a
run is reproducible; the retrieval time and latest observed month are
published with the forecast.

Series and the publication lag the forecast assumes (months, relative to an
end-of-month issue date):
  JTSLDL   JOLTS layoffs & discharges, total nonfarm, SA, thousands  (lag 2)
  JTSJOL   JOLTS job openings, total nonfarm, SA, thousands          (lag 2)
  JTSHIL   JOLTS hires, total nonfarm, SA, thousands                 (lag 2)
  UNRATE   Unemployment rate U-3, SA, %                              (lag 1)
  PAYEMS   Total nonfarm payroll employment, SA, thousands           (lag 1)
  AWHNONAG Average weekly hours, production & nonsupervisory, SA     (lag 1)
  ICSA     Initial unemployment insurance claims, weekly, NSA, count (lag 1)
Lags are conservative approximations of BLS/DOL release calendars: JOLTS is
published roughly six weeks after its reference month; the Employment
Situation series early the following month; claims weekly. Treating claims at
lag 1 keeps the whole feature set honest at an end-of-month issue date.

The values are the latest vintages as downloaded, not historical as-of
vintages; econ_forecast.py carries that caveat in its output.
"""
import csv, datetime, io, sys, urllib.request
from common import DATA, INTER, UA, dump_json

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


def parse_csv(text):
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        if r["observation_date"] and r[list(r)[1]] not in (".", "", None):
            try:
                rows.append((r["observation_date"], float(list(r.values())[1])))
            except ValueError:
                continue
    return rows


def main():
    snap = DATA / "snapshots" / "econ"
    snap.mkdir(parents=True, exist_ok=True)
    retrieved = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out = {"retrieved_at": retrieved, "export": "FRED public CSV (fredgraph.csv), no key",
           "series": {}}
    failed = []
    for sid, (label, units, lag) in SERIES.items():
        url = FREDGRAPH.format(sid)
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                text = r.read().decode("utf-8")
            rows = parse_csv(text)
            if len(rows) < 24:
                raise ValueError(f"only {len(rows)} observations")
            (snap / f"{sid}.csv").write_text(text)
            out["series"][sid] = {
                "label": label, "units": units, "lag_months": lag,
                "url": url, "series_page": f"https://fred.stlouisfed.org/series/{sid}",
                "first": rows[0][0], "latest": rows[-1][0], "n": len(rows)}
            print(f"{sid}: {rows[0][0]} .. {rows[-1][0]} ({len(rows)} obs)")
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
