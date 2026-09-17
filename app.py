from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import secrets, sys, threading, time
from urllib.parse import parse_qs
from store import Store, Conflict, NotFound, canon, sha256

def open_store():
    url=os.environ.get("MOSAIC_DATABASE_URL", "")
    if url.startswith(("postgresql://", "postgres://")):
        from postgres_store import PostgresStore
        return PostgresStore(url, os.environ.get("MOSAIC_DB_POOL_MIN",1), os.environ.get("MOSAIC_DB_POOL_MAX",10), os.environ.get("MOSAIC_AUTO_MIGRATE","true").lower() in ("1","true","yes"))
    return Store(os.environ.get("MOSAIC_DB_PATH", str(Path(__file__).parent / "mosaic.db")))
from extra_packs import DATA as EXTRA_DATA, BANDS as EXTRA_BANDS, REG as EXTRA_REG, SUP as EXTRA_SUP, SUB as EXTRA_SUB, make_pack
ROOT=Path(__file__).parent; MAX_BYTES=256*1024
TODAY='2026-09-17'
BASE_QUESTIONS=[
 {'key':'name','text':'First, what should we call your business?','type':'text','placeholder':'e.g. Asha Pharmacy'},
 {'key':'vertical','text':'What do you sell? I’ll adapt the language and workflows.','type':'choice','options':['Grocery','Fashion','Electronics','Pharmacy','Beauty & wellness','Home & specialty']},
 {'key':'country','text':'Which tax jurisdiction is home base? Onboarding, invoices, and compliance adapt to it.','type':'choice','options':['India','UAE','Singapore','China','Vietnam','Malaysia','United Kingdom','United States','Canada','European Union']+list(EXTRA_DATA)},
 {'key':'locations','text':'What does your store network look like?','type':'choice','options':['One store','2–5 stores','6–20 stores','20+ stores']},
 {'key':'channels','text':'Where do customers buy from you?','type':'multi','options':['In store','Own website','Marketplaces','WhatsApp / social']},
 {'key':'inventory','text':'Which inventory problem costs you the most?','type':'choice','options':['Stockouts','Overstock','Transfers','Batch / expiry','Variants / serials']},
 {'key':'sales','text':'How does checkout work today?','type':'choice','options':['POS software','Accounting app','Spreadsheet / paper','Online only']},
 {'key':'credit','text':'Which credit flows should we control?','type':'choice','options':['Customer + supplier','Customer credit','Supplier credit','No credit']},
 {'key':'staff','text':'How should your team be organized?','type':'multi','options':['Cashiers','Store managers','Buyers','Warehouse team','Accountant']},
 {'key':'priority','text':'What must improve first?','type':'choice','options':['Inventory accuracy','Checkout speed','Margins & cash','Customer loyalty','Multi-store control']},
]
COUNTRIES=[q['options'] for q in BASE_QUESTIONS if q['key']=='country'][0]
CA_PROV={'Ontario':('HST',13),'Nova Scotia':('HST',14),'New Brunswick':('HST',15),'Newfoundland and Labrador':('HST',15),'Prince Edward Island':('HST',15),'British Columbia':('GST + PST',12),'Manitoba':('GST + RST',12),'Saskatchewan':('GST + PST',11),'Quebec':('GST + QST',14.975),'Alberta':('GST only',5)}
EU_VAT={'Germany':19,'France':20,'Italy':22,'Spain':21,'Netherlands':21,'Belgium':21,'Poland':23,'Sweden':25,'Ireland':23,'Austria':20,'Denmark':25,'Portugal':23,'Greece':24,'Finland':25.5}
US_STATE={'California':7.25,'Texas':6.25,'New York':4,'Florida':6,'Washington':6.5,'Illinois':6.25,'New Jersey':6.625,'Pennsylvania':6,'Ohio':5.75,'Georgia':4,'Oregon':0,'Alaska':0,'Delaware':0,'Montana':0,'New Hampshire':0}
def jq(a):
 c=a.get('country'); out=[]
 if c=='United States':out.append({'key':'subdivision','text':'Which US state? State and local sales tax rules differ.','type':'choice','options':sorted(US_STATE)})
 elif c=='Canada':out.append({'key':'subdivision','text':'Which province or territory? GST, HST, PST, and QST differ by province.','type':'choice','options':list(CA_PROV)})
 elif c=='European Union':out.append({'key':'subdivision','text':'Which EU member state sets your VAT?','type':'choice','options':sorted(EU_VAT)+['Other member state']})
 if c in EXTRA_SUB:
  text,opts=EXTRA_SUB[c];out.append({'key':'subdivision','text':text,'type':'choice','options':opts})
 bands={'India':['Up to ₹40 lakh','₹40 lakh – ₹1.5 crore','₹1.5 – 5 crore','Above ₹5 crore'],'UAE':['Up to AED 187,500','AED 187,500 – 375,000','Above AED 375,000'],'Singapore':['Up to S$1 million','Above S$1 million'],'China':['Up to RMB 5 million','Above RMB 5 million'],'Vietnam':['Any turnover'],'Malaysia':['Up to RM500,000','Above RM500,000'],'United Kingdom':['Up to £90,000','Above £90,000'],'United States':['Under $100,000','$100,000 – $1 million','Above $1 million'],'Canada':['Up to CA$30,000','Above CA$30,000'],'European Union':['Up to €10,000 cross-border sales','Above €10,000 cross-border sales']}
 regs={'India':['Regular','Composition','Not registered yet'],'UAE':['VAT registered','Voluntary registration','Not registered'],'Singapore':['GST registered','Not registered'],'China':['General VAT taxpayer','Small-scale taxpayer'],'Vietnam':['Deduction method','Direct method'],'Malaysia':['SST registered - goods','SST registered - services','Not registered'],'United Kingdom':['VAT registered','Flat rate scheme','Not registered'],'United States':['Collecting sales tax','Not collecting yet'],'Canada':['GST/HST registered','Not registered (small supplier)'],'European Union':['VAT registered','OSS registered','Not registered']}
 supply={'India':['Within my state','Across India','India + exports'],'UAE':['Within the UAE','Across the GCC','UAE + exports outside GCC'],'Singapore':['Within Singapore','Singapore + exports'],'China':['Within China','China + exports'],'Vietnam':['Within Vietnam','Vietnam + exports'],'Malaysia':['Within Malaysia','Malaysia + exports'],'United Kingdom':['Within the UK','UK + EU sales','UK + worldwide exports'],'United States':['Within my state','Across states'],'Canada':['Within my province','Across provinces','Canada + exports'],'European Union':['Within my member state','Across the EU','EU + exports outside the EU']}
 if c in bands:out.append({'key':'turnover','text':'What is your annual turnover band? Registration duties and invoice rules depend on it.','type':'choice','options':bands[c]})
 if c in regs:out.append({'key':'registration','text':'Which registration fits you today?','type':'choice','options':regs[c]})
 if c in supply:out.append({'key':'supply','text':'How far do you sell? Place-of-supply rules depend on it.','type':'choice','options':supply[c]})
 if c:out.append({'key':'buyers','text':'Who do you mainly sell to?','type':'choice','options':['Consumers','Businesses','Both']})
 return out
