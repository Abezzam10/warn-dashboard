"""Download the daily WARN Feed snapshot (CC BY 4.0).

Source: https://approjects-warn-act-notices.static.hf.space (api.html states:
no key, no signup, no fee for the static files; mirroring allowed under
CC BY 4.0). We keep the snapshot only for the duration of the run and record
its coverage metadata and content hash in meta.json instead of committing
multi-MB CSV snapshots to git history every day.
"""
import sys, json
from common import DATA, WARN_BASE, fetch, dump_json, sha256, today


def main():
    snap = DATA / "snapshots" / today()
    csv_path = fetch(f"{WARN_BASE}/data/warn_notices.csv", snap / "warn_notices.csv")
    cov_path = fetch(f"{WARN_BASE}/data/coverage.json", snap / "coverage.json")
    cov = json.loads(cov_path.read_text())
    digest = sha256(csv_path)
    dump_json({"snapshot_dir": str(snap), "csv_sha256": digest,
               "coverage_generated_at": cov.get("generated_at"),
               "coverage": cov}, DATA / "intermediate" / "warn_fetch.json")
    print(f"WARN snapshot ok: generated_at={cov.get('generated_at')} "
          f"rows={cov.get('total_rows')} sha256={digest[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
