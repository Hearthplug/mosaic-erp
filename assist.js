/* Answer-shaping chooser: shared by the interview start and Assistant settings.
   Every control is wired to /api/ai/preference; the server rejects any provider
   id it does not wire, so an unwired option can never silently take effect.
   Key options are BYOK: the key goes only to the preference endpoint, masked. */
(async()=>{
const root=document.querySelector('.assist-chooser');if(!root)return;
const $=s=>root.querySelector(s);
const api=async(path,body)=>{const opt=body?{method:'POST',headers:{'Content-Type':'application/json',...MosaicAuth.headers},body:JSON.stringify(body)}:{headers:{...MosaicAuth.headers}};const r=await fetch(path,opt);const d=await r.json();if(r.status===401){MosaicAuth.expired();throw Error('Signed out')};if(!r.ok)throw Error(d.error||'Request failed');return d};
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
  const needsKey=p.provider!=='standard'&&p.provider!=='custom'&&!p.has_key;
  if(needsKey)pending=p.provider;
  $('#assist-key').hidden=!(pending&&pending!=='standard'&&pending!=='custom');
  if(pending)$('#assist-key-input').placeholder='Paste your '+brandOf(pending)+' key';
  if(p.provider==='custom'){openCustom(p);$('#assist-key').hidden=true}
  let line='';
  if(p.provider==='custom'&&p.custom&&p.custom.base_url)line='Your own server at '+p.custom.base_url+' is shaping your answers.';
  else if(p.provider!=='standard'&&p.has_key)line=nameOf(p.provider)+' is shaping your answers with your own '+brandOf(p.provider)+' key.';
  $('#assist-state').textContent=line;
}
function customBox(){
  let b=$('#assist-custom');if(b)return b;
  b=document.createElement('div');b.className='assist-custom';b.id='assist-custom';b.hidden=true;
  b.innerHTML='<label>Server address<input id="assist-cu-base" type="text" autocomplete="off" placeholder="http://localhost:8080/v1"></label>'
    +'<label>Chat model<input id="assist-cu-chat" type="text" autocomplete="off" placeholder="llama3"></label>'
    +'<label>Vision model <small>for photo reading - optional</small><input id="assist-cu-vision" type="text" autocomplete="off" placeholder="llava"></label>'
    +'<label>Transcription model <small>for the microphone - optional</small><input id="assist-cu-trans" type="text" autocomplete="off" placeholder="whisper-1"></label>'
    +'<label>Server key <small>only if your server asks for one - optional</small><input id="assist-cu-key" type="password" autocomplete="new-password" placeholder="Leave blank if none"></label>'
    +'<div class="assist-cu-actions"><button id="assist-cu-test" type="button">Test connection</button>'
    +'<button id="assist-cu-save" type="button" class="primary">Save and use</button><span id="assist-cu-state" aria-live="polite"></span></div>';
  $('#assist-key').after(b);
  b.querySelector('#assist-cu-save').onclick=saveCustom;
  b.querySelector('#assist-cu-test').onclick=testCustom;
  return b
}
function customConfig(){
  const val=id=>($('#'+id)?$('#'+id).value.trim():'');
  return {base_url:val('assist-cu-base'),models:{chat:val('assist-cu-chat'),vision:val('assist-cu-vision'),transcription:val('assist-cu-trans')}}
}
function fillCustom(c){
  $('#assist-cu-base').value=(c&&c.base_url)||'';
  const m=(c&&c.models)||{};
  $('#assist-cu-chat').value=m.chat||'';$('#assist-cu-vision').value=m.vision||'';$('#assist-cu-trans').value=m.transcription||'';
  $('#assist-cu-key').value='';
}
function openCustom(p){
  const b=customBox();fillCustom(p&&p.custom);b.hidden=false;
  $('#assist-cu-state').textContent='';
  if(!$('#assist-cu-base').value)$('#assist-cu-base').focus();
}
async function saveCustom(){
  const st=$('#assist-cu-state');st.textContent='';
  const cfg=customConfig(),key=$('#assist-cu-key').value.trim();
  try{
    const body={provider:'custom',config:cfg};if(key)body.api_key=key;
    const next=await api('/api/ai/preference/switch',body);st.textContent='Saved.';render(next);
  }catch(e){st.textContent=e.message}
}
async function testCustom(){
  const st=$('#assist-cu-state');st.textContent='Testing...';
  const cfg=customConfig(),key=$('#assist-cu-key').value.trim();
  try{
    const body={provider:'custom',config:cfg};if(key)body.api_key=key;
    const r=await api('/api/ai/preference/test',body);
    st.textContent=r.ok?('Works. '+ (r.detail||'')):('Could not connect. '+ (r.detail||''));
    st.className=r.ok?'ok':'';
  }catch(e){st.textContent='Could not connect. '+e.message;st.className=''}
}
async function choose(id,p){
  const state=$('#assist-state');state.textContent='';
  if(id==='custom'){pending=null;$('#assist-key').hidden=true;openCustom(p);return}
  const cb=$('#assist-custom');if(cb)cb.hidden=true;
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
