import {compute,unsupported,parseQuestion} from './chat.js';
const $=id=>document.getElementById(id), fmt=n=>Number(n).toLocaleString(), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let notices=[],meta,filtered=[],page=0;
const size=25;
function text(id,s){$(id).textContent=s;}
function date(n){return n.notice_date||n.effective_date||'';}
function params(){return {search:$('search').value.trim(),state:$('state').value,start:$('start').value,end:$('end').value};}
function apply(p=params()){
 for(const k of ['search','state','start','end']) $(k).value=p[k]||'';
 filtered=notices.filter(n=>(!p.search||(n.employer+' '+n.location).toLowerCase().includes(p.search.toLowerCase()))&&(!p.state||n.state===p.state)&&(!p.start||date(n)>=p.start)&&(!p.end||(date(n)&&date(n)<=p.end)));
 filtered.sort((a,b)=>date(b).localeCompare(date(a)));page=0;
 const workers=filtered.reduce((a,n)=>a+(n.workers_announced||0),0),missing=filtered.filter(n=>n.workers_missing).length,dups=filtered.filter(n=>n.duplicate_of).length;
 $('stats').innerHTML=[[fmt(filtered.length),'Notices'],[fmt(workers),'Announced positions (where headcount is known)'],[fmt(missing),'Notices missing a headcount'],[fmt(dups),'Possible duplicates (still counted)']].map(([n,l])=>`<div class="stat"><strong>${n}</strong><span>${l}</span></div>`).join('');
 renderRows(); chart(filtered); const url=new URL(location);url.search='';for(const [k,v] of Object.entries(p))if(v)url.searchParams.set(k,v);history.replaceState(null,'',url);
}
function renderRows(){
 const slice=filtered.slice(page*size,(page+1)*size);
 $('rows').innerHTML=slice.map(n=>`<tr><td><strong>${esc(n.employer)}</strong><small>${esc(n.location)}</small></td><td>${esc(n.state)}</td><td>${esc(n.notice_date||'Not recorded')}</td><td>${esc(n.effective_date||'Not recorded')}</td><td>${n.workers_missing?'Unknown':fmt(n.workers_announced)}</td><td>${n.workers_missing?'<span class="tag">Missing headcount</span>':''}${n.duplicate_of?`<span class="tag">Possible duplicate</span>`:''}</td></tr>`).join('')||'<tr><td colspan="6">No notices match these filters.</td></tr>';
 text('pageinfo',`${fmt(filtered.length? page*size+1:0)}-${fmt(Math.min((page+1)*size,filtered.length))} of ${fmt(filtered.length)}`);$('prev').disabled=page===0;$('next').disabled=(page+1)*size>=filtered.length;
}
function chart(rows){
 const m=new Map();for(const n of rows){if(date(n)){const k=date(n).slice(0,7);m.set(k,(m.get(k)||0)+1);}}
 const entries=[...m].sort((a,b)=>a[0].localeCompare(b[0])).slice(-36);const max=Math.max(1,...entries.map(e=>e[1]));
 $('chart').innerHTML=entries.length?`<svg viewBox="0 0 1000 180" role="img" aria-label="Monthly notices, last 36 months with data. Counts available by filtering and export.">${entries.map(([m,v],i)=>`<rect x="${i*960/entries.length+20}" y="${145-v/max*120}" width="${Math.max(1,960/entries.length-3)}" height="${v/max*120}" fill="#789562"><title>${esc(m)}: ${v} notices</title></rect>`).join('')}<text x="20" y="172">${esc(entries[0][0])}</text><text x="890" y="172">${esc(entries.at(-1)[0])}</text><text x="20" y="14">${fmt(max)} peak monthly notices</text></svg>`:'<p>No dated rows in this view.</p>';
}
function saved(){try{return JSON.parse(localStorage.getItem('warn-views')||'[]').filter(v=>v&&typeof v.name==='string'&&typeof v.params==='object').slice(0,25);}catch{return [];}}
function savedMenu(){ $('saved').innerHTML='<option value="">Saved views</option>'+saved().map((v,i)=>`<option value="${i}">${esc(v.name)}</option>`).join(''); }
function download(data,name,type){const a=document.createElement('a'),url=URL.createObjectURL(new Blob([data],{type}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);text('actionstatus',`Exported ${filtered.length} rows.`);}
function exportCSV(){const keys=['id','employer','state','location','notice_date','effective_date','workers_announced','workers_missing','duplicate_of'];const cell=v=>'"'+String(v??'').replace(/^[=+@-]/,"'$&").replaceAll('"','""')+'"';download([keys.join(','),...filtered.map(n=>keys.map(k=>cell(n[k])).join(','))].join('\r\n'),'warn-view.csv','text/csv');}
const MONTHNAME=['January','February','March','April','May','June','July','August','September','October','November','December'];
function dayLabel(d){const[y,m,dd]=d.split('-').map(Number);return `${MONTHNAME[m-1].slice(0,3)} ${dd}, ${y}`;}
// Plain-English rendering of the validated query spec, replacing the raw JSON.
function specPlain(spec){
 const what={notice_count:'notices',workers_announced_sum:'announced positions',top_employers:'notices per employer',monthly_series:'notices per month',employer_history:'notices over time',forecast:'a forecast'}[spec.metric]||spec.metric;
 const bits=[];const f=spec.filters||{};
 if(f.employer)bits.push(`employer name containing "${f.employer}"`);
 if(f.state)bits.push(`state ${f.state}`);
 if(f.notice_type)bits.push(`notice type "${f.notice_type}"`);
 const t=spec.time_range||{};
 if(t.start&&t.end)bits.push(`dated ${dayLabel(t.start)} to ${dayLabel(t.end)}`);
 else if(t.start)bits.push(`dated ${dayLabel(t.start)} or later`);
 else if(t.end)bits.push(`dated up to ${dayLabel(t.end)}`);
 let s=`Counted ${what}${bits.length?' where '+bits.join(', '):''}`;
 if(spec.group_by&&spec.metric!=='top_employers')s+=`, grouped by ${spec.group_by}`;
 return s+'.';
}
function analyze(spec,origin){try{
 const originText=origin==='parser'?'Fixed rules matched your typed words to this count - no AI. Check "what was counted" before relying on it.':'A preset question with fixed filters. Check "what was counted" before relying on it.';
 const r=compute(notices,spec);
 if(r.spec.metric==='forecast'){text('analysis','The archive cannot forecast: its source stopped updating and old snapshots were not kept. The forecast experiment lives in the first section above.');return;}
 const val=r.spec.metric==='workers_announced_sum'?fmt(r.workers):fmt(r.count),label=r.spec.metric==='workers_announced_sum'?'Known announced positions':'Notices';
 const grouped=r.groups.slice(r.spec.metric==='top_employers'?0:-12,r.spec.metric==='top_employers'?10:undefined);
 $('analysis').innerHTML=`<div class="big">${val}</div><h3>${label}</h3><p>${fmt(r.missing)} of these notices are missing a headcount. ${fmt(r.duplicates)} possible duplicate rows are still counted. These are announcements, not realized job losses.</p><p class="query"><strong>What was counted:</strong> ${esc(specPlain(r.spec))}</p><h3>${r.spec.metric==='top_employers'?'Top employers':'Breakdown'}</h3><ul>${grouped.map(([k,v])=>`<li>${esc(k)}: ${fmt(v)}</li>`).join('')}</ul><h3>Source rows</h3><p>${r.rows.slice(0,5).map(n=>`${esc(n.employer)} · ${esc(n.state)} · ${esc(date(n)||'undated')}`).join('<br>')||'No matching rows.'}</p><button id="showanalysisrows" class="secondary">See these rows in the archive</button><p>${originText} Source: <a href="${esc(meta.upstream.url)}">WARN Feed, CC BY 4.0</a>, snapshot of ${esc(meta.upstream.generated_at.slice(0,10))}.</p>`;
 $('showanalysisrows').onclick=()=>{filtered=r.rows.slice().sort((a,b)=>date(b).localeCompare(date(a)));page=0;renderRows();chart(filtered);$('stats').innerHTML=`<div class="stat"><strong>${fmt(r.count)}</strong><span>Answer source rows</span></div>`;$('explore').scrollIntoView();};
 }catch(e){text('analysis',`That question could not be answered: ${e.message}. Try the filters or a suggested question.`);}}
function abstain(reason){
 const why=reason==='relative'?'This archive is a fixed snapshot, so words like "last year" or "recent" are ambiguous - name explicit years (for example 2024 or 2025).':reason==='employer'?'Which employer? Name the company, for example "history of Amazon".':'I found no state, employer, explicit year or measure I recognize in that question.';
 $('analysis').innerHTML=`<p class="eyebrow">NOT ANSWERED</p><h3>I can't answer that reliably</h3><p>${esc(why)}</p><p>I can count notices and announced positions by state, employer, month or notice type with explicit years - for example "Amazon notices in Texas in 2025", "top employers in California", "monthly notices in 2024". Things the data does not record (industry, visa status, reasons) stay unknown.</p>`;
}
function unknown(){text('analysis',"Unknown. WARN notices record no visa or H-1B status, no reliable industry, and no reason for the layoff - so that count cannot be made from this data. Visa petition records are separate data and would not count laid-off visa holders either.");}
$('filters').onsubmit=e=>{e.preventDefault();if($('start').value&&$('end').value&&$('start').value>$('end').value){text('actionstatus','Start must precede end.');return;}apply();};$('reset').onclick=()=>apply({});$('prev').onclick=()=>{page--;renderRows();};$('next').onclick=()=>{page++;renderRows();};$('csv').onclick=exportCSV;$('json').onclick=()=>download(JSON.stringify({filters:params(),source:meta.upstream,notices:filtered},null,2),'warn-view.json','application/json');
$('save').onclick=()=>{try{const v=saved();v.push({name:`${params().state||'All states'} / ${params().search||'all employers'} / ${new Date().toLocaleDateString()}`,params:params()});localStorage.setItem('warn-views',JSON.stringify(v.slice(-25)));savedMenu();text('actionstatus','Saved on this device only.');}catch{text('actionstatus','Local storage unavailable. Use export instead.');}};
$('saved').onchange=()=>{const v=saved()[Number($('saved').value)];if($('saved').value!==''&&v)apply(v.params);};$('share').onclick=async()=>{try{await navigator.clipboard.writeText(location.href);text('actionstatus','Copied link. Your filters will be visible to anyone you send it to.');}catch{text('actionstatus','Copy the current address bar link to share this view.');}};
document.querySelectorAll('[data-preset]').forEach(b=>b.onclick=()=>{if(b.dataset.preset==='visa'){unknown();return;}analyze(b.dataset.preset==='ny'?{metric:'notice_count',filters:{state:'NY'},group_by:'month',time_range:{start:'2025-01-01',end:'2025-12-31'}}:{metric:'top_employers',filters:{},group_by:'employer',time_range:{}});});
$('questionform').onsubmit=e=>{e.preventDefault();const q=$('question').value.trim();if(!q)return;if(unsupported(q)){unknown();return;}const p=parseQuestion(q);if(p.spec){analyze(p.spec,'parser');}else{abstain(p.reason);}};
try {const [n,m]=await Promise.all(['notices','meta'].map(x=>fetch(`data/${x}.json`).then(r=>{if(!r.ok)throw Error(`${x}: HTTP ${r.status}`);return r.json();})));notices=n.notices;meta=m;
 $('state').innerHTML='<option value="">All states</option>'+[...new Set(notices.map(n=>n.state))].sort().map(s=>`<option>${esc(s)}</option>`).join('');
 const age=Math.floor((Date.now()-Date.parse(meta.upstream.generated_at))/86400000);
 text('freshness',age>7?`Heads up: the notice archive below is frozen at ${meta.upstream.generated_at.slice(0,10)} - its source has not published anything new in ${age} days, so recent announcements are missing. The forecast and the California check use fresher official data.`:`Notice archive updated ${meta.upstream.generated_at.slice(0,10)}.`);
 text('snapshot',`${fmt(notices.length)} notices / WARN Feed, CC BY 4.0`);apply(Object.fromEntries(new URLSearchParams(location.search)));savedMenu();
}catch(e){text('freshness',`Published data could not load: ${e.message}. No sample numbers are substituted. See source code and raw data links.`);}
