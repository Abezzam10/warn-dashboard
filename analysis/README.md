# analysis/ - California WARN small-batch pilot (Aug-Oct 2026)

Reproducible change-detection pilot on official California EDD WARN data only.

- `warn_batch.py` - builds the monthly series from EDD's current XLSX and prior-year PDF
  archives, computes robust-z change detection vs the trailing 24 official months,
  writes `results_final.json`.
- `test_warn_batch.py` - 31 executable assertions (parse completeness, dedup false-merge
  guard, dates, monthly reconciliation, zero-MAD handling, baseline values, feed overlap,
  cross-engine count). Run: `python3 test_warn_batch.py` (exits nonzero on failure).
- `SOURCES.md` - exact source URLs, retrieval dates, units policy, method, findings.
- `results_final.json` - series, baselines, z-scores, seasonal norms, lag stats.

Data inputs (not committed): the EDD XLSX, `pdftotext -layout` output of the three EDD
archive PDFs, and this repo's `data/notices.json` for the feed cross-checks. Paths are
documented in SOURCES.md.
