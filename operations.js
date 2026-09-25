const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const VIEWS={
  today:{title:'Today',sub:'Start with the task in front of you.'},
  stock:{title:'Stock',sub:'What you have, and where it is.'},
  sales:{title:'Sales',sub:'Every bill, payment and refund.'},
  buying:{title:'Buying',sub:'Orders, deliveries and supplier bills.'},
  money:{title:'Money',sub:'Till sessions and period locks.'}
};
let LISTS={stock:[],sales:[],buying:[],money:[]},CURRENCY='USD';
let IDBY_LABEL={},PO_LINES={};

function api(path,body){return fetch(path,{method:'POST',headers:{'Content-Type':'application/json',...MosaicAuth.headers},body:JSON.stringify(body)}).then(r=>r.json().then(j=>{if(r.status===401){MosaicAuth.expired();throw Error('Signed out')};if(!r.ok)throw Error(j.error||'Could not complete');return j}))}
function get(path){return fetch(path,{headers:MosaicAuth.headers}).then(r=>{if(r.status===401){MosaicAuth.clear();throw Error('Signed out')}if(!r.ok)throw Error('Could not load');return r.json()})}
function data(f){return Object.fromEntries(new FormData(f))}
function esc(x){return String(x==null?'':x)}
function fmtMoney(minor,currency){if(minor===null||minor===undefined||minor==='')return '—';try{return new Intl.NumberFormat(undefined,{style:'currency',currency:currency||CURRENCY}).format(minor/100)}catch(e){return (minor/100).toFixed(2)+' '+(currency||CURRENCY)}}
function fmtQty(q){if(q===null||q===undefined)return '—';const n=Number(q);if(!isFinite(n))return esc(q);return n.toLocaleString(undefined,{maximumFractionDigits:2})}
function fmtWhen(iso){if(!iso)return '—';const d=new Date(iso);if(isNaN(d))return esc(iso).slice(0,10);const now=new Date();
  if(d.toDateString()===now.toDateString())return d.toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'});
  return d.toLocaleDateString(undefined,{day:'numeric',month:'short'})}
const STATUS={draft:['st-gray','Draft'],approved:['st-blue','Approved'],part_received:['st-amber','Part received'],received:['st-green','Received'],cancelled:['st-red','Cancelled'],completed:['st-green','Completed'],returned:['st-amber','Returned'],voided:['st-red','Voided'],open:['st-green','Open'],closed:['st-gray','Closed']};
function pill(status){const s=STATUS[status]||['st-gray',esc(status)];const e=document.createElement('span');e.className='pill '+s[0];e.textContent=s[1];return e}
function cell(text,cls,sub){const td=document.createElement('td');if(cls)td.className=cls;if(sub!==undefined){const b=document.createElement('span');b.className='cell-main';b.textContent=text;td.appendChild(b);const u=document.createElement('span');u.className='cell-sub';u.textContent=sub;td.appendChild(u)}else td.textContent=text;return td}
function pillCell(status){const td=document.createElement('td');td.appendChild(pill(status));return td}
function fill(tableId,rows,emptyText){const tb=$('#'+tableId+' tbody');tb.innerHTML='';if(!rows.length){const tr=document.createElement('tr');tr.className='empty-row';const td=document.createElement('td');td.colSpan=tb.closest('table').querySelectorAll('th').length;td.textContent=emptyText;tr.appendChild(td);tb.appendChild(tr);return}rows.forEach(r=>tb.appendChild(r))}

let noticeTimer=null;
function notice(ok,text,detail){const n=$('#notice');n.hidden=false;$('#notice-text').textContent=text;$('#notice-icon-ok').hidden=!ok;$('#notice-icon-err').hidden=ok;$('#notice-json').textContent=detail||'';$('#notice-details').open=false;$('#notice-details').hidden=!detail;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>{n.hidden=true},6000)}
$('#notice-close').onclick=()=>{$('#notice').hidden=true;clearTimeout(noticeTimer)};

