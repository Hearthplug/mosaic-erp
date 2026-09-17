"""Versioned operational tax calculations. Statutory output remains adapter-gated."""
from decimal import Decimal,ROUND_HALF_UP
from store import Conflict,NotFound,utcnow,canon,sha256
import secrets
class TaxEngine:
 def __init__(self,s):self.s=s
 def add_rule(self,wid,actor,jurisdiction,code,version,effective_from,effective_to,rate_percent,price_includes_tax=False,scope='domestic',verified_by=None,source_url=None):
  x='txr_'+secrets.token_hex(8);status='verified' if verified_by and source_url else 'unverified'
  with self.s.tx():self.s._db.execute('INSERT INTO tax_rules(id,workspace_id,jurisdiction,code,version,effective_from,effective_to,rate_bps,price_includes_tax,scope,status,verified_by,verified_at,source_url,rules_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(x,wid,jurisdiction,code,version,effective_from,effective_to,int(Decimal(str(rate_percent))*100),int(price_includes_tax),scope,status,verified_by,utcnow() if verified_by else None,source_url,sha256(canon({'j':jurisdiction,'c':code,'v':version,'from':effective_from,'to':effective_to,'rate':str(rate_percent),'inclusive':price_includes_tax,'scope':scope}))));self.s._audit(wid,actor,'tax.rule',{'id':x,'jurisdiction':jurisdiction,'version':version,'status':status})
  return {'id':x,'status':status}
 def calculate(self,wid,transaction_date,jurisdiction,code,gross_or_net_minor,scope='domestic',business_customer=False):
  r=self.s._db.execute("SELECT * FROM tax_rules WHERE workspace_id=? AND jurisdiction=? AND code=? AND scope=? AND status='verified' AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) ORDER BY effective_from DESC,version DESC LIMIT 1",(wid,jurisdiction,code,scope,transaction_date,transaction_date)).fetchone()
  if not r:raise Conflict('No professionally verified tax rule covers this date, place and transaction')
  amount=int(gross_or_net_minor);rate=Decimal(r['rate_bps'])/10000
  if r['price_includes_tax']:net=int((Decimal(amount)/(1+rate)).quantize(Decimal('1'),rounding=ROUND_HALF_UP));tax=amount-net;gross=amount
  else:net=amount;tax=int((Decimal(net)*rate).quantize(Decimal('1'),rounding=ROUND_HALF_UP));gross=net+tax
  return {'rule_id':r['id'],'rules_version':r['version'],'rules_hash':r['rules_hash'],'jurisdiction':jurisdiction,'scope':scope,'transaction_date':transaction_date,'net_minor':net,'tax_minor':tax,'gross_minor':gross,'statutory_document_allowed':False}
