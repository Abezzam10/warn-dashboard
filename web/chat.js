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

const STATES={alabama:'AL',alaska:'AK',arizona:'AZ',arkansas:'AR',california:'CA',colorado:'CO',connecticut:'CT',delaware:'DE','district of columbia':'DC',florida:'FL',georgia:'GA',hawaii:'HI',idaho:'ID',illinois:'IL',indiana:'IN',iowa:'IA',kansas:'KS',kentucky:'KY',louisiana:'LA',maine:'ME',maryland:'MD',massachusetts:'MA',michigan:'MI',minnesota:'MN',mississippi:'MS',missouri:'MO',montana:'MT',nebraska:'NE',nevada:'NV','new hampshire':'NH','new jersey':'NJ','new mexico':'NM','new york':'NY','north carolina':'NC','north dakota':'ND',ohio:'OH',oklahoma:'OK',oregon:'OR',pennsylvania:'PA','rhode island':'RI','south carolina':'SC','south dakota':'SD',tennessee:'TN',texas:'TX',utah:'UT',vermont:'VT',virginia:'VA',washington:'WA','west virginia':'WV',wisconsin:'WI',wyoming:'WY'};
const STATE_CODES=new Set(Object.values(STATES));
const AMBIGUOUS_CODES=new Set(['IN','ME','OH','HI','OK','AS']);
const MONTH_RE='january|february|march|april|may|june|july|august|september|october|november|december';
const MONTH_NUM={january:1,february:2,march:3,april:4,may:5,june:6,july:7,august:8,september:9,october:10,november:11,december:12};
const EMPLOYER_STOP=new Set('how many much what which when where who whom show list give tell find get all the a an in on of for by at from to since before after during between and or not notices notice layoffs layoff closures closure worker workers position positions employee employees job jobs company companies employer employers total number count top most largest biggest highest monthly month months year years trend over time data dashboard warn act signal are were was is did do does have has had any there their its new us usa ai unknown issued filed announce announced affecting affected'.split(' '));
const blank=(s,re)=>s.replace(re,m=>' '.repeat(m.length));
// Deterministic keyword parser for typed questions. NOT a model: fixed rules
// map recognizable phrasing onto the same validated query spec, or abstain.
export function parseQuestion(raw){
  const q=String(raw||'').slice(0,1000).trim();
  if(!q) return {reason:'empty'};
  if(/\b(last|this|next)\s+(year|month|quarter|week)\b|\brecent(ly)?\b|\blatest\b|\btoday\b|\bcurrently\b/i.test(q)) return {reason:'relative'};
  const lower=q.toLowerCase();
  let masked=q,state;
  for(const name of Object.keys(STATES).sort((a,b)=>b.length-a.length)){
    const re=new RegExp('\\b'+name.replace(/ /g,'\\s+')+'\\b','i');
    if(re.test(masked)){state=STATES[name];masked=blank(masked,re);break;}
  }
  if(!state)for(const m of q.match(/\b[A-Z]{2}\b/g)||[]){if(STATE_CODES.has(m)&&!AMBIGUOUS_CODES.has(m)){state=m;break;}}
  let time_range={};
  const my=[...masked.matchAll(new RegExp('\\b('+MONTH_RE+')\\s+(\\d{4})\\b','gi'))];
  if(my.length){
    const first=my[0],last=my[my.length-1],y1=+first[2],m1=MONTH_NUM[first[1].toLowerCase()],y2=+last[2],m2=MONTH_NUM[last[1].toLowerCase()],pad=n=>String(n).padStart(2,'0');
    time_range={start:`${y1}-${pad(m1)}-01`,end:`${y2}-${pad(m2)}-${new Date(y2,m2,0).getDate()}`};
    masked=blank(masked,new RegExp('\\b('+MONTH_RE+')\\s+\\d{4}\\b','gi'));
  }else{
    const years=[...masked.matchAll(/\b(19\d{2}|20\d{2})\b/g)].map(m=>+m[1]);
    if(/\bsince\s+(19\d{2}|20\d{2})\b/i.test(lower)) time_range={start:Math.min(...years)+'-01-01'};
    else if(/\b(?:before|until|through)\s+(19\d{2}|20\d{2})\b/i.test(lower)) time_range={end:(Math.min(...years)-(/\bbefore\s/i.test(lower)?1:0))+'-12-31'};
    else if(years.length>1) time_range={start:Math.min(...years)+'-01-01',end:Math.max(...years)+'-12-31'};
    else if(years.length===1) time_range={start:years[0]+'-01-01',end:years[0]+'-12-31'};
  }
  const countIntent=/\b(how many|how much|number of|count|total|announced)\b/i.test(lower);
  const wantsWorkers=countIntent&&/\b(workers|positions|people|employees|jobs)\b/i.test(lower);
  let metric='notice_count',group_by,metricKey=countIntent;
  if(/\b(forecast|predict|projection|future)\b/i.test(lower)){metric='forecast';metricKey=true;}
  else if(/\b(top|most|largest|biggest|highest|rank(?:ed|ing)?)\b/i.test(lower)||/\bwhich (employers|companies)\b/i.test(lower)){metric='top_employers';group_by='employer';metricKey=true;}
  else if(/\bhistory\b/i.test(lower)){metric='employer_history';metricKey=true;}
  else if(wantsWorkers) metric='workers_announced_sum';
  let groupKey=false;
  if(!group_by){
    if(/\b(?:by|per|each)\s+state\b|\bstate.by.state\b/i.test(lower)){group_by='state';groupKey=true;}
    else if(/\bnotice\s+type|\bby\s+type\b/i.test(lower)){group_by='notice_type';groupKey=true;}
    else if(/\bmonthly|by\s+month|per\s+month|each\s+month|over\s+time|trend/i.test(lower)){group_by='month';groupKey=true;}
  }
  let employer;
  const quoted=q.match(/"([^"]{1,60})"|'([^']{1,60})'/);
  if(quoted) employer=(quoted[1]||quoted[2]).trim();
  if(!employer){
    const m=masked.match(/\b(?:at|by|from)\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,2})/);
    if(m) employer=m[1];
  }
  if(!employer)for(const m of masked.matchAll(/[A-Z][a-z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,2}/g)){
    const cand=m[0].trim();
    if(cand.length>1&&!EMPLOYER_STOP.has(cand.toLowerCase())&&!STATES[cand.toLowerCase()]&&!MONTH_NUM[cand.toLowerCase()]){employer=cand;break;}
  }
  if(employer){employer=employer.replace(/[.,;:!?]+$/,'').trim();if(employer.length<2||EMPLOYER_STOP.has(employer.toLowerCase()))employer=undefined;}
  if(metric==='employer_history'&&!employer) return {reason:'employer'};
  if(!(state||employer||time_range.start||time_range.end||metricKey||groupKey)) return {reason:'unknown'};
  const filters={};
  if(state)filters.state=state;
  if(employer)filters.employer=employer;
  return {spec:validateSpec({metric,filters,...(group_by?{group_by}:{}) ,time_range})};
}
