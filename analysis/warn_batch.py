"""California WARN small-batch change detection, Aug-Oct 2026.

Change detection uses a FIXED 24-month reference window (Jul 2024-Jun 2026) -
the same window for all three target months, not a rolling per-month trailing
window. The |z| > 2 flag is an exploratory heuristic cutoff chosen for
resistance to one-off heavy months; no calibrated false-alarm rate is claimed.

Data policy (verified, not assumed):
- All monthly series are county-level rows from official California EDD reports only:
  the current WARN XLSX (processed 07/01/26-11/04/26) and EDD's published prior-year
  PDF archives (FY 2023-24 .. FY 2025-26). The public feed is used only as a
  cross-check (overlap reconciliation, cross-engine count, staleness finding).
- Employee totals are plain row sums: EDD files one row per site/county. For the 23
  filings with rows in multiple counties we verified every group has distinct site
  addresses, so equal headcounts (two Dreyer's plants at 221 each; three Kaiser sites
  at 1 each) are distinct sites, not repeated totals. Collapsing them was tried and
  rejected on that evidence.
- "Distinct filings" (company + notice date + effective date) are reported alongside
  rows for context only; employee figures never use filing-level dedup.
"""
import json, math, re, statistics, collections, datetime, openpyxl

PDF_ROW = re.compile(r'^\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(.*?)\s+([A-Za-z\. ]+County)\s+(\d[\d,]*)\s+(Layoff|Closure)')

def norm(s): return re.sub(r'[^a-z0-9]', '', str(s).lower())

def load_edd_xlsx(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb['Detailed WARN Report ']
    rows, hdr = [], None
    for row in ws.iter_rows(values_only=True):
        if hdr is None:
            if row and row[0] == 'County/Parish': hdr = row
            continue
        if not row or not row[0]: continue
        county, notice, proc, eff, company, typ, emps, addr, ind = row[:9]
        rows.append(dict(county=county,
                         notice=notice.date().isoformat() if notice else None,
                         processed=proc.date().isoformat() if proc else None,
                         effective=eff.date().isoformat() if eff else None,
                         company=str(company).strip(), type=typ, employees=emps,
                         address=str(addr).strip(), industry=ind))
    return rows

def parse_official_pdf_text(path):
    """Rows from pdftotext -layout of an EDD prior-year WARN PDF."""
    out, unparsed = [], []
    for line in open(path, errors='replace'):
        m = PDF_ROW.match(line)
        if m:
            nd, rd, ed, company, county, emps, typ = m.groups()
            mm, dd, yy = nd.split('/')
            out.append(dict(notice=f'{yy}-{mm}-{dd}', company=company.strip(),
                            county=county.strip(), employees=int(emps.replace(',', ''))))
        elif re.match(r'^\s*\d{2}/', line):
            unparsed.append(line.rstrip())
    return out, unparsed

def filings_of(rows):
    g = collections.defaultdict(list)
    for r in rows:
        g[(norm(r['company']), r['notice'], r['effective'])].append(r)
    return g

def monthly(rows, get_date=lambda r: r['notice'], get_emps=lambda r: r['employees']):
    m = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        d = get_date(r)
        if not d: continue
        k = d[:7]
        m[k][0] += 1
        e = get_emps(r)
        if isinstance(e, (int, float)): m[k][1] += e
    return m

def median_mad(vals):
    med = statistics.median(vals)
    mad = statistics.median([abs(v - med) for v in vals])
    return med, mad

def robust_z(value, vals):
    """Robust z vs median/MAD of vals. MAD=0: 0 when value==median, signed inf otherwise."""
    med, mad = median_mad(vals)
    if mad == 0:
        if value == med: return 0.0, med, mad
        return math.copysign(math.inf, value - med), med, mad
    return (value - med) / (1.4826 * mad), med, mad

def lag_stats(rows):
    lags = [(datetime.date.fromisoformat(r['effective']) - datetime.date.fromisoformat(r['notice'])).days
            for r in rows if r['notice'] and r['effective']]
    lags.sort()
    return dict(n=len(lags), median=statistics.median(lags),
                p25=lags[len(lags)//4], p75=lags[3*len(lags)//4])

if __name__ == '__main__':
    edd = load_edd_xlsx('/tmp/ca_warn.xlsx')
    off_rows = []
    for fy in ('2324', '2425', '2526'):
        parsed, unparsed = parse_official_pdf_text(f'/tmp/warn_fy{fy}.txt')
        print(f'FY{fy} PDF: {len(parsed)} rows parsed, {len(unparsed)} unparsed')
        off_rows += parsed
    off_m = monthly(off_rows)
    edd_m = monthly(edd)
    series = {m: list(off_m[m]) for m in off_m if '2023-07' <= m <= '2026-06'}
    # XLSX covers processed Jul 2026+; PDFs cover processed through Jun 2026.
    # Notice months are disjoint by processed date, so XLSX months >= 2026-06
    # complete the series (late-June notices processed in early July appear only in the XLSX).
    for m in edd_m:
        if m >= '2026-06':
            base = series.get(m, [0, 0])
            series[m] = [base[0] + edd_m[m][0], base[1] + edd_m[m][1]]
    g = filings_of(edd)
    multi = {k: v for k, v in g.items() if len(v) > 1}
    print(f'EDD XLSX: {len(edd)} rows = {len(g)} distinct filings; multi-county {len(multi)}')
    allm = sorted(m for m in series if '2024-07' <= m <= '2026-06')
    res = {'series': {m: series[m] for m in sorted(series)}, 'targets': {}}
    for t in ('2026-08', '2026-09', '2026-10'):
        z_r, med, mad = robust_z(series[t][0], [series[m][0] for m in allm if m < t][-24:])
        z_e, mede, made = robust_z(series[t][1], [series[m][1] for m in allm if m < t][-24:])
        same = [series[f'{y}-{t[5:]}'][0] for y in (2023, 2024, 2025)]
        res['targets'][t] = dict(rows=series[t][0], employees=series[t][1],
                                 z_rows=round(z_r, 2), z_emps=round(z_e, 2),
                                 base_rows=[med, mad], base_emps=[mede, made],
                                 seasonal=same, seasonal_median=statistics.median(same))
        print(t, series[t], f'z_rows={z_r:.2f} z_emps={z_e:.2f} seasonal={same}')
    res['lag'] = lag_stats(edd)
    print('lag:', res['lag'])
    json.dump(res, open('/tmp/ca_analysis/results_final.json', 'w'), indent=1)
    print('wrote /tmp/ca_analysis/results_final.json')
