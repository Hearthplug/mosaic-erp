#!/usr/bin/env python3
"""Generate intake-e1 train/development data for file-to-migration-pack mapping.
Deterministic, seeded, self-contained. Never reads prior prompts or results.
Task: given a business file excerpt (CSV/TSV/prose-table), answer with the Mosaic
migration pack it maps to and the column mapping, or CLARIFY when it is not a
mappable pack, a required column is unrecoverable, or the pack is ambiguous.
Development rows use held-out synonym variants and held-out value families; the
companion check script proves train/dev non-overlap."""
import argparse,hashlib,json,random,pathlib
R=pathlib.Path(__file__).parent
# Ground truth mirrors migration_packs.SCHEMAS required fields (kept in sync by the
# test test_intake_e1_generator.py which imports both and asserts equality).
PACKS={
 'products':({'name','sku','selling_price_minor','cost_minor'},'sku'),
 'customers':({'name','external_id'},'external_id'),
 'vendors':({'name','external_id'},'external_id'),
 'opening_balances':({'account_code','balance_minor','normal'},'account_code'),
 'stock':({'external_id','sku','quantity','unit_cost_minor','location_code'},'external_id'),
 'open_invoices':({'external_id','customer_external_id','issue_date','total_minor'},'external_id'),
 'open_bills':({'external_id','vendor_external_id','issue_date','total_minor'},'external_id')}
# Synonym pools per field. Index 0..2 are TRAIN variants, 3..4 are DEVELOPMENT-held-out
# variants. The exact Mosaic field name may appear in both splits (it is the canonical
# target, not a phrasing leak).
SYN={
 'name':['name','Item Name','Product Name','Party Name','Display Name'],
 'sku':['sku','Item Code','Product Code','Code','Item No'],
 'selling_price_minor':['price','Rate','Selling Price','MRP','Sale Rate'],
 'cost_minor':['cost','Purchase Rate','Cost Price','Buy Price','Landing Cost'],
 'external_id':['external_id','Ref','Reference No','ID','Ledger Ref'],
 'account_code':['account_code','Ledger Code','Account No','GL Code','Acct Code'],
 'balance_minor':['balance','Opening Balance','Balance Amount','Opening Amt','Ledger Balance'],
 'normal':['normal','Dr/Cr','Balance Side','DC','Side'],
 'quantity':['quantity','Qty','Stock Qty','On Hand','Closing Qty'],
 'unit_cost_minor':['unit_cost','Unit Rate','Unit Cost','Rate per Unit','Per Unit Cost'],
 'location_code':['location_code','Godown','Warehouse Code','Location','Store Code'],
 'customer_external_id':['customer_external_id','Customer Ref','Buyer ID','Customer ID','Client Ref'],
 'vendor_external_id':['vendor_external_id','Supplier Ref','Vendor ID','Supplier ID','Vendor Ref'],
 'issue_date':['issue_date','Invoice Date','Bill Date','Date','Doc Date'],
 'total_minor':['total','Invoice Total','Bill Total','Grand Total','Amount']}
SYSTEM=('Map the uploaded business file excerpt to exactly one Mosaic migration pack and give the '
 'column mapping from Mosaic field names to the file\'s own column headers. Answer CLARIFY when the '
 'file is not one of the packs, a required column cannot be identified, or the pack is ambiguous. '
 'Never invent values; every mapped header must appear in the excerpt.')
def values_for(field,rng,family):
 if field in ('selling_price_minor','cost_minor','balance_minor','unit_cost_minor','total_minor'):
  return str(rng.choice([1500,2999,45000,120050,999]) if family==0 else rng.choice([2500,3999,56000,230075,1499]))
 if field=='quantity': return str(rng.choice([3,12,40]) if family==0 else rng.choice([7,25,60]))
 if field=='normal': return rng.choice(['debit','credit'])
 if field=='issue_date': return rng.choice(['2026-01-15','2026-02-03']) if family==0 else rng.choice(['2026-03-11','2026-04-22'])
 if field=='sku': return rng.choice(['SKU-101','SKU-205','P-331']) if family==0 else rng.choice(['SKU-410','SKU-522','P-744'])
 if field=='location_code': return rng.choice(['LOC-A','LOC-B']) if family==0 else rng.choice(['LOC-C','LOC-D'])
 if field=='account_code': return rng.choice(['1000','4000','6100']) if family==0 else rng.choice(['1100','5000','6200'])
 if field=='external_id': return rng.choice(['C-1001','V-2001','STK-301']) if family==0 else rng.choice(['C-1055','V-2077','STK-366'])
 if field=='customer_external_id': return rng.choice(['C-1001','C-1002']) if family==0 else rng.choice(['C-1055','C-1066'])
 if field=='vendor_external_id': return rng.choice(['V-2001','V-2002']) if family==0 else rng.choice(['V-2077','V-2088'])
 return rng.choice(['Cotton Shirt','Steel Bolt','Rice Bag']) if family==0 else rng.choice(['Silk Scarf','Brass Valve','Wheat Flour'])
