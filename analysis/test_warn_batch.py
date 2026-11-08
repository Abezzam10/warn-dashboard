"""Executable tests for the CA WARN Aug-Oct 2026 batch. Run: python3 test_warn_batch.py
Exits nonzero on the first failure. Data paths match warn_batch.py."""
import math, sys, json, collections
import warn_batch as w

FAILURES = []
def check(name, cond, detail=''):
    if cond: print(f'PASS {name}')
    else:
        print(f'FAIL {name} {detail}'); FAILURES.append(name)

edd = w.load_edd_xlsx('/tmp/ca_warn.xlsx')
off = []
unp = []
for fy in ('2324', '2425', '2526'):
    p, u = w.parse_official_pdf_text(f'/tmp/warn_fy{fy}.txt')
    off += p; unp += u
off_m = w.monthly(off)
edd_m = w.monthly(edd)
series = {m: list(off_m[m]) for m in off_m if '2023-07' <= m <= '2026-06'}
for m in edd_m:
    if m >= '2026-06':
        b = series.get(m, [0, 0]); series[m] = [b[0] + edd_m[m][0], b[1] + edd_m[m][1]]

# T-PARSE: official PDFs fully parsed (no dropped data lines)
check('T-PARSE no unparsed date-lines in official PDFs', len(unp) == 0, f'{len(unp)} left: {unp[:2]}')

# T-ROWS: XLSX shape
g = w.filings_of(edd)
check('T-ROWS 458 EDD rows', len(edd) == 458, f'got {len(edd)}')
check('T-ROWS 420 distinct filings', len(g) == 420, f'got {len(g)}')

# T-DEDUP: employee totals are row sums; every multi-county filing must show distinct site addresses
multi = {k: v for k, v in g.items() if len(v) > 1}
check('T-DEDUP 23 multi-county filings', len(multi) == 23, f'got {len(multi)}')
# Policy: employee totals are plain row sums. The single known same-site repeat
# (John Muir Health 2540 East Street: identical rows except 15 vs 3 employees) could be
# two batches or an amendment; we count it as reported (18) and label the 3-position
# uncertainty. Any NEW same-address repeat fails this guard and forces review.
same_addr = [(k, v) for k, v in multi.items() if len(set(w.norm(r['address']) for r in v)) < len(v)]
check('T-DEDUP only the known John Muir same-site pair reuses an address (false-merge guard)',
      len(same_addr) == 1 and 'johnmuir' in same_addr[0][0][0] and sorted(r['employees'] for r in same_addr[0][1]) == [3, 15],
      f'{[(v[0]["company"], [(r["county"], r["employees"], r["address"]) for r in v]) for k, v in same_addr][:3]}')
known = [v for k, v in multi.items() if len(set(r['employees'] for r in v)) == 1]
check('T-DEDUP identical-count groups all have distinct addresses (Dreyer/Kaiser evidence)',
      all(len(set(w.norm(r['address']) for r in v)) == len(v) for v in known) and len(known) == 2,
      f'found {len(known)} identical-count groups')

# T-DATES: validity
bad_dates = [r for r in edd if not r['notice'] or not r['effective']]
nve = [r for r in edd if r['notice'] and r['effective'] and r['notice'] > r['effective']]
check('T-DATES every row has notice and effective dates', len(bad_dates) == 0, f'{len(bad_dates)} missing')
check('T-DATES notice>effective count is the known 10 amended rows', len(nve) == 10, f'got {len(nve)}')
neg = [r for r in edd if not isinstance(r['employees'], (int, float)) or r['employees'] < 0]
check('T-DATES no negative/non-numeric employee cells', len(neg) == 0)

# T-LAG: notice->effective lag
lag = w.lag_stats(edd)
check('T-LAG median lag 61 days', lag['median'] == 61, f"got {lag}")

# T-MONTHLY: reconciliation of the official series against known anchors
expect = {'2026-07': [84, 4670], '2026-08': [130, 5168], '2026-09': [125, 6763], '2026-10': [101, 9809]}
for m, v in expect.items():
    check(f'T-MONTHLY {m} rows/employees {v}', series[m] == v, f'got {series[m]}')
check('T-MONTHLY May 2025 spike is real: 22,372 employees', series['2025-05'][1] == 22372, f"got {series['2025-05']}")
check('T-MONTHLY Jun 2026 includes 4 late-June notices from XLSX: 134 rows', series['2026-06'][0] == 134, f"got {series['2026-06']}")

# T-T1: EDD internal total
tot = sum(r['employees'] for r in edd if isinstance(r['employees'], (int, float)))
check('T-T1 raw employee total 27,163', tot == 27163, f'got {tot}')

