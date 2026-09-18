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
 def verification_checklist(self,candidate):
  return {'jurisdiction':candidate['jurisdiction'],'pack_hash':candidate['pack_hash'],'must_verify':['registration and taxpayer status','effective dates for each rate','item or service classification basis','place-of-supply and customer-type scope','tax-inclusive or tax-exclusive price basis','rounding at line or document level','zero-rated/exempt evidence rules','reverse-charge conditions','credit/recovery restrictions','invoice fields, filing and e-invoicing adapter separately'],'sources':candidate['sources'],'statutory_adapter_state':'disabled'}
 def attest(self,wid,actor,data,rules):
  required=('jurisdiction','rules_version','professional','credentials','verified_on','effective_from','registration_scope','supply_scope','item_classification_basis','price_basis','rounding_basis','source_urls','limitations')
  missing=[k for k in required if not data.get(k)]
  if missing:raise ValueError('verification is incomplete: '+', '.join(missing))
  if not rules:raise ValueError('at least one reviewed tax rule is required')
  if data['price_basis'] not in ('inclusive','exclusive'):raise ValueError('price_basis must be inclusive or exclusive')
  payload={k:data.get(k) for k in required}|{'rules':rules};h=sha256(canon(payload));vid='txv_'+secrets.token_hex(8)
  with self.s.tx():
   self.s._db.execute("UPDATE tax_verifications SET status='superseded' WHERE workspace_id=? AND jurisdiction=? AND status='active'",(wid,data['jurisdiction']))
   self.s._db.execute('INSERT INTO tax_verifications(id,workspace_id,jurisdiction,rules_version,professional,credentials,verified_on,effective_from,effective_to,registration_scope,supply_scope,item_classification_basis,price_basis,rounding_basis,source_urls_json,limitations,attestation_hash,status,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,\'active\',?,?)',(vid,wid,data['jurisdiction'],data['rules_version'],data['professional'],data['credentials'],data['verified_on'],data['effective_from'],data.get('effective_to'),data['registration_scope'],data['supply_scope'],data['item_classification_basis'],data['price_basis'],data['rounding_basis'],canon(data['source_urls']),data['limitations'],h,actor,utcnow()))
   ids=[]
   for r in rules:
    rid='txr_'+secrets.token_hex(8);rule_payload={'j':data['jurisdiction'],'c':r['code'],'v':data['rules_version'],'from':data['effective_from'],'to':data.get('effective_to'),'rate':str(r['rate_percent']),'inclusive':data['price_basis']=='inclusive','scope':r.get('scope','domestic')};self.s._db.execute('INSERT INTO tax_rules(id,workspace_id,jurisdiction,code,version,effective_from,effective_to,rate_bps,price_includes_tax,scope,status,verified_by,verified_at,source_url,rules_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,wid,data['jurisdiction'],r['code'],data['rules_version'],data['effective_from'],data.get('effective_to'),int(Decimal(str(r['rate_percent']))*100),int(data['price_basis']=='inclusive'),r.get('scope','domestic'),'verified',data['professional'],utcnow(),r['source_url'],sha256(canon(rule_payload))));ids.append(rid)
   self.s._audit(wid,actor,'tax.verification.attest',{'id':vid,'jurisdiction':data['jurisdiction'],'rules_version':data['rules_version'],'rules':ids,'attestation_hash':h,'statutory_adapter_state':'disabled'})
  return {'id':vid,'status':'active','attestation_hash':h,'verified_rules':ids,'statutory_adapter_state':'disabled'}
 def regression(self,wid,jurisdiction,cases):
  results=[]
  for x in cases:
   try:
    got=self.calculate(wid,x['transaction_date'],jurisdiction,x['code'],x['amount_minor'],x.get('scope','domestic'));expected={k:x[k] for k in ('net_minor','tax_minor','gross_minor')};actual={k:got[k] for k in expected};results.append({'name':x.get('name',x['code']),'passed':actual==expected,'expected':expected,'actual':actual,'rules_hash':got['rules_hash']})
   except Exception as e:results.append({'name':x.get('name',x.get('code','case')),'passed':False,'error':str(e)})
  return {'jurisdiction':jurisdiction,'passed':bool(results) and all(x['passed'] for x in results),'cases':results,'statutory_document_allowed':False}
