/* Answer-shaping chooser: shared by the interview start and Assistant settings.
   Every control is wired to /api/ai/preference; unavailable options render disabled
   with an honest label and can never be submitted (the server also rejects them). */
(async()=>{
const root=document.querySelector('.assist-chooser');if(!root)return;
const $=s=>root.querySelector(s);
const api=async(path,body)=>{const opt=body?{method:'POST',headers:{'Content-Type':'application/json',...MosaicAuth.headers},body:JSON.stringify(body)}:{headers:{...MosaicAuth.headers}};const r=await fetch(path,opt);const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d};
function render(p){
  const box=$('#assist-options');box.innerHTML='';
  p.options.forEach(o=>{
    const label=document.createElement('label');label.className='assist-opt'+(o.available?'':' disabled');
    const input=document.createElement('input');input.type='radio';input.name='assist-'+root.id;input.value=o.id;
    input.checked=(p.provider===o.id);input.disabled=!o.available;
    const span=document.createElement('span');
    const b=document.createElement('b');b.textContent=o.name;
    const small=document.createElement('small');small.textContent=o.line+' ';
    if(!o.available){const em=document.createElement('em');em.textContent='Not available yet.';small.textContent=o.line.replace(/ ?Not available yet\.?/,'')+' ';small.appendChild(em)}
    span.appendChild(b);span.appendChild(small);label.appendChild(input);label.appendChild(span);box.appendChild(label);
    if(o.available)input.onchange=()=>choose(o.id,p);
  });
  $('#assist-consent').textContent=p.consent_note;
  $('#assist-key').hidden=!(p.provider==='jev'&&!p.has_key);
  $('#assist-state').textContent=p.provider==='jev'?(p.has_key?'Jev is shaping your answers with your own TypeSafe key.':''):'';
}
async function choose(id,p){
  const state=$('#assist-state');state.textContent='';
  if(id==='jev'&&!p.has_key){$('#assist-key').hidden=false;$('#jev-key').focus();
    document.querySelectorAll('input[name=assist-'+root.id+']').forEach(i=>{i.checked=(i.value===p.provider)});
    state.textContent='Paste your own TypeSafe key to use Jev.';return}
  try{const next=await api('/api/ai/preference/switch',{provider:id});render(next)}
  catch(e){state.textContent=e.message;render(p)}
}
$('#jev-key-save').onclick=async()=>{
  const state=$('#jev-key-state');state.textContent='';
  const key=$('#jev-key').value.trim();if(!key){state.textContent='Paste the key first.';return}
  try{const next=await api('/api/ai/preference/switch',{provider:'jev',api_key:key});$('#jev-key').value='';state.textContent='Key saved.';render(next)}
  catch(e){state.textContent=e.message}
};
try{render(await api('/api/ai/preference'))}catch(e){/* preference card stays hidden on load errors */}
})();
