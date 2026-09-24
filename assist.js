/* Answer-shaping chooser: shared by the interview start and Assistant settings.
   Every control is wired to /api/ai/preference; the server rejects any provider
   id it does not wire, so an unwired option can never silently take effect.
   Key options are BYOK: the key goes only to the preference endpoint, masked. */
(async()=>{
const root=document.querySelector('.assist-chooser');if(!root)return;
const $=s=>root.querySelector(s);
const api=async(path,body)=>{const opt=body?{method:'POST',headers:{'Content-Type':'application/json',...MosaicAuth.headers},body:JSON.stringify(body)}:{headers:{...MosaicAuth.headers}};const r=await fetch(path,opt);const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d};
let prefs=null,pending=null; // pending = provider id waiting for a pasted key
function brandOf(id){const o=prefs.options.find(x=>x.id===id);return (o&&o.key_brand)||'provider'}
function nameOf(id){const o=prefs.options.find(x=>x.id===id);return o?o.name.replace(' (your key)',''):id}
function render(p){
  prefs=p;
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
  const needsKey=p.provider!=='standard'&&!p.has_key;
  if(needsKey)pending=p.provider;
  $('#assist-key').hidden=!(pending&&pending!=='standard');
  if(pending)$('#assist-key-input').placeholder='Paste your '+brandOf(pending)+' key';
  $('#assist-state').textContent=(p.provider!=='standard'&&p.has_key)?(nameOf(p.provider)+' is shaping your answers with your own '+brandOf(p.provider)+' key.'):'';
}
async function choose(id,p){
  const state=$('#assist-state');state.textContent='';
  try{pending=null;const next=await api('/api/ai/preference/switch',{provider:id});render(next)}
  catch(e){
    document.querySelectorAll('input[name=assist-'+root.id+']').forEach(i=>{i.checked=(i.value===p.provider)});
    const opt=p.options.find(o=>o.id===id);
    if(opt&&opt.needs_key){pending=id;$('#assist-key').hidden=false;$('#assist-key-input').placeholder='Paste your '+brandOf(id)+' key';$('#assist-key-input').focus()}
    state.textContent=e.message;
  }
}
$('#assist-key-save').onclick=async()=>{
  const state=$('#assist-key-state');state.textContent='';
  const key=$('#assist-key-input').value.trim();if(!key){state.textContent='Paste the key first.';return}
  if(!pending){state.textContent='Choose a key provider first.';return}
  try{const next=await api('/api/ai/preference/switch',{provider:pending,api_key:key});$('#assist-key-input').value='';pending=null;state.textContent='Key saved.';render(next)}
  catch(e){state.textContent=e.message}
};
async function init(){try{render(await api('/api/ai/preference'));root.hidden=false}catch(e){root.hidden=true}}
document.addEventListener('mosaic-session',init);
init();
})();
