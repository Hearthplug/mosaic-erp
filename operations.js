const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const VIEWS={
  today:{title:'Today',sub:'Start with the task in front of you.'},
  stock:{title:'Stock',sub:'What you have, and where it is.'},
  sales:{title:'Sales',sub:'Every bill, payment and refund.'},
  buying:{title:'Buying',sub:'Orders, deliveries and supplier bills.'},
  money:{title:'Money',sub:'Tills (cash drawers) and period locks (stopping changes to a finished month).'}
};
let LISTS={stock:[],sales:[],buying:[],money:[]},CURRENCY='USD',LOW_SET=new Set();
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
function fill(tableId,rows,emptyText){const tb=$('#'+tableId+' tbody');tb.innerHTML='';if(!rows.length){const tr=document.createElement('tr');tr.className='empty-row';const td=document.createElement('td');td.colSpan=tb.closest('table').querySelectorAll('th').length;td.textContent=emptyText;tr.appendChild(td);tb.appendChild(tr);return}const heads=[...tb.closest('table').querySelectorAll('thead th')].map(th=>th.textContent.trim());rows.forEach(r=>{[...r.children].forEach((td,i)=>{if(heads[i])td.setAttribute('data-h',heads[i])});tb.appendChild(r)})}

let noticeTimer=null;
function notice(ok,text,detail){const n=$('#notice');n.hidden=false;$('#notice-text').textContent=text;$('#notice-icon-ok').hidden=!ok;$('#notice-icon-err').hidden=ok;$('#notice-json').textContent=detail||'';$('#notice-details').open=false;$('#notice-details').hidden=!detail;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>{n.hidden=true},6000)}
$('#notice-close').onclick=()=>{$('#notice').hidden=true;clearTimeout(noticeTimer)};

function select(name){if(!VIEWS[name])name='today';
  $$('.rail-item[data-view]').forEach(b=>b.classList.toggle('on',b.dataset.view===name));
  $$('.view').forEach(v=>v.hidden=v.id!=='view-'+name);
  $('#page-title').textContent=VIEWS[name].title;$('#page-crumb').textContent=VIEWS[name].title;$('#page-sub').textContent=VIEWS[name].sub;
  if(('#'+name)!==location.hash)history.replaceState(null,'','#'+name)}
$$('.rail-item[data-view]').forEach(b=>b.onclick=()=>select(b.dataset.view));
const sf=$('#sales-from'),sto=$('#sales-to');if(sf){sf.onchange=()=>{SALES_FROM=sf.value;renderSales()};sto.onchange=()=>{SALES_TO=sto.value;renderSales()}}
addEventListener('hashchange',()=>select(location.hash.slice(1)));

function renderStock(){const rows=LISTS.stock.map(r=>{const tr=document.createElement('tr');if(LOW_SET.has(r.location_id+':'+r.product_id))tr.dataset.low='1';
  tr.appendChild(cell(r.name,'',r.sku));tr.appendChild(cell(r.location_name,'',r.location_code));tr.appendChild(cell(fmtQty(r.on_hand)+(r.unit&&r.unit!=='each'?' '+r.unit:''),'num'));return tr});
  fill('stock-table',rows,'No items yet. Your first delivery appears here.');
  $('#stock-count').textContent=LISTS.stock.length?LISTS.stock.length+' rows':'';
  $('#kpi-stock').textContent=LISTS.stock.length?fmtQty(LISTS.stock.reduce((a,r)=>a+Number(r.on_hand||0),0)):'0';if($('#move-tiles'))moveRender()}
let SALES_FROM='',SALES_TO='';
function renderSales(){const vis=LISTS.sales.filter(r=>{const d=(r.sold_at||'').slice(0,10);return (!SALES_FROM||d>=SALES_FROM)&&(!SALES_TO||d<=SALES_TO)});const rows=vis.map(r=>{const tr=document.createElement('tr');tr.className='sale-openable';tr.title='Tap to see the bill or refund items';tr.onclick=()=>openSaleDetail(r.id);
  tr.appendChild(cell(r.number,'cell-main'));tr.appendChild(cell(fmtWhen(r.sold_at)));tr.appendChild(cell(r.location_code));tr.appendChild(cell(String(r.line_count),'num'));tr.appendChild(cell(fmtMoney(r.total_minor,r.currency),'num'));tr.appendChild(cell(fmtMoney(r.paid_minor,r.currency),'num'));tr.appendChild(pillCell(r.status));return tr});
  fill('sales-table',rows,'No sales yet. Make your first sale on the till below.');
  $('#sales-count').textContent=vis.length?((SALES_FROM||SALES_TO)?vis.length+' in range':'last '+vis.length):'';
  const today=new Date().toDateString(),todays=LISTS.sales.filter(r=>new Date(r.sold_at).toDateString()===today);
  $('#kpi-sales').textContent=todays.length?fmtMoney(todays.reduce((a,r)=>a+r.total_minor,0),todays[0].currency):'—';
  $('#kpi-sales-sub').textContent=todays.length?todays.length+(todays.length===1?' bill':' bills')+' today':'no bills yet'}
