const $=s=>document.querySelector(s);let schema,session,current,selected,templateUsed=sessionStorage.mosaicTemplate||null;const identity=JSON.parse(localStorage.getItem('mosaicIdentity')||'{}');if($('#rail-company'))$('#rail-company').textContent=identity.workspace_name||'Your company';
async function api(path,method='GET',body){let r=await fetch(path,{method,headers:{'Content-Type':'application/json',...MosaicAuth.headers},body:body&&JSON.stringify(body)});let j=await r.json();if(!r.ok)throw Error(j.error||'Could not continue');return j}
async function begin(){if(!MosaicAuth.require())return;schema=await api('/api/onboarding/schema');let id=localStorage.mosaicOnboarding;if(id){try{session=await api('/api/onboarding/session?id='+encodeURIComponent(id))}catch(e){localStorage.removeItem('mosaicOnboarding')}}if(!session){session=await api('/api/onboarding/start','POST',{});localStorage.mosaicOnboarding=session.id}$('#connect').hidden=true;render()}
function render(){if(session.status==='ready'||session.status==='needs_review'||session.status==='applied'){showSummary();return}current=schema.questions.find(q=>q.key===session.current_question);let n=schema.questions.indexOf(current);$('#interview').hidden=false;$('#bar').value=(n/schema.questions.length)*100;$('#rail-step').textContent='Question '+(n+1)+' of '+schema.questions.length;if(templateUsed){let answered=Object.keys(session.answers||{}).length,remaining=schema.questions.length-answered;$('#bar').value=(answered/schema.questions.length)*100;$('#rail-step').textContent=templateUsed+' template - '+remaining+' question'+(remaining===1?'':'s')+' left';$('#question-step').hidden=true;let tip=$('.regional-note');if(tip)tip.innerHTML='<b>'+templateUsed+' template.</b> INR and GST settings are pre-set. You will review everything before it is saved.';let foot=document.querySelector('.interview-rail footer span');if(foot)foot.textContent='India · INR';}$('#question-step').textContent=String(n+1).padStart(2,'0')+' / '+String(schema.questions.length).padStart(2,'0');$('#question').textContent=current.text;$('#why').textContent='Why Mosaic asks: '+current.why;$('#examples').textContent=current.examples?'For example: '+current.examples.join(' / '):'';$('#answer').hidden=current.type==='choice'||current.type==='multi';$('#answer').value='';selected=current.type==='multi'?[]:null;$('#options').innerHTML='';(current.options||[]).forEach(o=>{let b=document.createElement('button');b.textContent=o;b.onclick=()=>{if(current.type==='multi'){selected.includes(o)?selected.splice(selected.indexOf(o),1):selected.push(o);b.classList.toggle('selected',selected.includes(o))}else{selected=o;[...$('#options').children].forEach(x=>x.classList.remove('selected'));b.classList.add('selected')}};$('#options').appendChild(b)})}
async function save(){let value=current.type==='text'?$('#answer').value:selected;if(!value||(Array.isArray(value)&&!value.length)){ $('#saved').textContent='Please answer in the way that fits your business.';return}session=await api('/api/onboarding/answer','POST',{id:session.id,key:current.key,value});$('#saved').textContent='Saved';render()}
function rail(step){let li=document.querySelectorAll('.rail-progress li');li[1].className=step>=2?'done':'on';li[1].querySelector('i').textContent=step>=2?'\u2713':'2';li[2].className=step>=3?'done':(step===2?'on':'');li[2].querySelector('i').textContent=step>=3?'\u2713':'3'}
function showApplied(){rail(3);let bar=document.querySelector('#summary .card-bar span');if(bar)bar.textContent='LIVE';let note=document.querySelector('.summary-note');if(note)note.textContent='Your Mosaic is ready. The setup you reviewed is now live in your workspace.';let acts=document.querySelector('.summary-actions');if(acts)acts.innerHTML='<p id="apply-state"></p><a class="open-workspace" href="/operations">Open your workspace \u2192</a>'}
async function applySetup(){let b=$('#apply');if(!b)return;b.disabled=true;$('#apply-state').textContent='Saving your confirmed settings\u2026';try{for(let k in jevEdits){session=await api('/api/onboarding/answer','POST',{id:session.id,key:k,value:jevEdits[k]})}$('#apply-state').textContent='Applying your setup\u2026';await api('/api/onboarding/apply','POST',{id:session.id});session.status='applied';showApplied()}catch(e){b.disabled=false;$('#apply-state').textContent=e.message}}
function showSummary(){loadJev();$('#interview').hidden=true;$('#summary').hidden=false;rail(session.status==='applied'?3:2);let i=session.inference;$('#review').innerHTML='<b>Business:</b> '+(i.owner_summary.business||'Your business')+'<br><b>First goal:</b> '+(i.owner_summary.first_goal||'Not answered')+'<br><b>Why features are enabled:</b><ul>'+i.explanations.map(x=>'<li>'+x.because+'</li>').join('')+'</ul>'+(session.contradictions.length?'<b>One thing to clarify:</b> '+session.contradictions.map(x=>x.message).join(' '):'<b>Ready for owner and professional review.</b>');if(session.status==='applied')showApplied()}
$('#start').onclick=()=>begin().catch(e=>$('#state').textContent=e.message);$('#signout').onclick=()=>MosaicAuth.clear();if(MosaicAuth.token&&localStorage.mosaicOnboarding)begin().catch(e=>$('#state').textContent=e.message);$('#save').onclick=()=>save().catch(e=>$('#saved').textContent=e.message);$('#apply').onclick=()=>applySetup();

