import unittest
from app import configure,partial,export_config,questions_for,BASE_QUESTIONS,chat
BASE={'name':'Asha','vertical':'Grocery','country':'India','locations':'One store','channels':['In store'],'inventory':'Stockouts','sales':'POS software','credit':'No credit','staff':['Cashiers'],'priority':'Checkout speed','turnover':'₹40 lakh – ₹1.5 crore','registration':'Regular','supply':'Within my state','buyers':'Consumers'}
def full(country,**over):
 a={k:v for k,v in BASE.items() if k not in ('turnover','registration','supply','buyers')}
 a|={'country':country}|over
 bands={'UAE':'Above AED 375,000','Singapore':'Above S$1 million','China':'Above RMB 5 million','Vietnam':'Any turnover','Malaysia':'Above RM500,000','United Kingdom':'Above £90,000','United States':'$100,000 – $1 million','Canada':'Above CA$30,000','European Union':'Above €10,000 cross-border sales'}
 regs={'UAE':'VAT registered','Singapore':'GST registered','China':'General VAT taxpayer','Vietnam':'Deduction method','Malaysia':'SST registered - goods','United Kingdom':'VAT registered','United States':'Collecting sales tax','Canada':'GST/HST registered','European Union':'OSS registered'}
 sup={'UAE':'Within the UAE','Singapore':'Within Singapore','China':'Within China','Vietnam':'Within Vietnam','Malaysia':'Within Malaysia','United Kingdom':'Within the UK','United States':'Within my state','Canada':'Within my province','European Union':'Within my member state'}
 if country in bands:
  for k,v in {'turnover':bands[country],'registration':regs[country],'supply':sup[country],'buyers':'Both'}.items():a.setdefault(k,v)
 return a
class EngineTests(unittest.TestCase):
 def ids(self,a):return {x['id'] for x in configure(a)['modules']}
 def test_base_interview_is_complete(self):self.assertEqual(len(BASE_QUESTIONS),10)
 def test_country_extends_interview(self):
  self.assertEqual(len(questions_for({'country':'India'})),14);self.assertEqual(len(questions_for({'country':'Canada'})),15);self.assertEqual(len(questions_for({})),10)
 def test_live_partial_configuration(self):
  p=partial({'name':'Asha','vertical':'Fashion'});self.assertEqual(p['terminology']['items'],'Styles');self.assertGreater(p['completion'],0)
 def test_grocery_language_and_expiry_flow(self):
  r=configure(BASE);self.assertEqual(r['terminology']['customers'],'Shoppers');self.assertTrue(any('Expiry' in x for x in r['workflows']))
 def test_fashion_changes_real_structure(self):
  r=configure(BASE|{'vertical':'Fashion','inventory':'Variants / serials'});self.assertEqual(r['terminology']['items'],'Styles');self.assertEqual(r['terminology']['stock_unit'],'Variant');self.assertIn('Size & colour matrix',[x['name'] for x in r['modules']])
 def test_pharmacy_multistore_omnichannel_credit(self):
  a=BASE|{'vertical':'Pharmacy','locations':'2–5 stores','channels':['In store','WhatsApp / social'],'credit':'Customer + supplier','staff':['Store managers','Accountant']};r=configure(a);self.assertTrue({'network','channel','ledger','team'}<=self.ids(a));self.assertIn('Batch & expiry',[x['name'] for x in r['modules']]);self.assertTrue(any('manager' in x.lower() for x in r['roles']))
 def test_electronics_warranty_and_serials(self):
  r=configure(BASE|{'vertical':'Electronics'});self.assertEqual(r['terminology']['stock_unit'],'Serial');self.assertIn('Serials & warranty',[x['name'] for x in r['modules']])
 def test_beauty_adds_service_model(self):
  r=configure(BASE|{'vertical':'Beauty & wellness'});self.assertIn('Services & appointments',[x['name'] for x in r['modules']]);self.assertIn('Bookings',r['kpis'])
 def test_single_store_has_no_network_module(self):self.assertNotIn('network',self.ids(BASE))
 def test_incomplete_final_rejected(self):
  with self.assertRaises(ValueError):configure({'name':'A'})