def questions_for(a):return BASE_QUESTIONS+jq(a)
VERTICAL={
 'Grocery':dict(items='Items',sale='Bills',customer='Shoppers',unit='SKU',accent='#ff7a48',special=('Freshness & batches','Expiry and fast-moving stock','◔'),kpis=['Today’s sales','Gross margin','Low stock','Expiring soon'],flow='Expiry risk → markdown suggestion'),
 'Fashion':dict(items='Styles',sale='Orders',customer='Customers',unit='Variant',accent='#8a5cf6',special=('Size & colour matrix','Variants, seasons, and collections','◈'),kpis=['Net sales','Sell-through','Returns','Top collection'],flow='Slow style → transfer or markdown'),
 'Electronics':dict(items='Devices',sale='Invoices',customer='Buyers',unit='Serial',accent='#1685e5',special=('Serials & warranty','IMEI/serial trace and warranty','⌁'),kpis=['Today’s sales','Margin','Serials in stock','Warranty cases'],flow='Sale → register serial and warranty'),
 'Pharmacy':dict(items='Medicines',sale='Bills',customer='Patients',unit='Batch',accent='#12a879',special=('Batch & expiry','Batch trace, FEFO, and expiry','✚'),kpis=['Today’s sales','Gross margin','Expiring stock','Reorder alerts'],flow='Near expiry → alert and FEFO action'),
 'Beauty & wellness':dict(items='Products',sale='Sales',customer='Clients',unit='SKU',accent='#e64f93',special=('Services & appointments','Products, services, and bookings','✦'),kpis=['Today’s sales','Bookings','Repeat clients','Retail margin'],flow='Visit completed → loyalty follow-up'),
 'Home & specialty':dict(items='Products',sale='Orders',customer='Customers',unit='SKU',accent='#e09225',special=('Custom catalog','Collections, bundles, and attributes','◇'),kpis=['Today’s sales','Gross margin','Open orders','Low stock'],flow='Custom order → deposit and fulfilment'),
}
INDIA_SLAB={'Grocery':[('Fresh & unbranded staples',0),('Packaged essentials',5)],'Fashion':[('Apparel up to ₹2,500',5),('Apparel above ₹2,500',18)],'Electronics':[('Devices & accessories',18)],'Pharmacy':[('Medicines',5)],'Beauty & wellness':[('Salon & wellness services',5),('Beauty products',18)],'Home & specialty':[('Goods & decor',18)]}
def slabs(v,pairs):return [{'band':b,'rate':r} for b,r in INDIA_SLAB.get(v,INDIA_SLAB['Home & specialty'])] if pairs=='india' else [{'band':b,'rate':r} for b,r in pairs]
def india(a):
 v=a.get('vertical'); turnover=a.get('turnover'); reg=a.get('registration'); supply=a.get('supply'); buyers=a.get('buyers')
 band={'Up to ₹40 lakh':'lt40l','₹40 lakh – ₹1.5 crore':'40l_1_5cr','₹1.5 – 5 crore':'1_5_5cr','Above ₹5 crore':'gt5cr'}.get(turnover); warns=[]
 if reg=='Composition' and band in ('1_5_5cr','gt5cr'):warns.append('Composition is capped at ₹1.5 crore goods turnover, so the blueprint moves you to Regular');reg='Regular'
 if reg=='Not registered yet' and band and band!='lt40l':warns.append('Turnover is above the ₹40 lakh goods threshold, so GST registration is required')
 if reg=='Composition' and v=='Beauty & wellness':warns.append('Composition for services is capped at ₹50 lakh turnover')
 registered=reg in ('Regular','Composition')
 split={'Within my state':['Intra-state sale → CGST + SGST (half each)'],'Across India':['Intra-state sale → CGST + SGST (half each)','Inter-state sale → IGST by place of supply'],'India + exports':['Intra-state sale → CGST + SGST (half each)','Inter-state sale → IGST by place of supply','Export → zero-rated under LUT']}.get(supply,[])
 einv=registered and reg=='Regular' and band=='gt5cr'
 hsn=None if not registered else (6 if band=='gt5cr' else 4)
 if reg=='Regular':
  returns=['GSTR-1 outward supplies (monthly'+('; QRMP quarterly eligible up to ₹5 crore' if band in ('40l_1_5cr','1_5_5cr') else '')+')','GSTR-3B summary and payment']
  if band in ('1_5_5cr','gt5cr'):returns.append('GSTR-9 annual return')
 elif reg=='Composition':returns=['CMP-08 quarterly payment','GSTR-4 annual return']
 else:returns=['No returns until registered','Track turnover against the ₹40 lakh registration threshold']
 val=[]
 if registered:val.append(('HSN codes',('6-digit minimum (AATO above ₹5 crore)' if hsn==6 else '4-digit minimum (AATO up to ₹5 crore)')+' on documents and GSTR-1 Table 12'))
 val.append(('E-invoicing',('Required: B2B invoices carry IRN + QR from an IRP'+(' - applies when you make B2B sales' if buyers=='Consumers' else '')) if einv else ('Not required: composition taxpayers are outside e-invoicing' if reg=='Composition' else 'Not required below the ₹5 crore AATO threshold' if registered else 'Applies only after registration')))
 val.append(('E-way bill','Required above ₹50,000 consignment value' if registered and supply in ('Across India','India + exports') else 'Not triggered for current supply scope'))
 if registered and 'Marketplaces' in a.get('channels',[]):val.append(('Marketplace TCS','Operator collects TCS under Sec 52; reconcile credits in GSTR-2B'))
 flows=[]
 if reg=='Composition':flows.append('Bill of supply → no GST charged → CMP-08 quarterly')
 elif reg=='Regular':flows.append('Inter-state sale → apply IGST by place of supply' if supply in ('Across India','India + exports') else 'Sale → split CGST + SGST by slab')
 if registered and supply in ('Across India','India + exports'):flows.append('Inter-state consignment above ₹50,000 → e-way bill before dispatch')
 if supply=='India + exports' and registered:flows.append('Export order → LUT zero-rated invoice → refund tracking')
 if einv:flows.append('B2B invoice → IRN + QR code from IRP before dispatch')
 if reg=='Not registered yet':flows.append('Turnover crossing ₹40 lakh → GST registration within 30 days')
 if registered and 'Marketplaces' in a.get('channels',[]):flows.append('Marketplace payout → reconcile operator TCS credit')
 return {'jurisdiction':'India','subdivision':None,'tax_name':'GST','authority':'CBIC / GST Council','currency':{'code':'INR','symbol':'₹'},'registration':{'type':reg or 'Undecided','registered':registered,'label':('GSTIN: 2 state + 10 PAN + entity + Z + check' if registered else 'Unregistered; monitor the threshold'),'threshold':'₹40 lakh goods / ₹20 lakh services'},'rates':{'structure':'GST 2.0: 5% merit, 18% standard, 40% de-merit, NIL for exempt goods','slabs':slabs(v,'india'),'note':'Item-level rates must be confirmed against HSN classification'},'rules':split,'invoice':['Tax invoice with GSTIN, HSN, place of supply, and tax split' if reg=='Regular' else ('Bill of supply; no GST may be charged' if reg=='Composition' else 'Commercial invoice until registered')],'credits':'Input tax credit on inputs, capital goods, and input services; blocked credits under Sec 17(5)' if reg=='Regular' else ('No ITC; flat rate paid from own pocket' if reg=='Composition' else 'No ITC until registered'),'returns':returns,'validations':[{'check':c,'status':s} for c,s in val],'warnings':warns,'reverse_charge':'Watchlist: GTA freight, import of services, and notified categories','workflows':flows,'kpi':'Output tax' if reg=='Regular' else ('Composition tax' if reg=='Composition' else 'Turnover watch'),'sources':[{'title':'GST Council: Next-Gen GST reforms press release (2-rate structure 5%/18% + 40% de-merit)','url':'https://gstcouncil.gov.in/sites/default/files/2025-09/press_release_press_information_bureau_0.pdf'},{'title':'GSTN advisory: HSN reporting in GSTR-1 Table 12 by AATO','url':'https://tutorial.gst.gov.in/downloads/news/hsn_advisory_table_12_2.pdf'},{'title':'GST Council: Notification 10/2023-Central Tax (e-invoice above ₹5 crore from 01-08-2023)','url':'https://www.gstcouncil.gov.in/node/4365'}],'effective':TODAY}
