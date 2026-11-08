# California WARN batch, Aug-Oct 2026 - sources, method, tests

Everything retrieved 8 Nov 2026 (America/New_York). All series are built from official
California EDD reports only; the public feed is used solely as a cross-check.

## Official sources (analysis data)
1. Current WARN report (XLSX), notices processed 07/01/26 to 11/04/2026, updated Tue/Thu:
   https://edd.ca.gov/siteassets/files/jobs_and_training/warn/warn_report1.xlsx
   (linked from https://edd.ca.gov/en/jobs_and_Training/Layoff_Services_WARN)
   458 county-level rows = 420 distinct filings (company + notice date + effective date).
2. EDD published prior-year WARN archives (PDF, parsed with pdftotext -layout):
   FY 2023-24: https://edd.ca.gov/siteassets/files/jobs_and_training/warn/warn-report-for-7-1-2023-to-06-30-2024.pdf (1,814 rows; seasonal 2023 months)
   FY 2024-25: https://edd.ca.gov/siteassets/files/jobs_and_training/warn/warn-report-for-7-1-2024-to-06-30-2025.pdf (1,506 rows)
   FY 2025-26: https://edd.ca.gov/siteassets/files/jobs_and_training/warn/warn-report-for-7-1-25-to-6-30-26.pdf (1,593 rows)
   Files are by processed date; the series is by notice date, so the current XLSX also
   contributes 4 late-June 2026 notices (processed in July) to the 2026-06 month.

## Cross-check sources only
3. WARN Feed (APVentureEngine, CC BY 4.0): https://github.com/APVentureEngine/warn-act-notices
   Snapshot data/notices.json built 2026-09-25T00:11:25Z (last push 2026-09-25T00:19:03Z) -
   ~6 weeks stale vs its "updated daily" claim. Clone at /tmp/warn-dashboard in the build
   environment. Used for: overlap reconciliation (T-T2), cross-engine count (T-T4),
   staleness finding.
4. Deployed dashboard engine: https://abezzam10.github.io/warn-dashboard/ (T-T4 reference).

## Reproduce
- python3 warn_batch.py        # rebuilds series, prints findings, writes results_final.json
- python3 test_warn_batch.py   # 31 executable assertions, exits nonzero on failure
Needs: openpyxl; pdftotext output of the three PDFs at /tmp/warn_fy{2324,2425,2526}.txt;
the XLSX at /tmp/ca_warn.xlsx; the feed clone at /tmp/warn-dashboard (T-T2/T-T4 only).

## Units policy (evidence-based)
- Monthly counts and employee totals are county-level ROW sums on every side, so
  baselines and targets are the same unit. EDD files one row per site/county.
- 23 of 420 filings have rows in multiple county rows. In 22 of 23 the rows have
  distinct site addresses, so identical headcounts (Dreyer's Bakersfield 221 vs
  Tulare 221; Kaiser San Rafael/Corona/Folsom 1 each) are distinct sites, NOT repeated
  totals. An earlier draft that collapsed them was wrong and was corrected.
- The 23rd is the ambiguous pair: John Muir Health, 2540 East Street, identical rows
  except 15 vs 3 employees (same site, dates, type, processed date). Counted as
  reported (18); a 3-position uncertainty in August, labeled on the page.
- Distinct-filing counts (130/125/101 rows = 122/115/89 filings for Aug/Sep/Oct) are
  shown for context; no employee figure uses filing-level dedup.

## Method
Baseline: median of a FIXED 24-month reference window (Jul 2024-Jun 2026, official
rows) - the same window for all three target months, not a rolling trailing window.
Robust z = (month - median) / (1.4826 * MAD); flag |z| > 2 - an exploratory heuristic
cutoff chosen for resistance to one-off heavy months; no calibrated false-alarm rate
is claimed or validated. MAD = 0 handled explicitly:
z = 0 when the month equals the median, signed infinity otherwise (never silently 0).
Baselines: notices median 116, MAD 25; employees median 6,445, MAD 1,591.
Seasonal cross-check: same month in 2023/2024/2025.

## Findings (descriptive, not forecasts)
Aug 2026: 130 rows (z +0.38), 5,168 employees (z -0.54); same-month norm 114.
Sep 2026: 125 rows (z +0.24), 6,763 employees (z +0.14); same-month norm 98.
Oct 2026: 101 rows (z -0.40), 9,809 employees (z +1.43); same-month norm 143.
No month crossed the flag. Oct headcount elevated but below it; ~32% of Oct is two
employers (AEG Management Oakland 1,605; Dreyer's Grand Ice Cream 1,543).
Notice-to-effective lag: median 61 days (middle half 59-63, n=458).
May 2025 spike (22,372 employees) is real: one Tend Exchange notice of 16,132.

## Feed staleness (T-T2), EDD rows vs feed rows
Jul 2026: 84 vs 82 (employees 4,670 vs 4,568, ~2%). Aug: 130 vs 102 (5,168 vs 4,856, ~6%).
Sep: 125 vs 84 (6,763 vs 3,840) - the 25 Sep feed snapshot missed late-month filings
and everything after.
