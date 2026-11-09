// Layoff outlook (research prototype): multi-horizon forecasts of JOLTS
// layoffs & discharges. All numbers come from data/econ_forecast.json,
// precomputed by ingest/econ_forecast.py. Nothing is estimated in the browser.
// Copy is written for a non-technical reader; the technical detail stays in
// expandable blocks, never deleted.
const $e = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => Number(n).toLocaleString();
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const mlabel = m => `${MONTHS[Number(m.slice(5)) - 1]} ${m.slice(0, 4)}`;
const mil = v => `${(v / 1000).toFixed(2)} million`;
const MODEL_LABEL = {
  huber: 'Linear regression with Huber loss (outlier-robust) - machine learning',
  huber_targetonly: 'Huber linear model on lagged layoffs only - ML ablation, no economic inputs',
  ridge: 'Regularized linear regression (Ridge) - machine learning',
  residual_ridge: 'Ridge on deviation from 12-month mean - machine learning',
  gbt: 'Gradient-boosted trees - machine learning',
  seasonal_naive: 'Same month last year - simple baseline, not ML',
  persistence: 'Latest published value - simple baseline, not ML',
  ma12: '12-month moving average - simple baseline, not ML'};
// Short names for plain sentences.
const MODEL_SHORT = {
  huber: 'a machine-learning model', huber_targetonly: 'a machine-learning model using only past layoffs',
  ridge: 'a machine-learning model', residual_ridge: 'a machine-learning model', gbt: 'a machine-learning model',
  seasonal_naive: 'the same month last year', persistence: 'the latest published value', ma12: 'a 12-month average'};
let EF = null, H = 1;
const genDate = () => new Date(EF.generated_at).toLocaleDateString('en-US',
  {timeZone: 'America/New_York', year: 'numeric', month: 'short', day: 'numeric'}) + ' ET';

function chip(text, warn) {
  return `<span class="tag"${warn ? ' style="border-color:#b0822f;color:#b0822f"' : ''}>${esc(text)}</span>`;
}

