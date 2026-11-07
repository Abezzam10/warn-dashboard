// One optional on-device model. No remote inference. All output is validated.
let generator;
self.onmessage=async({data})=>{
 try {
  if(data.type==='load') {
   const {pipeline,env}=await import('https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.2');
   env.allowLocalModels=false;
   generator=await pipeline('text-generation','HuggingFaceTB/SmolLM2-1.7B-Instruct',{
    revision:data.revision, dtype:'q4', device:data.device,
    progress_callback:p=>self.postMessage({type:'progress',text:`${p.status} ${p.file||''} ${p.progress?Math.round(p.progress)+'%':''}`})});
   self.postMessage({type:'ready'});
  } else if(data.type==='ask') {
   if(!generator) throw Error('Model is not loaded');
   const system='Translate this WARN data question to ONE JSON object. No explanation. Keys: metric, filters, group_by, time_range. metric one of notice_count, workers_announced_sum, top_employers, monthly_series, employer_history, forecast. filters may only contain state (US two-letter code), employer (substring), notice_type. group_by month, state, employer, notice_type. time_range {start:YYYY-MM-DD,end:YYYY-MM-DD} optional. Use {} for unspecified filters/time. Never invent filters or dates. Example: notices in New York -> {"metric":"notice_count","filters":{"state":"NY"},"group_by":"month","time_range":{}}';
   const out=await generator([{role:'system',content:system},{role:'user',content:data.question}],{max_new_tokens:180,do_sample:false,return_full_text:false});
   const raw=out[0].generated_text;
   const text=typeof raw==='string'?raw:raw[raw.length-1].content;
   const match=text.match(/\{[\s\S]*\}/);
   if(!match) throw Error('Model did not produce a query. Use the explorer or suggested questions.');
   self.postMessage({type:'answer',spec:JSON.parse(match[0])});
  }
 } catch(e) {self.postMessage({type:'error',text:e.message});}
};