function renderBuying(){const rows=LISTS.buying.map(r=>{const tr=document.createElement('tr');tr.className='sale-openable'+(REC_PO===r.id?' po-picked':'');tr.title='Tap to confirm what arrived';tr.onclick=()=>openReceive(r.id);
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
  if($('#cash-sessions'))cashRender();
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

const XLSX={crc:(()=>{const t=[];for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0}return t})(),
crc32(s){let c=0xFFFFFFFF;for(let i=0;i<s.length;i++)c=this.crc[(c^s.charCodeAt(i))&0xFF]^(c>>>8);return (c^0xFFFFFFFF)>>>0},
zip(files){const enc=s=>unescape(encodeURIComponent(s));let out=[],central=[],off=0;
files.forEach(f=>{const name=enc(f.name),data=enc(f.data),crc=this.crc32(data),head=[0x50,0x4b,3,4,20,0,0,0,0,0,0,0,0,0,crc&255,crc>>>8&255,crc>>>16&255,crc>>>24&255,data.length&255,data.length>>>8&255,data.length>>>16&255,data.length>>>24&255,data.length&255,data.length>>>8&255,data.length>>>16&255,data.length>>>24&255,name.length&255,name.length>>>8&255,0,0];
out=out.concat(head);for(let i=0;i<name.length;i++)out.push(name.charCodeAt(i));for(let i=0;i<data.length;i++)out.push(data.charCodeAt(i));
const cd=[0x50,0x4b,1,2,20,0,20,0,0,0,0,0,0,0,0,0,crc&255,crc>>>8&255,crc>>>16&255,crc>>>24&255,data.length&255,data.length>>>8&255,data.length>>>16&255,data.length>>>24&255,data.length&255,data.length>>>8&255,data.length>>>16&255,data.length>>>24&255,name.length&255,name.length>>>8&255,0,0,0,0,0,0,0,0,0,0,0,0,off&255,off>>>8&255,off>>>16&255,off>>>24&255];
central=central.concat(cd);for(let i=0;i<name.length;i++)central.push(name.charCodeAt(i));off+=head.length+name.length+data.length});
const end=[0x50,0x4b,5,6,0,0,0,0,files.length&255,files.length>>>8&255,files.length&255,files.length>>>8&255,central.length&255,central.length>>>8&255,central.length>>>16&255,central.length>>>24&255,off&255,off>>>8&255,off>>>16&255,off>>>24&255,0,0];
const bytes=new Uint8Array(out.concat(central,end));return bytes},
col(n){let s='';n++;while(n>0){const m=(n-1)%26;s=String.fromCharCode(65+m)+s;n=(n-1-m)/26|0}return s},
esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))},
sheet(rows){let xml='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>';
rows.forEach((r,ri)=>{xml+='<row r="'+(ri+1)+'">';r.forEach((v,ci)=>{const ref=this.col(ci)+(ri+1);const num=typeof v==='number'&&isFinite(v);xml+=num?'<c r="'+ref+'"><v>'+v+'</v></c>':'<c r="'+ref+'" t="inlineStr"><is><t xml:space="preserve">'+this.esc(v)+'</t></is></c>'});xml+='</row>'});
return xml+'</sheetData></worksheet>'},
blob(rows){const files=[
{name:'[Content_Types].xml',data:'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'},
{name:'_rels/.rels',data:'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'},
{name:'xl/workbook.xml',data:'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Export" sheetId="1" r:id="rId1"/></sheets></workbook>'},
{name:'xl/_rels/workbook.xml.rels',data:'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'},
{name:'xl/worksheets/sheet1.xml',data:this.sheet(rows)}];
return new Blob([this.zip(files)],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})}};

