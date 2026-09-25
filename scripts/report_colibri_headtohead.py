import json,sys
a=json.load(open('benchmark-amd64.json'));b=json.load(open('benchmark-colibri-olmoe.json'))
def g(d,*ks):
    for k in ks:
        if k in d: return d[k]
    return None
rows=[('metric','current: Qwen2.5-1.5B+adapter (llama.cpp)','colibri: OLMoE-1B-7B (int8)')]
keys=[('exact_schema_rate','exact_schema_rate'),('label_accuracy','label_accuracy'),
 ('intent_slot_rate','intent_slot_rate'),('unsafe_rejection_rate','unsafe_rejection_rate'),
 ('clarify_rate','clarify_rate'),('startup_seconds','startup_s','startup_seconds'),('p50_ms','p50_ms'),('p95_ms','p95_ms'),
 ('peak_rss_mb','peak_rss_mb'),('max_cpu_percent','max_cpu_percent','max_cpu_pct'),('disk_bytes','disk_bytes')]
report={}
for row in keys:
    name=row[0];av=g(a,*row[1:]);bv=g(b,*row[1:])
    rows.append((name,av,bv));report[name]={'current':av,'colibri':bv}
for r in rows: print(' | '.join(str(x) for x in r))
json.dump({'current_stack':a,'colibri_olmoe':b,'comparison':report},open('headtohead-report.json','w'),indent=1)