function select(name){if(!VIEWS[name])name='today';
  $$('.rail-item[data-view]').forEach(b=>b.classList.toggle('on',b.dataset.view===name));
  $$('.view').forEach(v=>v.hidden=v.id!=='view-'+name);
  $('#page-title').textContent=VIEWS[name].title;$('#page-crumb').textContent=VIEWS[name].title;$('#page-sub').textContent=VIEWS[name].sub;
  if(('#'+name)!==location.hash)history.replaceState(null,'','#'+name)}
$$('.rail-item[data-view]').forEach(b=>b.onclick=()=>select(b.dataset.view));
addEventListener('hashchange',()=>select(location.hash.slice(1)));

function renderStock(){const rows=LISTS.stock.map(r=>{const tr=document.createElement('tr');
  tr.appendChild(cell(r.name,'',r.sku));tr.appendChild(cell(r.location_name,'',r.location_code));tr.appendChild(cell(fmtQty(r.on_hand)+(r.unit&&r.unit!=='each'?' '+r.unit:''),'num'));return tr});
  fill('stock-table',rows,'No items yet. Your first delivery appears here.');
  $('#stock-count').textContent=LISTS.stock.length?LISTS.stock.length+' rows':'';
  $('#kpi-stock').textContent=LISTS.stock.length?fmtQty(LISTS.stock.reduce((a,r)=>a+Number(r.on_hand||0),0)):'0'}
function renderSales(){const rows=LISTS.sales.map(r=>{const tr=document.createElement('tr');tr.className='sale-openable';tr.title='Tap to see the bill or refund items';tr.onclick=()=>openSaleDetail(r.id);
  tr.appendChild(cell(r.number,'cell-main'));tr.appendChild(cell(fmtWhen(r.sold_at)));tr.appendChild(cell(r.location_code));tr.appendChild(cell(String(r.line_count),'num'));tr.appendChild(cell(fmtMoney(r.total_minor,r.currency),'num'));tr.appendChild(cell(fmtMoney(r.paid_minor,r.currency),'num'));tr.appendChild(pillCell(r.status));return tr});
  fill('sales-table',rows,'No sales yet. Make your first sale on the till below.');
  $('#sales-count').textContent=LISTS.sales.length?'last '+LISTS.sales.length:'';
  const today=new Date().toDateString(),todays=LISTS.sales.filter(r=>new Date(r.sold_at).toDateString()===today);
  $('#kpi-sales').textContent=todays.length?fmtMoney(todays.reduce((a,r)=>a+r.total_minor,0),todays[0].currency):'—';
  $('#kpi-sales-sub').textContent=todays.length?todays.length+(todays.length===1?' bill':' bills')+' today':'no bills yet'}
function renderBuying(){const rows=LISTS.buying.map(r=>{const tr=document.createElement('tr');
  tr.appendChild(cell(r.number,'cell-main'));tr.appendChild(cell(r.vendor_name));tr.appendChild(cell(r.location_code));tr.appendChild(cell(fmtWhen(r.ordered_on)));tr.appendChild(cell(String(r.line_count),'num'));tr.appendChild(cell(fmtMoney(r.total_minor,r.currency),'num'));
  const st=pillCell(r.status);
  if(r.status==='draft'){const b=document.createElement('button');b.type='button';b.className='btn row-action';b.textContent='Approve';b.onclick=()=>run('/api/retail/purchases/approve',{purchase_order_id:r.id},'Purchase order approved');st.appendChild(b)}
  tr.appendChild(st);return tr});
  fill('buying-table',rows,'No orders yet. Order from a supplier below.');
  $('#buying-count').textContent=LISTS.buying.length?'last '+LISTS.buying.length:'';
  $('#kpi-orders').textContent=String(LISTS.buying.filter(r=>['draft','approved','part_received'].includes(r.status)).length)}