class IndiaGstTests(unittest.TestCase):
 def tax(self,a):return configure(a)['tax']
 def test_tax_module_appears(self):self.assertIn('tax',{x['id'] for x in configure(BASE)['modules']})
 def test_intra_state_splits_cgst_sgst(self):
  t=self.tax(BASE);self.assertEqual(t['rules'],['Intra-state sale → CGST + SGST (half each)']);self.assertIn('Sale → split CGST + SGST by slab',configure(BASE)['workflows'])
 def test_inter_state_uses_igst_and_eway_bill(self):
  a=BASE|{'supply':'Across India'};t=self.tax(a);self.assertTrue(any('IGST' in x for x in t['rules']));self.assertIn('Inter-state consignment above ₹50,000 → e-way bill before dispatch',configure(a)['workflows'])
 def test_exports_are_zero_rated_under_lut(self):
  self.assertTrue(any('zero-rated under LUT' in x for x in self.tax(BASE|{'supply':'India + exports'})['rules']))
 def test_composition_bill_of_supply_no_itc(self):
  a=BASE|{'registration':'Composition'};t=self.tax(a);self.assertIn('Bill of supply',t['invoice'][0]);self.assertTrue(t['credits'].startswith('No ITC'));self.assertEqual(t['returns'],['CMP-08 quarterly payment','GSTR-4 annual return']);self.assertIn('Composition tax',configure(a)['kpis'])
 def test_composition_ineligible_above_limit(self):
  t=self.tax(BASE|{'registration':'Composition','turnover':'₹1.5 – 5 crore'});self.assertEqual(t['registration']['type'],'Regular');self.assertTrue(any('capped at ₹1.5 crore' in x for x in t['warnings']))
 def test_einvoicing_mandatory_above_5cr_b2b(self):
  t=self.tax(BASE|{'turnover':'Above ₹5 crore','buyers':'Both'});v={x['check']:x['status'] for x in t['validations']};self.assertIn('Required',v['E-invoicing']);self.assertTrue(any('IRN + QR code from IRP' in x for x in configure(BASE|{'turnover':'Above ₹5 crore','buyers':'Both'})['workflows']))
 def test_hsn_digits_follow_turnover(self):
  v=lambda a:{x['check']:x['status'] for x in self.tax(a)['validations']};self.assertIn('4-digit',v(BASE)['HSN codes']);self.assertIn('6-digit',v(BASE|{'turnover':'Above ₹5 crore'})['HSN codes'])
 def test_marketplace_sales_add_tcs_reconciliation(self):
  self.assertTrue(any('TCS' in x for x in configure(BASE|{'channels':['In store','Marketplaces']})['workflows']))
 def test_unregistered_watches_threshold(self):
  t=self.tax(BASE|{'registration':'Not registered yet','turnover':'Up to ₹40 lakh'});self.assertFalse(t['registration']['registered']);self.assertTrue(any('₹40 lakh' in x for x in t['returns']));self.assertIn('Turnover watch',configure(BASE|{'registration':'Not registered yet','turnover':'Up to ₹40 lakh'})['kpis'])
 def test_sources_and_effective_date_on_file(self):
  t=self.tax(BASE);self.assertGreaterEqual(len(t['sources']),2);self.assertTrue(all('http' in s['url'] for s in t['sources']));self.assertTrue(t['effective'])