def uae(a):
 t=a.get('turnover');reg=a.get('registration');supply=a.get('supply');registered=reg in ('VAT registered','Voluntary registration');warns=[]
 if reg=='Not registered' and t=='Above AED 375,000':warns.append('Turnover is above the AED 375,000 mandatory registration threshold')
 if supply=='Across the GCC':warns.append('GCC cross-border VAT treatment depends on each member state; confirm before invoicing')
 rules=['Domestic supply → 5% VAT' if registered else 'No VAT charged until registered']
 if supply=='UAE + exports outside GCC':rules.append('Exports outside the GCC → zero-rated with evidence of export')
 if a.get('buyers') in ('Businesses','Both'):rules.append('Specified imports → reverse charge in your VAT return, not at payment')
 return {'jurisdiction':'UAE','subdivision':None,'tax_name':'VAT','authority':'Federal Tax Authority','currency':{'code':'AED','symbol':'AED '},'registration':{'type':reg or 'Undecided','registered':registered,'label':'TRN: 15-digit tax registration number' if registered else 'Monitor taxable supplies against the threshold','threshold':'AED 375,000 mandatory / AED 187,500 voluntary'},'rates':{'structure':'5% standard, 0% zero-rated, exempt categories','slabs':slabs(a.get('vertical'),[('Standard-rated supplies',5),('Zero-rated (exports, specified goods)',0)]),'note':'Confirm category treatment per FTA guide'},'rules':rules,'invoice':['Tax invoice with TRN, VAT amount, and supply date' if registered else 'Commercial invoice until registered'],'credits':'Input VAT recoverable on business purchases; blocked on entertainment and personal vehicles' if registered else 'No input VAT recovery until registered','returns':['VAT return per tax period (monthly or quarterly as assigned)','Voluntary disclosure for past errors'] if registered else ['No returns until registered'],'validations':[{'check':'Registration threshold','status':'Above AED 375,000 - registration mandatory' if t=='Above AED 375,000' else 'Below mandatory threshold'},{'check':'E-invoicing','status':'UAE e-invoicing is being phased in from 2026; confirm your wave with the FTA'}],'warnings':warns,'reverse_charge':'Reverse charge on imported services and specified goods for registered businesses','workflows':(['Sale → add 5% VAT → TRN on invoice'] if registered else [])+(['Export order → zero-rate → keep export evidence'] if supply=='UAE + exports outside GCC' else [])+(['Import of services → reverse-charge entry in VAT return'] if a.get('buyers') in ('Businesses','Both') and registered else []),'kpi':'VAT payable' if registered else 'Turnover watch','sources':[{'title':'FTA: VAT registration thresholds','url':'https://tax.gov.ae/en/taxes/vat/vat.topics/registration.for.vat.aspx'},{'title':'Ministry of Finance: VAT introduced at 5% standard rate','url':'https://mof.gov.ae/en/public-finance/tax/value-added-tax-vat/'}],'effective':TODAY}
def singapore(a):
 reg=a.get('registration');supply=a.get('supply');registered=reg=='GST registered'
 rules=['Domestic supply → 9% GST' if registered else 'No GST until registered']
 if supply=='Singapore + exports':rules.append('Export of goods and zero-rated international services → 0%')
 return {'jurisdiction':'Singapore','subdivision':None,'tax_name':'GST','authority':'IRAS','currency':{'code':'SGD','symbol':'S$'},'registration':{'type':reg or 'Undecided','registered':registered,'label':'GST registration number on invoices' if registered else 'Monitor taxable turnover against S$1 million','threshold':'S$1 million taxable turnover (retrospective or prospective)'},'rates':{'structure':'9% standard from 1 Jan 2024, 0% zero-rated, exempt categories','slabs':slabs(a.get('vertical'),[('Standard-rated supplies',9),('Exports and international services',0)]),'note':'Confirm category treatment per IRAS e-Tax guides'},'rules':rules,'invoice':['Tax invoice with GST registration number and GST amount' if registered else 'Commercial invoice until registered'],'credits':'Input GST claimable with valid tax invoices' if registered else 'No input claims until registered','returns':['GST F5 return per accounting period (usually quarterly)'] if registered else ['No returns until registered'],'validations':[{'check':'Registration threshold','status':'Registration required' if a.get('turnover')=='Above S$1 million' and not registered else 'Within declared band'}],'warnings':[],'reverse_charge':'Reverse charge applies to imported services for partially exempt or non-registered businesses above thresholds','workflows':(['Sale → add 9% GST → registration number on invoice'] if registered else [])+(['Export order → zero-rate → retain export documents'] if supply=='Singapore + exports' and registered else []),'kpi':'GST payable' if registered else 'Turnover watch','sources':[{'title':'IRAS: Do I need to register for GST (S$1 million)','url':'https://www.iras.gov.sg/taxes/goods-services-tax-(gst)/gst-registration-deregistration/do-i-need-to-register-for-gst'},{'title':'IRAS: GST rate change to 9% from 1 Jan 2024','url':'https://www.iras.gov.sg/taxes/goods-services-tax-(gst)/gst-rate-change/gst-rate-change-for-business/overview-of-gst-rate-change'}],'effective':TODAY}
def china(a):
 reg=a.get('registration');supply=a.get('supply');general=reg=='General VAT taxpayer'
 rules=['Sales of goods → 13% VAT' if general else 'Small-scale levy 3% (reduced rates have applied under recent relief policies - confirm current rate)']
 if supply=='China + exports':rules.append('Exports → VAT exemption, credit, and refund under export rebate rules')
 return {'jurisdiction':'China','subdivision':None,'tax_name':'VAT','authority':'State Taxation Administration','currency':{'code':'CNY','symbol':'¥'},'registration':{'type':reg or 'Undecided','registered':True,'label':'Unified social credit code; special VAT invoices (fapiao) for general taxpayers' if general else 'Small-scale taxpayer status (annual sales up to RMB 5 million)','threshold':'RMB 5 million annual sales separates small-scale from general taxpayers'},'rates':{'structure':'13% goods, 9% specified goods/services, 6% modern services; small-scale levy rate','slabs':slabs(a.get('vertical'),[('Goods, processing, tangible leasing',13),('Necessity goods, transport, publications',9),('Modern services',6)]),'note':'Confirm rate by commodity code'},'rules':rules,'invoice':['Special VAT fapiao for creditable input VAT' if general else 'General fapiao; no input credit'],'credits':'Input VAT creditable against output VAT' if general else 'No input credit under the small-scale levy','returns':['Monthly or quarterly VAT filing'],'validations':[{'check':'Taxpayer status','status':'General taxpayer: full credit chain' if general else 'Small-scale: simplified levy'}],'warnings':[],'reverse_charge':'Withholding VAT can apply on payments to non-resident suppliers','workflows':['Sale → issue fapiao → 13% output VAT' if general else 'Sale → issue general fapiao → levy rate']+(['Export order → exemption-credit-refund computation'] if supply=='China + exports' else []),'kpi':'Output VAT','sources':[{'title':'State Taxation Administration: VAT law rates (13% goods)','url':'https://fgk.chinatax.gov.cn/zcfgk/c100009/c5237365/content.html'},{'title':'STA English portal: VAT in China','url':'https://www.chinatax.gov.cn/eng/c102962/c102968/c102969/c5245967/content.html'}],'effective':TODAY}
def vietnam(a):
 reg=a.get('registration');supply=a.get('supply');ded=reg=='Deduction method'
 rules=['Domestic supply → 10% standard VAT (8% for eligible goods under the reduction running to 31 Dec 2026)' if ded else 'Direct method: VAT on revenue at sector percentage']
 if supply=='Vietnam + exports':rules.append('Exports → 0% with customs and payment evidence')
 return {'jurisdiction':'Vietnam','subdivision':None,'tax_name':'VAT','authority':'General Department of Taxation','currency':{'code':'VND','symbol':'₫'},'registration':{'type':reg or 'Undecided','registered':True,'label':'Tax code on every e-invoice','threshold':'VAT method set at business registration'},'rates':{'structure':'10% standard, 8% temporary reduction for eligible goods (Decree 174/2025, to 31 Dec 2026), 5% reduced, 0% exports','slabs':slabs(a.get('vertical'),[('Standard goods and services',10),('Eligible goods during reduction',8),('Exports',0)]),'note':'Confirm eligibility lists in the current decree'},'rules':rules,'invoice':['E-invoice is mandatory nationwide; issue through an authorized provider'],'credits':'Input VAT creditable under the deduction method' if ded else 'No input credit under the direct method','returns':['Monthly or quarterly VAT declarations'],'validations':[{'check':'E-invoice','status':'Mandatory nationwide'},{'check':'Reduction window','status':'8% rate applies to eligible goods until 31 Dec 2026'}],'warnings':[],'reverse_charge':'Withholding can apply to foreign contractor supplies','workflows':['Sale → e-invoice → VAT declaration']+(['Export order → 0% → keep customs evidence'] if supply=='Vietnam + exports' else []),'kpi':'VAT payable','sources':[{'title':'Decree 174/2025/ND-CP: VAT reduction under Resolution 204/2025/QH15 (to 31 Dec 2026)','url':'https://www.dfdl.com/insights/legal-and-tax-updates/vietnam-extension-of-the-reduced-8-vat-rate-to-31-december-2026/'}],'effective':TODAY}
