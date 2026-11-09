// Layoff outlook (research prototype): multi-horizon forecasts of JOLTS
// layoffs & discharges. All numbers come from data/econ_forecast.json,
// precomputed by ingest/econ_forecast.py. Nothing is estimated in the browser.
const $e = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => Number(n).toLocaleString();
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const mlabel = m => `${MONTHS[Number(m.slice(5)) - 1]} ${m.slice(0, 4)}`;
const MODEL_LABEL = {
  huber: 'Linear regression with Huber loss (outlier-robust) - machine learning',
  huber_targetonly: 'Huber linear model on lagged layoffs only - ML ablation, no economic inputs',
  ridge: 'Regularized linear regression (Ridge) - machine learning',
  residual_ridge: 'Ridge on deviation from 12-month mean - machine learning',
  gbt: 'Gradient-boosted trees - machine learning',
  seasonal_naive: 'Same month last year - simple baseline, not ML',
  persistence: 'Latest published value - simple baseline, not ML',
  ma12: '12-month moving average - simple baseline, not ML'};
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
    <circle cx="${X(li)}" cy="${Y(live.point)}" r="4.5" fill="#b0822f"><title>${esc(live.target_month)} forecast: ${fmt(live.point)}k; band ${fmt(live.lower_80)}k-${fmt(live.upper_80)}k</title></circle>` : '';
  return `<svg viewBox="0 0 1000 220" role="img" aria-label="Backtested predictions versus reported layoffs and discharges, with the current forecast and its residual band.">
    <path d="${line('a')}" fill="none" stroke="#789562" stroke-width="2"/>
    <path d="${line('p')}" fill="none" stroke="#4a6fa5" stroke-width="2" stroke-dasharray="5 3"/>
    ${liveSvg}
    <text x="40" y="16" font-size="12" fill="#789562">reported (BLS JOLTS)</text>
    <text x="230" y="16" font-size="12" fill="#4a6fa5">backtest prediction (${esc(hz.published_model)})</text>
    ${live ? `<text x="560" y="16" font-size="12" fill="#b0822f">current forecast + residual band</text>` : ''}
    <text x="40" y="212" font-size="11">${esc(mlabel(series[0].m))}</text>
    <text x="880" y="212" font-size="11">${live ? esc(mlabel(live.target_month)) : esc(mlabel(series.at(-1).m))}</text>
  </svg>`;
}

function metricsTable(hz) {
  const eras = [['sel_2024', '2024 (selection)'], ['sel_2025', '2025 (selection)'], ['test_2026', '2026 (untouched test)']];
  const models = Object.keys(MODEL_LABEL).filter(m => eras.some(([e]) => hz.metrics[e]?.models?.[m]));
  const best = e => Math.min(...models.map(m => hz.metrics[e]?.models?.[m]?.mae ?? Infinity));
  return `<div class="tablewrap"><table><thead><tr><th>Model</th>${eras.map(([, l]) => `<th>${l} MAE</th>`).join('')}</tr></thead><tbody>
    ${models.map(m => `<tr>${m === hz.published_model ? '<td><strong>' + esc(MODEL_LABEL[m]) + ' (published)</strong></td>' : '<td>' + esc(MODEL_LABEL[m]) + '</td>'}
      ${eras.map(([e]) => {const d = hz.metrics[e]?.models?.[m]; const b = d && d.mae === best(e);
        return `<td>${d ? (b ? '<strong>' : '') + fmt(d.mae) + 'k' + (b ? '</strong>' : '') + ` <span class="muted">n=${d.n}</span>` : '-'}</td>`;}).join('')}</tr>`).join('')}
  </tbody></table></div>
  <p class="muted">MAE in thousands of layoffs/discharges per month (the series runs about 1.5-1.9M). Lower is better;
  bold is the era's best. Model choice and band calibration used 2024-2025 only; 2026 was never used for any choice.
  A pre-2024 diagnostic era overlaps training data and lives only in the raw artifact, not here.</p>`;
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

function coverageChip(hz) {
  const sel = hz.interval.selection_coverage, tst = hz.interval.test_2026_coverage;
  const bad = tst && tst.coverage_80 != null && tst.coverage_80 < 0.6;
  return chip(`band contained actuals: ${sel?.coverage_80 ?? '-'} of 2024-25 (in-calibration, optimistic) · ${tst?.coverage_80 ?? '-'} of ${tst?.n ?? 0} in 2026 (held out)`, bad)
    + (bad ? chip('band ran too narrow on the 2026 test - treat as optimistic', true) : '');
}

function render() {
  const hz = EF.horizons[String(H)];
  const isML = hz.published_model_kind === 'machine_learning';
  const hd = hz.holdout_2026;
  const l = hz.live;
  const tstModels = hz.metrics.test_2026?.models || {};
  const best26 = Object.entries(tstModels).sort((a, b) => a[1].mae - b[1].mae)[0];
  const pub26 = tstModels[hz.published_model]?.mae;
  const statusChip = isML
    ? (hd.held_up ? chip('ML won 2024-25 selection and stayed ahead on the untouched 2026 test')
                  : chip('ML won 2024-25 selection but LOST to a simple baseline on the untouched 2026 test', true))
    : chip('ML did not beat simple baselines on 2024-25 here - the baseline is published instead', true)
    + (best26 && pub26 != null && best26[0] !== hz.published_model
      ? chip(`retrospectively, ${best26[0]} was better on the 2026 test (${fmt(best26[1].mae)}k vs ${fmt(pub26)}k) - not used for selection`, true)
      : chip('published model was also the best on the 2026 test'));
  $e('econfc-body').innerHTML = `
    <div class="pilot-controls">${[1,2,3,4,5,6].map(h =>
      `<button class="secondary" data-h="${h}" ${h === H ? 'aria-pressed="true" style="font-weight:700"' : ''}>${h} mo ahead</button>`).join('')}</div>
    <div class="stats">
      ${l ? `<div class="stat"><strong>${fmt(l.point)}k</strong><span>forecast for ${esc(mlabel(l.target_month))}</span></div>
      <div class="stat"><strong>${fmt(l.lower_80)}k - ${fmt(l.upper_80)}k</strong><span>residual band (calibrated on 2024-25, nominal 80%)</span></div>` : ''}
      <div class="stat"><strong>${isML ? 'ML' : 'Baseline'}</strong><span>${esc(MODEL_LABEL[hz.published_model])}</span></div>
    </div>
    <p>${statusChip} ${coverageChip(hz)}</p>
    ${l ? `<p class="muted">Issued from the latest-revised values the lag rule expects published as of ${genDate()}
      (issue month ${esc(mlabel(EF.issue_month))}; latest reported layoffs month: ${esc(mlabel(EF.target.latest_observed_month))}).
      Trained on ${fmt(l.n_train)} monthly examples through issue ${esc(l.trained_through_issue)}.
      This is a retrospective approximation of real-time skill, not a prospectively validated forecast.</p>` : ''}
    <div class="panel">${forecastChart(hz)}<p class="muted">The prediction line is the model selected on 2024-2025; its 2024-2025 segment is the evidence selection was based on - retrospective, not independent proof. Only the 2026 segment was untouched by every choice.</p></div>
    <h3>Backtest scores, all candidate models</h3>${metricsTable(hz)}
    ${alertTable(hz)}`;
  document.querySelectorAll('[data-h]').forEach(b => b.onclick = () => {H = Number(b.dataset.h); render();});
}

(async () => {
  try {
    EF = await fetch('data/econ_forecast.json').then(r => {if (!r.ok) throw Error(`HTTP ${r.status}`); return r.json();});
    $e('econfc-freshness').textContent =
      `RESEARCH PROTOTYPE · pseudo-real-time backtest on latest-revised data with publication-lag simulation - ` +
      `not as-of vintages, not prospectively validated; real-time skill is usually lower. Generated ${genDate()}.`;
    const gaps = EF.source_gaps || {};
    const gapNote = Object.keys(gaps).length
      ? ` Source gaps handled by past-only carry-forward with a missingness flag (never the target, never reaching forward): ` +
        Object.entries(gaps).map(([k, v]) => `${k} ${v.join(', ')}${EF.gap_notes?.[k]?.[v[0]] ? ' - ' + EF.gap_notes[k][v[0]] : ''}`).join('; ') + '.' : '';
    $e('econfc-methods').innerHTML = `
      <h3>How this forecast works</h3>
      <p>One model per horizon (1-6 months ahead) predicts the national JOLTS <strong>layoffs and discharges</strong> level
      (${esc(EF.target.units)}). That measure includes firings and other discharges - not only layoffs for economic
      weakness - and it is not a WARN notice count and not a count of people. ${esc(EF.issue_semantics)}</p>
      <p>Clues expected available at each issue date under the lag rule: earlier layoffs, job openings and hires (JOLTS,
      published about six weeks late), unemployment rate, payrolls and weekly hours (published the following month), and
      DOL weekly initial claims (seasonally adjusted, averaged to months). Training rows are restricted to targets already
      published at each test origin; lookup lineage and future-perturbation tests run on every pipeline execution and
      abort the publish on any future-influence leak.</p>
      <p>Evaluation is chronological and prequential: each backtest prediction comes from a model refit on everything
      published by that origin (later 2026 predictions may train on earlier 2026 actuals). Model choice and band
      calibration used 2024-2025 only - that is the sense in which 2026 is an untouched test. The ablation row
      (Huber on lagged layoffs only) is an exploratory comparison on identical folds: with this few origins, the
      incremental value of the economic inputs carries wide uncertainty, and no causal importance is attributed to
      any input. A learned model is published
      only where it beat the strongest simple baseline (same month last year, latest published value, or 12-month average)
      on 2024-2025. Where it did not, the baseline is published as the forecast and the ML scores stay visible as failed
      candidates - a baseline is never dressed up as ML. Where a selected ML model later lost on the 2026 test, that is
      labeled above; models are not re-picked on 2026.</p>
      <h3>Limits to read before using a number</h3>
      <p>Latest-revised series, not as-of vintages: BLS revises these figures, so the backtest approximates - and usually
      flatters - real-time performance. Publication lags are fixed approximations of the release calendar, not a per-release
      audit; weekly claims are not seasonally adjusted. Only about 24 selection and 9 final-test months exist per horizon,
      so per-year scores carry wide sampling error. Nothing here says the economy <em>caused</em> a layoff, and no accuracy
      level is promised beyond the measured backtests shown above.${esc(gapNote)}</p>
      <p class="muted">Sources: ${EF.sources.map(s =>
        `<a href="${esc(s.series_page)}">${esc(s.id)}</a> (${esc(s.agency)}, through ${esc(s.latest.slice(0, 7))})`).join(' · ')}.
        Snapshots and code: <a href="https://github.com/Abezzam10/warn-dashboard">this repository</a>.</p>`;
    render();
  } catch (e) {
    $e('econfc-freshness').textContent = `Economic forecast data could not load: ${e.message}. No numbers are substituted.`;
  }
})();