class JurisdictionPackTests(unittest.TestCase):
 def tax(self,c,**o):return configure(full(c,**o))['tax']
 def test_uae_vat(self):
  t=self.tax('UAE');self.assertEqual(t['tax_name'],'VAT');self.assertIn('AED 375,000',t['registration']['threshold']);self.assertTrue(any(s['rate']==5 for s in t['rates']['slabs']));self.assertIn('tax.gov.ae',t['sources'][0]['url'])
 def test_uae_warns_over_threshold_unregistered(self):
  t=self.tax('UAE',**{'registration':'Not registered'});self.assertTrue(any('mandatory registration' in w for w in t['warnings']))
 def test_singapore_gst9(self):
  t=self.tax('Singapore');self.assertTrue(any(s['rate']==9 for s in t['rates']['slabs']));self.assertIn('S$1 million',t['registration']['threshold'])
 def test_china_vat13_general_taxpayer(self):
  t=self.tax('China');self.assertTrue(any(s['rate']==13 for s in t['rates']['slabs']));self.assertIn('fapiao',t['invoice'][0]);t2=self.tax('China',**{'registration':'Small-scale taxpayer'});self.assertIn('No input credit',t2['credits'])
 def test_vietnam_reduction_window(self):
  t=self.tax('Vietnam');self.assertTrue(any(s['rate']==8 for s in t['rates']['slabs']));self.assertTrue(any('31 Dec 2026' in x['status'] for x in t['validations']))
 def test_malaysia_sst(self):
  t=self.tax('Malaysia');self.assertIn('RM500,000',t['registration']['threshold']);self.assertEqual(t['returns'],['SST-02 return every two months'])
 def test_uk_vat_mtd(self):
  t=self.tax('United Kingdom');self.assertIn('£90,000',t['registration']['threshold']);self.assertTrue(any(s['rate']==20 for s in t['rates']['slabs']));self.assertTrue(any('MTD' in r for r in t['returns']))
 def test_us_state_preserved_and_local_warning(self):
  t=self.tax('United States',**{'subdivision':'California'});self.assertEqual(t['subdivision'],'California');self.assertTrue(any(s['rate']==7.25 for s in t['rates']['slabs']));self.assertTrue(any('Local' in w for w in t['warnings']));t2=self.tax('United States',**{'subdivision':'Oregon'});self.assertTrue(any('no statewide sales tax' in r for r in t2['rules']))
 def test_us_economic_nexus_when_crossing_states(self):
  t=self.tax('United States',**{'subdivision':'Texas','supply':'Across states'});self.assertTrue(any('Economic nexus' in w for w in t['warnings']))
 def test_canada_province_models(self):
  self.assertTrue(any(s['rate']==13 for s in self.tax('Canada',**{'subdivision':'Ontario'})['rates']['slabs']))
  ns=self.tax('Canada',**{'subdivision':'Nova Scotia'});self.assertTrue(any(s['rate']==14 for s in ns['rates']['slabs']))
  qc=self.tax('Canada',**{'subdivision':'Quebec'});self.assertTrue(any('Revenu Québec' in w for w in qc['warnings']))
 def test_eu_member_state_and_oss(self):
  t=self.tax('European Union',**{'subdivision':'Germany'});self.assertTrue(any(s['rate']==19 for s in t['rates']['slabs']));self.assertTrue(any('OSS' in r for r in t['returns']))
  t2=self.tax('European Union',**{'subdivision':'Germany','supply':'Across the EU'});self.assertTrue(any('VIES' in r for r in t2['rules']))
 def test_eu_requires_member_state(self):
  a=full('European Union');a.pop('subdivision',None);self.assertIsNone(partial(a)['tax'])
class ExportTests(unittest.TestCase):
 def test_export_json_carries_full_configuration(self):
  e=export_config(BASE);self.assertEqual(e['export']['format'],'mosaic-erp-blueprint');self.assertIn('tax profile',e['export']['contents']);self.assertIn('audit trail',e['export']['contents']);self.assertEqual(e['tax']['jurisdiction'],'India');self.assertTrue(e['ready'])
 def test_export_partial_still_valid(self):
  e=export_config({'name':'Kirana'});self.assertIsNone(e['tax']);self.assertIn('export',e)