function refreshExport(){return get('/api/retail/export').then(x=>{EXP=x;PO_LINES={};(x.purchase_order_lines||[]).forEach(l=>{(PO_LINES[l.purchase_order_id]=PO_LINES[l.purchase_order_id]||[]).push(l)});tillRenderTiles();if($('#move-tiles'))moveRender();if($('#buy-tiles'))buyRender()}).catch(()=>{})}
function productLabel(id){const o=IDBY_LABEL['prodbyid:'+id];return o||id}
function updateMoneyLabels(){document.querySelectorAll('label').forEach(l=>{if(['Cash received','Unit cost','Amount'].includes(l.childNodes[0].textContent.trim()))l.childNodes[0].textContent=l.childNodes[0].textContent.trim()+' ('+CURRENCY+')'})}
function connect(){if(!MosaicAuth.require())return;
  let identity=JSON.parse(localStorage.getItem('mosaicIdentity')||'{}');
  $('#company').textContent=identity.workspace_name||'Your company';
  $('#signout').onclick=()=>MosaicAuth.clear();
  Promise.all([get('/api/operations/context'),get('/api/accounting/status').catch(()=>({base_currency:'USD'}))]).then(async([c,book])=>{CURRENCY=book.base_currency||'USD';updateMoneyLabels();
    $('#state').textContent='Ready · '+(identity.role||'your role');
    refreshLists(c);tillSetup(c.locations||[]);moveSetup();buySetup(c.vendors||[]);cashSetup();
    Promise.all((c.locations||[]).map(l=>get('/api/retail/reorder?location_id='+encodeURIComponent(l.id)).then(r=>(r.items||[]).forEach(i=>{if(Number(i.suggested)>0)LOW_SET.add(l.id+':'+i.product_id)})).catch(()=>{}))).then(()=>renderStock());
    const ol=$('#next');ol.innerHTML='';ol.classList.remove('checklist');
    if(!c.products.length){
      ol.classList.add('checklist');
      const steps=[
        {label:'Add your first item',view:'stock',done:false},
        {label:'Add a store to sell from',view:'stock',done:(c.locations||[]).length>0},
        {label:'Open a till to take cash',view:'money',done:(c.cash_sessions||[]).length>0},
        {label:'Ring up your first sale',view:'sales',done:false}
      ];
      steps.forEach(s=>{const li=document.createElement('li');li.className='todo-step'+(s.done?' done':'');li.textContent=s.label;li.onclick=()=>select(s.view);ol.appendChild(li)});
    }else{
      ol.classList.add('checklist');
      const tasks=[];
      const lowSet=new Set();
      await Promise.all((c.locations||[]).map(l=>get('/api/retail/reorder?location_id='+encodeURIComponent(l.id)).then(r=>(r.items||[]).forEach(i=>{if(Number(i.suggested)>0)lowSet.add(i.product_id)})).catch(()=>{})));
      if(lowSet.size)tasks.push({label:lowSet.size+(lowSet.size===1?' item':' items')+' running low - reorder soon',view:'stock'});
      (c.cash_sessions||[]).forEach(s=>{const t=new Date(s.opened_at);const clock=t.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});tasks.push({label:'1 till still open at '+s.location_name+' since '+clock,view:'money'})});
      const drafts=(c.purchase_orders||[]).filter(o=>o.status==='draft').length;
      if(drafts)tasks.push({label:drafts+(drafts===1?' draft order':' draft orders')+' to approve',view:'buying'});
      const unpaid=(c.open_bills||[]).filter(b=>Number(b.balance_minor)>0).length;
      if(unpaid)tasks.push({label:unpaid+(unpaid===1?' supplier bill':' supplier bills')+' unpaid',view:'buying'});
      if(!tasks.length){const li=document.createElement('li');li.className='todo-step done';li.textContent='All caught up';ol.appendChild(li)}
      tasks.forEach(t=>{const li=document.createElement('li');li.className='todo-step';li.textContent=t.label;li.onclick=()=>select(t.view);ol.appendChild(li)});
    }
    reload();refreshExport()
  }).catch(e=>{$('#state').textContent='Could not open workspace';notice(false,e.message)})}