function renderMoney(){const rows=LISTS.money.map(r=>{const tr=document.createElement('tr');
  tr.appendChild(cell(r.location_code,'cell-main'));tr.appendChild(cell(fmtWhen(r.opened_at)));tr.appendChild(cell(fmtMoney(r.opening_minor),'num'));tr.appendChild(cell(fmtMoney(r.expected_minor),'num'));tr.appendChild(cell(fmtMoney(r.actual_minor),'num'));
  const v=r.variance_minor;const td=document.createElement('td');td.className='num';
  if(v===null||v===undefined)td.textContent='—';else{const s=document.createElement('span');s.className='pill '+(v===0?'st-green':'st-red');s.textContent=(v>0?'+':'')+fmtMoney(v).replace(/^([^0-9-+]*)/,'$1');td.appendChild(s)}
  tr.appendChild(td);tr.appendChild(pillCell(r.status));return tr});
  fill('money-table',rows,'No till sessions yet. Open the till to start the day.');
  $('#money-count').textContent=LISTS.money.length?'last '+LISTS.money.length:'';
  const open=LISTS.money.filter(r=>r.status==='open');
  $('#kpi-cash').textContent=String(open.length);
  $('#kpi-cash-sub').textContent=open.length?fmtMoney(open.reduce((a,r)=>a+r.opening_minor,0))+' in floats':'no tills open'}

function reload(){return Promise.all([
  get('/api/retail/stock-register').then(j=>{LISTS.stock=j.rows;renderStock()}),
  get('/api/retail/sales-list').then(j=>{LISTS.sales=j.rows;renderSales()}),
  get('/api/retail/purchases-list').then(j=>{LISTS.buying=j.rows;renderBuying()}),
  get('/api/retail/cash-sessions').then(j=>{LISTS.money=j.rows;renderMoney()})
]).catch(e=>notice(false,e.message))}

function run(path,body,okText){api(path,body).then(x=>{notice(true,okText,JSON.stringify(x,null,2));reload();refreshContext();refreshExport()}).catch(e=>notice(false,e.message))}

function register(kind,label,id){IDBY_LABEL[kind+':'+label]=id;return label}
function resolveId(kind,val){return IDBY_LABEL[kind+':'+val]||val}
function refreshLists(c){
  IDBY_LABEL={};
  const fill=(id,rows,kind,label)=>{$(id).innerHTML=rows.map(x=>'<option value="'+esc(register(kind,label(x),x.id))+'"></option>').join('')};
  fill('#locations',c.locations,'loc',x=>x.code+' · '+x.name);
  fill('#products',c.products,'prod',x=>x.sku+' · '+x.name);
  c.products.forEach(x=>{IDBY_LABEL['prodbyid:'+x.id]=x.sku+' · '+x.name});
  fill('#vendors',c.vendors,'vendor',x=>x.name);
  fill('#orders',c.purchase_orders,'po',x=>x.number+' · '+(STATUS[x.status]?STATUS[x.status][1]:x.status));
  fill('#bill-options',c.open_bills,'bill',x=>x.number+' · '+fmtMoney(x.balance_minor))}