class ChatTests(unittest.TestCase):
 def setUp(self):self.cfg=configure(BASE)
 def test_view_settings(self):
  r=chat(BASE,self.cfg,'show my tax settings');self.assertEqual(r['intent'],'view');self.assertIn('GST',r['reply']);self.assertIn('Regular',r['reply'])
 def test_change_preview_requires_confirmation(self):
  r=chat(BASE,self.cfg,'change registration to composition');self.assertEqual(r['intent'],'preview');p=r['preview'];self.assertEqual(p['to'],'Composition');self.assertEqual(p['from'],'Regular');self.assertTrue(p['affects']);self.assertTrue(p['sources']);self.assertTrue(p['effective']);self.assertNotIn('config',r)
 def test_apply_versions_and_audits(self):
  r=chat(BASE,self.cfg,'change registration to composition');r2=chat(BASE,self.cfg,'apply',pending=r['preview']);self.assertEqual(r2['intent'],'applied');nc=r2['config'];self.assertEqual(nc['version'],3);self.assertEqual(nc['tax']['registration']['type'],'Composition');self.assertEqual(len(nc['history']),1)
 def test_rollback_restores_previous(self):
  r=chat(BASE,self.cfg,'change registration to composition');r2=chat(BASE,self.cfg,'apply',pending=r['preview']);r3=chat(BASE,r2['config'],'rollback');self.assertEqual(r3['intent'],'rollback');self.assertEqual(r3['config']['tax']['registration']['type'],'Regular');self.assertEqual(len(r3['config']['history']),0)
 def test_apply_rejects_forged_pending(self):
  r=chat(BASE,self.cfg,'change registration to composition');p=dict(r['preview']);p['answers']=dict(p['answers'],registration='Regular');r2=chat(BASE,self.cfg,'apply',pending=p);self.assertEqual(r2['intent'],'refuse')
 def test_apply_without_pending_refused(self):
  self.assertEqual(chat(BASE,self.cfg,'apply')['intent'],'refuse')
 def test_ambiguous_change_refused(self):
  r=chat(BASE,self.cfg,'make my tax better');self.assertEqual(r['intent'],'refuse');self.assertIn('country',r['reply'])
 def test_invalid_value_lists_options(self):
  r=chat(BASE,self.cfg,'change registration to gold');self.assertEqual(r['intent'],'refuse');self.assertIn('Composition',r['reply'])
 def test_country_change_collects_subdivision(self):
  r=chat(BASE,self.cfg,'switch country to canada');self.assertEqual(r['intent'],'collect');self.assertEqual(r['draft']['country'],'Canada')
  r2=chat(BASE,self.cfg,'ontario',draft=r['draft']);self.assertEqual(r2['intent'],'preview');self.assertEqual(r2['preview']['to'],'Ontario')
  r3=chat(BASE,self.cfg,'apply',pending=r2['preview']);nc=r3['config'];self.assertEqual(nc['tax']['jurisdiction'],'Canada');self.assertEqual(nc['tax']['subdivision'],'Ontario');self.assertTrue(any(s['rate']==13 for s in nc['tax']['rates']['slabs']))
 def test_multi_turn_jurisdiction_switch(self):
  r=chat(BASE,self.cfg,'change country to uae');na=r['preview']['answers'];r2=chat(BASE,self.cfg,'apply',pending=r['preview']);nc=r2['config'];self.assertEqual(nc['tax']['tax_name'],'VAT');self.assertIn('AED 375,000',nc['tax']['registration']['threshold'])
 def test_unsafe_composition_change_warns_in_preview(self):
  a=BASE|{'turnover':'Above ₹5 crore'};cfg=configure(a);r=chat(a,cfg,'change registration to composition');self.assertEqual(r['intent'],'preview');self.assertTrue(any('capped' in w for w in r['preview']['warnings']))
 def test_export_from_chat(self):
  r=chat(BASE,self.cfg,'export my tax configuration');self.assertEqual(r['intent'],'export');self.assertEqual(r['export']['tax']['jurisdiction'],'India')
 def test_rollback_without_history_refused(self):
  self.assertEqual(chat(BASE,self.cfg,'rollback')['intent'],'refuse')
if __name__=='__main__':unittest.main()