$('#bill-match').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/three-way-match',{purchase_order_id:resolveId('po',d.purchase_order_id),bill_id:resolveId('bill',d.bill_id)},'Match complete')};
$('#add-vendor').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/accounting/parties',{kind:'vendor',name:d.name},'Supplier added');e.target.reset()};
$('#add-item').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/products',{sku:d.sku,name:d.name,selling_price_minor:Math.round(+d.price*100),cost_minor:Math.round(+d.cost*100)},'Item added');e.target.reset()};
$('#add-location').onsubmit=e=>{e.preventDefault();let d=data(e.target);run('/api/retail/locations',{code:d.code.toUpperCase(),name:d.name,kind:'store'},'Store added');e.target.reset()};
const periodChips=$('#period-chips'),periodLockId=$('#period-lock-id'),periodLockBtn=$('#close button[type=submit]');
const loadPeriods=async()=>{const ps=await get('/api/accounting/periods');periodChips.innerHTML='';const today=new Date().toISOString().slice(0,10);const open=ps.filter(p=>p.status==='open');const lockable=open.filter(p=>p.ends_on<today);const running=open.filter(p=>p.ends_on>=today);if(!lockable.length){periodChips.innerHTML='<span class="hint">No finished periods to lock yet</span>';}lockable.forEach(p=>{const b=document.createElement('button');b.type='button';b.className='chip';b.textContent=p.name+' ('+p.starts_on+' to '+p.ends_on+')';b.onclick=()=>{periodChips.querySelectorAll('.chip').forEach(c=>c.classList.remove('on'));b.classList.add('on');periodLockId.value=p.id;periodLockBtn.disabled=false;};periodChips.appendChild(b);});running.forEach(p=>{const s=document.createElement('span');s.className='hint';s.textContent=p.name+' is still running - it can be locked after '+p.ends_on+'.';periodChips.appendChild(s);});};
$('#close').onsubmit=e=>{e.preventDefault();if(!periodLockId.value)return;run('/api/accounting/periods/lock',{period_id:periodLockId.value},'Period locked').then(()=>{periodLockId.value='';periodLockBtn.disabled=true;loadPeriods();});};
loadPeriods();

select(location.hash.slice(1)||'today');
connect();


function tableRows(table){return [...table.tBodies[0].rows].filter(r=>!r.classList.contains('empty-row'))}
$$('.toolbar').forEach(bar=>{
  const table=$('#'+bar.dataset.table),input=bar.querySelector('input[type=search]');
  const apply=()=>{const term=input.value.trim().toLowerCase(),filter=bar.querySelector('.filter-chip.on')?.dataset.filter||'all';tableRows(table).forEach(row=>{const text=row.textContent.toLowerCase();row.hidden=!(text.includes(term)&&(filter==='all'||(filter==='low'?row.dataset.low==='1':text.includes(filter))))})};
  input.addEventListener('input',apply);
  bar.querySelectorAll('.filter-chip:not(:disabled)').forEach(btn=>btn.onclick=()=>{bar.querySelectorAll('.filter-chip').forEach(x=>x.classList.remove('on'));btn.classList.add('on');apply()});
  const menu=document.createElement('div');menu.className='export-menu';menu.hidden=true;menu.innerHTML='<button type="button" data-kind="csv">CSV file</button><button type="button" data-kind="xlsx">XLSX file (Excel)</button>';bar.appendChild(menu);
  const btn=bar.querySelector('.export-btn');btn.textContent='Export ▾';btn.title='Download this table as a CSV or XLSX file';
  const visibleRows=()=>[...table.rows].filter(r=>!r.hidden&&!r.classList.contains('empty-row'));
  const grid=()=>visibleRows().map(row=>[...row.cells].map(c=>c.innerText.trim()));
  const save=(blob,name)=>{const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),0)};
  btn.onclick=e=>{e.stopPropagation();menu.hidden=!menu.hidden};
  document.addEventListener('click',()=>{menu.hidden=true});
  menu.onclick=e=>{const kind=e.target.dataset.kind;if(!kind)return;menu.hidden=true;const rows=grid();const stem=table.id.replace('-table','')+'-'+new Date().toISOString().slice(0,10);
    if(kind==='csv'){const csv=rows.map(r=>r.map(c=>'"'+c.replaceAll('"','""')+'"').join(',')).join('\n');save(new Blob([csv],{type:'text/csv'}),stem+'.csv')}
    else{save(XLSX.blob(rows),stem+'.xlsx')}};
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