function refreshContext(){return get('/api/operations/context').then(c=>{refreshLists(c)}).catch(()=>{})}
function refreshExport(){return get('/api/retail/export').then(x=>{EXP=x;PO_LINES={};(x.purchase_order_lines||[]).forEach(l=>{(PO_LINES[l.purchase_order_id]=PO_LINES[l.purchase_order_id]||[]).push(l)});tillRenderTiles()}).catch(()=>{})}
function productLabel(id){const o=IDBY_LABEL['prodbyid:'+id];return o||id}
function updateMoneyLabels(){document.querySelectorAll('label').forEach(l=>{if(['Cash received','Unit cost','Amount'].includes(l.childNodes[0].textContent.trim()))l.childNodes[0].textContent=l.childNodes[0].textContent.trim()+' ('+CURRENCY+')'})}
function connect(){if(!MosaicAuth.require())return;
  let identity=JSON.parse(localStorage.getItem('mosaicIdentity')||'{}');
  $('#company').textContent=identity.workspace_name||'Your company';
  $('#signout').onclick=()=>MosaicAuth.clear();
  Promise.all([get('/api/operations/context'),get('/api/accounting/status').catch(()=>({base_currency:'USD'}))]).then(([c,book])=>{CURRENCY=book.base_currency||'USD';updateMoneyLabels();
    $('#state').textContent='Ready · '+(identity.role||'your role');
    refreshLists(c);tillSetup(c.locations||[]);
    const ol=$('#next');ol.innerHTML='';
    c.next_steps.forEach(s=>{const li=document.createElement('li');li.textContent=s;ol.appendChild(li)});
    reload();refreshExport()
  }).catch(e=>{$('#state').textContent='Could not open workspace';notice(false,e.message)})}

$('#stock').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/transfers',{product_id:resolveId('prod',d.product_id),from_location:resolveId('loc',d.from_location),to_location:resolveId('loc',d.to_location),quantity:d.quantity},'Stock transferred')};

$('#buy').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/purchases',{vendor_id:resolveId('vendor',d.vendor_id),location_id:resolveId('loc',d.location_id),ordered_on:d.ordered_on,lines:[{product_id:resolveId('prod',d.product_id),quantity:d.quantity,unit_cost_minor:Math.round(+d.unit_cost_minor*100)}],currency:CURRENCY},'Purchase order saved')};
const poInput=$('#receive input[name=purchase_order_id]'),lineSel=$('#receive select[name=line_id]');
function fillLines(){const po=resolveId('po',poInput.value),lines=PO_LINES[po]||[];
  lineSel.innerHTML=lines.length?lines.map(l=>'<option value="'+l.id+'">'+esc(productLabel(l.product_id))+' - '+esc(l.quantity)+' ordered, '+esc(l.received_quantity||'0')+' received</option>').join(''):'<option value="">No open lines on this order</option>'}
poInput.addEventListener('input',fillLines);poInput.addEventListener('change',fillLines);
$('#receive').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/purchases/receive',{purchase_order_id:resolveId('po',d.purchase_order_id),received:{[d.line_id]:d.quantity}},'Stock received')};
$('#bill-match').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/three-way-match',{purchase_order_id:resolveId('po',d.purchase_order_id),bill_id:resolveId('bill',d.bill_id)},'Match complete')};
$('#cash').onsubmit=e=>e.preventDefault();
$('#cash button[name=open]').onclick=()=>{let d=data($('#cash'));run('/api/retail/cash/open',{location_id:resolveId('loc',d.location_id),opening_minor:Math.round(+d.amount_minor*100)},'Till opened')};
$('#cash button[name=close]').onclick=()=>{let d=data($('#cash'));run('/api/retail/cash/close',{session_id:d.session_id,actual_minor:Math.round(+d.amount_minor*100)},'Till closed')};
$('#add-vendor').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/accounting/parties',{kind:'vendor',name:d.name},'Supplier added');e.target.reset()};
$('#add-item').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/products',{sku:d.sku,name:d.name,selling_price_minor:Math.round(+d.price*100),cost_minor:Math.round(+d.cost*100)},'Item added');e.target.reset()};
$('#add-location').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/locations',{code:d.code.toUpperCase(),name:d.name,kind:'store'},'Store added');e.target.reset()};
$('#close').onsubmit=e=>{e.preventDefault();run('/api/accounting/periods/lock',{period_id:data(e.target).period_id},'Period locked')};

select(location.hash.slice(1)||'today');
connect();