function forecastChart(hz) {
  const rows = hz.backtest.filter(r => r.preds[hz.published_model] != null);
  const series = rows.map(r => ({m: r.target, a: r.actual, p: r.preds[hz.published_model]}));
  const live = hz.live;
  const all = series.flatMap(p => [p.a, p.p]);
  if (live) all.push(live.upper_80 ?? live.point, live.lower_80 ?? live.point);
  const lo = Math.min(...all) * 0.9, hi = Math.max(...all) * 1.08;
  const X = i => 40 + i * (900 / Math.max(1, series.length - 1 + 2));
  const Y = v => 190 - (v - lo) / (hi - lo) * 170;
  const line = k => series.map((p, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(p[k]).toFixed(1)}`).join('');
  const li = series.length + 1;
  const liveSvg = live ? `
    <line x1="${X(li)}" x2="${X(li)}" y1="${Y(live.lower_80)}" y2="${Y(live.upper_80)}" stroke="#b0822f" stroke-width="2"/>
    <circle cx="${X(li)}" cy="${Y(live.point)}" r="4.5" fill="#b0822f"><title>${esc(mlabel(live.target_month))} forecast: ${fmt(live.point)}k; range ${fmt(live.lower_80)}k-${fmt(live.upper_80)}k</title></circle>` : '';
  return `<svg viewBox="0 0 1000 220" role="img" aria-label="What the model would have predicted versus what was actually reported, plus the current forecast and its uncertainty range.">
    <path d="${line('a')}" fill="none" stroke="#789562" stroke-width="2"/>
    <path d="${line('p')}" fill="none" stroke="#4a6fa5" stroke-width="2" stroke-dasharray="5 3"/>
    ${liveSvg}
    <text x="40" y="16" font-size="12" fill="#789562">actually reported (BLS JOLTS)</text>
    <text x="250" y="16" font-size="12" fill="#4a6fa5">what the model would have predicted</text>
    ${live ? `<text x="620" y="16" font-size="12" fill="#b0822f">forecast + uncertainty range</text>` : ''}
    <text x="40" y="212" font-size="11">${esc(mlabel(series[0].m))}</text>
    <text x="880" y="212" font-size="11">${live ? esc(mlabel(live.target_month)) : esc(mlabel(series.at(-1).m))}</text>
  </svg>`;
}

function metricsTable(hz) {
  const eras = [['sel_2024', '2024 (used to choose)'], ['sel_2025', '2025 (used to choose)'], ['test_2026', '2026 (unseen final test)']];
  const models = Object.keys(MODEL_LABEL).filter(m => eras.some(([e]) => hz.metrics[e]?.models?.[m]));
  const best = e => Math.min(...models.map(m => hz.metrics[e]?.models?.[m]?.mae ?? Infinity));
  return `<div class="tablewrap"><table><thead><tr><th>Model</th>${eras.map(([, l]) => `<th>${l}</th>`).join('')}</tr></thead><tbody>
    ${models.map(m => `<tr>${m === hz.published_model ? '<td><strong>' + esc(MODEL_LABEL[m]) + ' (shown above)</strong></td>' : '<td>' + esc(MODEL_LABEL[m]) + '</td>'}
      ${eras.map(([e]) => {const d = hz.metrics[e]?.models?.[m]; const b = d && d.mae === best(e);
        return `<td>${d ? (b ? '<strong>' : '') + fmt(d.mae) + 'k' + (b ? '</strong>' : '') + ` <span class="muted">n=${d.n}</span>` : '-'}</td>`;}).join('')}</tr>`).join('')}
  </tbody></table></div>
  <p class="muted">MAE = average miss, in thousands of layoffs/discharges per month (the series runs about 1.5-1.9M, so
  64k is roughly a 3-4% miss). Lower is better; bold is the era's best. Models were chosen on 2024-2025 only;
  2026 was never used for any choice. A pre-2024 diagnostic era overlaps training data and stays in the raw data file.</p>`;
}

function alertTable(hz) {
  const years = Object.keys(hz.alerts.by_year).sort();
  if (!years.length) return '';
  return `<details><summary>Experimental: historical "elevated month" flag counts (not a risk indicator)</summary>
  <div class="tablewrap"><table><thead><tr><th>Year</th><th>Correct flags</th><th>False alarms</th><th>Missed</th><th>Quiet correct</th><th>Precision</th><th>Recall</th></tr></thead><tbody>
    ${years.map(y => {const a = hz.alerts.by_year[y];
      return `<tr><td>${y}</td><td>${a.tp}</td><td>${a.fp}</td><td>${a.fn}</td><td>${a.tn}</td><td>${a.precision ?? '-'}</td><td>${a.recall ?? '-'}</td></tr>`;}).join('')}
  </tbody></table></div>
  <p class="muted">Historical backtest bookkeeping only. "Elevated" meant above the trailing 60-month 80th percentile -
  an exploratory definition, not tuned to any required false-alarm rate. No zero-false-alarm guarantee is possible.
  Counts are tiny; one month either way flips these rates. The current forecast carries no alert flag.</p></details>`;
}

function verdictChips(hz) {
  const isML = hz.published_model_kind === 'machine_learning';
  const hd = hz.holdout_2026;
  const tstModels = hz.metrics.test_2026?.models || {};
  const best26 = Object.entries(tstModels).sort((a, b) => a[1].mae - b[1].mae)[0];
  const pub26 = tstModels[hz.published_model]?.mae;
  const out = [];
  if (isML && hd.held_up) {
    out.push(chip('Beat the simple guesses in 2024-25 testing AND stayed ahead on the unseen 2026 test - the strongest result on this page, but still based on only 9 test months'));
  } else if (isML) {
    out.push(chip('Won the 2024-25 testing but LOST to a simple guess on the unseen 2026 test - treat this forecast as unreliable', true));
  } else {
    out.push(chip('Machine-learning models were tested here and lost - this forecast is a simple baseline instead', true));
    if (best26 && pub26 != null && best26[0] !== hz.published_model) {
      out.push(chip(`Looking back, ${esc(MODEL_SHORT[best26[0]] || best26[0])} did better in 2026 (${fmt(best26[1].mae)}k vs ${fmt(pub26)}k average miss) - but re-picking after seeing the test would be cheating, so it stays unused`, true));
    } else {
      out.push(chip('This baseline was also the best performer on the 2026 test'));
    }
  }
  const tst = hz.interval.test_2026_coverage;
  const sel = hz.interval.selection_coverage;
  const held = tst && tst.coverage_80 != null ? Math.round(tst.coverage_80 * tst.n) : null;
  if (tst && tst.coverage_80 != null && tst.coverage_80 < 0.6) {
    out.push(chip(`In the 2026 test the real number landed inside the uncertainty range only ${held} of ${tst.n} months - the range is too narrow, so distrust it`, true));
  } else if (tst) {
    out.push(chip(`In the 2026 test the real number landed inside the uncertainty range ${held} of ${tst.n} months (in the 2024-25 period it was tuned on: ${sel?.coverage_80 ?? '-'})`));
  }
  return out.join(' ');
}

function render() {
  const hz = EF.horizons[String(H)];
  const isML = hz.published_model_kind === 'machine_learning';
  const l = hz.live;
  $e('econfc-body').innerHTML = `
    <div class="pilot-controls">${[1,2,3,4,5,6].map(h =>
      `<button class="secondary" data-h="${h}" ${h === H ? 'aria-pressed="true" style="font-weight:700"' : ''}>${h} mo ahead</button>`).join('')}</div>
    <div class="stats">
      ${l ? `<div class="stat"><strong>${mil(l.point)}</strong><span>expected layoffs and discharges in ${esc(mlabel(l.target_month))}, nationwide</span></div>
      <div class="stat"><strong>${mil(l.lower_80)} - ${mil(l.upper_80)}</strong><span>uncertainty range - read the trust notes below before using it</span></div>` : ''}
      <div class="stat"><strong>${isML ? 'ML model' : 'Simple baseline'}</strong><span>${esc(MODEL_SHORT[hz.published_model] || hz.published_model)} makes this forecast</span></div>
    </div>
    <p>${verdictChips(hz)}</p>
    ${l ? `<p class="muted">Issued ${genDate()} from the latest government data (issue month ${esc(mlabel(EF.issue_month))};
      the most recent actually-reported layoffs month is ${esc(mlabel(EF.target.latest_observed_month))}).
      This is a research prototype, not a validated forecast.</p>` : ''}
    <div class="panel">${forecastChart(hz)}<p class="muted">The dashed line over 2024-2025 is the testing the model choice was based on - retrospective, not independent proof. Only the 2026 part was a truly unseen test.</p></div>
    <details><summary>Test scores for every model, including the losers</summary>${metricsTable(hz)}</details>
    ${alertTable(hz)}`;
  document.querySelectorAll('[data-h]').forEach(b => b.onclick = () => {H = Number(b.dataset.h); render();});
}

(async () => {
  try {
    EF = await fetch('data/econ_forecast.json').then(r => {if (!r.ok) throw Error(`HTTP ${r.status}`); return r.json();});
    $e('econfc-freshness').textContent =
      `RESEARCH PROTOTYPE - testing used revised historical data with assumed publication delays, ` +
      `so real-world accuracy will likely be worse than the tests suggest. Generated ${genDate()}.`;
    const gaps = EF.source_gaps || {};
    const gapNote = Object.keys(gaps).length
      ? ` Some input months were missing and were filled by carrying the last known value forward (never backward): ` +
        Object.entries(gaps).map(([k, v]) => `${k} ${v.join(', ')}${EF.gap_notes?.[k]?.[v[0]] ? ' - ' + EF.gap_notes[k][v[0]] : ''}`).join('; ') + '.' : '';
    $e('econfc-methods').innerHTML = `
      <h3>How this forecast works, in plain terms</h3>
      <p>It predicts the national monthly count of <strong>layoffs and discharges</strong> from the BLS JOLTS survey
      (in thousands; that count includes firings and other discharges, not only layoffs for economic weakness - and it
      is a different measure from the WARN notice archive below). For each horizon, one model looks at what was known
      at the time: earlier layoffs, job openings and hires, the unemployment rate, payrolls, weekly hours worked, and
      weekly unemployment claims.</p>
      <p>To keep it honest, models were chosen using only 2024-2025 and then graded on 2026, which played no part in
      any choice. A machine-learning model is used for a horizon only if it beat simple guesses (last month's value,
      the same month last year, a 12-month average) in 2024-2025; where it didn't, the simple guess is the forecast and
      the failed model's scores stay visible. Where a chosen model later lost on 2026, that is labeled above - models
      are not re-picked after seeing the test. Automated checks rerun on every update to confirm no future information
      leaks into a past prediction, and the whole update aborts if they fail.</p>
      <h3>Why you should still not fully trust it</h3>
      <p>Training used today's revised history with assumed publication delays, not the exact figures known on each
      past date - so these tests flatter real-world skill. Only about two dozen choosing months and nine 2026 test
      months exist per horizon, so the scores themselves are noisy. Adding the economic inputs has not been proven to
      beat using past layoffs alone - that comparison is shown in the score table, and with this little data it is
      inconclusive. Nothing here says the economy <em>caused</em> any layoff, and no accuracy level is promised beyond
      the tests shown.${esc(gapNote)}</p>
      <p class="muted">Sources: ${EF.sources.map(s =>
        `<a href="${esc(s.series_page)}">${esc(s.id)}</a> (${esc(s.agency)}, through ${esc(s.latest.slice(0, 7))})`).join(' · ')}.
        Code and data: <a href="https://github.com/Abezzam10/warn-dashboard">this repository</a>.</p>`;
    render();
  } catch (e) {
    $e('econfc-freshness').textContent = `Economic forecast data could not load: ${e.message}. No numbers are substituted.`;
  }
})();
