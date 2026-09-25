const MosaicAuth={token:sessionStorage.getItem('mosaicSession')||localStorage.getItem('mosaicSession'),get headers(){return this.token?{Authorization:'Bearer '+this.token}:{}},require(){if(!this.token){location.href='/signin?next='+encodeURIComponent(location.pathname);return false}return true},set(x,remember=true){this.token=x.session_token;(remember?localStorage:sessionStorage).setItem('mosaicSession',this.token);localStorage.setItem('mosaicIdentity',JSON.stringify({workspace_id:x.workspace_id,user_id:x.user_id,role:x.role,workspace_name:x.workspace_name}));},clear(){localStorage.removeItem('mosaicSession');sessionStorage.removeItem('mosaicSession');localStorage.removeItem('mosaicIdentity');location.href='/signin'},expired(){localStorage.removeItem('mosaicSession');sessionStorage.removeItem('mosaicSession');localStorage.removeItem('mosaicIdentity');location.href='/signin?next='+encodeURIComponent(location.pathname)}};

// Update check: one hourly, cached look at GitHub Releases via the app.
// Shows a dismissible card when a newer release exists; silent offline.
(function(){
  if(!MosaicAuth.token)return;
  fetch('/api/update-check',{headers:MosaicAuth.headers}).then(function(r){return r.ok?r.json():null}).then(function(u){
    if(!u||!u.update_available)return;
    if(localStorage.getItem('mosaicUpdateDismissed')===u.latest)return;
    var link=document.createElement('link');link.rel='stylesheet';link.href='/update.css';document.head.appendChild(link);
    var mobile=/Android|iPhone|iPad|iPod|Mobile|Tablet/i.test(navigator.userAgent||'');
    var card=document.createElement('div');card.className='mosupd';card.setAttribute('role','status');
    var h=document.createElement('h2');h.textContent='Mosaic ERP '+u.latest+' is available';card.appendChild(h);
    var p=document.createElement('p'),code=null,sub=null;
    if(u.docker){
      p.textContent="You're running "+u.current+". Run this where Mosaic is installed:";
      code=document.createElement('code');code.textContent=u.compose_command;
      sub=document.createElement('p');sub.className='usub';sub.appendChild(document.createTextNode('Using plain docker instead? '));
      var subcode=document.createElement('code');subcode.textContent=u.pull_command;sub.appendChild(subcode);
      sub.appendChild(document.createTextNode(', then recreate the container.'));
    }else if(mobile){
      p.textContent="You're running "+u.current+". Update Mosaic on the computer it's installed on - your data stays where it is.";
    }else{
      p.textContent="You're running "+u.current+". Download the new installer and open it - your data stays in your Mosaic folder and the update picks it up. Windows or Mac may warn the app isn't signed; that's expected, choose to run it anyway.";
    }
    card.appendChild(p);if(code)card.appendChild(code);if(sub)card.appendChild(sub);
    var row=document.createElement('div');row.className='urow';
    if(u.docker){
      var copy=document.createElement('button');copy.className='ubtn';copy.textContent='Copy command';
      copy.onclick=function(){if(navigator.clipboard)navigator.clipboard.writeText(u.compose_command);copy.textContent='Copied'};
      row.appendChild(copy);
      var rel=document.createElement('a');rel.className='ubtn ughost';rel.href=u.release_url;rel.target='_blank';rel.rel='noopener';rel.textContent="See what's new";row.appendChild(rel);
    }else if(mobile){
      var relm=document.createElement('a');relm.className='ubtn';relm.href=u.release_url;relm.target='_blank';relm.rel='noopener';relm.textContent="See what's new";row.appendChild(relm);
    }else{
      var ua=navigator.userAgent||'',win=ua.indexOf('Windows')>=0,mac=ua.indexOf('Mac')>=0;
      var asset=(win&&u.assets&&u.assets.windows)||(mac&&u.assets&&u.assets.mac)||null;
      var a=document.createElement('a');a.className='ubtn';a.href=asset||u.release_url;a.target='_blank';a.rel='noopener';
      a.textContent=asset?(win?'Download for Windows':'Download for Mac'):"See what's new";
      row.appendChild(a);
      if(asset){var rel2=document.createElement('a');rel2.className='ubtn ughost';rel2.href=u.release_url;rel2.target='_blank';rel2.rel='noopener';rel2.textContent="See what's new";row.appendChild(rel2);}
    }
    var dis=document.createElement('button');dis.className='ubtn udismiss';dis.textContent='Not now';
    dis.onclick=function(){localStorage.setItem('mosaicUpdateDismissed',u.latest);card.remove();document.body.style.paddingBottom=''};
    row.appendChild(dis);card.appendChild(row);document.body.appendChild(card);
    if(mobile||window.innerWidth<=640){document.body.style.paddingBottom=(card.offsetHeight+16)+'px'}
  }).catch(function(){});
})();