function tableRows(table){return [...table.tBodies[0].rows].filter(r=>!r.classList.contains('empty-row'))}
$$('.toolbar').forEach(bar=>{
  const table=$('#'+bar.dataset.table),input=bar.querySelector('input[type=search]');
  const apply=()=>{const term=input.value.trim().toLowerCase(),filter=bar.querySelector('.filter-chip.on')?.dataset.filter||'all';tableRows(table).forEach(row=>{const text=row.textContent.toLowerCase();row.hidden=!(text.includes(term)&&(filter==='all'||text.includes(filter)))})};
  input.addEventListener('input',apply);
  bar.querySelectorAll('.filter-chip:not(:disabled)').forEach(btn=>btn.onclick=()=>{bar.querySelectorAll('.filter-chip').forEach(x=>x.classList.remove('on'));btn.classList.add('on');apply()});
  bar.querySelector('.export-btn').onclick=()=>{const rows=[...table.rows].filter(r=>!r.hidden&&!r.classList.contains('empty-row'));const csv=rows.map(row=>[...row.cells].map(c=>'"'+c.innerText.trim().replaceAll('"','""')+'"').join(',')).join('\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));a.download=table.id.replace('-table','')+'-'+new Date().toISOString().slice(0,10)+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),0)};
});

/* ===== Till ===== */
let EXP={},CART=new Map(),TILL_LOC='',TILL_LOCS=[],DETAIL_SALE=null;
const tillProducts=()=>((EXP.retail_products||[]).filter(p=>p.active!==0)).slice().sort((a,b)=>String(a.name).localeCompare(String(b.name)));
const tillTotalMinor=()=>{let t=0;CART.forEach((q,id)=>{const p=(EXP.retail_products||[]).find(x=>x.id===id);if(p)t+=Math.round(q*int(p.selling_price_minor))});return t};
function int(v){return parseInt(v,10)||0}
function tillSetup(locs){TILL_LOCS=locs||[];const wrap=$('#till-store-wrap'),sel=$('#till-store');
  if(TILL_LOCS.length===1){TILL_LOC=TILL_LOCS[0].id;wrap.hidden=true}
  else if(TILL_LOCS.length>1){wrap.hidden=false;sel.innerHTML=TILL_LOCS.map(l=>'<option value="'+l.id+'">'+esc(l.code+' - '+l.name)+'</option>').join('');TILL_LOC=TILL_LOCS[0].id;sel.onchange=()=>{TILL_LOC=sel.value}}
  $('#till-search').oninput=tillRenderTiles;
  $('#till-given').oninput=()=>{const g=$('#till-given');g.value=g.value.replace(/[^0-9.]/g,'').replace(/(\..*)\./g,'$1');tillRefreshTender()};
  $('#till-pad').querySelectorAll('button').forEach(b=>b.onclick=()=>{const g=$('#till-given');const k=b.dataset.k;if(k==='back')g.value=g.value.slice(0,-1);else if(k==='.'&&g.value.includes('.'))return;else g.value+=k;tillRefreshTender()});
  $('#till-take').onclick=()=>tillComplete('cash');
  $('#till-bank').onclick=()=>tillComplete('bank');
  $('#cb-charge').onclick=()=>tillComplete('cash');
  $('#refund-go').onclick=refundGo;
  $('#sale-detail-close').onclick=()=>{$('#sale-detail').hidden=true;DETAIL_SALE=null};
  tillRenderCart()}
function tillRenderTiles(){const box=$('#till-tiles');if(!box)return;const q=($('#till-search').value||'').toLowerCase();
  const prods=tillProducts().filter(p=>!q||String(p.name).toLowerCase().includes(q)||String(p.sku).toLowerCase().includes(q));
  if(!prods.length){box.innerHTML='<p class="tilegrid-empty">'+((EXP.retail_products||[]).length?'Nothing matches that search.':'No items yet - add your first item on the Stock page, then sell it here.')+'</p>';return}
  box.innerHTML='';prods.forEach(p=>{const b=document.createElement('button');b.type='button';b.className='tile'+(CART.has(p.id)?' incart':'');
    const inCart=CART.get(p.id)||0;
    b.innerHTML='<b>'+esc(p.name)+'</b><span>'+esc(fmtMoney(p.selling_price_minor))+'</span>'+(inCart?'<span class="tile-qty">'+inCart+' in this sale</span>':'');
    b.onclick=()=>{CART.set(p.id,(CART.get(p.id)||0)+1);tillRenderTiles();tillRenderCart()};box.appendChild(b)})}
function tillRenderCart(){const box=$('#till-lines');const n=CART.size;
  $('#till-count').textContent=n?'':'';
  if(!n){box.innerHTML='<p class="hint">Nothing added yet - tap an item'+(window.innerWidth<=720?' above':' on the left')+'.</p>'}
  else{box.innerHTML='';CART.forEach((q,id)=>{const p=(EXP.retail_products||[]).find(x=>x.id===id);if(!p)return;
    const row=document.createElement('div');row.className='till-line';
    row.innerHTML='<div class="tl-name">'+esc(p.name)+'<small>'+q+' &times; '+esc(fmtMoney(p.selling_price_minor))+'</small></div>';
    const st=document.createElement('div');st.className='stepper';
    const minus=document.createElement('button');minus.type='button';minus.textContent='\u2212';minus.onclick=()=>{if(q<=1)CART.delete(id);else CART.set(id,q-1);tillRenderTiles();tillRenderCart()};
    const qb=document.createElement('b');qb.textContent=q;
    const plus=document.createElement('button');plus.type='button';plus.textContent='+';plus.onclick=()=>{CART.set(id,q+1);tillRenderTiles();tillRenderCart()};
    st.append(minus,qb,plus);row.appendChild(st);
    const amt=document.createElement('div');amt.className='tl-amt';amt.textContent=fmtMoney(Math.round(q*int(p.selling_price_minor)));row.appendChild(amt);
    box.appendChild(row)})}
  tillRefreshTender()}
function tillRefreshTender(){const t=tillTotalMinor();$('#till-total').textContent=fmtMoney(t);
  const n=[...CART.values()].reduce((a,b)=>a+b,0);
  $('#cb-total').textContent=fmtMoney(t);$('#cb-count').textContent=n?n+(n===1?' item':' items'):'No items yet';
  const givenStr=$('#till-given').value.trim();const given=givenStr?Math.round(parseFloat(givenStr)*100):null;
  const ch=$('#till-change');
  if(!t){ch.textContent='';$('#till-take').disabled=true;$('#till-take').textContent='Take cash';$('#till-bank').disabled=true;$('#till-bank').textContent='Card or bank';$('#cb-charge').disabled=true;return}
  if(given===null){ch.textContent='Type the cash given, or take exact cash.'}else if(given<t){ch.textContent='That is '+fmtMoney(t-given)+' short of the total.'}else if(given===t){ch.textContent='Exact cash.'}else{ch.innerHTML='Change to give back: <b>'+esc(fmtMoney(given-t))+'</b>'}
  const cashOk=given===null||given>=t;
  $('#till-take').disabled=!cashOk;$('#till-take').textContent=given&&given>=t?'Take '+fmtMoney(given)+' cash':'Take '+fmtMoney(t)+' cash';
  $('#till-bank').disabled=false;$('#till-bank').textContent='Card or bank - '+fmtMoney(t);
  $('#cb-charge').disabled=false}
function tillComplete(kind){const t=tillTotalMinor();if(!t)return;
  const lines=[...CART.entries()].map(([id,q])=>({product_id:id,quantity:String(q)}));
  const givenStr=$('#till-given').value.trim();const given=givenStr?Math.round(parseFloat(givenStr)*100):null;
  if(kind==='cash'&&given!==null&&given<t){notice(false,'The cash given is short of the total.');return}
  const btn=kind==='cash'?$('#till-take'):$('#till-bank');btn.disabled=true;
  api('/api/retail/sales',{location_id:TILL_LOC,lines,tenders:[{kind,amount_minor:t}],currency:CURRENCY})
    .then(x=>{notice(true,'Sale '+x.number+' completed - '+fmtMoney(x.total_minor));CART.clear();$('#till-given').value='';tillRenderTiles();tillRenderCart();reload();refreshContext();refreshExport()})
    .catch(e=>{notice(false,e.message);tillRefreshTender()})}
function openSaleDetail(id){const s=LISTS.sales.find(r=>r.id===id);if(!s)return;DETAIL_SALE=id;
  const lines=(EXP.sale_lines||[]).filter(l=>l.sale_id===id);
  const returned={};(EXP.retail_return_lines||[]).forEach(rl=>{if(lines.some(l=>l.id===rl.sale_line_id))returned[rl.sale_line_id]=(returned[rl.sale_line_id]||0)+Number(rl.quantity)});
  $('#sale-detail-title').textContent='Bill '+s.number;
  $('#sale-detail-sub').textContent=fmtWhen(s.sold_at)+' \u00b7 '+s.location_code+' \u00b7 '+fmtMoney(s.total_minor)+' \u00b7 '+(STATUS[s.status]?STATUS[s.status][1]:s.status);
  const box=$('#sale-detail-lines');box.innerHTML='';
  if(!lines.length){box.innerHTML='<p class="hint" style="padding:10px 14px">Quick sale without item lines - nothing to refund item by item.</p>'}
  lines.forEach(l=>{const p=(EXP.retail_products||[]).find(x=>x.id===l.product_id);const left=Number(l.quantity)-(returned[l.id]||0);
    const row=document.createElement('div');row.className='sd-line';
    row.innerHTML='<div class="sd-name">'+esc(p?p.name:'Item')+'<small>'+l.quantity+' sold at '+esc(fmtMoney(l.unit_price_minor))+(left<Number(l.quantity)?' \u00b7 '+left+' left to return':'')+'</small></div>';
    if(left>0){const st=document.createElement('div');st.className='stepper';st.dataset.line=l.id;st.dataset.max=left;
      const minus=document.createElement('button');minus.type='button';minus.textContent='\u2212';
      const qb=document.createElement('b');qb.textContent='0';
      const plus=document.createElement('button');plus.type='button';plus.textContent='+';
      minus.onclick=()=>{const v=Math.max(0,int(qb.textContent)-1);qb.textContent=v;refundCheck()};
      plus.onclick=()=>{const v=Math.min(Number(left),int(qb.textContent)+1);qb.textContent=v;refundCheck()};
      st.append(minus,qb,plus);row.appendChild(st)}
    box.appendChild(row)});
  $('#refund-reason').value='';refundCheck();
  $('#sale-detail').hidden=false;$('#sale-detail').scrollIntoView({behavior:'smooth',block:'nearest'})}
function refundCheck(){let any=false;document.querySelectorAll('#sale-detail-lines .stepper').forEach(st=>{if(int(st.querySelector('b').textContent)>0)any=true});
  $('#refund-go').disabled=!any||!$('#refund-reason').value.trim();
  if(!$('#refund-reason').oninput)$('#refund-reason').oninput=refundCheck}
function refundGo(){if(!DETAIL_SALE)return;const lines={};document.querySelectorAll('#sale-detail-lines .stepper').forEach(st=>{const q=int(st.querySelector('b').textContent);if(q>0)lines[st.dataset.line]=q});
  $('#refund-go').disabled=true;
  api('/api/retail/returns',{sale_id:DETAIL_SALE,lines,reason:$('#refund-reason').value.trim(),approved_by:'manager',refund_kind:'cash'})
    .then(x=>{notice(true,'Return refunded');$('#sale-detail').hidden=true;DETAIL_SALE=null;reload();refreshExport()})
    .catch(e=>{notice(false,e.message);refundCheck()})}
