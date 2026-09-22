const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const VIEWS={
  today:{title:'Today',sub:'Start with the task in front of you.'},
  stock:{title:'Stock',sub:'What you have, and where it is.'},
  sales:{title:'Sales',sub:'Every bill, payment and refund.'},
  buying:{title:'Buying',sub:'Orders, deliveries and supplier bills.'},
  money:{title:'Money',sub:'Till sessions and period locks.'}
};
let LISTS={stock:[],sales:[],buying:[],money:[]},CURRENCY='INR';

function api(path,body){return fetch(path,{method:'POST',headers:{'Content-Type':'application/json',...MosaicAuth.headers},body:JSON.stringify(body)}).then(r=>r.json().then(j=>{if(!r.ok)throw Error(j.error||'Could not complete');return j}))}
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
function renderSales(){const rows=LISTS.sales.map(r=>{const tr=document.createElement('tr');
  tr.appendChild(cell(r.number,'cell-main'));tr.appendChild(cell(fmtWhen(r.sold_at)));tr.appendChild(cell(r.location_code));tr.appendChild(cell(String(r.line_count),'num'));tr.appendChild(cell(fmtMoney(r.total_minor,r.currency),'num'));tr.appendChild(cell(fmtMoney(r.paid_minor,r.currency),'num'));tr.appendChild(pillCell(r.status));return tr});
  fill('sales-table',rows,'No sales yet. Ring up your first sale below.');
  $('#sales-count').textContent=LISTS.sales.length?'last '+LISTS.sales.length:'';
  const today=new Date().toDateString(),todays=LISTS.sales.filter(r=>new Date(r.sold_at).toDateString()===today);
  $('#kpi-sales').textContent=todays.length?fmtMoney(todays.reduce((a,r)=>a+r.total_minor,0),todays[0].currency):'—';
  $('#kpi-sales-sub').textContent=todays.length?todays.length+(todays.length===1?' bill':' bills')+' today':'no bills yet'}
function renderBuying(){const rows=LISTS.buying.map(r=>{const tr=document.createElement('tr');
  tr.appendChild(cell(r.number,'cell-main'));tr.appendChild(cell(r.vendor_name));tr.appendChild(cell(r.location_code));tr.appendChild(cell(fmtWhen(r.ordered_on)));tr.appendChild(cell(String(r.line_count),'num'));tr.appendChild(cell(fmtMoney(r.total_minor,r.currency),'num'));tr.appendChild(pillCell(r.status));return tr});
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

function run(path,body,okText){api(path,body).then(x=>{notice(true,okText,JSON.stringify(x,null,2));reload()}).catch(e=>notice(false,e.message))}

function connect(){if(!MosaicAuth.require())return;
  let identity=JSON.parse(localStorage.getItem('mosaicIdentity')||'{}');
  $('#company').textContent=identity.workspace_name||'Your company';
  $('#signout').onclick=()=>MosaicAuth.clear();
  Promise.all([get('/api/operations/context'),get('/api/accounting/status').catch(()=>({base_currency:'INR'}))]).then(([c,book])=>{CURRENCY=book.base_currency||'INR';
    $('#state').textContent='Ready · '+(identity.role||'your role');
    const fill=(id,rows,label)=>{$(id).innerHTML=rows.map(x=>'<option value="'+x.id+'">'+esc(label(x))+'</option>').join('')};
    fill('#locations',c.locations,x=>x.code+' · '+x.name);
    fill('#products',c.products,x=>x.sku+' · '+x.name);
    fill('#vendors',c.vendors,x=>x.name);
    fill('#orders',c.purchase_orders,x=>x.number+' · '+x.status);
    fill('#bill-options',c.open_bills,x=>x.number+' · '+x.balance_minor);
    const ol=$('#next');ol.innerHTML='';
    c.next_steps.forEach(s=>{const li=document.createElement('li');li.textContent=s;ol.appendChild(li)});
    reload()
  }).catch(e=>{$('#state').textContent='Could not open workspace';notice(false,e.message)})}

$('#stock').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/transfers',{product_id:d.product_id,from_location:d.from_location,to_location:d.to_location,quantity:d.quantity},'Stock transferred')};
$('#sell').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/sales',{location_id:d.location_id,lines:[{product_id:d.product_id,quantity:d.quantity}],tenders:[{kind:'cash',amount_minor:Math.round(+d.amount_minor*100)}],currency:CURRENCY},'Sale completed')};
$('#return').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/returns',{sale_id:d.sale_id,lines:{[d.line_id]:d.quantity},reason:d.reason,approved_by:'manager',refund_kind:'cash'},'Return refunded')};
$('#buy').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/purchases',{vendor_id:d.vendor_id,location_id:d.location_id,ordered_on:d.ordered_on,lines:[{product_id:d.product_id,quantity:d.quantity,unit_cost_minor:Math.round(+d.unit_cost_minor*100)}],currency:CURRENCY},'Purchase order saved')};
$('#receive').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/purchases/receive',{purchase_order_id:d.purchase_order_id,received:{[d.line_id]:d.quantity}},'Stock received')};
$('#bill-match').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/three-way-match',{purchase_order_id:d.purchase_order_id,bill_id:d.bill_id},'Match complete')};
$('#cash').onsubmit=e=>e.preventDefault();
$('#cash button[name=open]').onclick=()=>{let d=data($('#cash'));run('/api/retail/cash/open',{location_id:d.location_id,opening_minor:Math.round(+d.amount_minor*100)},'Till opened')};
$('#cash button[name=close]').onclick=()=>{let d=data($('#cash'));run('/api/retail/cash/close',{session_id:d.session_id,actual_minor:Math.round(+d.amount_minor*100)},'Till closed')};
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
