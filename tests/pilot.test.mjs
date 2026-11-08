import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {median, robustZ, flagCrossed, readingFor, fmtZ, windowMonths, chartRows, monthStats, FLAG} from '../web/pilot.js';

const data = JSON.parse(readFileSync(new URL('../web/ca-pilot.json', import.meta.url)));

test('fixed reference window is exactly Jul 2024 - Jun 2026', () => {
  const w = windowMonths(data);
  assert.equal(w.length, 24);
  assert.equal(w[0], '2024-07');
  assert.equal(w[23], '2026-06');
});

test('recomputed robust z matches shipped precomputed z for every target and measure', () => {
  for (const [m, t] of Object.entries(data.months)) {
    const zr = monthStats(data, m, 'rows').z;
    const ze = monthStats(data, m, 'employees').z;
    assert.ok(Math.abs(zr - t.z_rows) <= 0.005, `${m} rows recomputed ${zr} vs shipped ${t.z_rows}`);
    assert.ok(Math.abs(ze - t.z_emps) <= 0.005, `${m} emps recomputed ${ze} vs shipped ${t.z_emps}`);
  }
});

test('window median and MAD match the artifact metadata', () => {
  const w = windowMonths(data);
  const rows = w.map(m => data.series[m][0]);
  const emps = w.map(m => data.series[m][1]);
  assert.equal(median(rows), data.reference_window.notices_median);
  assert.equal(median(emps), data.reference_window.employees_median);
  const madR = median(rows.map(v => Math.abs(v - median(rows))));
  const madE = median(emps.map(v => Math.abs(v - median(emps))));
  assert.equal(madR, data.reference_window.notices_mad);
  assert.equal(madE, data.reference_window.employees_mad);
});

test('no pilot month crosses the flag on either measure', () => {
  for (const t of Object.values(data.months)) {
    assert.ok(!flagCrossed(t.z_rows), `rows z ${t.z_rows}`);
    assert.ok(!flagCrossed(t.z_emps), `emps z ${t.z_emps}`);
  }
});

test('October view carries the verified figures', () => {
  const s = monthStats(data, '2026-10', 'employees');
  assert.equal(s.rows, 101);
  assert.equal(s.distinctFilings, 89);
  assert.equal(s.employees, 9809);
  assert.equal(s.seasonalMedian, 143);
  assert.equal(s.concentration[0].company, 'AEG Management Oakland LLC');
  assert.equal(s.concentration[0].employees, 1605);
  assert.equal(s.concentration[1].company, "Dreyer's Grand Ice Cream");
  assert.equal(s.concentration[1].employees, 1543);
});

test('months block agrees with the series block', () => {
  for (const [m, t] of Object.entries(data.months)) {
    assert.equal(data.series[m][0], t.rows);
    assert.equal(data.series[m][1], t.employees);
  }
});

test('chart rows exclude the partial month and tag the window', () => {
  const rows = chartRows(data, 'rows', '2026-10');
  assert.ok(!rows.some(r => r.month === data.partial.month));
  assert.equal(rows.filter(r => r.kind === 'window').length, 24);
  assert.equal(rows.filter(r => r.kind === 'target').length, 1);
  assert.equal(rows.find(r => r.kind === 'target').month, '2026-10');
  assert.deepEqual(rows.filter(r => r.kind === 'after').map(r => r.month), ['2026-07', '2026-08', '2026-09']);
});

test('reading scale stays literal: threshold wording, no normal-range claim', () => {
  assert.equal(readingFor(0.38), 'Below the exploratory flag threshold');
  assert.equal(readingFor(1.43), 'Elevated, below the exploratory flag threshold');
  assert.equal(readingFor(-0.4), 'Below the exploratory flag threshold');
  assert.equal(readingFor(-1.6), 'Quiet, below the exploratory flag threshold');
  assert.ok(readingFor(2.5).includes('Crossed the exploratory flag threshold'));
  assert.ok(readingFor(-2.5).includes('Crossed the exploratory flag threshold'));
  for (const z of [0.38, 1.43, -0.4, -1.6, 2.5, -2.5, 0]) {
    assert.ok(!readingFor(z).toLowerCase().includes('normal range'), `no normal-range claim at z=${z}`);
  }
  assert.equal(FLAG, 2);
});

test('robust z zero-MAD handling never silently returns 0', () => {
  assert.equal(robustZ(5, [5, 5, 5]), 0);
  assert.equal(robustZ(7, [5, 5, 5]), Infinity);
  assert.equal(robustZ(3, [5, 5, 5]), -Infinity);
});

test('z formatting matches the published snapshot', () => {
  assert.equal(fmtZ(0.38), '+0.4');
  assert.equal(fmtZ(-0.54), '-0.5');
  assert.equal(fmtZ(1.43), '+1.4');
});

test('unknown month rejected', () => {
  assert.throws(() => monthStats(data, '2026-07', 'rows'));
});