/* ===== Move stock (pick-first) ===== */
let MOVE={product:null,from:null,to:null,qty:1};
function stockOnHand(pid,locId){let n=0;LISTS.stock.forEach(r=>{const p=(EXP.retail_products||[]).find(x=>x.sku===r.sku);if(!p||p.id!==pid)return;if(locId&&r.location_code!==(TILL_LOCS.find(l=>l.id===locId)||{}).code)return;n+=Number(r.on_hand||0)});return n}
function moveSetup(){const s=$('#move-search');if(!s)return;s.oninput=moveRender;
  $('#move-minus').onclick=()=>{MOVE.qty=Math.max(1,MOVE.qty-1);moveRender()};
  $('#move-plus').onclick=()=>{const cap=MOVE.from?stockOnHand(MOVE.product,MOVE.from):Infinity;MOVE.qty=Math.min(cap===0?1:cap,MOVE.qty+1);moveRender()};
  $('#move-go').onclick=moveGo;moveRender()}
function moveRender(){const box=$('#move-tiles');if(!box)return;const q=($('#move-search').value||'').toLowerCase();
  const prods=tillProducts().filter(p=>!q||String(p.name).toLowerCase().includes(q)||String(p.sku).toLowerCase().includes(q));
  box.innerHTML=prods.length?'':'<p class="tilegrid-empty">No items match.</p>';
  prods.forEach(p=>{const b=document.createElement('button');b.type='button';b.className='tile'+(MOVE.product===p.id?' incart':'');
    const oh=stockOnHand(p.id,MOVE.from||null);
    b.innerHTML='<b>'+esc(p.name)+'</b><span>'+(MOVE.from?'At this store: ':'On hand: ')+fmtQty(oh)+'</span>';
    b.onclick=()=>{MOVE.product=p.id;MOVE.qty=1;moveRender()};box.appendChild(b)});
  const chips=(id,cur,cb)=>{const el=$(id);el.innerHTML='';TILL_LOCS.forEach(l=>{const c=document.createElement('button');c.type='button';c.className='chip'+(cur===l.id?' on':'');c.textContent=l.code;c.title=l.name;c.onclick=()=>cb(l.id);el.appendChild(c)})};
  chips('#move-from',MOVE.from,v=>{if(MOVE.to===v)MOVE.to=null;MOVE.from=v;MOVE.qty=1;moveRender()});
  chips('#move-to',MOVE.to,v=>{MOVE.to=v;moveRender()});
  $('#move-qty').textContent=MOVE.qty;
  const p=tillProducts().find(x=>x.id===MOVE.product);const go=$('#move-go');
  const cap=MOVE.from&&p?stockOnHand(p.id,MOVE.from):null;
  const ok=p&&MOVE.from&&MOVE.to&&MOVE.from!==MOVE.to&&MOVE.qty>=1&&(cap===null||cap>0);
  go.disabled=!ok;
  go.textContent=!p?'Move stock':(!MOVE.from||!MOVE.to)?'Pick both stores':(MOVE.from===MOVE.to?'Pick two different stores':(cap===0?'Nothing at that store':'Move '+MOVE.qty+' \u00d7 '+p.name))}
function moveGo(){const p=tillProducts().find(x=>x.id===MOVE.product);if(!p)return;$('#move-go').disabled=true;
  api('/api/retail/transfers',{product_id:MOVE.product,from_location:MOVE.from,to_location:MOVE.to,quantity:String(MOVE.qty)})
    .then(()=>{notice(true,'Moved '+MOVE.qty+' \u00d7 '+p.name);MOVE.qty=1;moveRender();reload();refreshContext();refreshExport()})
    .catch(e=>{notice(false,e.message);moveRender()})}

/* ===== Order from a supplier (pick-first) ===== */
let BUY={vendor:null,store:null,lines:new Map()},VENDORS=[];
function buySetup(vendors){VENDORS=vendors||[];const s=$('#buy-search');if(!s)return;s.oninput=buyRender;
  $('#buy-date').value=new Date().toISOString().slice(0,10);
  $('#buy-go').onclick=buyGo;buyRender()}
