const $=s=>document.querySelector(s);let batch;let SCHEMAS={};
const norm=s=>String(s).toLowerCase().replace(/[^a-z0-9]/g,'');
function csvHeaders(text){let line='';for(const l of text.split(/\r?\n/)){if(l.trim()){line=l;break}}
 const out=[];let cur='',q=false;for(let i=0;i<line.length;i++){const c=line[i];
  if(q){if(c==='"'){if(line[i+1]==='"'){cur+='"';i++}else q=false}else cur+=c}
  else if(c==='"')q=true;else if(c===','){out.push(cur);cur=''}else cur+=c}
 out.push(cur);return out.map(h=>h.trim())}
const csvQuote=v=>/[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;
function replaceHeaders(text,ren){const hs=csvHeaders(text).map(h=>ren[h]||h);const lines=text.split(/\r?\n/);let i=0;while(i<lines.length&&!lines[i].trim())i++;lines[i]=hs.map(csvQuote).join(',');return lines.join('\n')}
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
async function connect(){if(!MosaicAuth.require())return;try{const boot=await api('/api/migrations');SCHEMAS=boot.schemas||{};$('#state').textContent='Ready';$('#studio').hidden=false;$('#signout').onclick=()=>MosaicAuth.clear()}catch(e){if(String(e).includes('401'))MosaicAuth.clear();else $('#state').textContent=e.message}}connect()
async function doStage(){batch=await api('/api/migrations/stage',{kind:$('#kind').value,source_system:$('#source').value,csv:$('#csv').value});showStage(batch,$('#kind').value);$('#apply').disabled=batch.status!=='validated';$('#rollback').disabled=true;$('#reviewfields').hidden=$('#kind').value!=='opening_balances'}
function renderMap(missing){const hs=csvHeaders($('#csv').value);const rows=$('#maprows');rows.innerHTML='';
 missing.forEach(f=>{const row=document.createElement('div');row.className='maprow';
  const lab=document.createElement('label');lab.textContent=f;lab.htmlFor='map-'+f;row.appendChild(lab);
  const sel=document.createElement('select');sel.id='map-'+f;sel.dataset.field=f;
  const blank=document.createElement('option');blank.value='';blank.textContent='Choose a column';sel.appendChild(blank);
  hs.forEach(h=>{if(!h)return;const o=document.createElement('option');o.value=h;o.textContent=h;sel.appendChild(o)});
  row.appendChild(sel);rows.appendChild(row)});
 $('#mapcard').hidden=false}
$('#stage').onclick=async()=>{try{const kind=$('#kind').value;
 const missing=(SCHEMAS[kind]||[]).filter(f=>!csvHeaders($('#csv').value).map(norm).includes(norm(f)));
 if(missing.length){renderMap(missing);$('#result').textContent='Your file is missing '+missing.length+' column'+(missing.length===1?'':'s')+' Mosaic needs. Match them below, then validate again.';return}
 $('#mapcard').hidden=true;await doStage()}catch(e){$('#result').textContent=e.message}}
$('#mapgo').onclick=async()=>{try{const sels=[...document.querySelectorAll('#maprows select')];
 if(sels.some(s=>!s.value)){$('#result').textContent='Choose a column for every Mosaic column, or press Back.';return}
 const vals=sels.map(s=>s.value);if(new Set(vals).size!==vals.length){$('#result').textContent='Each file column can only be matched once.';return}
 const ren={};sels.forEach(s=>ren[s.value]=s.dataset.field);
 $('#csv').value=replaceHeaders($('#csv').value,ren);$('#mapcard').hidden=true;await doStage()}catch(e){$('#result').textContent=e.message}}
$('#mapcancel').onclick=()=>{$('#mapcard').hidden=true};
$('#csv').addEventListener('input',()=>{$('#mapcard').hidden=true});
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