def malaysia(a):
 reg=a.get('registration');supply=a.get('supply');goods=reg=='SST registered - goods';svc=reg=='SST registered - services';registered=goods or svc
 rules=['Sales tax 5%/10% on taxable goods manufactured or imported' if goods else ('Service tax 8% on taxable services' if svc else 'No SST charged until registered')]
 if supply=='Malaysia + exports':rules.append('Exported goods and eligible exported services → exempt / out of scope with evidence')
 return {'jurisdiction':'Malaysia','subdivision':None,'tax_name':'SST','authority':'Royal Malaysian Customs Department','currency':{'code':'MYR','symbol':'RM'},'registration':{'type':reg or 'Undecided','registered':registered,'label':'SST registration number on invoices' if registered else 'Monitor sales value against RM500,000','threshold':'RM500,000 over 12 months'},'rates':{'structure':'Sales tax 5%/10% per 2025 Rate Order; service tax 8%','slabs':slabs(a.get('vertical'),[('Taxable goods (per 2025 Rate Order)',10),('Selected goods',5),('Taxable services',8)]),'note':'Confirm item lists under the 2025 Orders effective 1 July 2025'},'rules':rules,'invoice':['Invoice with SST registration number and tax amounts' if registered else 'Commercial invoice until registered'],'credits':'No input tax credit chain under SST; relief and exemptions by order','returns':['SST-02 return every two months'] if registered else ['No returns until registered'],'validations':[{'check':'Registration threshold','status':'Registration required' if a.get('turnover')=='Above RM500,000' and not registered else 'Within declared band'}],'warnings':[],'reverse_charge':'Imported taxable services attract service tax for registered businesses','workflows':(['Sale → apply sales tax per rate order' if goods else 'Invoice → apply 8% service tax' if svc else 'Turnover crossing RM500,000 → SST registration'])+(['Export order → exemption evidence retained'] if supply=='Malaysia + exports' and registered else []),'kpi':'SST payable' if registered else 'Turnover watch','sources':[{'title':'RMCD MySST: registration (RM500,000)','url':'https://mysst.customs.gov.my/registering-business/'},{'title':'MOF: sales tax revision and service tax expansion effective 1 July 2025','url':'https://www.mof.gov.my/portal/en/news/press-release/targeted-revision-of-sales-tax-rate-and-expansion-of-service-tax-scope-effective-1-july-2025'}],'effective':TODAY}
def uk(a):
 reg=a.get('registration');supply=a.get('supply');registered=reg in ('VAT registered','Flat rate scheme');warns=[]
 if reg=='Not registered' and a.get('turnover')=='Above £90,000':warns.append('Turnover is above the £90,000 registration threshold')
 rules=['Domestic supply → 20% standard VAT' if registered else 'No VAT until registered']
 if supply=='UK + EU sales':rules.append('B2B EU sales → zero-rated with VAT number evidence; B2C → confirm OSS/Import rules')
 if supply=='UK + worldwide exports':rules.append('Exports outside the UK → zero-rated with evidence')
 return {'jurisdiction':'United Kingdom','subdivision':None,'tax_name':'VAT','authority':'HMRC','currency':{'code':'GBP','symbol':'£'},'registration':{'type':reg or 'Undecided','registered':registered,'label':'VAT registration number (9 digits)' if registered else 'Monitor taxable turnover against £90,000','threshold':'£90,000 rolling 12-month turnover'},'rates':{'structure':'20% standard, 5% reduced, 0% zero-rated, exempt','slabs':slabs(a.get('vertical'),[('Standard-rated supplies',20),('Reduced rate categories',5),('Zero-rated categories',0)]),'note':'Confirm category treatment per HMRC guidance'},'rules':rules,'invoice':['VAT invoice with VRN, rate, and VAT amount' if registered else 'Commercial invoice until registered'],'credits':'Input VAT reclaimable; restricted under the flat rate scheme' if registered else 'No reclaims until registered','returns':['MTD VAT return (usually quarterly) via compatible software'] if registered else ['No returns until registered'],'validations':[{'check':'Making Tax Digital','status':'Digital records and MTD filing required' if registered else 'Applies once registered'}],'warnings':warns,'reverse_charge':'Domestic reverse charge applies to construction services; reverse charge on imported services','workflows':(['Sale → add 20% VAT → VRN on invoice'] if registered else [])+(['EU B2B sale → zero-rate → capture customer VAT number'] if supply=='UK + EU sales' and registered else [])+(['Export order → zero-rate → keep export evidence'] if supply=='UK + worldwide exports' and registered else []),'kpi':'VAT payable' if registered else 'Turnover watch','sources':[{'title':'GOV.UK: register for VAT (£90,000 threshold)','url':'https://www.gov.uk/register-for-vat'},{'title':'GOV.UK: VAT rates (20% standard)','url':'https://www.gov.uk/vat-rates'}],'effective':TODAY}
def usa(a):
 st=a.get('subdivision');reg=a.get('registration');collect=reg=='Collecting sales tax'
 rate=US_STATE.get(st);warns=[]
 if st and rate is None:warns.append('State not in the built-in rate table; confirm combined state and local rates with the state revenue department')
 elif st:warns.append('Local city/county/district add-ons can apply on top of the state rate')
 if a.get('supply')=='Across states':warns.append('Economic nexus can create collection duties in states where you have no presence (post-Wayfair; commonly $100,000 in sales)')
 if 'Marketplaces' in a.get('channels',[]):warns.append('Marketplace facilitator laws shift collection to the platform for marketplace sales in most states')
 rules=[(f'{st} sales tax → {rate}% state rate' + (' (no statewide sales tax)' if rate==0 else ' + applicable local rates')) if st and rate is not None and collect else 'No sales tax collection until registered in the state']
 return {'jurisdiction':'United States','subdivision':st,'tax_name':'Sales tax','authority':'State revenue departments (no federal sales tax)','currency':{'code':'USD','symbol':'$'},'registration':{'type':reg or 'Undecided','registered':collect,'label':f"Seller's permit in {st}" if st and collect else 'Register per state before collecting','threshold':'State-specific; economic nexus commonly $100,000'},'rates':{'structure':'State base rate plus local add-ons; five states have no statewide sales tax','slabs':([{'band':st+' state rate','rate':rate}] if st and rate is not None else []),'note':'Confirm combined rates and product exemptions per state'},'rules':rules,'invoice':['Receipt showing sales tax collected per jurisdiction' if collect else 'Commercial receipt until collecting'],'credits':'Resale certificates exempt wholesale purchases; no input credit chain','returns':['State sales tax returns per assigned frequency'] if collect else ['No returns until registered'],'validations':[{'check':'Economic nexus','status':'Track sales into each state against its threshold'},{'check':'Marketplace facilitator','status':'Platform collects on marketplace sales in most states' if 'Marketplaces' in a.get('channels',[]) else 'Not applicable'}],'warnings':warns,'reverse_charge':'Use tax accrual applies on untaxed business purchases','workflows':([f'Sale → collect {st} sales tax at combined rate'] if st and collect else [])+(['Inter-state sale → check destination-state nexus → register when threshold crossed'] if a.get('supply')=='Across states' else [])+(['Marketplace sale → platform collects → reconcile facilitator reports'] if 'Marketplaces' in a.get('channels',[]) else []),'kpi':'Sales tax collected' if collect else 'Nexus watch','sources':[{'title':'Supreme Court: South Dakota v. Wayfair (economic nexus)','url':'https://www.supremecourt.gov/opinions/17pdf/17-494_j4el.pdf'},{'title':'Streamlined Sales Tax: marketplace facilitator laws','url':'https://www.streamlinedsalestax.org/for-businesses/marketplace-facilitator'}],'effective':TODAY}