function buyRender(){const vb=$('#buy-vendor');if(!vb)return;
  vb.innerHTML='';VENDORS.forEach(v=>{const c=document.createElement('button');c.type='button';c.className='chip'+(BUY.vendor===v.id?' on':'');c.textContent=v.name;c.onclick=()=>{BUY.vendor=v.id;buyRender()};vb.appendChild(c)});
  if(!VENDORS.length)vb.innerHTML='<span class="hint">Add a supplier below first.</span>';
  const sb=$('#buy-store');sb.innerHTML='';TILL_LOCS.forEach(l=>{const c=document.createElement('button');c.type='button';c.className='chip'+(BUY.store===l.id?' on':'');c.textContent=l.code;c.title=l.name;c.onclick=()=>{BUY.store=l.id;buyRender()};sb.appendChild(c)});
  if(!BUY.store&&TILL_LOCS.length===1)BUY.store=TILL_LOCS[0].id;
  const q=($('#buy-search').value||'').toLowerCase();
  const prods=tillProducts().filter(p=>!q||String(p.name).toLowerCase().includes(q)||String(p.sku).toLowerCase().includes(q));
  const tb=$('#buy-tiles');tb.innerHTML=prods.length?'':'<p class="tilegrid-empty">No items match.</p>';
  prods.forEach(p=>{const b=document.createElement('button');b.type='button';b.className='tile'+(BUY.lines.has(p.id)?' incart':'');
    const ln=BUY.lines.get(p.id);
    b.innerHTML='<b>'+esc(p.name)+'</b><span>cost '+esc(fmtMoney(p.cost_minor))+'</span>'+(ln?'<span class="tile-qty">'+ln.qty+' on order</span>':'');
    b.onclick=()=>{const cur=BUY.lines.get(p.id)||{qty:0,cost:int(p.cost_minor)};cur.qty+=1;BUY.lines.set(p.id,cur);buyRender()};tb.appendChild(b)});
  const lb=$('#buy-lines');lb.innerHTML='';
  BUY.lines.forEach((ln,pid)=>{const p=tillProducts().find(x=>x.id===pid);if(!p)return;
    const row=document.createElement('div');row.className='till-line';
    row.innerHTML='<div class="tl-name">'+esc(p.name)+'<small>'+ln.qty+' ordered</small></div>';
    const st=document.createElement('div');st.className='stepper';
    const minus=document.createElement('button');minus.type='button';minus.textContent='\u2212';minus.onclick=()=>{if(ln.qty<=1)BUY.lines.delete(pid);else ln.qty-=1;buyRender()};
    const qb=document.createElement('b');qb.textContent=ln.qty;
    const plus=document.createElement('button');plus.type='button';plus.textContent='+';plus.onclick=()=>{ln.qty+=1;buyRender()};
    st.append(minus,qb,plus);row.appendChild(st);
    const cost=document.createElement('input');cost.className='buy-cost';cost.type='text';cost.inputMode='decimal';cost.value=(ln.cost/100).toFixed(2);cost.title='Unit cost';
    cost.onchange=()=>{const v=Math.round(parseFloat(cost.value||'0')*100);ln.cost=isNaN(v)?ln.cost:v;cost.value=(ln.cost/100).toFixed(2)};
    row.appendChild(cost);lb.appendChild(row)});
  const n=BUY.lines.size;const go=$('#buy-go');
  go.disabled=!(BUY.vendor&&BUY.store&&n&&$('#buy-date').value);
  go.textContent=n?'Save purchase order ('+n+(n===1?' item':' items')+')':'Save purchase order'}

function buyGo(){if(!(BUY.vendor&&BUY.store&&BUY.lines.size))return;$('#buy-go').disabled=true;
  const lines=[...BUY.lines.entries()].map(([pid,ln])=>({product_id:pid,quantity:String(ln.qty),unit_cost_minor:ln.cost}));
  api('/api/retail/purchases',{vendor_id:BUY.vendor,location_id:BUY.store,ordered_on:$('#buy-date').value,lines,currency:CURRENCY})
    .then(x=>{notice(true,'Purchase order '+(x.number||'')+' saved');BUY.lines.clear();buyRender();reload();refreshExport();refreshContext()})
    .catch(e=>{notice(false,e.message);buyRender()})}

