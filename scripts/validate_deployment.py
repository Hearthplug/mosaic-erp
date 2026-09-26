#!/usr/bin/env python3
"""Dependency-free static validation for release deployment artifacts."""
from pathlib import Path
import json, re, subprocess, sys
R = Path(__file__).resolve().parents[1]
errors = []
def need(path, *tokens):
    text = (R / path).read_text()
    for token in tokens:
        if token not in text:
            errors.append(f'{path}: missing {token}')
need('Dockerfile', 'USER 10001:10001', 'HEALTHCHECK', 'ENTRYPOINT ["python", "app.py"]', '@sha256:')
need('compose.yml', 'read_only: true', 'no-new-privileges:true', 'cap_drop: [ALL]', 'MOSAIC_DATABASE_URL', 'MOSAIC_PUBLIC_ORIGIN', 'ports: ["80:80", "443:443"]')
need('Caddyfile', 'reverse_proxy app:8000', 'Strict-Transport-Security')
need('deploy/helm/mosaic-erp/templates/validate.yaml', 'hosted ingress requires config.publicOrigin', 'hosted ingress requires ingress.tls', 'every ingress host must match config.publicOrigin')
need('deploy/kubernetes/base/deployment.yaml', 'runAsNonRoot: true', 'readOnlyRootFilesystem: true', 'startupProbe:', 'readinessProbe:', 'livenessProbe:', 'MOSAIC_DATABASE_URL')
need('deploy/helm/mosaic-erp/templates/deployment.yaml', 'runAsNonRoot: true', 'readOnlyRootFilesystem: true', 'startupProbe:', 'MOSAIC_DATABASE_URL')
need('deploy/helm/mosaic-erp/templates/migrate-job.yaml', 'pre-install', 'pre-upgrade', 'migrationSecretName')
need('deploy/helm/mosaic-erp/templates/networkpolicy.yaml', 'NetworkPolicy', 'policyTypes: [Ingress, Egress]')
schema = json.loads((R/'deploy/helm/mosaic-erp/values.schema.json').read_text())
if schema['properties']['replicaCount'].get('minimum') != 2: errors.append('chart schema must require at least two production replicas')
if 'YOUR_DOCKERHUB_NAMESPACE' not in (R/'deploy/kubernetes/base/deployment.yaml').read_text(): errors.append('raw manifest must retain explicit registry placeholder')
# Inspect versioned source, not ignored runtime databases created by tests.
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=R).split(b'\0')
for name in tracked:
    if not name: continue
    p = R / name.decode('utf-8', errors='surrogateescape')
    if p.is_file() and p.stat().st_size < 2_000_000:
        t = p.read_text(errors='ignore')
        if re.search(r'(DOCKERHUB_TOKEN|client_secret|password)\s*[:=]\s*["\']?[A-Za-z0-9_\-]{16,}', t, re.I):
            errors.append(f'{p.relative_to(R)}: possible committed secret')
if errors:
    print('\n'.join('FAIL '+e for e in errors)); sys.exit(1)
print('PASS deployment artifacts: pinned base, private app port, HTTPS edge, hosted ingress TLS gate, PostgreSQL secrets, migration job, probes, pod security, and network policy')
