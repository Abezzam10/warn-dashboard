import test from 'node:test';import assert from 'node:assert/strict';import {validateSpec,compute,unsupported} from '../web/chat.js';
const rows=[{id:'1',employer:'Example',state:'NY',notice_date:'2025-03-01',workers_announced:10,workers_missing:false},{id:'2',employer:'Other',state:'CA',notice_date:'2025-04-01',workers_announced:null,workers_missing:true}];
test('computes only matching rows and actual headcounts',()=>{const r=compute(rows,{metric:'workers_announced_sum',filters:{state:'NY'}});assert.equal(r.workers,10);assert.equal(r.count,1);});
test('rejects arbitrary fields, code, invalid filters and dates',()=>{for(const q of [{metric:'eval'},{metric:'notice_count',code:'alert(1)'},{metric:'notice_count',filters:{industry:'tech'}},{metric:'notice_count',time_range:{start:'tomorrow'}},{metric:'notice_count',filters:{county:'Kings'}}]) assert.throws(()=>validateSpec(q));});
test('visa questions unknown',()=>assert(unsupported('How many H-1B workers were laid off?')));
test('missing counts never treated as known',()=>{const r=compute(rows,{metric:'notice_count'});assert.equal(r.missing,1);assert.equal(r.workers,10);});
