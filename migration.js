const $=s=>document.querySelector(s);let batch;
async function api(path,body){let r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',...MosaicAuth.headers},body:body&&JSON.stringify(body)}),j=await r.json();if(r.status===401){MosaicAuth.expired();throw Error('Signed out')};if(!r.ok)throw Error(j.error||'Could not continue');return j}
const PACK_LABEL={products:'Products',customers:'Customers',vendors:'Suppliers',stock:'Stock',open_invoices:'Open invoices',open_bills:'Open bills',opening_balances:'Opening balances'};
const CUR={USD:'$',EUR:'\u20ac',GBP:'\u00a3',INR:'\u20b9',AED:'AED ',SAR:'SAR ',QAR:'QAR ',KWD:'KWD ',OMR:'OMR ',BHD:'BHD ',SGD:'$',AUD:'$',CAD:'$',MYR:'RM',THB:'\u0e3f',PHP:'\u20b1',IDR:'Rp',VND:'\u20ab',JPY:'\u00a5',KRW:'\u20a9',BDT:'\u09f3',LKR:'Rs',NPR:'Rs',PKR:'Rs'};
const money=(m,c)=>(CUR[c]||((c||'USD')+' '))+(Number(m)/100).toFixed(2);
function showStage(b,kind){
 const label=PACK_LABEL[kind]||kind;let t=label+' import - '+b.row_count+' row'+(b.row_count===1?'':'s')+' checked.\n';
 if(b.status==='validated'){t+=(b.row_count===1?'The row checks out':'All '+b.row_count+' rows check out')+'. Control total: '+money(b.control_total_minor,b.base_currency)+'.\nNothing is applied yet - review the totals, then apply.'}
 else{const errs=b.errors||[];t+=errs.length+' problem'+(errs.length===1?'':'s')+' to fix first:\n'+errs.slice(0,6).map(e=>'Row '+e.row+': '+e.error).join('\n')+(errs.length>6?'\n...and '+(errs.length-6)+' more.':'')}
 $('#result').textContent=t;
}
function showApplied(out){
 let t;
 if(out.journal_id){t='Opening balances applied and reconciled. Debits '+money(out.debit_minor,batch.base_currency)+' equal credits '+money(out.credit_minor,batch.base_currency)+'. Reviewed by '+out.reviewed_by+'.'}
 else{t='Import applied - '+out.row_count+' record'+(out.row_count===1?'':'s')+' created. '+(out.status==='reconciled'?'The control total matches.':'The control total did not match (expected '+money(out.expected_control_total_minor,batch.base_currency)+', posted '+money(out.actual_control_total_minor,batch.base_currency)+') - check the import before relying on it.')}
 $('#result').textContent=t;
}
async function connect(){if(!MosaicAuth.require())return;try{await api('/api/migrations');$('#state').textContent='Ready';$('#studio').hidden=false;$('#signout').onclick=()=>MosaicAuth.clear()}catch(e){if(String(e).includes('401'))MosaicAuth.clear();else $('#state').textContent=e.message}}connect()
$('#stage').onclick=async()=>{try{batch=await api('/api/migrations/stage',{kind:$('#kind').value,source_system:$('#source').value,csv:$('#csv').value});showStage(batch,$('#kind').value);$('#apply').disabled=batch.status!=='validated';$('#rollback').disabled=true;$('#reviewfields').hidden=$('#kind').value!=='opening_balances'}catch(e){$('#result').textContent=e.message}}
$('#apply').onclick=async()=>{try{let out=$('#kind').value==='opening_balances'?await api('/api/migrations/opening-balances/apply',{batch_id:batch.id,professional:$('#professional').value,approved_on:$('#approved').value}):await api('/api/migrations/apply',{batch_id:batch.id});showApplied(out);$('#apply').disabled=true;$('#rollback').disabled=$('#kind').value==='opening_balances'}catch(e){$('#result').textContent=e.message}}
$('#rollback').onclick=()=>{$('#confirmrollback').hidden=false};$('#cancelrollback').onclick=()=>{$('#confirmrollback').hidden=true};$('#doremove').onclick=async()=>{try{let out=await api('/api/migrations/rollback',{batch_id:batch.id});$('#result').textContent='Batch rolled back - '+out.objects+' records undone. Ledger history stays visible.';$('#rollback').disabled=true;$('#confirmrollback').hidden=true}catch(e){$('#result').textContent=e.message}}

$('#file').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{
  const buf=await f.arrayBuffer();let bin='';const b=new Uint8Array(buf);for(let i=0;i<b.length;i++)bin+=String.fromCharCode(b[i]);
  const out=await api('/api/build/read-file',{name:f.name,mime:f.type,data_b64:btoa(bin)});
  if(!out.detected||!out.detected.csv)throw Error('That file is not a spreadsheet or CSV.');
  $('#csv').value=out.detected.csv;
  if(out.detected.pack){$('#kind').value=out.detected.pack}
  const rows=out.detected.csv.split('\n').filter(l=>l.trim()).length-1;
  $('#result').textContent='Loaded '+f.name+' ('+rows+' rows). Check the data below, then validate.';}
  catch(err){$('#result').textContent=err.message}}
