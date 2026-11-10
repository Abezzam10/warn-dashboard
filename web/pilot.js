// Small-batch pilot view: renders the verified CA Aug-Oct 2026 analysis
// (ca-pilot.json, exported from analysis/results_final.json). All statistics
// are precomputed from official EDD data; this module only does display
// arithmetic. No AI is involved anywhere in this view.

export const FLAG = 2;

export function median(vals) {
  const s = [...vals].sort((a, b) => a - b);
  const n = s.length;
  if (!n) throw Error('median of empty list');
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

// Same estimator as analysis/warn_batch.py: (value - median) / (1.4826 * MAD).
// MAD 0: 0 when value == median, signed Infinity otherwise (never silently 0).
export function robustZ(value, vals) {
  const med = median(vals);
  const mad = median(vals.map(v => Math.abs(v - med)));
  if (mad === 0) return value === med ? 0 : Math.sign(value - med) * Infinity;
  return (value - med) / (1.4826 * mad);
}

export function flagCrossed(z) {
  return Math.abs(z) > FLAG;
}

export function readingFor(z) {
  // Literal threshold wording only: |z|>2 is an exploratory heuristic cutoff,
  // not a validated normal/unusual boundary, so no "normal range" claim.
  if (flagCrossed(z)) return z > 0 ? 'Crossed the exploratory flag threshold' : 'Crossed the exploratory flag threshold (low side)';
  if (z > 1) return 'Elevated, below the exploratory flag threshold';
  if (z < -1) return 'Quiet, below the exploratory flag threshold';
  return 'Below the exploratory flag threshold';
}

export function fmtZ(z) {
  if (!isFinite(z)) return z > 0 ? '+inf' : '-inf';
  return (z >= 0 ? '+' : '') + z.toFixed(1);
}

// Months of the fixed reference window, inclusive, from the artifact metadata.
export function windowMonths(data) {
  const out = [];
  const [y0, m0] = data.reference_window.start.split('-').map(Number);
  const [y1, m1] = data.reference_window.end.split('-').map(Number);
  for (let y = y0, m = m0; y < y1 || (y === y1 && m <= m1);) {
    out.push(`${y}-${String(m).padStart(2, '0')}`);
    if (++m > 12) { m = 1; y++; }
  }
  return out;
}

// Chart rows: every full month in the series (partial month excluded),
// tagged as reference-window, post-window, or the selected target.
export function chartRows(data, metric, target) {
  const idx = metric === 'employees' ? 1 : 0;
  const win = new Set(windowMonths(data));
  return Object.keys(data.series)
    .filter(m => m !== data.partial.month)
    .sort()
    .map(m => ({ month: m, value: data.series[m][idx],
                 kind: m === target ? 'target' : (win.has(m) ? 'window' : 'after') }));
}

// Stats for one target month + measure, with z recomputed from the shipped
// series and window (must match the shipped precomputed z in the artifact).
export function monthStats(data, monthKey, metric) {
  const t = data.months[monthKey];
  if (!t) throw Error('not a pilot month: ' + monthKey);
  const idx = metric === 'employees' ? 1 : 0;
  const win = windowMonths(data);
  const value = data.series[monthKey][idx];
  const z = robustZ(value, win.map(m => data.series[m][idx]));
  return { value, z, reading: readingFor(z),
           windowMedian: median(win.map(m => data.series[m][idx])),
           rows: t.rows, distinctFilings: t.distinct_filings,
           employees: t.employees, seasonal: t.seasonal,
           seasonalMedian: t.seasonal_median,
           concentration: t.concentration || null };
}

// --- DOM wiring (not exercised by unit tests) ---

const esc = s => String(s ?? '').replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = n => Number(n).toLocaleString('en-US');

function chartSvg(rows, metric, medianValue, targetLabel) {
  const W = 640, H = 190, padB = 22, padT = 12;
  const max = Math.max(...rows.map(r => r.value), medianValue) * 1.08;
  const bw = W / rows.length;
  const y = v => H - padB - (v / max) * (H - padB - padT);
  const fill = { window: '#8a9f76', after: '#cbd4ca', target: '#1b6250' };
  let bars = rows.map((r, i) =>
    `<rect x="${(i * bw + 1).toFixed(1)}" y="${y(r.value).toFixed(1)}" width="${(bw - 2).toFixed(1)}" height="${(H - padB - y(r.value)).toFixed(1)}" fill="${fill[r.kind]}"><title>${r.month}: ${fmt(r.value)}</title></rect>`).join('');
  const my = y(medianValue).toFixed(1);
  const line = `<line x1="0" x2="${W}" y1="${my}" y2="${my}" stroke="#17312f" stroke-dasharray="4 3" stroke-width="1"><title>Reference median ${fmt(medianValue)}</title></line>`;
  const ticks = rows.map((r, i) => (r.month.endsWith('-07') || r.month.endsWith('-01'))
    ? `<text x="${(i * bw + 1).toFixed(1)}" y="${H - 8}">${r.month.slice(2)}</text>` : '').join('');
  const t = rows.find(r => r.kind === 'target');
  const ti = rows.indexOf(t);
  const lab = `<text x="${Math.min(ti * bw + 1, W - 150).toFixed(1)}" y="${Math.max(y(t.value) - 6, 10).toFixed(1)}" style="fill:#17312f;font-weight:700;paint-order:stroke;stroke:#fffefa;stroke-width:4px">${esc(targetLabel)}: ${fmt(t.value)}</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Monthly ${metric} with fixed reference window">${bars}${line}${ticks}${lab}</svg>`;
}

async function init() {
  const root = document.getElementById('pilot-view');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const data = await (await fetch('ca-pilot.json')).json();
  const months = Object.keys(data.months).sort();
  let month = months[months.length - 1], metric = 'rows';

  $('pilot-freshness').textContent = data.freshness;
  $('pilot-method-text').textContent = data.method;
  $('pilot-units-text').textContent = data.units;
  $('pilot-limits-text').textContent = data.limits;
  $('pilot-lag').textContent = `Notice to effective date across the batch: median ${data.lag.median} days (middle half ${data.lag.p25}-${data.lag.p75}, n=${fmt(data.lag.n)} rows).`;
  $('pilot-srclink').innerHTML = `Source: <a href="${esc(data.source.url)}">${esc(data.source.name)}</a>, retrieved ${esc(data.source.retrieved)}. ${esc(data.source.note)} Reproducible: analysis/warn_batch.py in the repository.`;

  function drawControls() {
    $('pilot-months').innerHTML = months.map(m =>
      `<button type="button" data-m="${m}" class="${m === month ? 'active' : ''}">${esc(data.months[m].label)}</button>`).join('');
    $('pilot-metrics').innerHTML = [['rows', 'Notices filed'], ['employees', 'Announced job cuts']]
      .map(([k, l]) => `<button type="button" data-k="${k}" class="${k === metric ? 'active' : ''}">${l}</button>`).join('');
    $('pilot-months').querySelectorAll('button').forEach(b => b.onclick = () => { month = b.dataset.m; draw(); });
    $('pilot-metrics').querySelectorAll('button').forEach(b => b.onclick = () => { metric = b.dataset.k; draw(); });
  }

  function draw() {
    drawControls();
    const t = data.months[month];
    const s = monthStats(data, month, metric);
    $('pilot-month-label').textContent = t.label;
    $('pilot-source').textContent = 'official EDD data';
    const verdict = flagCrossed(s.z)
      ? `Our check <strong>flagged this month as unusual</strong> on this measure compared with the previous two years.`
      : `Our check <strong>did not flag this month as unusual</strong>. This month's count may still change as more notices arrive.`;
    $('pilot-stats').innerHTML = `
      <p class="big-answer">In <strong>${esc(t.label)}</strong>, California employers filed
        <strong>${fmt(s.rows)}</strong> WARN notices announcing about <strong>${fmt(s.employees)}</strong> job cuts.</p>
      <p>${verdict}</p>`;
    const rows = chartRows(data, metric, month);
    $('pilot-chart').innerHTML = chartSvg(rows, metric, s.windowMedian, t.label);
    const notes = [
      `Bars run Jul 2024 to Oct 2026. The dashed line is the typical month (median) of 2024-07 to 2026-06 - the same two-year window for every month shown. A month is flagged only when it sits far from that (z beyond +/-2: an exploratory line, with no guaranteed error rate).`,
      `Same-month comparison: in 2023-25 this month of the year typically saw ${fmt(s.seasonalMedian)} filings (this year: ${fmt(s.rows)}).`,
      `November so far: ${fmt(data.partial.rows)} rows, ${fmt(data.partial.employees)} announced - partial month, not compared.`,
    ];
    if (month === '2026-10') {
      notes.push('October is still completing: filings processed after 4 Nov are not yet in the EDD file.');
    }
    if (s.concentration) {
      const share = Math.round(s.concentration.slice(0, 2).reduce((a, c) => a + c.employees, 0) / s.employees * 100);
      notes.push(`Two employers - ${s.concentration[0].company} (${fmt(s.concentration[0].employees)}) and ${s.concentration[1].company} (${fmt(s.concentration[1].employees)}) - account for about ${share}% of October's announced positions.`);
    }
    $('pilot-note').innerHTML = notes.map(esc).join('<br>');
  }

  draw();
}

if (typeof document !== 'undefined') init();
