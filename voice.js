/* Shared mic control: record in the browser, transcribe on the owner's own
   key, hand the parsed result back for review. The button shows its real
   state at all times; when the key cannot transcribe it stays disabled with
   the plain reason next to it. */
const MosaicVoice=(()=>{
function b64(blob){return new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]||'');r.onerror=rej;r.readAsDataURL(blob)})}
async function attach(btn,statusEl,endpoint,onResult){
 let rec=null,chunks=[],busy=false;
 const lab=btn.querySelector('.miclabel');const setLabel=t=>{if(lab)lab.textContent=t;else btn.textContent=t};
 const say=t=>{if(statusEl)statusEl.textContent=t};
 let st={available:false,reason:'Checking voice entry…'};
 try{st=await fetch('/api/build/voice-status',{headers:{...MosaicAuth.headers}}).then(r=>{if(r.status===401){MosaicAuth.expired();throw Error('Signed out')}return r.json()})}catch(e){st={available:false,reason:'Could not check voice entry.'}}
 if(!navigator.mediaDevices||!window.MediaRecorder){st={available:false,reason:'This browser cannot record audio. Type instead.'}}
 if(!st.available){btn.disabled=true;say(st.reason);return}
 btn.disabled=false;setLabel('Speak');say(st.reason||'');
 btn.onclick=async()=>{
  if(busy)return;
  if(rec&&rec.state==='recording'){rec.stop();return}
  let stream;
  try{stream=await navigator.mediaDevices.getUserMedia({audio:true})}
  catch(e){say('Microphone access was refused. Allow it in the browser, or type instead.');return}
  chunks=[];rec=new MediaRecorder(stream);
  rec.ondataavailable=e=>{if(e.data&&e.data.size)chunks.push(e.data)};
  rec.onstop=async()=>{
   stream.getTracks().forEach(t=>t.stop());rec=null;
   setLabel('Speak');busy=true;say('Listening…');
   try{
    const blob=new Blob(chunks,{type:'audio/webm'});
    const data_b64=await b64(blob);
    const r=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json',...MosaicAuth.headers},body:JSON.stringify({data_b64:data_b64,name:'voice.webm',mime:'audio/webm'})});if(r.status===401){MosaicAuth.expired();throw Error('Signed out')};
    const j=await r.json().catch(()=>({}));
    if(!r.ok){say(j.error||'Could not transcribe. Type instead.');busy=false;return}
    say('');
    onResult(j);
   }catch(e){say('Could not transcribe. Type instead.')}
   busy=false;
  };
  rec.start();setLabel('Stop');say('Recording… tap Stop when done.');
 };
}
return {attach};
})();
