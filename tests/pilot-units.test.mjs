import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {monthStats} from '../web/pilot.js';

const data = JSON.parse(readFileSync(new URL('../web/ca-pilot.json', import.meta.url)));

// Regression guards: the main sentence must use verified distinct filings,
// never the county-level row count, and announced positions stay announcements.
test('shipped CA values: rows are site/county entries, distinct_filings are notices', () => {
  const expect = {'2026-08': [130, 122, 5168], '2026-09': [125, 115, 6763], '2026-10': [101, 89, 9809]};
  for (const [m, [rows, distinct, emps]] of Object.entries(expect)) {
    const s = monthStats(data, m, 'rows');
    assert.equal(s.rows, rows, `${m} rows`);
    assert.equal(s.distinctFilings, distinct, `${m} distinct filings`);
    assert.equal(s.employees, emps, `${m} employees`);
  }
});

test('pilot.js main sentence counts distinct filings, labeled as notices', () => {
  const src = readFileSync(new URL('../web/pilot.js', import.meta.url), 'utf8');
  assert.match(src, /fmt\(s\.distinctFilings\)\}<\/strong> WARN notices/);
  assert.doesNotMatch(src, /fmt\(s\.rows\)\}<\/strong> WARN notices/);
  assert.match(src, /not confirmed job losses/);
});