/* ===== Confirm what arrived (tap order -> steppers) ===== */
let REC_PO=null;
function openReceive(id){REC_PO=id;const po=LISTS.buying.find(r=>r.id===id);
  document.querySelectorAll('#buying-table tbody tr').forEach(t=>t.classList.remove('po-picked'));
  const lines=PO_LINES[id]||[];
  $('#receive-title').textContent=po?('Order '+po.number+' - '+po.vendor_name):'Order';
  const box=$('#receive-lines');box.innerHTML='';
  let anyLeft=false;
  if(!lines.length)box.innerHTML='<p class="hint">No lines on this order.</p>';
  lines.forEach(l=>{const left=Number(l.quantity)-Number(l.received_quantity||0);if(left>0)anyLeft=true;
    const row=document.createElement('div');row.className='sd-line';
    row.innerHTML='<div class="sd-name">'+esc(productLabel(l.product_id))+'<small>'+l.quantity+' ordered'+(Number(l.received_quantity)?' \u00b7 '+l.received_quantity+' already in':'')+(left>0?' \u00b7 '+left+' to come':' \u00b7 all received')+'</small></div>';
    if(left>0){const st=document.createElement('div');st.className='stepper';st.dataset.line=l.id;st.dataset.max=left;
      const minus=document.createElement('button');minus.type='button';minus.textContent='\u2212';
      const qb=document.createElement('b');qb.textContent=left;
      const plus=document.createElement('button');plus.type='button';plus.textContent='+';
      minus.onclick=()=>{qb.textContent=Math.max(0,int(qb.textContent)-1);recCheck()};
      plus.onclick=()=>{qb.textContent=Math.min(left,int(qb.textContent)+1);recCheck()};
      st.append(minus,qb,plus);row.appendChild(st)}
    box.appendChild(row)});
  $('#receive-empty').hidden=true;$('#receive-body').hidden=false;recCheck();
  $('#receive-card').scrollIntoView({behavior:'smooth',block:'nearest'});
  document.querySelectorAll('#buying-table tbody tr').forEach(t=>{if(t.firstChild&&po&&t.firstChild.textContent===po.number)t.classList.add('po-picked')})}
function recCheck(){let any=false;document.querySelectorAll('#receive-lines .stepper').forEach(st=>{if(int(st.querySelector('b').textContent)>0)any=true});
  $('#receive-go').disabled=!any;$('#receive-go').onclick=recGo}
function recGo(){if(!REC_PO)return;const received={};document.querySelectorAll('#receive-lines .stepper').forEach(st=>{const q=int(st.querySelector('b').textContent);if(q>0)received[st.dataset.line]=q});
  $('#receive-go').disabled=true;
  api('/api/retail/purchases/receive',{purchase_order_id:REC_PO,received})
    .then(()=>{notice(true,'Stock received');$('#receive-body').hidden=true;$('#receive-empty').hidden=false;REC_PO=null;reload();refreshExport();refreshContext()})
    .catch(e=>{notice(false,e.message);recCheck()})}

/* ===== Till open/close (pick-first) ===== */
let CASH={store:null,session:null};
const openSessions=()=>LISTS.money.filter(s=>s.status==='open');

const DENOMS={USD:[10000,5000,2000,1000,500,200,100,25,10,5,1],INR:[50000,20000,10000,5000,2000,1000,500,200,100],EUR:[50000,20000,10000,5000,2000,1000,500,200,100,50,20,10,5,2,1],GBP:[5000,2000,1000,500,200,100,50,20,10,5,2,1]};
let DENOM_COUNTS={};
function denomRender(){const box=$('#denom'),tog=$('#denom-toggle');if(!box)return;const ds=DENOMS[CURRENCY];tog.hidden=!ds;if(!ds)return;
  box.innerHTML='';
  ds.forEach(v=>{const row=document.createElement('div');row.className='denom-row';
    const lab=document.createElement('span');lab.className='denom-label';lab.textContent=fmtMoney(v,CURRENCY);
    const step=document.createElement('div');step.className='stepper';
    const minus=document.createElement('button');minus.type='button';minus.textContent='-';
    const cnt=document.createElement('span');cnt.className='stepper-val';cnt.textContent=String(DENOM_COUNTS[v]||0);
    const plus=document.createElement('button');plus.type='button';plus.textContent='+';
    const total=document.createElement('span');total.className='denom-total';total.textContent=fmtMoney((DENOM_COUNTS[v]||0)*v,CURRENCY);
    const bump=d=>{DENOM_COUNTS[v]=Math.max((DENOM_COUNTS[v]||0)+d,0);denomRender();denomApply()};
    minus.onclick=()=>bump(-1);plus.onclick=()=>bump(1);
    step.appendChild(minus);step.appendChild(cnt);step.appendChild(plus);
    row.appendChild(lab);row.appendChild(step);row.appendChild(total);box.appendChild(row)});
  const sum=document.createElement('div');sum.className='denom-sum';
  const tot=Object.entries(DENOM_COUNTS).reduce((a,[v,n])=>a+Number(v)*n,0);
  sum.textContent='Counted: '+fmtMoney(tot,CURRENCY);box.appendChild(sum)}