def canada(a):
 pv=a.get('subdivision');reg=a.get('registration');registered=reg=='GST/HST registered'
 model,rate=CA_PROV.get(pv,('GST/HST',None));warns=[]
 if pv and model!='GST/HST':warns.append(f'{pv} charges {model}'+(f' ({rate}% combined)' if rate else ''))
 if pv=='Quebec':warns.append('QST is administered by Revenu Québec, separate from CRA returns')
 if reg=='Not registered (small supplier)' and a.get('turnover')=='Above CA$30,000':warns.append('Turnover is above the CA$30,000 small-supplier threshold')
 rules=[(f'{pv} sales → charge {model}'+(f' at {rate}% combined' if rate else '')) if pv and registered else 'No GST/HST until registered']
 if a.get('supply')=='Across provinces':rules.append('Place-of-supply rules set the rate by destination province')
 if a.get('supply')=='Canada + exports':rules.append('Exports → zero-rated with evidence')
 return {'jurisdiction':'Canada','subdivision':pv,'tax_name':model if pv else 'GST/HST','authority':'Canada Revenue Agency'+( ' + Revenu Québec' if pv=='Quebec' else ''),'currency':{'code':'CAD','symbol':'CA$'},'registration':{'type':reg or 'Undecided','registered':registered,'label':'Business number with RT account' if registered else 'Small supplier; monitor CA$30,000 over four quarters','threshold':'CA$30,000 worldwide taxable sales over four quarters'},'rates':{'structure':'5% GST federal; HST 13-15% in participating provinces; separate PST/QST elsewhere','slabs':([{'band':pv,'rate':rate}] if pv and rate is not None else []),'note':'Confirm provincial rates and point-of-sale rebates'},'rules':rules,'invoice':['Invoice with BN/RT number and GST/HST amounts' if registered else 'Commercial invoice until registered'],'credits':'Input tax credits recover GST/HST paid on inputs' if registered else 'No ITCs until registered','returns':['GST/HST return per assigned period'] if registered else ['No returns until registered'],'validations':[{'check':'Place of supply','status':'Rate follows destination province for delivered goods'}],'warnings':warns,'reverse_charge':'Self-assessment can apply to certain imports and out-of-province purchases','workflows':([f'Sale → charge {model} in {pv}'] if pv and registered else [])+(['Delivered sale → apply destination-province rate'] if a.get('supply')=='Across provinces' and registered else [])+(['Export order → zero-rated → keep evidence'] if a.get('supply')=='Canada + exports' and registered else []),'kpi':'GST/HST payable' if registered else 'Turnover watch','sources':[{'title':'CRA: which GST/HST rate to charge (place of supply; NS HST 14% from 1 Apr 2025)','url':'https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/charge-collect-which-rate.html'},{'title':'CRA: GST/HST rates by province','url':'https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/charge-collect-which-rate/calculator.html'}],'effective':TODAY}
def eu(a):
 ms=a.get('subdivision');reg=a.get('registration');registered=reg in ('VAT registered','OSS registered')
 rate=EU_VAT.get(ms);warns=[]
 if ms=='Other member state':warns.append('Member state not in the built-in table; confirm its standard rate with the national tax authority')
 if a.get('supply')=='Across the EU':
  warns.append('B2C cross-border sales above €10,000 EU-wide trigger destination VAT; OSS simplifies reporting')
  rules_extra=['Intra-EU B2B supply → 0% with customer VAT number validated in VIES → customer reverse-charges']
 else:rules_extra=[]
 rules=[(f'Domestic {ms} supply → {rate}% standard VAT' if rate is not None else f'Domestic {ms} supply → confirm the member-state standard rate') if ms and registered else 'No VAT charged until registered']+rules_extra
 if a.get('supply')=='EU + exports outside the EU':rules.append('Exports outside the EU → zero-rated with customs evidence')
 return {'jurisdiction':'European Union','subdivision':ms,'tax_name':'VAT','authority':('National tax authority of '+ms if ms else 'National tax authorities')+' under the EU VAT Directive','currency':{'code':'EUR','symbol':'€'},'registration':{'type':reg or 'Undecided','registered':registered,'label':('VAT identification number' + (' + OSS scheme' if reg=='OSS registered' else '')) if registered else 'Register in your member state','threshold':'National thresholds; €10,000 EU-wide for cross-border B2C distance sales'},'rates':{'structure':'VAT Directive: standard rate at least 15%; member states set their own','slabs':([{'band':ms+' standard','rate':rate}] if rate is not None else []),'note':'Confirm member-state rates and reduced-rate categories'},'rules':rules,'invoice':['VAT invoice with VAT ID, rate, and reverse-charge note where applicable' if registered else 'Commercial invoice until registered'],'credits':'Input VAT deductible with valid invoices' if registered else 'No deductions until registered','returns':['National VAT returns per member state']+(['Quarterly OSS return for EU B2C distance sales'] if reg=='OSS registered' else []),'validations':[{'check':'VIES','status':'Validate customer VAT numbers for intra-EU B2B zero-rating'},{'check':'OSS threshold','status':'Above €10,000 cross-border B2C - charge destination VAT' if a.get('turnover')=='Above €10,000 cross-border sales' else 'Below €10,000 cross-border threshold'}],'warnings':warns,'reverse_charge':'B2B intra-EU acquisitions are reverse-charged to the customer','workflows':([f'Sale → charge {ms} VAT at {rate}%'] if ms and registered and rate is not None else [])+(['EU B2B sale → validate VAT number in VIES → zero-rate'] if a.get('supply')=='Across the EU' and registered else [])+(['B2C EU sale above threshold → destination VAT via OSS'] if a.get('supply')=='Across the EU' and reg=='OSS registered' else []),'kpi':'VAT payable' if registered else 'Threshold watch','sources':[{'title':'European Commission: VAT rates under the VAT Directive','url':'https://taxation-customs.ec.europa.eu/taxation/vat/vat-directive/vat-rates_en'},{'title':'European Commission: VAT One Stop Shop','url':'https://vat-one-stop-shop.ec.europa.eu/one-stop-shop_en'}],'effective':TODAY}
PACKS={'India':india,'UAE':uae,'Singapore':singapore,'China':china,'Vietnam':vietnam,'Malaysia':malaysia,'United Kingdom':uk,'United States':usa,'Canada':canada,'European Union':eu,**{c:(lambda a,_c=c:make_pack(a,TODAY)) for c in EXTRA_DATA}}
def tax_profile(a):
 c=a.get('country')
 if not c or c not in PACKS:return None
 if c in ('United States','Canada','European Union',*EXTRA_SUB) and not a.get('subdivision'):return None
 p=PACKS[c]
 need=[q['key'] for q in jq(a)]
 if not any(a.get(k) for k in ('turnover','registration','supply','buyers')):return None
 return p(a)
def partial(a):
 v=VERTICAL.get(a.get('vertical'),VERTICAL['Home & specialty']); name=a.get('name') or 'Your business'; locations=a.get('locations','One store'); channels=a.get('channels',[]); staff=a.get('staff',[]); credit=a.get('credit','No credit'); inv=a.get('inventory','Stockouts'); t=tax_profile(a)
 modules=[('home','Command','Live decisions and exceptions','⌂'),('sales',v['sale'],f"Checkout, returns, and {v['customer'].lower()}",'₹'),('catalog',v['items'],f"{v['unit']} catalog, prices, and tax",'◇'),('stock','Stock',inv+' control','▦')]
 if a.get('vertical'):modules.append(('special',*v['special']))
 if locations!='One store':modules.append(('network','Locations','Transfers and store comparison','◎'))
 if any(x!='In store' for x in channels):modules.append(('channel','Channels','One queue across digital sales','↔'))
 if credit!='No credit':modules.append(('ledger','Credit','Limits, dues, and follow-up','≋'))
 if staff:modules.append(('team','Team','Roles, targets, and approvals','♙'))
 if t:
  duty=next((f"{c}: {s}" for c,s in [(x['check'],x['status']) for x in t['validations']] if 'Required' in s or 'Mandatory' in s),t['registration']['threshold'])
  modules.append(('tax',t['tax_name'],f"{t['registration']['type']} · {t['jurisdiction']}"+(f" ({t['subdivision']})" if t['subdivision'] else ''),'⌗'))
 modules.append(('insights','Insights','Sales, margin, and stock analysis','↗'))
 roles=[]
 rolemap={'Cashiers':'Cashier · sell & return','Store managers':'Manager · approve & transfer','Buyers':'Buyer · purchase & price','Warehouse team':'Warehouse · receive & count','Accountant':'Accountant · books, tax & export'}
 for x in staff:roles.append(rolemap[x])
 if not roles:roles=['Owner · full access']
 workflows=['Sale complete → reduce stock → update cash',v['flow']]
 if locations!='One store':workflows.append('Store shortage → suggest transfer → manager approves')
 if any(x!='In store' for x in channels):workflows.append('Digital order → reserve stock → fulfil from best store')
 if credit!='No credit':workflows.append('Credit due → owner review → reminder draft')
 if 'Store managers' in staff:workflows.append('High discount → manager approval')
 if t:workflows+=t['workflows']
 kpis=v['kpis']
 if t:kpis=v['kpis'][:3]+[t['kpi']]
 return {'business':name,'vertical':a.get('vertical','Custom retail'),'accent':v['accent'],'currency':(t or {}).get('currency',{'code':'INR','symbol':'₹'}),'terminology':{'items':v['items'],'sales':v['sale'],'customers':v['customer'],'stock_unit':v['unit']},'priority':a.get('priority','Your first goal'),'modules':[{'id':x[0],'name':x[1],'why':x[2],'icon':x[3]} for x in modules],'navigation':[x[1] for x in modules],'kpis':kpis,'workflows':workflows,'roles':roles,'tax':t,'completion':round(len(a)/len(questions_for(a))*100)}
