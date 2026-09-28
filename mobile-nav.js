(function(){
  const icons={today:'<path d="M2.8 8.4 9 3l6.2 5.4M4.8 7.2V15h3.4v-3.8h1.6V15h3.4V7.2"/>',stock:'<path d="M2.8 5.6 9 2.4l6.2 3.2v6.8L9 15.6 2.8 12.4zM2.8 5.6 9 8.8l6.2-3.2M9 8.8v6.8"/>',sales:'<path d="M2.6 8.2V3.6a1 1 0 0 1 1-1h4.6l6.2 6.2a1.2 1.2 0 0 1 0 1.7l-4.3 4.3a1.2 1.2 0 0 1-1.7 0z"/><circle cx="6.4" cy="6.4" r="1.1"/>',buying:'<path d="M2.4 3.2h1.9l1.7 8.2h7.6l1.5-5.8H5.3"/><circle cx="7.6" cy="14.4" r="1.2"/><circle cx="12.6" cy="14.4" r="1.2"/>',more:'<circle cx="4" cy="9" r=".8"/><circle cx="9" cy="9" r=".8"/><circle cx="14" cy="9" r=".8"/>'};
  const tabs=[['today','Today'],['stock','Stock'],['sales','Sales'],['buying','Buying']];
  const root=document.createElement('nav');root.className='mobile-nav';root.setAttribute('aria-label','Mobile modules');
  const row=document.createElement('div');row.className='mobile-nav-tabs';
  tabs.forEach(([key,label])=>{const a=document.createElement('a');a.href='/operations#'+key;a.dataset.mobileView=key;a.innerHTML='<svg viewBox="0 0 18 18" aria-hidden="true">'+icons[key]+'</svg><span>'+label+'</span>';row.appendChild(a)});
  const more=document.createElement('button');more.type='button';more.setAttribute('aria-expanded','false');more.setAttribute('aria-controls','mobile-more-menu');more.innerHTML='<svg viewBox="0 0 18 18" aria-hidden="true">'+icons.more+'</svg><span>More</span>';row.appendChild(more);
  const menu=document.createElement('div');menu.className='mobile-nav-menu';menu.id='mobile-more-menu';menu.hidden=true;
  [['Money','/operations#money'],['Books','/accounting'],['Build','/build'],['Assistant','/assistant'],['Settings','/'],['Close the day','/close'],['Switch from old system','/migration']].forEach(([label,href])=>{const a=document.createElement('a');a.href=href;a.textContent=label;if(label==='Assistant'){const small=document.createElement('small');small.textContent='Preview';a.appendChild(small)}menu.appendChild(a)});
  root.appendChild(menu);root.appendChild(row);document.body.appendChild(root);
  const active=()=>{let key='';const path=location.pathname;if(path==='/operations')key=location.hash.slice(1)||'today';else if(path==='/'||path==='/settings')key='settings';else key=path.slice(1);row.querySelectorAll('a').forEach(a=>{const on=a.dataset.mobileView===key;a.classList.toggle('on',on);if(on)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});const isMore=!tabs.some(t=>t[0]===key);more.classList.toggle('on',isMore||!menu.hidden);menu.querySelectorAll('a').forEach(a=>{const on=a.getAttribute('href')===(key==='money'?'/operations#money':path);a.classList.toggle('on',on);if(on)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')})};
  const close=()=>{menu.hidden=true;more.setAttribute('aria-expanded','false');active()};
  more.onclick=()=>{menu.hidden=!menu.hidden;more.setAttribute('aria-expanded',String(!menu.hidden));active()};
  row.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{close();if(location.pathname==='/operations'){const key=a.dataset.mobileView;const view=document.querySelector('.rail-item[data-view="'+key+'"]');if(view)view.click();active()}}));
  menu.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{close();if(location.pathname==='/operations'&&a.getAttribute('href')==='/operations#money'){const view=document.querySelector('.rail-item[data-view="money"]');if(view)view.click();active()}}));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!menu.hidden){close();more.focus()}});
  document.addEventListener('click',e=>{if(!root.contains(e.target)&&!menu.hidden)close()});
  addEventListener('hashchange',active);active();
})();