# T-ZEROMAD: zero-MAD handling
z0, _, _ = w.robust_z(5, [5, 5, 5])
zi, _, _ = w.robust_z(7, [5, 5, 5])
zn, _, _ = w.robust_z(3, [5, 5, 5])
check('T-ZEROMAD value==median gives z=0', z0 == 0.0)
check('T-ZEROMAD value>median gives z=+inf (flags, never silently 0)', zi == math.inf)
check('T-ZEROMAD value<median gives z=-inf', zn == -math.inf)

# T-BASELINE: official fixed 24-month reference window (Jul2024-Jun2026) and z values
allm = sorted(m for m in series if '2024-07' <= m <= '2026-06')
check('T-BASELINE exactly 24 baseline months Jul2024-Jun2026', len(allm) == 24 and allm[0] == '2024-07' and allm[-1] == '2026-06')
exp_z = {'2026-08': (0.38, -0.54), '2026-09': (0.24, 0.14), '2026-10': (-0.40, 1.43)}
for t, (zr, ze) in exp_z.items():
    z_r, med, mad = w.robust_z(series[t][0], [series[m][0] for m in allm if m < t][-24:])
    z_e, mede, made = w.robust_z(series[t][1], [series[m][1] for m in allm if m < t][-24:])
    check(f'T-BASELINE {t} z_rows={zr} z_emps={ze}', round(z_r, 2) == zr and round(z_e, 2) == ze,
          f'got {z_r:.2f}/{z_e:.2f} baselines rows {med}/{mad} emps {mede}/{made}')
    check(f'T-BASELINE {t} no flag crossed', abs(z_r) <= 2 and abs(z_e) <= 2)

# T-DISTINCT: distinct-filing counts per target month (context figures only)
fm = collections.Counter()
for (comp, notice, eff) in g:
    if notice: fm[notice[:7]] += 1
check('T-DISTINCT Aug/Sep/Oct filings 122/115/89',
      (fm['2026-08'], fm['2026-09'], fm['2026-10']) == (122, 115, 89),
      f"got {(fm['2026-08'], fm['2026-09'], fm['2026-10'])}")
check('T-DISTINCT filings never exceed rows per month',
      all(fm[m] <= series[m][0] for m in ('2026-08', '2026-09', '2026-10')))

# T-OCTTOP: October concentration figures (plain row sums per company)
oct_by = collections.defaultdict(int)
for r in edd:
    if r['notice'] and r['notice'][:7] == '2026-10' and isinstance(r['employees'], (int, float)):
        oct_by[r['company']] += r['employees']
top = sorted(oct_by.items(), key=lambda kv: -kv[1])
check('T-OCTTOP AEG 1605 then Dreyer 1543',
      top[0] == ('AEG Management Oakland LLC', 1605) and top[1] == ("Dreyer's Grand Ice Cream", 1543),
      f'got {top[:2]}')
share = (top[0][1] + top[1][1]) / series['2026-10'][1]
check('T-OCTTOP top-2 share about 32% (30-35% guard)', 0.30 < share < 0.35, f'got {share:.3f}')

# T-T2: overlap reconciliation EDD vs feed snapshot (feed only a cross-check)
d = json.load(open('/tmp/warn-dashboard/data/notices.json'))
feed_rows = d['notices'] if isinstance(d, dict) else d
feed_ca = [r for r in feed_rows if r.get('state') == 'CA' and r.get('notice_date')]
feed_m = w.monthly(feed_ca, get_date=lambda r: r['notice_date'],
                   get_emps=lambda r: r['workers_announced'] if (not r.get('workers_missing') and isinstance(r.get('workers_announced'), (int, float))) else None)
for m, tol in (('2026-07', 5), ('2026-08', 30)):
    diff = abs(series[m][0] - feed_m[m][0])
    check(f'T-T2 {m} EDD vs feed rows within {tol}', diff <= tol, f"EDD {series[m][0]} feed {feed_m[m][0]}")
check('T-T2 2026-09 feed rows < EDD rows (feed 25 Sep cutoff misses late filings)',
      feed_m['2026-09'][0] < series['2026-09'][0], f"feed {feed_m['2026-09'][0]} EDD {series['2026-09'][0]}")

# T-T4: cross-engine count
ca25 = sum(1 for r in feed_ca if r['notice_date'].startswith('2025'))
check('T-T4 feed CA 2025 rows = 1,486 (matches dashboard engine)', ca25 == 1486, f'got {ca25}')

print()
if FAILURES:
    print(f'{len(FAILURES)} FAILURES: {FAILURES}'); sys.exit(1)
print('ALL TESTS PASSED')
