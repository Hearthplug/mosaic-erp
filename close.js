const $=s=>document.querySelector(s);let currency='USD';let today='';let summary=null;
const ZONES=['UTC','Asia/Kolkata','Asia/Dubai','Asia/Singapore','Asia/Shanghai','Asia/Ho_Chi_Minh','Asia/Kuala_Lumpur','Asia/Jakarta','Asia/Manila','Asia/Bangkok','Asia/Tokyo','Asia/Seoul','Asia/Riyadh','Europe/London','Europe/Brussels','Europe/Zurich','Africa/Johannesburg','America/New_York','America/Chicago','America/Denver','America/Los_Angeles','America/Toronto','America/Mexico_City','America/Sao_Paulo','Australia/Sydney','Pacific/Auckland'];
const money=(n,c)=>new Intl.NumberFormat(undefined,{style:'currency',currency:c||currency}).format((n||0)/100);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function api(path,opt){const r=await fetch(path,{...(opt||{}),headers:{'Content-Type':'application/json',...MosaicAuth.headers}});const j=await r.json().catch(()=>({}));if(r.status===401){MosaicAuth.expired();throw Error('Signed out')};if(!r.ok)throw Error(j.error||'Something went wrong');return j}
function render(){
 if(!summary)return;
 $('#s-sales').textContent=money(summary.sales_total_minor);
 $('#s-sales-sub').textContent=summary.sales_count+(summary.sales_count===1?' sale':' sales')+' this day';
 const tot=summary.payments_cash_minor+summary.payments_bank_minor;
 $('#s-payments').textContent=money(tot);
 $('#s-payments-sub').textContent='cash '+money(summary.payments_cash_minor)+' · bank '+money(summary.payments_bank_minor);
 $('#s-credit').textContent=money(summary.credit_minor);
 $('#s-items').textContent=summary.items_sold;
 $('#expected').textContent=money(summary.expected_cash_minor);
 $('#expected-sub').textContent=summary.expected_cash_minor>0?'All cash recorded in the books up to this day.':'No cash recorded in the books up to this day.';
 $('#tzname').textContent=summary.timezone||'UTC';
 $('#save').textContent=summary.date===today?"Save today's close":'Save close for '+summary.date;
 updateDiff();
}
function countedMinor(){const v=$('#counted').value.trim();if(v==='')return null;const n=Number(v);if(!isFinite(n)||n<0)return null;return Math.round(n*100)}
function updateDiff(){
 const el=$('#diff'),c=countedMinor();
 if(!summary){return}
 if(c===null){el.textContent='Type the counted cash to compare it with the books.';el.className='diff';$('#save').disabled=true;return}
 const d=c-summary.expected_cash_minor;
 if(d===0){el.textContent='Matches the books.';el.className='diff ok'}
 else if(d>0){el.textContent=money(d)+' over the books.';el.className='diff off'}
 else{el.textContent=money(-d)+' short of the books.';el.className='diff off'}
 $('#save').disabled=false;
}
async function loadSummary(date){
 $('#save').disabled=true;$('#savehint').textContent='';
 summary=await api('/api/dayclose/summary'+(date?'?date='+encodeURIComponent(date):''));
 $('#day').value=summary.date;render();
}
async function loadCloses(){
 const tb=$('#closes-body');
 try{
  const d=await api('/api/dayclose/closes');
  if(!d.closes.length){tb.innerHTML='<tr><td colspan="5">No closes saved yet. Your first close will appear here.</td></tr>';return}
  tb.innerHTML='';
  d.closes.forEach(c=>{
   const tr=document.createElement('tr');
   const diff=c.difference_minor===0?'Matches':(c.difference_minor>0?'+'+money(c.difference_minor):'-'+money(-c.difference_minor));
   const chip=c.changed_since_close?'<span class="chip amber">Changed since this close</span>':'<span class="chip green">On record</span>';
   tr.innerHTML='<td><b>'+esc(c.date)+'</b></td><td data-label="Counted cash" class="num"><span>'+money(c.counted_cash_minor)+'</span></td><td data-label="Difference" class="num"><span>'+diff+'</span></td><td data-label="Note"><span class="noteval">'+esc(c.note||'—')+'</span></td><td data-label="Status">'+chip+'</td>';
   tb.appendChild(tr);
  });
 }catch(e){tb.innerHTML='<tr><td colspan="5">Could not load past closes: '+esc(e.message)+'</td></tr>'}
}
async function save(){
 const c=countedMinor();if(c===null||!summary)return;
 $('#save').disabled=true;
 try{
  await api('/api/dayclose/save',{method:'POST',body:JSON.stringify({date:summary.date,counted_cash_minor:c,note:$('#note').value})});
  $('#savehint').textContent="Saved - saving again replaces this day's record. The day stays open.";
  $('#note').value='';
  await loadCloses();
  $('#save').disabled=false;
 }catch(e){$('#savehint').textContent=e.message;$('#save').disabled=false}
}
if(MosaicAuth.require()){
 const x=JSON.parse(localStorage.getItem('mosaicIdentity')||'{}');
 $('#company').textContent=x.workspace_name||'Your company';
 $('#authstate').textContent='Close the day · '+(x.role||'your role');
 $('#signout').onclick=()=>MosaicAuth.clear();
 api('/api/accounting/status').then(s=>{currency=s.base_currency||'USD';render()}).catch(()=>{});
 loadSummary().then(()=>{today=summary.date;render()}).catch(e=>{$('#diff').textContent='Could not load the day: '+e.message});
 loadCloses();
 $('#counted').addEventListener('input',updateDiff);
 $('#show-day').onclick=()=>{if($('#day').value){loadSummary($('#day').value).catch(e=>{$('#diff').textContent=e.message})}};
 $('#day').addEventListener('change',()=>{if($('#day').value){loadSummary($('#day').value).catch(e=>{$('#diff').textContent=e.message})}});
 $('#save').onclick=save;
 MosaicVoice.attach($('#mic'),$('#voicestatus'),'/api/dayclose/read-voice',r=>{
 if(r.counted_cash_minor!=null){$('#counted').value=(r.counted_cash_minor/100).toFixed(2);updateDiff()}
 if(r.note)$('#note').value=r.note;
 const vl=$('#voiceline');vl.hidden=false;
 vl.innerHTML='<b>Heard:</b> '+esc(r.transcript||'')+(r.missing&&r.missing.length?' <b>Type the counted cash above - I could not make out the amount.</b>':'');
});
$('#share').onclick=async()=>{
  if(!summary)return;
  try{
   const d=await api('/api/dayclose/share?date='+encodeURIComponent(summary.date));
   const st=$('#sharetext');st.textContent=d.text;st.hidden=false;
   window.open('https://wa.me/?text='+encodeURIComponent(d.text),'_blank','noopener');
  }catch(e){$('#savehint').textContent=e.message}
 };
}
$('#tz-change').onclick=()=>{
 const ed=$('#tz-editor');ed.hidden=!ed.hidden;
 if(!ed.hidden){const sel=$('#tz-select');sel.innerHTML='';ZONES.forEach(z=>{const o=document.createElement('option');o.value=z;o.textContent=z.replace(/_/g,' ');if(summary&&z===summary.timezone)o.selected=true;sel.appendChild(o)})}
};
$('#tz-save').onclick=async()=>{
 try{
  await api('/api/dayclose/timezone',{method:'POST',body:JSON.stringify({timezone:$('#tz-select').value})});
  $('#tz-editor').hidden=true;
  await loadSummary(summary?summary.date:null);await loadCloses();
 }catch(e){$('#diff').textContent=e.message}
};
const onNav=document.querySelector('.rail nav a.on');if(onNav)onNav.scrollIntoView({inline:'center',block:'nearest'});
