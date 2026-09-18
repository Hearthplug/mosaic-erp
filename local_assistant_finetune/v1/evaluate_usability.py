import json,sys
cases=[json.loads(x) for x in open(sys.argv[1] if len(sys.argv)>1 else 'local_assistant_finetune/v1/usability_cases.jsonl') if x.strip()]
required={'id','workflow','owner_request','expected_intent','required_slots','expected_behavior','synthetic'}
for c in cases:
 assert set(c)==required and c['synthetic'] is True
 assert c['owner_request'] and c['expected_behavior']
print(json.dumps({'cases':len(cases),'critical_failures_allowed':0,'metrics':['one_turn_completion_rate','unnecessary_clarification_rate','missing_clarification_rate','slot_edit_rate','deterministic_fallback_rate','reviewer_notes']}))
