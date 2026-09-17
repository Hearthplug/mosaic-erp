"""Persistent operational retail flows for Mosaic ERP's real-product target."""
from decimal import Decimal, ROUND_HALF_UP
import secrets
from store import utcnow, Conflict, NotFound

def ident(p): return p+'_'+secrets.token_hex(8)
class Retail:
 def __init__(self,store,books): self.s,self.books=store,books
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
  order=self.s._db.execute('SELECT * FROM purchase_orders WHERE id=? AND workspace_id=?',(po,wid)).fetchone()
  if not order or order['status'] not in ('approved','part_received'):raise Conflict('purchase order is not receivable')
  for line_id,qty in received.items():
   line=self.s._db.execute('SELECT * FROM purchase_order_lines WHERE id=? AND purchase_order_id=?',(line_id,po)).fetchone(); new=Decimal(line['received_quantity'])+Decimal(str(qty))
   if new>Decimal(line['quantity']):raise Conflict('receipt exceeds order')
   self.move_stock(wid,actor,line['product_id'],order['location_id'],qty,line['unit_cost_minor'],'receipt','purchase_order',po+'-'+line_id+'-'+str(new))
   with self.s.tx():self.s._db.execute('UPDATE purchase_order_lines SET received_quantity=? WHERE id=?',(str(new),line_id))
  left=self.s._db.execute('SELECT COUNT(*) n FROM purchase_order_lines WHERE purchase_order_id=? AND CAST(received_quantity AS REAL)<CAST(quantity AS REAL)',(po,)).fetchone()['n'];status='part_received' if left else 'received'
  with self.s.tx():self.s._db.execute('UPDATE purchase_orders SET status=? WHERE id=?',(status,po));self.s._audit(wid,actor,'purchase.receive',{'id':po,'status':status})
  return {'id':po,'status':status}
 def complete_sale(self,wid,actor,location_id,lines,tenders,customer_id=None,currency='USD'):
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
  for p,q,net,t in computed:self.move_stock(wid,actor,p['id'],location_id,-q,p['cost_minor'],'sale','sale',sale)
  self.s._audit(wid,actor,'sale.complete',{'id':sale,'number':number,'total_minor':total})
  return {'id':sale,'number':number,'total_minor':total,'paid_minor':paid}
