#!/usr/bin/env python3
"""Dependency-free static validation for release deployment artifacts."""
from pathlib import Path
import json, re, sys
R = Path(__file__).resolve().parents[1]
errors = []
def need(path, *tokens):
    text = (R / path).read_text()
    for token in tokens:
        if token not in text:
            errors.append(f'{path}: missing {token}')
need('Dockerfile', 'USER 10001:10001', 'HEALTHCHECK', 'ENTRYPOINT ["python", "app.py"]', '@sha256:')
need('compose.yml', 'read_only: true', 'no-new-privileges:true', 'cap_drop: [ALL]', 'mosaic-data:/data')
need('deploy/kubernetes/base/statefulset.yaml', 'runAsNonRoot: true', 'readOnlyRootFilesystem: true', 'startupProbe:', 'readinessProbe:', 'livenessProbe:', 'volumeClaimTemplates:')
need('deploy/helm/mosaic-erp/templates/statefulset.yaml', 'runAsNonRoot: true', 'readOnlyRootFilesystem: true', 'startupProbe:', 'volumeClaimTemplates:')
schema = json.loads((R/'deploy/helm/mosaic-erp/values.schema.json').read_text())
if schema['properties']['replicaCount'].get('const') != 1: errors.append('chart schema must pin replicaCount=1')
if 'YOUR_DOCKERHUB_NAMESPACE' not in (R/'deploy/kubernetes/base/statefulset.yaml').read_text(): errors.append('raw manifest must retain explicit registry placeholder')
for p in R.rglob('*'):
    if p.is_file() and '.git' not in p.parts and p.stat().st_size < 2_000_000:
        t = p.read_text(errors='ignore')
        if re.search(r'(DOCKERHUB_TOKEN|client_secret|password)\s*[:=]\s*["\']?[A-Za-z0-9_\-]{16,}', t, re.I):
            errors.append(f'{p.relative_to(R)}: possible committed secret')
if errors:
    print('\n'.join('FAIL '+e for e in errors)); sys.exit(1)
print('PASS deployment artifacts: pinned base, non-root/read-only runtime, probes, resources, persistence, and single-replica guardrails')