let jevEdits={};
const JEV_BADGE={auto_accept:['Matched','ok'],confirm:['Please confirm','warn'],blank_confirm:['Your choice','warn'],non_english:['Check meaning','warn'],empty:['Not answered','mute']};
function esc(s){return String(s??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]))}
async function loadJev(){jevEdits={};let box=$('#jev-review');if(!box)return;box.hidden=true;let rc=$('#reconfig');if(rc)rc.hidden=session.status!=='applied';let r;try{r=await api('/api/jev/map-interview','POST',{id:session.id})}catch(e){return}if(!r.proposals||!r.proposals.length)return;box.hidden=false;$('#jev-counts').textContent=r.auto_accepted+' matched \u00b7 '+r.needs_confirm+' to confirm';let rows=$('#jev-rows');rows.innerHTML='';r.proposals.forEach(p=>{let b=JEV_BADGE[p.status]||['','mute'];let div=document.createElement('div');div.className='jev-row jev-'+p.status;let control;if(p.status==='empty'){control='<span class="jev-none">Not answered</span>'}else if(p.probabilities){let opts=Object.keys(p.probabilities);control='<select data-key="'+p.key+'">'+opts.map(o=>'<option '+(o===p.proposed?'selected':'')+'>'+esc(o)+'</option>').join('')+'</select>'}else{control='<input data-key="'+p.key+'" value="'+esc(p.proposed)+'">'}div.innerHTML='<div class="jev-raw"><span>'+esc(p.ask)+'</span><q>'+esc(p.raw)+'</q></div><div class="jev-arrow">\u2192</div><div class="jev-mapped">'+control+'<em>'+esc(p.reason||'')+'</em></div><span class="jev-badge '+b[1]+'">'+b[0]+'</span>';rows.appendChild(div)});rows.querySelectorAll('select,input').forEach(el=>{el.onchange=()=>{let k=el.dataset.key;let row=el.closest('.jev-row');let badge=row.querySelector('.jev-badge');if(el.value&&el.value!==row.querySelector('q').textContent){jevEdits[k]=el.value;badge.textContent='Edited';badge.className='jev-badge ok'}else{delete jevEdits[k]}}})}
async function reconfigGo(){let t=$('#reconfig-text').value.trim();if(!t)return;$('#reconfig-state').textContent='Thinking\u2026';$('#reconfig-rows').innerHTML='';let r;try{r=await api('/api/jev/reconfigure','POST',{request:t})}catch(e){$('#reconfig-state').textContent=e.message;return}if(r.error==='non_english'){$('#reconfig-state').textContent=r.message;return}if(!r.changes.length){$('#reconfig-state').textContent='No clear setting change in that - try a little more detail.';return}$('#reconfig-state').textContent='';let box=$('#reconfig-rows');r.changes.forEach((c,i)=>{let div=document.createElement('div');div.className='jev-row jev-'+c.status;div.innerHTML='<label class="reconfig-check"><input type="checkbox" data-i="'+i+'" '+(c.status==='auto_accept'?'checked':'')+'></label><div class="jev-raw"><span>'+esc(c.ask||c.target)+'</span><q>'+esc(c.current)+'</q></div><div class="jev-arrow">\u2192</div><div class="jev-mapped"><b>'+esc(c.proposed)+'</b><em>'+esc(c.because)+'</em></div><span class="jev-badge '+(c.status==='auto_accept'?'ok':'warn')+'">'+(c.status==='auto_accept'?'Matched':'Please confirm')+'</span>';box.appendChild(div)});let apply=document.createElement('button');apply.textContent='Apply confirmed changes';apply.className='reconfig-apply';apply.onclick=()=>reconfigApply(r.changes);box.appendChild(apply)}
async function reconfigApply(changes){let picked=[...document.querySelectorAll('#reconfig-rows input[type=checkbox]:checked')].map(el=>changes[+el.dataset.i]);if(!picked.length)return;$('#reconfig-state').textContent='Applying\u2026';try{await api('/api/jev/reconfigure/apply','POST',{changes:picked});$('#reconfig-state').textContent='Done - your Mosaic now matches the change.';$('#reconfig-rows').innerHTML='';$('#reconfig-text').value=''}catch(e){$('#reconfig-state').textContent=e.message}}
if($('#reconfig-go'))$('#reconfig-go').onclick=()=>reconfigGo();

