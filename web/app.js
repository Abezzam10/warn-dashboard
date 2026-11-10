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
function download(data,name,type){const a=document.createElement('a'),url=URL.createObjectURL(new Blob([data],{type}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);text('actionstatus',`Exported ${filtered.length} rows.`);}
function exportCSV(){const keys=['id','employer','state','location','notice_date','effective_date','workers_announced','workers_missing','duplicate_of'];const cell=v=>'"'+String(v??'').replace(/^[=+@-]/,"'$&").replaceAll('"','""')+'"';download([keys.join(','),...filtered.map(n=>keys.map(k=>cell(n[k])).join(','))].join('\r\n'),'warn-view.csv','text/csv');}
$('filters').onsubmit=e=>{e.preventDefault();if($('start').value&&$('end').value&&$('start').value>$('end').value){text('actionstatus','Start must precede end.');return;}apply();};$('reset').onclick=()=>apply({});$('prev').onclick=()=>{page--;renderRows();};$('next').onclick=()=>{page++;renderRows();};$('csv').onclick=exportCSV;
try {const [n,m]=await Promise.all(['notices','meta'].map(x=>fetch(`data/${x}.json`).then(r=>{if(!r.ok)throw Error(`${x}: HTTP ${r.status}`);return r.json();})));notices=n.notices;meta=m;
 $('state').innerHTML='<option value="">All states</option>'+[...new Set(notices.map(n=>n.state))].sort().map(s=>`<option>${esc(s)}</option>`).join('');
 const age=Math.floor((Date.now()-Date.parse(meta.upstream.generated_at))/86400000);
 text('freshness',age>7?`Heads up: the notice archive below is frozen at ${meta.upstream.generated_at.slice(0,10)} - its source has not published anything new in ${age} days, so recent announcements are missing. The forecast and the California check use fresher official data.`:`Notice archive updated ${meta.upstream.generated_at.slice(0,10)}.`);
 text('snapshot',`${fmt(notices.length)} notices / WARN Feed, CC BY 4.0`);apply(Object.fromEntries(new URLSearchParams(location.search)));
}catch(e){text('freshness',`Published data could not load: ${e.message}. No sample numbers are substituted. See source code and raw data links.`);}
