const $=s=>document.querySelector(s);
function api(path,body){const opt=body===undefined?{headers:MosaicAuth.headers}:{method:'POST',headers:{'Content-Type':'application/json',...MosaicAuth.headers},body:JSON.stringify(body)};return fetch(path,opt).then(r=>r.json().then(j=>{if(r.status===401){MosaicAuth.expired();throw Error('Signed out')}if(!r.ok)throw Error(j.error||'Could not complete');return j}))}
let toastTimer=null;
function toast(ok,text){const t=$('#toast');t.textContent=text;t.className='toast show '+(ok?'ok':'err');clearTimeout(toastTimer);toastTimer=setTimeout(()=>{t.className='toast'},4200)}
const TAX_PLAIN={
 'registration and taxpayer status':'Registration and taxpayer status - whether you are registered for tax, and under which status',
 'effective dates for each rate':'Effective dates - which rates apply, and from when',
 'item or service classification basis':'Item classification - which rate each item or service falls under',
 'place-of-supply and customer-type scope':'Place of supply - how selling to another state or country changes the tax',
 'tax-inclusive or tax-exclusive price basis':'Price basis - whether your prices include tax or add it at checkout',
 'rounding at line or document level':'Rounding - how tax is rounded on each bill',
 'zero-rated/exempt evidence rules':'Zero-rated and exempt sales - which sales are tax-free, and what proof to keep',
 'reverse-charge conditions':'Reverse charge - when you pay tax on a supplier\u2019s behalf',
 'credit/recovery restrictions':'Credit and recovery - which purchase tax you can claim back',
 'invoice fields, filing and e-invoicing adapter separately':'Invoices and filing - what must appear on an invoice, how to file, and electronic filing (e-invoicing)'};
function plainTax(x){return TAX_PLAIN[x]||x}
function esc(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

function renderStores(locs){
  $('#store-count').textContent=locs.length+(locs.length===1?' store':' stores');
  $('#store-list').innerHTML=locs.length?locs.map(l=>'<div class="store-row"><b>'+esc(l.code)+'</b><span>'+esc(l.name)+'</span></div>').join(''):'<p class="hint">No stores yet - add your first one below.</p>';
}
function connect(){if(!MosaicAuth.require())return;
  const identity=JSON.parse(localStorage.getItem('mosaicIdentity')||'{}');
  $('#signout').onclick=()=>MosaicAuth.clear();
  api('/api/settings/summary').then(s=>{
    const name=s.workspace.name||'Your company';
    $('#company').textContent=name;$('#state').textContent='Ready · '+(identity.role||'your role');
    $('#shop-name').value=s.workspace.name||'';
    const nameSave=$('#name-save');
    $('#shop-name').oninput=()=>{nameSave.disabled=!($('#shop-name').value.trim()&&$('#shop-name').value.trim()!==s.workspace.name)};
    nameSave.onclick=()=>{nameSave.disabled=true;api('/api/workspace/rename',{name:$('#shop-name').value.trim()}).then(w=>{s.workspace.name=w.name;$('#company').textContent=w.name;identity.workspace_name=w.name;localStorage.setItem('mosaicIdentity',JSON.stringify(identity));toast(true,'Shop name saved')}).catch(e=>{nameSave.disabled=false;toast(false,e.message)})};
    $('#currency').textContent=s.books.base_currency||'Not set up yet';
    $('#fy').textContent=s.books.fiscal_year_start||'-';
    $('#verify-state').textContent=s.books.verification_state?({unverified:'Not reviewed yet',verified:'Reviewed by an accountant',invalidated:'Changed - needs a fresh review'})[s.books.verification_state]||s.books.verification_state:'Not set up yet';
    renderStores(s.locations||[]);
    $('#store-add').onclick=()=>{const code=$('#store-code').value.trim().toUpperCase(),nm=$('#store-name').value.trim();if(!code||!nm){toast(false,'Give the store a code and a name');return}$('#store-add').disabled=true;api('/api/retail/locations',{code:code,name:nm,kind:'store'}).then(l=>{(s.locations=s.locations||[]).push(l);renderStores(s.locations);$('#store-code').value='';$('#store-name').value='';toast(true,'Store added')}).catch(e=>toast(false,e.message)).finally(()=>{$('#store-add').disabled=false})};
    const tax=s.tax||{};
    $('#tax-jurisdiction').textContent=tax.jurisdiction||(s.country_answer?'Based on: '+s.country_answer:'Not set up yet');
    $('#tax-tag').textContent=tax.jurisdiction?'':'from your interview';
    const mv=tax.must_verify||[];
    $('#tax-verify-wrap').hidden=!mv.length;
    $('#tax-list').innerHTML=mv.map(x=>'<li>'+esc(plainTax(x))+'</li>').join('');
  }).catch(e=>{$('#state').textContent='Could not open settings';toast(false,e.message)});
}
connect();
