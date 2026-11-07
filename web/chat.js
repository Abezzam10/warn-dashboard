export const METRICS = new Set(['notice_count','workers_announced_sum','top_employers','monthly_series','employer_history','forecast']);
export const FILTERS = new Set(['state','county','employer','notice_type']);
export const GROUP_BY = new Set(['month','state','notice_type','employer']);
export function validateSpec(s) {
  if (!s || Array.isArray(s) || typeof s !== 'object') throw Error('Query must be an object');
  if (Object.keys(s).some(k=>!['metric','filters','group_by','time_range'].includes(k))) throw Error('Unsupported query field');
  if (!METRICS.has(s.metric)) throw Error('Unsupported metric');
  const f=s.filters??{};
  if (!f || Array.isArray(f) || typeof f!=='object') throw Error('Invalid filters');
  for(const [k,v] of Object.entries(f)) if(!FILTERS.has(k)||typeof v!=='string'||v.length>160) throw Error('Unsupported filter');
  if(f.county) throw Error('County is unavailable: locations are unstructured text');
  if(f.state&&!/^[A-Z]{2}$/.test(f.state)) throw Error('Use a two-letter state code');
  if(s.group_by&&!GROUP_BY.has(s.group_by)) throw Error('Unsupported grouping');
  const t=s.time_range??{};
  if(!t||Array.isArray(t)||typeof t!=='object'||Object.keys(t).some(k=>!['start','end'].includes(k))) throw Error('Invalid date range');
  for(const v of Object.values(t)) if(typeof v!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(v)||Number.isNaN(Date.parse(v))) throw Error('Invalid date');
  if(t.start&&t.end&&t.start>t.end) throw Error('Start date must precede end');
  return {metric:s.metric,filters:f,group_by:s.group_by??'month',time_range:t};
}
export function selectRows(rows,s) {
  const q=validateSpec(s);
  return rows.filter(n=>Object.entries(q.filters).every(([k,v])=>k==='employer'?n.employer.toLowerCase().includes(v.toLowerCase()):n[k]===v)&&(!q.time_range.start||(n.notice_date||n.effective_date||'')>=q.time_range.start)&&(!q.time_range.end||(n.notice_date||n.effective_date||'9999')<=q.time_range.end));
}
export function compute(rows,s) {
  const q=validateSpec(s), r=selectRows(rows,q), groups=new Map();
  for(const n of r) {const k=q.metric==='top_employers'?n.employer:q.group_by==='month'?(n.notice_date||n.effective_date||'Undated').slice(0,7):(n[q.group_by]||'Unknown');groups.set(k,(groups.get(k)||0)+(q.metric==='workers_announced_sum'?(n.workers_announced||0):1));}
  return {spec:q,rows:r,count:r.length,workers:r.reduce((a,n)=>a+(n.workers_announced||0),0),missing:r.filter(n=>n.workers_missing).length,duplicates:r.filter(n=>n.duplicate_of).length,groups:[...groups].sort((a,b)=>q.metric==='top_employers'?b[1]-a[1]:a[0].localeCompare(b[0]))};
}
export function unsupported(question) {return /\b(h[- ]?1b|visa|caus(?:e|al)|why|industry|ethnicity|race|gender)\b/i.test(question);}
