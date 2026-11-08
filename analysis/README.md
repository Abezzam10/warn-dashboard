# analysis/ - California WARN small-batch pilot (Aug-Oct 2026)

Reproducible change-detection pilot on official California EDD WARN data only.

- `warn_batch.py` - builds the monthly series from EDD's current XLSX and prior-year PDF
  archives, computes robust-z change detection vs a fixed 24-month reference window
  (Jul 2024 - Jun 2026, the same window for all three target months), writes
  `results_final.json`.
- `export_pilot.py` - maps the verified `results_final.json` to `../web/ca-pilot.json`,
  the static artifact the dashboard's pilot section renders. Recomputes nothing.
- `test_warn_batch.py` - 35 executable assertions (parse completeness, dedup false-merge
  guard, dates, monthly reconciliation, zero-MAD handling, baseline values, feed overlap,
  cross-engine count, distinct-filing counts, October concentration). Run:
  `python3 test_warn_batch.py` (exits nonzero on failure).
- `SOURCES.md` - exact source URLs, retrieval dates, units policy, method, findings.
- `results_final.json` - series, baselines, z-scores, seasonal norms, lag stats.

Data inputs (not committed): the EDD XLSX, `pdftotext -layout` output of the three EDD
archive PDFs, and this repo's `data/notices.json` for the feed cross-checks. Paths are
documented in SOURCES.md.
