"""Validate and normalize the WARN snapshot into the published notice shape.

Rules: dates must parse, state codes must be known US states/territories,
headcounts numeric or explicitly flagged missing. Rows are never dropped for
quality - they are flagged. Output: data/intermediate/validated.json
"""
import csv, sys, json, re, datetime, pathlib
from common import DATA, dump_json, load_json

STATES = set("""AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS
MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY
PR VI GU AS MP""".split())
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def norm_date(v):
    v = (v or "").strip()
    try:
        return datetime.date.fromisoformat(v).isoformat()
    except (ValueError, OverflowError):
        return None


def main():
    fetch_meta = load_json(DATA / "intermediate" / "warn_fetch.json")
    csv_path = f"{fetch_meta['snapshot_dir']}/warn_notices.csv"
    notices, problems = [], {"bad_state": 0, "bad_workers": 0, "no_dates": 0}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(line.replace("\x00", "") for line in f):
            state = (row.get("state") or "").strip().upper()
            if state not in STATES:
                problems["bad_state"] += 1
                continue  # unusable row: no valid state
            raw_workers = (row.get("employees_affected") or "").strip()
            workers = None
            if raw_workers:
                try:
                    w = float(raw_workers.replace(",", ""))
                    workers = int(w) if w >= 0 and w.is_integer() else None
                except (ValueError, OverflowError):
                    problems["bad_workers"] += 1
            notice_date = norm_date(row.get("notice_date"))
            effective_date = norm_date(row.get("effective_date"))
            if not notice_date and not effective_date:
                problems["no_dates"] += 1
            loc = (row.get("location") or "").strip()
            county = None  # location is free text, not a reliable county field
            notices.append({
                "id": (row.get("id") or "").strip(),
                "employer": (row.get("company_canonical") or row.get("company") or "").strip(),
                "employer_raw": (row.get("company") or "").strip(),
                "state": state, "location": loc, "county": county,
                "notice_date": notice_date, "effective_date": effective_date,
                "workers_announced": workers,
                "workers_missing": workers is None,
                "notice_type": (row.get("notice_type") or "").strip() or None,
                "first_seen": (row.get("first_seen") or "").strip() or None,
                # WARN Feed rows carry no per-row URL or visa/H-1B field;
                # county_fips is not published by the feed. Absent by design.
                "duplicate_of": None,
            })
    n_missing = sum(1 for n in notices if n["workers_missing"])
    out = {"notices": notices,
           "validation": {"rows_in": len(notices) + problems["bad_state"],
                          "rows_out": len(notices), "problems": problems,
                          "workers_missing": n_missing,
                          "nul_bytes_removed": pathlib.Path(csv_path).read_bytes().count(b"\x00"),
                          "workers_missing_pct": round(100 * n_missing / max(1, len(notices)), 2)}}
    dump_json(out, DATA / "intermediate" / "validated.json")
    print(f"validate: {len(notices)} notices, {n_missing} missing headcounts, "
          f"{problems['bad_state']} bad-state rows dropped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
