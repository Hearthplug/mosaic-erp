"""Persistent operational retail flows for Mosaic ERP's real-product target."""
from decimal import Decimal, ROUND_HALF_UP
import threading
import secrets
from store import utcnow, Conflict, NotFound

def ident(p): return p+'_'+secrets.token_hex(8)
class Retail:
 def __init__(self,store,books): self.s,self.books=store,books;self._operation_lock=threading.RLock()
 def setup_location(self,wid,actor,code,name,kind='store'):
  x=ident('loc')
  with self.s.tx(): self.s._db.execute('INSERT INTO locations(id,workspace_id,code,name,kind) VALUES(?,?,?,?,?)',(x,wid,code,name,kind));self.s._audit(wid,actor,'location.create',{'id':x,'code':code})
  return {'id':x,'code':code,'name':name}
 def product(self,wid,actor,sku,name,selling_price_minor,cost_minor,**x):
  p=ident('prd')
  with self.s.tx(): self.s._db.execute('INSERT INTO retail_products(id,workspace_id,sku,name,barcode,unit,selling_price_minor,cost_minor,tax_code_id,inventory_account_id,cogs_account_id,income_account_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(p,wid,sku,name,x.get('barcode'),x.get('unit','each'),int(selling_price_minor),int(cost_minor),x.get('tax_code_id'),x.get('inventory_account_id'),x.get('cogs_account_id'),x.get('income_account_id')));self.s._audit(wid,actor,'product.create',{'id':p,'sku':sku})
  return {'id':p,'sku':sku,'name':name}
 def stock(self,wid,product_id,location_id):
  r=self.s._db.execute('SELECT COALESCE(SUM(CAST(quantity_delta AS REAL)),0) q FROM stock_ledger WHERE workspace_id=? AND product_id=? AND location_id=?',(wid,product_id,location_id)).fetchone();return Decimal(str(r['q']))
 def move_stock(self,wid,actor,product_id,location_id,quantity,unit_cost_minor,kind,source_type,source_id,allow_negative=False):
  q=Decimal(str(quantity)); after=self.stock(wid,product_id,location_id)+q
  if after<0 and not allow_negative: raise Conflict('insufficient stock')
  m=ident('stk')
  with self.s.tx(): self.s._db.execute('INSERT INTO stock_ledger(id,workspace_id,product_id,location_id,effective_at,quantity_delta,unit_cost_minor,kind,source_type,source_id,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(m,wid,product_id,location_id,utcnow(),str(q),int(unit_cost_minor),kind,source_type,source_id,actor,utcnow()));self.s._audit(wid,actor,'stock.move',{'id':m,'product_id':product_id,'quantity':str(q),'balance':str(after)})
  return {'id':m,'balance':str(after)}
 def purchase_order(self,wid,actor,vendor_id,location_id,ordered_on,lines,currency='USD'):
  po=ident('po'); number=self.books._next(wid,'purchase_bill').replace('BILL-','PO-')
  with self.s.tx():
   self.s._db.execute('INSERT INTO purchase_orders(id,workspace_id,number,vendor_id,location_id,ordered_on,status,currency,created_by,created_at) VALUES(?,?,?,?,?,?,\'draft\',?,?,?)',(po,wid,number,vendor_id,location_id,ordered_on,currency,actor,utcnow()))
   for x in lines:self.s._db.execute('INSERT INTO purchase_order_lines(id,purchase_order_id,product_id,quantity,unit_cost_minor,tax_code_id) VALUES(?,?,?,?,?,?)',(ident('pol'),po,x['product_id'],str(x['quantity']),int(x['unit_cost_minor']),x.get('tax_code_id')))
   self.s._audit(wid,actor,'purchase.create',{'id':po,'number':number})
  return {'id':po,'number':number,'status':'draft'}
 def approve_purchase(self,wid,actor,po):
  with self.s.tx():
   if self.s._db.execute("UPDATE purchase_orders SET status='approved',approved_by=? WHERE id=? AND workspace_id=? AND status='draft'",(actor,po,wid)).rowcount!=1:raise Conflict('purchase order must be draft')
   self.s._audit(wid,actor,'purchase.approve',{'id':po})
 def receive_purchase(self,wid,actor,po,received):
  with self.s.tx():
   self.s.accounting_lock(wid,'purchase:'+po)
   return self._receive_purchase(wid,actor,po,received)
 def _receive_purchase(self,wid,actor,po,received):
  order=self.s._db.execute('SELECT * FROM purchase_orders WHERE id=? AND workspace_id=?',(po,wid)).fetchone()
  if not order or order['status'] not in ('approved','part_received'):raise Conflict('purchase order is not receivable')
  for line_id,qty in received.items():
   line=self.s._db.execute('SELECT l.* FROM purchase_order_lines l JOIN purchase_orders p ON p.id=l.purchase_order_id WHERE l.id=? AND l.purchase_order_id=? AND p.workspace_id=?',(line_id,po,wid)).fetchone(); new=Decimal(line['received_quantity'])+Decimal(str(qty))
   if new>Decimal(line['quantity']):raise Conflict('receipt exceeds order')
   self.move_stock(wid,actor,line['product_id'],order['location_id'],qty,line['unit_cost_minor'],'receipt','purchase_order',po+'-'+line_id+'-'+str(new))
   with self.s.tx():
    changed=self.s._db.execute('UPDATE purchase_order_lines SET received_quantity=? WHERE id=? AND purchase_order_id=? AND EXISTS (SELECT 1 FROM purchase_orders p WHERE p.id=purchase_order_id AND p.workspace_id=?)',(str(new),line_id,po,wid)).rowcount
    if changed!=1:raise Conflict('purchase order line was not updated')
  left=self.s._db.execute('SELECT COUNT(*) n FROM purchase_order_lines l JOIN purchase_orders p ON p.id=l.purchase_order_id WHERE l.purchase_order_id=? AND p.workspace_id=? AND CAST(l.received_quantity AS REAL)<CAST(l.quantity AS REAL)',(po,wid)).fetchone()['n'];status='part_received' if left else 'received'
  with self.s.tx():
   if self.s._db.execute('UPDATE purchase_orders SET status=? WHERE id=? AND workspace_id=?',(status,po,wid)).rowcount!=1:raise Conflict('purchase order status was not updated')
   self.s._audit(wid,actor,'purchase.receive',{'id':po,'status':status})
  return {'id':po,'status':status}
 def complete_sale(self,wid,actor,location_id,lines,tenders,customer_id=None,currency='USD'):
  with self._operation_lock,self.s.tx():
   for x in sorted(lines,key=lambda y:y['product_id']):self.s.accounting_lock(wid,'stock:'+location_id+':'+x['product_id'])
   return self._complete_sale(wid,actor,location_id,lines,tenders,customer_id,currency)
 def _complete_sale(self,wid,actor,location_id,lines,tenders,customer_id=None,currency='USD'):
  sale=ident('sale'); number=self.books._next(wid,'sales_invoice'); computed=[]; sub=tax=0
  for x in lines:
   p=self.s._db.execute('SELECT * FROM retail_products WHERE id=? AND workspace_id=?',(x['product_id'],wid)).fetchone()
   if not p:raise NotFound('product not found')
   q=Decimal(str(x['quantity']));net=int((q*int(x.get('unit_price_minor',p['selling_price_minor']))).quantize(Decimal('1')))-int(x.get('discount_minor',0));t=0
   if p['tax_code_id']:
    tr=self.s._db.execute('SELECT rate_bps FROM tax_codes WHERE id=?',(p['tax_code_id'],)).fetchone();t=int((Decimal(net)*tr['rate_bps']/10000).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
   computed.append((p,q,net,t));sub+=net;tax+=t
  total=sub+tax;paid=sum(int(x['amount_minor']) for x in tenders)
  if paid!=total:raise Conflict('tenders must equal sale total')
  with self.s.tx():
   self.s._db.execute('INSERT INTO sales(id,workspace_id,number,location_id,customer_id,sold_at,status,currency,subtotal_minor,tax_minor,total_minor,paid_minor,created_by) VALUES(?,?,?,?,?,?,\'completed\',?,?,?,?,?,?)',(sale,wid,number,location_id,customer_id,utcnow(),currency,sub,tax,total,paid,actor))
   for p,q,net,t in computed:self.s._db.execute('INSERT INTO sale_lines(id,sale_id,product_id,quantity,unit_price_minor,discount_minor,tax_minor,total_minor,cost_minor) VALUES(?,?,?,?,?,?,?,?,?)',(ident('sln'),sale,p['id'],str(q),p['selling_price_minor'],0,t,net+t,p['cost_minor']))
   for x in tenders:self.s._db.execute('INSERT INTO tender_entries(id,workspace_id,sale_id,kind,amount_minor,reference,received_at,actor_id) VALUES(?,?,?,?,?,?,?,?)',(ident('ten'),wid,sale,x['kind'],int(x['amount_minor']),x.get('reference'),utcnow(),actor))
  cogs=sum(int((q*p['cost_minor']).quantize(Decimal('1'))) for p,q,net,t in computed)
  for p,q,net,t in computed:self.move_stock(wid,actor,p['id'],location_id,-q,p['cost_minor'],'sale','sale',sale)
  cash_lines=[]
  for tnd in tenders: cash_lines.append({'account_id':self.books._system(wid,'cash' if tnd['kind']=='cash' else 'bank'),'debit_minor':int(tnd['amount_minor'])})
  cash_lines.append({'account_id':self.books._system(wid,'sales'),'credit_minor':sub})
  if tax:cash_lines.append({'account_id':self.books._system(wid,'sales_tax'),'credit_minor':tax})
  if cogs:cash_lines.extend([{'account_id':self.books._system(wid,'cogs'),'debit_minor':cogs},{'account_id':self.books._system(wid,'inventory'),'credit_minor':cogs}])
  journal=self.books.post_journal(wid,actor,utcnow()[:10],'POS sale '+number,cash_lines,'sale',sale,number,currency)
  self.s._audit(wid,actor,'sale.complete',{'id':sale,'number':number,'total_minor':total,'journal_id':journal['id'],'cogs_minor':cogs})
  return {'id':sale,'number':number,'total_minor':total,'paid_minor':paid,'journal_id':journal['id'],'cogs_minor':cogs}

 def set_credit(self,wid,actor,party_id,limit_minor,terms_days=0,blocked=False):
  with self.s.tx():
   self.s._db.execute('INSERT INTO credit_policies(workspace_id,party_id,limit_minor,terms_days,blocked) VALUES(?,?,?,?,?) ON CONFLICT(workspace_id,party_id) DO UPDATE SET limit_minor=excluded.limit_minor,terms_days=excluded.terms_days,blocked=excluded.blocked',(wid,party_id,int(limit_minor),int(terms_days),int(blocked)));self.s._audit(wid,actor,'credit.policy',{'party_id':party_id,'limit_minor':int(limit_minor),'blocked':blocked})
 def check_credit(self,wid,party_id,new_amount_minor):
  p=self.s._db.execute('SELECT * FROM credit_policies WHERE workspace_id=? AND party_id=?',(wid,party_id)).fetchone()
  if not p:return True
  outstanding=int(self.s._db.execute("SELECT COALESCE(SUM(balance_minor),0) n FROM documents WHERE workspace_id=? AND party_id=? AND kind IN ('sales_invoice','debit_note') AND status='posted'",(wid,party_id)).fetchone()['n'])
  if p['blocked'] or outstanding+int(new_amount_minor)>p['limit_minor']:raise Conflict('customer credit limit exceeded or account blocked')
  return True
 def open_cash(self,wid,actor,location_id,opening_minor):
  if self.s._db.execute("SELECT 1 FROM cash_sessions WHERE workspace_id=? AND location_id=? AND status='open'",(wid,location_id)).fetchone():raise Conflict('cash session already open')
  x=ident('cash');
  with self.s.tx():self.s._db.execute("INSERT INTO cash_sessions(id,workspace_id,location_id,opened_by,opened_at,opening_minor,status) VALUES(?,?,?,?,?,?,'open')",(x,wid,location_id,actor,utcnow(),int(opening_minor)));self.s._audit(wid,actor,'cash.open',{'id':x,'opening_minor':int(opening_minor)})
  return {'id':x,'status':'open'}
 def close_cash(self,wid,actor,session_id,actual_minor):
  x=self.s._db.execute("SELECT * FROM cash_sessions WHERE id=? AND workspace_id=? AND status='open'",(session_id,wid)).fetchone()
  if not x:raise Conflict('open cash session required')
  tenders=int(self.s._db.execute("SELECT COALESCE(SUM(t.amount_minor),0) n FROM tender_entries t JOIN sales s ON s.id=t.sale_id WHERE t.workspace_id=? AND s.location_id=? AND t.kind IN ('cash','refund_cash') AND t.received_at>=?",(wid,x['location_id'],x['opened_at'])).fetchone()['n']); expected=int(x['opening_minor'])+tenders;variance=int(actual_minor)-expected
  with self.s.tx():
   if self.s._db.execute("UPDATE cash_sessions SET status='closed',closed_by=?,closed_at=?,expected_minor=?,actual_minor=?,variance_minor=? WHERE id=? AND workspace_id=? AND status='open'",(actor,utcnow(),expected,int(actual_minor),variance,session_id,wid)).rowcount!=1:raise Conflict('cash session was not closed')
   self.s._audit(wid,actor,'cash.close',{'id':session_id,'expected_minor':expected,'actual_minor':int(actual_minor),'variance_minor':variance})
  return {'id':session_id,'expected_minor':expected,'actual_minor':int(actual_minor),'variance_minor':variance}
 def transfer(self,wid,actor,product_id,from_location,to_location,quantity):
  p=self.s._db.execute('SELECT cost_minor FROM retail_products WHERE id=? AND workspace_id=?',(product_id,wid)).fetchone();x=ident('xfer');self.move_stock(wid,actor,product_id,from_location,-Decimal(str(quantity)),p['cost_minor'],'transfer_out','transfer',x);self.move_stock(wid,actor,product_id,to_location,quantity,p['cost_minor'],'transfer_in','transfer',x);return {'id':x}
 def reorder(self,wid,location_id,minimum=5):
  rows=self.s._db.execute('SELECT id,sku,name FROM retail_products WHERE workspace_id=? AND active=1',(wid,)).fetchall();return [{'product_id':r['id'],'sku':r['sku'],'name':r['name'],'on_hand':str(self.stock(wid,r['id'],location_id)),'suggested':str(max(Decimal(str(minimum))-self.stock(wid,r['id'],location_id),0))} for r in rows if self.stock(wid,r['id'],location_id)<Decimal(str(minimum))]
 def count_stock(self,wid,actor,location_id,counts,approved_by):
  cid=ident('cnt')
  with self.s.tx():self.s._db.execute("INSERT INTO stock_counts(id,workspace_id,location_id,status,created_by,approved_by,created_at) VALUES(?,?,?,'approved',?,?,?)",(cid,wid,location_id,actor,approved_by,utcnow()))
  for product_id,counted in counts.items():
   expected=self.stock(wid,product_id,location_id);self.s._db.execute('INSERT INTO stock_count_lines(id,stock_count_id,product_id,expected_quantity,counted_quantity) VALUES(?,?,?,?,?)',(ident('cln'),cid,product_id,str(expected),str(counted)));delta=Decimal(str(counted))-expected
   if delta:self.move_stock(wid,approved_by,product_id,location_id,delta,0,'count_adjustment','stock_count',cid+'-'+product_id)
  with self.s.tx():
   if self.s._db.execute("UPDATE stock_counts SET status='posted' WHERE id=? AND workspace_id=? AND status='approved'",(cid,wid)).rowcount!=1:raise Conflict('stock count was not posted')
   self.s._audit(wid,approved_by,'stock.count.post',{'id':cid})
  return {'id':cid,'status':'posted'}
 def return_sale(self,wid,actor,sale_id,lines,reason,approved_by,refund_kind='cash'):
  with self.s.tx():
   self.s.accounting_lock(wid,'return:'+sale_id)
   return self._return_sale(wid,actor,sale_id,lines,reason,approved_by,refund_kind)
 def _return_sale(self,wid,actor,sale_id,lines,reason,approved_by,refund_kind='cash'):
  sale=self.s._db.execute('SELECT * FROM sales WHERE id=? AND workspace_id=?',(sale_id,wid)).fetchone();rid=ident('ret');refund=0; moves=[]; cogs=0
  if not sale:raise NotFound('sale not found')
  with self.s.tx():
   self.s._db.execute("INSERT INTO retail_returns(id,workspace_id,number,sale_id,location_id,returned_at,reason,status,refund_minor,created_by,approved_by) VALUES(?,?,?,?,?,?,?,'approved',0,?,?)",(rid,wid,'RET-'+sale['number'],sale_id,sale['location_id'],utcnow(),reason,actor,approved_by))
   for line_id,qty in lines.items():
    l=self.s._db.execute('SELECT * FROM sale_lines WHERE id=? AND sale_id=?',(line_id,sale_id)).fetchone();q=Decimal(str(qty));amount=int((q*Decimal(l['total_minor'])/Decimal(l['quantity'])).quantize(Decimal('1')));refund+=amount;cogs+=int((q*l['cost_minor']).quantize(Decimal('1')));moves.append((l,q,line_id));self.s._db.execute('INSERT INTO retail_return_lines(id,return_id,sale_line_id,quantity,restock) VALUES(?,?,?,?,1)',(ident('rln'),rid,line_id,str(q)))
   if self.s._db.execute("UPDATE retail_returns SET status='completed',refund_minor=? WHERE id=? AND workspace_id=? AND status='approved'",(refund,rid,wid)).rowcount!=1:raise Conflict('return was not completed')
   self.s._db.execute('INSERT INTO tender_entries(id,workspace_id,sale_id,kind,amount_minor,reference,received_at,actor_id) VALUES(?,?,?,?,?,?,?,?)',(ident('ten'),wid,sale_id,'refund_'+refund_kind,-refund,rid,utcnow(),approved_by))
  for l,q,line_id in moves:self.move_stock(wid,approved_by,l['product_id'],sale['location_id'],q,l['cost_minor'],'return','return',rid+'-'+line_id)
  tax=sum(int((Decimal(str(qty))*Decimal(self.s._db.execute('SELECT tax_minor,quantity FROM sale_lines WHERE id=?',(line_id,)).fetchone()['tax_minor'])/Decimal(self.s._db.execute('SELECT quantity FROM sale_lines WHERE id=?',(line_id,)).fetchone()['quantity'])).quantize(Decimal('1'))) for line_id,qty in lines.items());net=refund-tax
  acc=[{'account_id':self.books._system(wid,'sales_returns'),'debit_minor':net},{'account_id':self.books._system(wid,'cash' if refund_kind=='cash' else 'bank'),'credit_minor':refund}]
  if tax:acc.append({'account_id':self.books._system(wid,'sales_tax'),'debit_minor':tax})
  if cogs:acc.extend([{'account_id':self.books._system(wid,'inventory'),'debit_minor':cogs},{'account_id':self.books._system(wid,'cogs'),'credit_minor':cogs}])
  journal=self.books.post_journal(wid,approved_by,utcnow()[:10],'Return '+sale['number'],acc,'retail_return',rid,'RET-'+sale['number'],sale['currency'])
  self.s._audit(wid,approved_by,'sale.return',{'id':rid,'refund_minor':refund,'journal_id':journal['id']})
  return {'id':rid,'refund_minor':refund,'status':'completed','journal_id':journal['id']}
 def three_way_match(self,wid,actor,po,bill):
  ordered=self.s._db.execute('SELECT COALESCE(SUM(CAST(l.quantity AS REAL)*l.unit_cost_minor),0) v,COALESCE(SUM(CAST(l.quantity AS REAL)-CAST(l.received_quantity AS REAL)),0) q FROM purchase_order_lines l JOIN purchase_orders p ON p.id=l.purchase_order_id WHERE l.purchase_order_id=? AND p.workspace_id=?',(po,wid)).fetchone();b=self.s._db.execute('SELECT total_minor FROM documents WHERE id=? AND workspace_id=?',(bill,wid)).fetchone();variance=int(b['total_minor'])-int(ordered['v']);status='matched' if not ordered['q'] and not variance else 'variance';x=ident('match')
  with self.s.tx():self.s._db.execute('INSERT INTO three_way_matches(id,workspace_id,purchase_order_id,purchase_bill_id,status,quantity_variance,value_variance_minor,checked_by,checked_at) VALUES(?,?,?,?,?,?,?,?,?)',(x,wid,po,bill,status,str(ordered['q']),variance,actor,utcnow()));self.s._audit(wid,actor,'purchase.match',{'id':x,'status':status})
  return {'id':x,'status':status,'quantity_variance':str(ordered['q']),'value_variance_minor':variance}
 def export_all(self,wid):
  names=('locations','retail_products','stock_ledger','purchase_orders','purchase_order_lines','sales','sale_lines','tender_entries','retail_returns','retail_return_lines','cash_sessions','credit_policies');return {n:[dict(x) for x in self.s._db.execute(f'SELECT * FROM {n} WHERE workspace_id=?',(wid,)).fetchall()] if n not in ('purchase_order_lines','sale_lines','retail_return_lines') else [dict(x) for x in self.s._db.execute(f'SELECT * FROM {n}').fetchall()] for n in names}
