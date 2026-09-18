"""Convert all 22 source-backed country packs into fail-closed operational candidates."""
from app import COUNTRIES,PACKS
from store import canon,sha256
SCHEMA_VERSION=1
def candidate(country,answers=None):
 a={'country':country,'registration':'Verified candidate','turnover':'Candidate','supply':'Within '+country,'buyers':'Both',**(answers or {})};
 if country in ('United States','Canada','European Union'):a['subdivision']={'United States':'California','Canada':'Ontario','European Union':'Germany'}[country]
 p=PACKS[country](a);slabs=p.get('rates',{}).get('slabs',[])
 rules=[]
 for idx,x in enumerate(slabs):
  rate=x.get('rate');
  if not isinstance(rate,(int,float)):continue
  rules.append({'code':str(x.get('band') or x.get('name') or f'RATE{idx+1}').upper().replace(' ','_')[:40],'rate_percent':str(rate),'effective_from':p.get('effective'),'effective_to':None,'scope':'candidate_only','price_includes_tax':None})
 return {'schema_version':SCHEMA_VERSION,'jurisdiction':country,'currency':p.get('currency',{}).get('code'),'registration':p.get('registration'),'candidate_rules':rules,'sources':p.get('sources',[]),'warnings':p.get('warnings',[]),'verification_state':'requires_owner_or_professional_review','statutory_adapter_state':'disabled','pack_hash':sha256(canon(p))}
def all_candidates():return {c:candidate(c) for c in COUNTRIES}