const TEMPLATES=[
{id:'kirana',name:'Kirana store',region:'India · INR · GST-ready',blurb:'Neighbourhood grocery with khata credit for regulars',answers:{
 vertical:'Groceries or food',locations:'One place',
 selling:'Customers pick items from the shelves, we weigh or scan them at the counter, they pay by UPI, card or cash.',
 buying:'I buy from local wholesalers and distributor salesmen, check every delivery against the bill, and reorder when stock runs low.',
 stock_pain:'Running out',credit_behavior:'Customers and suppliers both use credit',
 discounts:'Regular customers get small discounts at the counter. Refunds always need the owner.',
 returns:'We exchange unopened items within a few days with the bill.',
 staff:'Two helpers run the counter and refill shelves. The owner manages purchasing and prices.',
 money_view:['Sales','Money customers owe','Low stock'],
 country:'India',
 selling_locations:['Near my registered business'],buying_locations:['Nearby suppliers'],
 price_display:'Tax is included in the shown price',customer_type:'Households',
 product_tax_facts:'Staple foods and everyday items; no special tax treatment that our accountant flags.',
 existing_records:'Paper books',
 exceptions:'Customer credit entries (khata) and partial supplier deliveries cause the most confusion.',
 brand_style:'Warm and welcoming',brand_colors:'Warm yellow and green',logo:'No, use the business name for now',
 screen_preference:'Today’s manager checklist',
 goal:'Keep the khata and stock straight without the evening paper tally.'}},
{id:'pharmacy',name:'Pharmacy',region:'India · INR · GST-ready',blurb:'Chemist shop with batch and expiry tracking',answers:{
 vertical:'Pharmacy or health',locations:'One place',
 selling:'Customers bring prescriptions or ask for common medicines; we bill at the counter by batch, they pay by UPI, card or cash.',
 buying:'I order from two or three medicine distributors and check batches and expiry on delivery against the bill.',
 stock_pain:'Expiry or batches',credit_behavior:'Only suppliers give us credit',
 discounts:'The printed standard discount on medicines; anything more needs the owner.',
 returns:'Unopened medicines can be returned within a few days with the bill; no returns on opened strips.',
 staff:'One pharmacist handles sales and batches. The owner manages purchasing and supplier payments.',
 money_view:['Sales','Low stock','Money I owe suppliers'],
 country:'India',
 selling_locations:['Near my registered business'],buying_locations:['Nearby suppliers'],
 price_display:'Tax is included in the shown price',customer_type:'Households',
 product_tax_facts:'Medicines and health products that need batch and expiry tracking.',
 existing_records:'Spreadsheets',
 exceptions:'Expired stock sent back to distributors and short-expiry deliveries cause the most confusion.',
 brand_style:'Clean and professional',brand_colors:'White and medical green',logo:'No, use the business name for now',
 screen_preference:'Stock needing attention',
 goal:'Never sell an expired strip and know what to reorder each morning.'}},
{id:'apparel',name:'Apparel shop',region:'India · INR · GST-ready',blurb:'Clothing store with seasonal buying and size exchanges',answers:{
 vertical:'Clothing or footwear',locations:'One place',
 selling:'Customers browse and try items, we bill at the counter, they pay by UPI, card or cash.',
 buying:'I buy from wholesale markets and brand distributors before each season and check deliveries against the bill.',
 stock_pain:'Buying too much',credit_behavior:'Only suppliers give us credit',
 discounts:'Season-end sale discounts are set by the owner. Refunds always need the owner.',
 returns:'We exchange within seven days with the bill; sale items are exchange-only.',
 staff:'Two sales staff help customers and manage the floor. The owner manages buying and pricing.',
 money_view:['Sales','Low stock','Profit'],
 country:'India',
 selling_locations:['Near my registered business'],buying_locations:['Nearby suppliers'],
 price_display:'Tax is included in the shown price',customer_type:'Households',
 product_tax_facts:'Clothing and footwear; no special tax treatment that our accountant flags.',
 existing_records:'Paper books',
 exceptions:'Size exchanges and season-end leftover stock cause the most confusion.',
 brand_style:'Bold and energetic',brand_colors:'Deep maroon and cream',logo:'No, use the business name for now',
 screen_preference:'Start selling',
 goal:'Know which sizes and styles to reorder before the season turns.'}}];
function renderTemplates(){let sec=$('#templates'),box=$('#template-cards');if(!sec||!box)return;if(localStorage.mosaicOnboarding)return;sec.hidden=false;TEMPLATES.forEach(t=>{let b=document.createElement('button');b.type='button';b.className='template-card';b.innerHTML='<b>'+t.name+'</b><span class="template-region">'+t.region+'</span><small>'+t.blurb+'</small>';b.onclick=()=>startTemplate(t).catch(e=>{$('#state').textContent=e.message});box.appendChild(b)})}
async function startTemplate(t){templateUsed=t.name;sessionStorage.mosaicTemplate=t.name;$('#state').textContent='Starting from the '+t.name+' template - pre-filling typical answers…';await begin();for(const [k,v] of Object.entries(t.answers)){session=await api('/api/onboarding/answer','POST',{id:session.id,key:k,value:v})}$('#state').textContent='Template answers pre-filled. Tell Mosaic your shop’s name, then review everything before it goes live.';render()}
renderTemplates();
