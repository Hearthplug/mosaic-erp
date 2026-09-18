import json,re
from pathlib import Path
matrix=Path(__file__).with_name('COVERAGE_MATRIX.md').read_text()
rows=[]
for line in matrix.splitlines():
 if not line.startswith('| ') or line.startswith('| Story') or line.startswith('|---'):continue
 cells=[x.strip() for x in line.strip('|').split('|')]
 rows.append({'story':cells[0],'intent_families':re.findall(r'`([^`]+)`',cells[1]),'owning_tests':re.findall(r'`([^`]+)`',cells[2]),'boundary':cells[3]})
assert len(rows)>=17
out={'schema':'mosaic-user-story-coverage-v1','required_variants':['happy','paraphrase','clarify','invalid_value','permission_denial','cross_company','cancel','correction','idempotent_retry','recovery'],'acceptance':['intent_slot_correct','safe_fallback','owner_response_usable'],'stories':rows}
Path(__file__).with_name('coverage_manifest.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'stories':len(rows),'required_case_cells':len(rows)*10}))