NOISE_COLS=['Notes','HSN','Category','Brand','Remarks','Group','Batch']
def render_rows(headers,fields,rng,family,n):
 out=[]
 for _ in range(n):
  out.append([values_for(f,rng,family) for f in fields])
 return out
def csv_text(headers,rows,delim):
 lines=[delim.join(headers)]
 for r in rows:lines.append(delim.join(r))
 return '\n'.join(lines)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args()
 rng=random.Random(20261002);rows=[]
 packs=sorted(PACKS)
 for pack in packs:
  required,_=PACKS[pack];fields=sorted(required)
  for i in range(150):
   dev=(i%6==0)
   family=1 if dev else 0
   # header variants: canonical name always allowed; synonym index range differs per split
   headers=[]
   for f in fields:
    pool=SYN[f]
    if rng.random()<0.35:h=f
    else:
     h=pool[rng.randrange(3,5)] if dev else pool[rng.randrange(0,3)]
    headers.append(h)
   noise=[c for c in rng.sample(NOISE_COLS,k=rng.randrange(0,3))]
   all_headers=headers+noise
   all_fields=fields+['']*len(noise)
   order=list(range(len(all_headers)));rng.shuffle(order)
   sh_headers=[all_headers[j] for j in order]
   sh_fields=[all_fields[j] for j in order]
   nrows=rng.randrange(2,5)
   vals=render_rows(sh_headers,sh_fields,rng,family,nrows)
   # render_rows keyed by fields list: replace '' fields with noise words
   for r in vals:
    for j,f in enumerate(sh_fields):
     if f=='':r[j]=rng.choice(['x','-','note'])
   delim=';' if rng.random()<0.15 else ','
   excerpt=csv_text(sh_headers,vals,delim)
   mapping={f:headers[fields.index(f)] for f in fields}
   label='INTAKE_MAP_'+pack.upper()
   rows.append({'label':label,'text':excerpt,'slots':{'mapping':mapping,'missing':[]},'split':'development' if dev else 'train'})
 # missing-required cases: drop one required column -> CLARIFY with partial mapping + missing
 for pack in packs:
  required,_=PACKS[pack];fields=sorted(required)
  for i in range(36):
   dev=(i%6==0);family=1 if dev else 0
   drop=fields[i%len(fields)]
   keep=[f for f in fields if f!=drop]
   headers=[SYN[f][rng.randrange(3,5)] if dev else SYN[f][rng.randrange(0,3)] for f in keep]
   vals=render_rows(headers,keep,rng,family,3)
   excerpt=csv_text(headers,vals,',')
   mapping={f:headers[keep.index(f)] for f in keep}
   rows.append({'label':'CLARIFY','text':excerpt,'slots':{'mapping':mapping,'missing':[drop]},'split':'development' if dev else 'train'})
 # non-ERP documents -> CLARIFY empty
 NONERP=['Meeting minutes: discussed hiring plan for Q3 and the new warehouse lease. Action items assigned to ops.',
  'Dear sir, please find attached our company profile. We are a leading exporter of textiles established in 1998.',
  'RESUME - Priya Sharma, accountant, 6 years experience in AP/AR, Tally and Excel, seeking full-time role.',
  'Warranty card: product registered on 12 Jan. Keep this card for service claims within 24 months.',
  'Menu: paneer tikka 240, butter naan 40, dal makhani 180, jeera rice 120. Served 11am to 11pm.',
  'Bank notification: your statement for the quarter is ready to download from the secure portal.']
 for i in range(120):
  dev=(i%6==0)
  rows.append({'label':'CLARIFY','text':NONERP[i%len(NONERP)],'slots':{'mapping':{},'missing':[]},'split':'development' if dev else 'train'})
 rng.shuffle(rows)
 out=[]
 for i,r in enumerate(rows):
  out.append({'id':f"e1-{r['split'][0]}-{i:04d}",'split':r['split'],
   'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':r['text']}],
   'target':{'label':r['label'],'slots':r['slots']}})
 p=pathlib.Path(a.output)
 p.write_text(''.join(json.dumps(x,separators=(',',':'),sort_keys=True)+'\n' for x in out))
 stats={'records':len(out),'train':sum(x['split']=='train' for x in out),'development':sum(x['split']=='development' for x in out),
  'labels':sorted({x['target']['label'] for x in out}),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 print(json.dumps(stats,sort_keys=True))
if __name__=='__main__':main()