def configure(a):
 missing=[q['key'] for q in questions_for(a) if q['key'] not in a]
 if missing:raise ValueError('Missing answers: '+', '.join(missing))
 return partial(a)|{'version':2,'ready':True,'history':[],'answers':a}
def export_config(a):
 try:cfg=configure(a)
 except ValueError:cfg=partial(a)
 cfg['export']={'format':'mosaic-erp-blueprint','schema':3,'exported_at':datetime.now(timezone.utc).isoformat(),'contents':['business profile','terminology','navigation','kpis','modules','workflows','roles','tax profile','audit trail']}
 return cfg
EDITABLE={'country':'country','jurisdiction':'country','registration':'registration','turnover':'turnover','band':'turnover','supply':'supply','scope':'supply','buyers':'buyers','customers':'buyers','subdivision':'subdivision','state':'subdivision','province':'subdivision','member':'subdivision'}
def token(a):return hashlib.sha1(json.dumps(a,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:10]
def diff(old,new):
 out=[]
 on={m['name'] for m in old.get('modules',[])};nn={m['name'] for m in new.get('modules',[])}
 if on!=nn:out.append('modules: '+', '.join(sorted(nn-on) or ['none added'])+' changed')
 if old.get('workflows')!=new.get('workflows'):out.append('workflows updated ('+str(len(new['workflows']))+' active)')
 ot,nt=old.get('tax') or {},new.get('tax') or {}
 for k in ('registration','rates','rules','invoice','returns','validations','warnings'):
  if ot.get(k)!=nt.get(k):out.append('tax '+k+' changed')
 if old.get('kpis')!=new.get('kpis'):out.append('KPIs updated')
 return out
def chat(a,cfg,message,pending=None,draft=None):
 m=(message or '').strip(); ml=m.lower()
 if not m:return {'intent':'refuse','reply':'Say what you want to view or change. You can ask to see tax settings, change registration, turnover, supply scope, buyers, country, or state/province, then apply, export, or roll back.'}
 base=dict(draft or a)
 if ml in ('cancel','never mind','stop'):return {'intent':'cancel','reply':'Change discarded. Nothing was applied.'}
 if ml in ('rollback','undo','revert'):
  h=cfg.get('history') or []
  if not h:return {'intent':'refuse','reply':'Nothing to roll back yet - no applied changes are on record.'}
  last=h[-1];na=last['answers'];nc=configure(na);nc['history']=h[:-1];nc['version']=cfg.get('version',2)+1
  return {'intent':'rollback','reply':f"Rolled back the last change ({last.get('change','')}). Settings are back to version {last['version']}.",'config':nc}
 if ml.startswith('export') or ml.startswith('download'):
  e=export_config(a);return {'intent':'export','reply':'Full configuration export is ready as JSON, including the tax profile and audit trail.','export':e}
 if ml.startswith('apply') or ml in ('confirm','yes','yes apply'):
  if not pending:return {'intent':'refuse','reply':'There is no pending change to apply. Ask for a change first and review its preview.'}
  if pending.get('token')!=token(pending.get('answers',{})):return {'intent':'refuse','reply':'The pending change could not be verified. Ask for the change again.'}
  try:nc=configure(pending['answers'])
  except ValueError as e:return {'intent':'refuse','reply':'Cannot apply: '+str(e)}
  nc['history']=(cfg.get('history') or [])+[{'version':cfg.get('version',2),'at':datetime.now(timezone.utc).isoformat(),'change':pending.get('summary','change'),'answers':a}];nc['version']=cfg.get('version',2)+1
  return {'intent':'applied','reply':'Applied. '+pending.get('summary','')+' Version '+str(nc['version'])+' is live; say "rollback" to revert.','config':nc}
 if any(w in ml for w in ('show','view','what','current','list','status')) and any(w in ml for w in ('tax','compliance','setting','vat','gst','registration')):
  t=cfg.get('tax') or {}
  r=t.get('registration',{})
  return {'intent':'view','reply':f"Current {t.get('tax_name','tax')} settings: {t.get('jurisdiction','-')}{(' - '+t['subdivision']) if t.get('subdivision') else ''}. Registration: {r.get('type','-')} ({r.get('threshold','-')}). Rates: {t.get('rates',{}).get('structure','-')}. Returns: {('; '.join(t.get('returns',[]))) or '-'}. Sources on file: {len(t.get('sources',[]))}, effective {t.get('effective','-')}."}
 field=None
 for w,k in EDITABLE.items():
  if w in ml.split() or (w=='scope' and 'scope' in ml):field=k;break
 if field is None and any(w in ml for w in ('change','set','update','switch','move','enable','disable','add')):
  return {'intent':'refuse','reply':'I could not tell which setting to change. Editable settings: country, subdivision (state/province/member state), registration, turnover, supply scope, buyers.'}
 if field=='country':
  hit=[c for c in COUNTRIES if c.lower() in ml or any(x in ml for x in c.lower().split())]
  hit=[c for c in COUNTRIES if c.lower() in ml]
  if not hit:
   alias={'uae':'UAE','dubai':'UAE','britain':'United Kingdom','uk':'United Kingdom','usa':'United States','america':'United States','eu':'European Union','europe':'European Union','sg':'Singapore','ksa':'Saudi Arabia','saudi':'Saudi Arabia','korea':'South Korea'}
   hit=[v for k,v in alias.items() if k in ml]
  if len(hit)!=1:return {'intent':'refuse','reply':'Which country? Options: '+', '.join(COUNTRIES)+'.'}
  na=dict(base);na['country']=hit[0];na.pop('subdivision',None)
  for q in jq(na):
   if q['key'] not in na and q['key']!='subdivision':
    old=a.get(q['key'])
  missing=[q for q in jq(na) if q['key'] not in na]
  if any(q['key']=='subdivision' for q in missing):
   prompt=next(q['text'] for q in missing if q['key']=='subdivision')
   return {'intent':'collect','reply':f"{hit[0]} needs a sub-jurisdiction before I can preview. {prompt}",'draft':na}
  for q in missing:na[q['key']]=q['options'][0]
  return propose(a,na,cfg,'country',hit[0])
 if field=='subdivision':
  c=base.get('country')
  opts={'United States':sorted(US_STATE),'Canada':list(CA_PROV),'European Union':sorted(EU_VAT)+['Other member state'],**{k:v[1] for k,v in EXTRA_SUB.items()}}.get(c)
  if not opts:return {'intent':'refuse','reply':f"{c or 'This country'} has no sub-jurisdiction to set."}
  hit=[o for o in opts if o.lower() in ml]
  if len(hit)!=1:return {'intent':'refuse','reply':'Which one? Options: '+', '.join(opts)+'.'}
  na=dict(base);na['subdivision']=hit[0]
  return propose(a,na,cfg,'subdivision',hit[0])
 if field in ('registration','turnover','supply','buyers'):
  q=next((q for q in questions_for(base) if q['key']==field),None)
  if not q:return {'intent':'refuse','reply':'That setting needs a country first.'}
  hit=[o for o in q['options'] if o.lower() in ml]
  if len(hit)>1:return {'intent':'refuse','reply':'That matches more than one option - pick one: '+', '.join(hit)+'.'}
  if not hit:return {'intent':'refuse','reply':f"Valid {field} options: "+', '.join(q['options'])+'.'}
  na=dict(base);na[field]=hit[0]
  return propose(a,na,cfg,field,hit[0])
 if base.get('country') in ('United States','Canada','European Union',*EXTRA_SUB) and not base.get('subdivision'):
  opts={'United States':sorted(US_STATE),'Canada':list(CA_PROV),'European Union':sorted(EU_VAT)+['Other member state'],**{k:v[1] for k,v in EXTRA_SUB.items()}}[base['country']]
  hit=[o for o in opts if o.lower() in ml]
  if len(hit)==1:
   na=dict(base);na['subdivision']=hit[0]
   return propose(a,na,cfg,'subdivision',hit[0])
  return {'intent':'refuse','reply':'Pick one: '+', '.join(opts)+'.'}
 return {'intent':'refuse','reply':'I can view, change, apply, export, or roll back tax and compliance settings. Editable: country, subdivision, registration, turnover, supply scope, buyers.'}
def propose(a,na,cfg,field,value):
 missing=[q['key'] for q in questions_for(na) if q['key'] not in na]
 if missing:return {'intent':'refuse','reply':'This change leaves required answers missing: '+', '.join(missing)}
 oldv=a.get(field,'-')
 try:newc=configure(na)
 except ValueError as e:return {'intent':'refuse','reply':'Cannot preview: '+str(e)}
 t=newc.get('tax') or {}
 affects=diff(cfg,newc)
 p={'field':field,'from':oldv,'to':value,'summary':f"Change {field} from {oldv} to {value}",'affects':affects,'warnings':t.get('warnings',[]),'sources':t.get('sources',[]),'effective':t.get('effective','-'),'answers':na,'token':token(na)}
 return {'intent':'preview','reply':f"Preview: set {field} to {value} (was {oldv}). Affects: {('; '.join(affects)) or 'no structural change'}. Source: {t.get('sources',[{}])[0].get('title','-')}, effective {t.get('effective','-')}. "+(f"Warnings: {'; '.join(t['warnings'])}. " if t.get('warnings') else '')+'Say "apply" to confirm or "cancel" to discard.','preview':p}
class RateLimiter:
    """Persistent token bucket shared by all workers using the same database."""
    def __init__(self, rpm, store=None):
        self.rpm = max(int(rpm), 1); self.store = store
    def allow(self, identity):
        return (self.store or STORE).rate_allow(identity, self.rpm)

class Metrics:
    def __init__(self):
        self._lock = threading.Lock(); self.requests = {}; self.latency = {}
    def record(self, route, status, ms):
        with self._lock:
            k = f'{route}|{status}'
            self.requests[k] = self.requests.get(k, 0) + 1
            s, n = self.latency.get(route, (0.0, 0))
            self.latency[route] = (s + ms, n + 1)
    def snapshot(self):
        with self._lock:
            return {'requests': dict(self.requests),
                    'latency_ms_avg': {r: round(t / n, 2) for r, (t, n) in self.latency.items()}}

METRICS = Metrics()
def log_event(**kv):
    sys.stderr.write(json.dumps({'ts': datetime.now(timezone.utc).isoformat(), **kv}, ensure_ascii=False) + '\n')

class H(BaseHTTPRequestHandler):
    server_version = 'MosaicERP/2'
    def out(self, s, b, k='application/json', hdrs=None, rid=None):
        x = json.dumps(b, ensure_ascii=False).encode() if k == 'application/json' else b.encode()
        self.send_response(s)
        self.send_header('Content-Type', k)
        self.send_header('Content-Length', str(len(x)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        if k == 'application/json':
            self.send_header('Cache-Control', 'no-store')
        else:
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'")
        if rid:
            self.send_header('X-Request-ID', rid)
        for h, v in (hdrs or {}).items():
            self.send_header(h, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(x)
    def _route(self, fn):
        """Shared envelope: request id, rate limit, metrics, structured logs."""
        rid = self.headers.get('X-Request-ID') or 'req_' + secrets.token_hex(8)
        start = time.monotonic(); status = 500; route = self.command + ' ' + urlparse(self.path).path
        try:
            retry = LIMITER.allow(self._identity())
            if retry:
                status = 429
                return self.out(429, {'error': 'Rate limit exceeded; slow down and retry', 'request_id': rid},
                                hdrs={'Retry-After': str(max(int(retry), 1))}, rid=rid)
            status = fn(rid) or status
        except BrokenPipeError:
            status = 499
        except AuthError as e:
            status = e.status
            try:
                self.out(e.status, {'error': e.message, 'request_id': rid}, rid=rid)
            except Exception:
                pass
        except (Conflict, NotFound) as e:
            status = 409 if isinstance(e, Conflict) else 404
            try:
                self.out(status, {'error': str(e), 'request_id': rid}, rid=rid)
            except Exception:
                pass
        except Exception as e:
            status = 500
            log_event(request_id=rid, route=route, error=repr(e))
            try:
                self.out(500, {'error': 'Internal error; the request id is in the server log', 'request_id': rid}, rid=rid)
            except Exception:
                pass
        finally:
            ms = round((time.monotonic() - start) * 1000, 2)
            METRICS.record(route if status < 500 else route + ' (error)', status, ms)
            log_event(request_id=rid, route=route, status=status, ms=ms, identity=self._identity()[:12])
    def _identity(self):
        auth = self.headers.get('Authorization', '')
        return sha256(auth[7:])[:16] if auth.startswith('Bearer ') else (self.client_address[0] if self.client_address else 'unknown')
    def _auth(self, minimum='viewer'):
        auth = self.headers.get('Authorization', '')
        token = auth[7:].strip() if auth.startswith('Bearer ') else ''
        ident = STORE.authenticate(token)
        if not ident:
            session = STORE.authenticate_session(token)
            ident = session[:3] if session else None
        if not ident:
            raise AuthError(401, 'Missing or invalid Bearer API key')
        wid, key_id, role = ident
        if not Store.role_ok(role, minimum):
            raise AuthError(403, f'This key has role {role}; {minimum} or higher is required')
        return wid, key_id, role
    def _body(self):
        n = int(self.headers.get('Content-Length', '0'))
        if n <= 0 or n > MAX_BYTES:
            raise AuthError(413, 'Invalid request size')
        try:
            return json.loads(self.rfile.read(n))
        except json.JSONDecodeError:
            raise AuthError(400, 'Request body is not valid JSON')
    def do_GET(self):
        self._route(self._get)
    def do_POST(self):
        self._route(self._post)
    def do_PUT(self):
        self._route(self._put)
    def do_DELETE(self):
        self._route(self._delete)
    def _get(self, rid):
        p = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)
        if p == '/':
            return self.out(200, (ROOT / 'static.html').read_text(), 'text/html; charset=utf-8', rid=rid) or 200
        if p in ('/static.css', '/static.js'):
            kind = 'text/css; charset=utf-8' if p.endswith('.css') else 'application/javascript; charset=utf-8'
            return self.out(200, (ROOT / p[1:]).read_text(), kind, hdrs={'Cache-Control': 'public, max-age=3600'}, rid=rid) or 200
        if p == '/api/questions':
            return self.out(200, {'questions': questions_for({})}, rid=rid) or 200
        if p == '/health':
            return self.out(200, {'status': 'ok', 'schema_version': 1}, rid=rid) or 200
        if p == '/health/ready':
            try:
                ok = STORE.integrity_check()
            except Exception:
                ok = False
            return self.out(200 if ok else 503, {'status': 'ready' if ok else 'not-ready', 'database': ok}, rid=rid) or (200 if ok else 503)
        if p == '/metrics':
            return self.out(200, METRICS.snapshot(), rid=rid) or 200
        if p == '/api/workspace':
            wid, _, _ = self._auth('viewer')
            ws = STORE.get_workspace(wid)
            ws['versions'] = STORE.list_versions(wid)
            return self.out(200, ws, rid=rid) or 200
        if p == '/api/workspace/config':
            wid, _, _ = self._auth('viewer')
            v = qs.get('version', [None])[0]
            data = STORE.get_config(wid, int(v) if v else None)
            return self.out(200, data, rid=rid) or 200
        if p == '/api/workspace/versions':
            wid, _, _ = self._auth('viewer')
            return self.out(200, {'versions': STORE.list_versions(wid)}, rid=rid) or 200
        if p == '/api/workspace/audit':
            wid, _, _ = self._auth('viewer')
            return self.out(200, {'events': STORE.audit_trail(wid)}, rid=rid) or 200
        if p == '/api/workspace/export':
            wid, key_id, _ = self._auth('editor')
            data = STORE.export_workspace(wid, key_id)
            return self.out(200, data, hdrs={'Content-Disposition': 'attachment; filename="mosaic-erp-workspace-export.json"'}, rid=rid) or 200
        return self.out(404, {'error': 'Not found', 'request_id': rid}, rid=rid) or 404
    def _post(self, rid):
        p = urlparse(self.path).path
        if p in ('/api/questions', '/api/preview', '/api/configure', '/api/export', '/api/chat'):
            n = int(self.headers.get('Content-Length', '0'))
            if n <= 0 or n > MAX_BYTES:
                return self.out(413, {'error': 'Invalid request size', 'request_id': rid}, rid=rid) or 413
            try:
                d = json.loads(self.rfile.read(n))
                if p.endswith('questions'):
                    return self.out(200, {'questions': questions_for(d.get('answers', d))}, rid=rid) or 200
                if p.endswith('export'):
                    return self.out(200, export_config(d), hdrs={'Content-Disposition': 'attachment; filename="mosaic-erp-config.json"'}, rid=rid) or 200
                if p.endswith('chat'):
                    return self.out(200, chat(d.get('answers', {}), d.get('config', {}), d.get('message', ''), d.get('pending'), d.get('draft')), rid=rid) or 200
                return self.out(200, configure(d) if p.endswith('configure') else partial(d), rid=rid) or 200
            except Exception as e:
                return self.out(400, {'error': str(e), 'request_id': rid}, rid=rid) or 400
        if p == '/api/session':
            d = self._body()
            result = STORE.login(d.get('workspace_id',''), d.get('email',''), d.get('password',''))
            if not result:
                raise AuthError(401, 'Invalid workspace, email, or password')
            return self.out(201, result, hdrs={'Cache-Control':'no-store'}, rid=rid) or 201
        if p == '/api/workspaces':
            d = self._body()
            idem = self.headers.get('Idempotency-Key')
            req_hash = sha256(canon(d))
            if idem:
                hit = STORE._idem_lookup(idem, '', 'POST /api/workspaces', req_hash)
                if hit:
                    return self.out(hit['status'], hit['body'] | {'idempotent_replay': True},
                                    hdrs={'Idempotency-Replayed': 'true'}, rid=rid) or hit['status']
            wid, key = STORE.create_workspace(d.get('name', 'Workspace'))
            body = {'workspace_id': wid, 'api_key': key, 'role': 'owner',
                    'note': 'Store this key now; it is shown once and only its hash is kept.'}
            if idem:
                with STORE.tx():
                    STORE._idem_store(idem, '', 'POST /api/workspaces', req_hash, 201, body)
            return self.out(201, body, rid=rid) or 201
        if p == '/api/workspace/users':
            wid, actor_id, _ = self._auth('owner')
            d = self._body()
            result = STORE.create_user(wid, d.get('email',''), d.get('password',''), d.get('role','viewer'), actor_id)
            return self.out(201, result, rid=rid) or 201
        if p == '/api/workspace/rollback':
            wid, key_id, _ = self._auth('editor')
            d = self._body()
            target = d.get('version')
            if not isinstance(target, int):
                raise AuthError(400, 'Body must include integer "version" to restore')
            idem = self.headers.get('Idempotency-Key')
            result, replayed = STORE.rollback(wid, target, key_id, idem_key=idem,
                                              request_hash=sha256(canon(d)))
            hdrs = {'Idempotency-Replayed': 'true'} if replayed else None
            return self.out(200, result, hdrs=hdrs, rid=rid) or 200
        if p == '/api/workspace/keys':
            wid, key_id, _ = self._auth('owner')
            d = self._body()
            new_id, new_key = STORE.create_key(wid, d.get('role', 'viewer'), d.get('label', ''), key_id)
            return self.out(201, {'key_id': new_id, 'api_key': new_key, 'role': d.get('role', 'viewer'),
                                  'note': 'Store this key now; it is shown once and only its hash is kept.'}, rid=rid) or 201
        return self.out(404, {'error': 'Not found', 'request_id': rid}, rid=rid) or 404
    def _put(self, rid):
        p = urlparse(self.path).path
        if p == '/api/workspace/config':
            wid, key_id, _ = self._auth('editor')
            d = self._body()
            for field in ('answers', 'config'):
                if not isinstance(d.get(field), dict):
                    raise AuthError(400, f'Body must include object "{field}"')
            idem = self.headers.get('Idempotency-Key')
            result, replayed = STORE.save_config(wid, d['answers'], d['config'], int(d.get('base_version', 0)),
                                                 d.get('summary', ''), key_id, idem_key=idem,
                                                 request_hash=sha256(canon(d)))
            hdrs = {'Idempotency-Replayed': 'true'} if replayed else None
            return self.out(200, result, hdrs=hdrs, rid=rid) or 200
        return self.out(404, {'error': 'Not found', 'request_id': rid}, rid=rid) or 404
    def _delete(self, rid):
        p = urlparse(self.path).path
        if p.startswith('/api/workspace/keys/'):
            wid, key_id, _ = self._auth('owner')
            STORE.revoke_key(wid, p.rsplit('/', 1)[1], key_id)
            return self.out(200, {'revoked': True}, rid=rid) or 200
        if p == '/api/workspace':
            wid, key_id, _ = self._auth('owner')
            if self.headers.get('X-Confirm-Delete') != wid:
                raise AuthError(409, f'Destruction requires header X-Confirm-Delete: {wid}')
            STORE.delete_workspace(wid, key_id)
            return self.out(200, {'deleted': True, 'workspace_id': wid}, rid=rid) or 200
        return self.out(404, {'error': 'Not found', 'request_id': rid}, rid=rid) or 404
    def log_message(self, *a):
        pass

class AuthError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message

def create_store():
    return open_store()

STORE = create_store()
LIMITER = RateLimiter(os.getenv('MOSAIC_RATE_LIMIT_RPM', '120'), STORE)

def main():
    import argparse
    ap = argparse.ArgumentParser(description='Mosaic ERP server and data operations')
    sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('serve', help='Run the HTTP server (default)')
    b = sub.add_parser('backup', help='Consistent online backup of the workspace database')
    b.add_argument('--out', required=True, help='Destination .db file path')
    r = sub.add_parser('restore', help='Restore the database from a backup (stop the server first)')
    r.add_argument('--from', dest='src', required=True, help='Backup .db file path')
    r.add_argument('--yes', action='store_true', help='Confirm replacement of the live database file')
    args, _unknown = ap.parse_known_args()
    db_path = os.getenv('MOSAIC_DATABASE_URL') or os.getenv('MOSAIC_DB_PATH', str(ROOT / 'mosaic.db'))
    if args.cmd == 'backup':
        out = create_store().backup(args.out)
        print(f'Backup verified and written to {out}')
        return
    if args.cmd == 'restore':
        if not args.yes:
            raise SystemExit('Restore replaces the live database; re-run with --yes to confirm')
        Store.restore(args.src, db_path)
        print(f'Restored {args.src} -> {db_path}; integrity and schema verified before replacement')
        return
    host = os.getenv('MOSAIC_HOST', '127.0.0.1')
    port = int(os.getenv('PORT', '8000'))
    print(f'Mosaic ERP at http://{host}:{port} (database: {db_path})')
    ThreadingHTTPServer((host, port), H).serve_forever()

if __name__ == '__main__':
    main()