function denomApply(){const tot=Object.entries(DENOM_COUNTS).reduce((a,[v,n])=>a+Number(v)*n,0);
  $('#cash-close-amt').value=(tot/100).toFixed(2);cashRender()}

function cashSetup(){if(!$('#cash-open-amt'))return;
  const amt=(id,fn)=>{$(id).addEventListener('input',()=>{const el=$(id);el.value=el.value.replace(/[^0-9.]/g,'').replace(/(\..*)\./g,'$1');fn()})};
  amt('#cash-open-amt',cashRender);amt('#cash-close-amt',cashRender);
  $('#cash-open-go').onclick=()=>{const v=Math.round(parseFloat($('#cash-open-amt').value||'0')*100);if(!(CASH.store&&v>0))return;$('#cash-open-go').disabled=true;
    api('/api/retail/cash/open',{location_id:CASH.store,opening_minor:v})
      .then(()=>{notice(true,'Till opened with '+fmtMoney(v));$('#cash-open-amt').value='';CASH.store=null;cashRender();reload()})
      .catch(e=>{notice(false,e.message);cashRender()})};
  $('#cash-close-go').onclick=()=>{const v=Math.round(parseFloat($('#cash-close-amt').value||'0')*100);if(!(CASH.session&&$('#cash-close-amt').value))return;$('#cash-close-go').disabled=true;
    api('/api/retail/cash/close',{session_id:CASH.session,actual_minor:v})
      .then(()=>{notice(true,'Till closed');$('#cash-close-amt').value='';CASH.session=null;cashRender();reload();refreshExport()})
      .catch(e=>{notice(false,e.message);cashRender()})};
  const togBtn=$('#denom-toggle');if(togBtn)togBtn.onclick=()=>{const box=$('#denom');box.hidden=!box.hidden;if(!box.hidden)denomRender();togBtn.textContent=box.hidden?'Count by notes and coins':'Hide the note and coin counter'};
  cashRender()}
function cashRender(){if(!$('#cash-store'))return;
  const open=openSessions();
  const sb=$('#cash-store');sb.innerHTML='';
  TILL_LOCS.forEach(l=>{const hasOpen=open.some(s=>s.location_code===l.code);if(hasOpen)return;
    const c=document.createElement('button');c.type='button';c.className='chip'+(CASH.store===l.id?' on':'');c.textContent=l.code;c.title=l.name;
    c.onclick=()=>{CASH.store=l.id;cashRender()};sb.appendChild(c)});
  if(!sb.children.length)sb.innerHTML='<span class="hint">Every store already has an open till.</span>';
  if(CASH.store&&open.some(s=>{const l=TILL_LOCS.find(x=>x.id===CASH.store);return l&&s.location_code===l.code}))CASH.store=null;
  const cb=$('#cash-sessions');cb.innerHTML='';
  if(!open.length)cb.innerHTML='<span class="hint">No open tills. Open one on the left first.</span>';
  open.forEach(s=>{const c=document.createElement('button');c.type='button';c.className='chip'+(CASH.session===s.id?' on':'');
    c.textContent=s.location_code+' \u00b7 opened '+fmtWhen(s.opened_at)+(s.expected_minor!=null?' \u00b7 should have '+fmtMoney(s.expected_minor):'');
    c.onclick=()=>{CASH.session=s.id;cashRender()};cb.appendChild(c)});
  const openAmt=$('#cash-open-amt').value.trim();
  $('#cash-open-go').disabled=!(CASH.store&&openAmt&&parseFloat(openAmt)>0);
  $('#cash-open-go').textContent=CASH.store?'Open till':'Pick a store';
  const ses=open.find(s=>s.id===CASH.session);
  const closeAmt=$('#cash-close-amt').value.trim();
  const diff=$('#cash-diff');
  if(ses&&closeAmt&&ses.expected_minor!=null){const counted=Math.round(parseFloat(closeAmt)*100);const d=counted-ses.expected_minor;
    diff.innerHTML=d===0?'Matches the books exactly.':(d>0?'<b>'+esc(fmtMoney(d))+'</b> more than the books expect.':'<b>'+esc(fmtMoney(-d))+'</b> short of what the books expect.')}
  else diff.textContent=ses?'Count the drawer and type what you find.':'';
  $('#cash-close-go').disabled=!(ses&&closeAmt);
  $('#cash-close-go').textContent=ses?'Close '+ses.location_code+' till':'Pick an open session'}
