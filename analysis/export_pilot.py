"""Export the verified CA small-batch analysis (results_final.json) to the
dashboard's static pilot artifact (web/ca-pilot.json).

Numbers come only from results_final.json - the artifact produced and tested
by warn_batch.py from official California EDD reports. This script adds labels
and the on-page method/units/limits text; it recomputes nothing. A contract
test (tests/test_pilot_contract.py) keeps the two files in sync.

Run from the repository root:  python3 analysis/export_pilot.py
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS = ROOT / 'analysis' / 'results_final.json'
OUT = ROOT / 'web' / 'ca-pilot.json'

TARGETS = {
    '2026-08': 'August 2026',
    '2026-09': 'September 2026',
    '2026-10': 'October 2026',
}

METHOD = ("Each recent month is compared with a fixed 24-month reference window, "
          "July 2024 to June 2026 - the same window for all three months, built only "
          "from official state data. Robust z = (month - median) / (1.4826 x MAD). "
          "An absolute z above 2 on rows or on announced employees flags a month as "
          "unusual: that is an exploratory heuristic cutoff, chosen because it resists "
          "one-off heavy months like May 2025. No calibrated false-alarm rate is claimed. "
          "A seasonal cross-check compares the same month in 2023, 2024 and 2025.")

UNITS = ("Rows are EDD county-level WARN rows, one per site per county. Announced "
         "employees are plain row sums: every filing with rows in several counties was "
         "checked by site address, and 22 of 23 groups are separate sites (equal "
         "headcounts like two Dreyer's plants at 221 each are real, not double counts). "
         "The one same-site pair (John Muir Health, 15 vs 3 positions, identical dates) "
         "is counted as reported - a 3-position uncertainty in August. Distinct filings "
         "(same company, notice date and effective date) are context only.")

LIMITS = ("Descriptive change detection, not a forecast and not a causal claim. WARN "
          "filings do not record why layoffs happen, so this view cannot confirm or rule "
          "out an AI link. Announced positions are plans, not realized job losses, and "
          "are not unique people. California only; other states file under different "
          "thresholds, so this says nothing about the country. October is still "
          "completing: filings processed after 4 Nov are not yet in the EDD file.")

FRESHNESS = ("Official California EDD data through 4 Nov 2026, retrieved 8 Nov 2026. "
             "The public feed's newest snapshot is 25 Sep 2026, about six weeks behind.")


def main():
    res = json.loads(RESULTS.read_text())
    series = {m: v for m, v in res['series'].items() if m >= '2024-07'}
    months = {}
    for key, label in TARGETS.items():
        t = res['targets'][key]
        months[key] = {
            'label': label,
            'rows': t['rows'],
            'distinct_filings': t['distinct_filings'],
            'employees': t['employees'],
            'z_rows': t['z_rows'],
            'z_emps': t['z_emps'],
            'seasonal': t['seasonal'],
            'seasonal_median': t['seasonal_median'],
        }
    months['2026-10']['concentration'] = res['october_top']
    out = {
        'schema_version': 1,
        'title': 'California small-batch pilot, August to October 2026',
        'source': {
            'name': 'California EDD WARN reports (official)',
            'url': 'https://edd.ca.gov/en/jobs_and_Training/Layoff_Services_WARN',
            'retrieved': '2026-11-08',
            'data_through': '2026-11-04',
            'note': ('Current WARN XLSX (processed 1 Jul to 4 Nov 2026) plus EDD '
                     'prior-year PDF archives, FY 2023-24 through FY 2025-26. The '
                     'public feed is used only as a cross-check.'),
        },
        'freshness': FRESHNESS,
        'reference_window': {
            'start': '2024-07',
            'end': '2026-06',
            'notices_median': res['targets']['2026-08']['base_rows'][0],
            'notices_mad': res['targets']['2026-08']['base_rows'][1],
            'employees_median': res['targets']['2026-08']['base_emps'][0],
            'employees_mad': res['targets']['2026-08']['base_emps'][1],
        },
        'series': series,
        'partial': {'month': '2026-11', 'rows': series['2026-11'][0],
                    'employees': series['2026-11'][1]},
        'months': months,
        'lag': res['lag'],
        'method': METHOD,
        'units': UNITS,
        'limits': LIMITS,
    }
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    print(f'wrote {OUT}')


if __name__ == '__main__':
    main()
