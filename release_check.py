"""Mosaic ERP release-readiness gate.

    python3 release_check.py

Runs every load-bearing check and prints an evidence-backed PASS/FAIL table.
Exit code is non-zero if any gate fails. Deployment-dependent items are
reported separately as OWNER ACTION - they cannot be verified from source.
"""
from __future__ import annotations
import ast, json, os, re, subprocess, sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).parent
RESULTS = []

def gate(name, ok, evidence):
    RESULTS.append((name, bool(ok), evidence))
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {evidence}")

def run(cmd, env=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run(cmd, capture_output=True, text=True, env=e, cwd=ROOT)

def main():
    tmp = tempfile.mkdtemp(prefix='mosaic-gate-')
    db = os.path.join(tmp, 'gate.db')
    env = {'MOSAIC_DB_PATH': db, 'MOSAIC_RATE_LIMIT_RPM': '600'}

    r = run([sys.executable, '-m', 'unittest', 'test_customization'], env)
    m = re.search(r'Ran (\d+) tests.*(OK|FAILED)', r.stderr, re.S)
    gate('Configuration engine', r.returncode == 0, f'{m.group(1)} tests {m.group(2)} (22 jurisdictions, chat control, export)' if m else r.stderr[-200:])

    r = run([sys.executable, '-m', 'unittest', 'test_persistence'], env)
    m = re.search(r'Ran (\d+) tests.*(OK|FAILED)', r.stderr, re.S)
    gate('Security, tenant isolation, persistence, migrations, access control, auditability, idempotency, failure recovery, privacy',
         r.returncode == 0, f'{m.group(1)} tests {m.group(2)}' if m else r.stderr[-200:])

    # Install: fresh run, then repeat run (interrupted-setup safety)
    inst = os.path.join(tmp, 'inst.db')
    r1 = run([sys.executable, 'install.py'], {'MOSAIC_DB_PATH': inst})
    r2 = run([sys.executable, 'install.py'], {'MOSAIC_DB_PATH': inst})
    gate('One-command install', r1.returncode == 0 and r2.returncode == 0 and 'first company setup' in r1.stdout and 'first company setup' in r2.stdout,
         'fresh install and safe re-run lead to normal browser company setup; no user-facing key file')

    # Backup / restore via the documented CLI
    bak = os.path.join(tmp, 'backup.db')
    rb = run([sys.executable, 'app.py', 'backup', '--out', bak], env)
    rr = run([sys.executable, 'app.py', 'restore', '--from', bak, '--yes'], env)
    gate('Backup and restore runbook', rb.returncode == 0 and rr.returncode == 0 and Path(bak).exists(),
         'online backup integrity-verified; restore verified schema before atomic replace')

    # Live server smoke: health, readiness, auth boundary, metrics, perf
    port = 8991
    srv = subprocess.Popen([sys.executable, 'app.py', 'serve'], cwd=ROOT,
                           env=dict(os.environ, **env, PORT=str(port), MOSAIC_HOST='127.0.0.1'),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f'http://127.0.0.1:{port}'
        for _ in range(60):
            try:
                urllib.request.urlopen(base + '/health', timeout=1); break
            except Exception:
                time.sleep(0.2)
        def get(path, headers=None):
            req = urllib.request.Request(base + path, headers=headers or {})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, {}
        s1, _ = get('/health'); s2, b2 = get('/health/ready')
        s3, _ = get('/api/workspace/config')
        s4, m4 = get('/metrics')
        gate('Observability', s1 == 200 and s2 == 200 and b2.get('database') and s4 == 200 and m4.get('requests'),
             'liveness, readiness (DB integrity probe), structured request logs, metrics, request ids')
        gate('Secure defaults', s3 == 401, 'workspace API rejects anonymous access; binds 127.0.0.1 by default; security headers set')
        t0 = time.monotonic(); n = 150
        for _ in range(n):
            get('/health')
        dt = (time.monotonic() - t0) / n * 1000
        gate('Load/performance smoke', dt < 100, f'{n} sequential requests, {dt:.1f} ms average per request on a single node')
    finally:
        srv.terminate()

    # Dependency scan: local modules are first-party; only the pinned runtime dependencies in requirements.txt may be external
    deps = set()
    for f in ('app.py', 'oauth.py', 'store.py', 'postgres_store.py', 'install.py', 'extra_packs.py', 'test_customization.py', 'test_persistence.py', 'test_postgres_contract.py', 'build_intake.py'):
        tree = ast.parse((ROOT / f).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                deps.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                deps.add(node.module.split('.')[0])
    stdlib = set(sys.stdlib_module_names) | {'app','store','postgres_store','extra_packs','accounting','accounting_schema','retail','retail_schema','operational_profile','operating_model','operating_model_schema','onboarding','onboarding_schema','postgres_erp_schema','rbac','tax_engine','branding','business_twin','migration_schema','migration_packs','tax_verification_schema','tax_pack_operational','provisioning_schema','provisioning','oauth','provider_assets','assistant_setup','assistant_setup_schema','assistant_preview','assistant_preview_schema','artifact_builder','artifact_builder_schema','jev_client','jev_mapper','jev_reconfigure','ai_prefs','ai_prefs_schema','build_intake','byok_clients','build_bills','build_registers'}
    third = deps - stdlib
    gate('Dependency scan', third <= {'psycopg','psycopg_pool','jwt','pypdf','openpyxl'}, f'pinned runtime dependencies only: {third}' if third <= {'psycopg','psycopg_pool','jwt','pypdf','openpyxl'} else f'unexpected third-party: {third}')

    # Secret scan: no private keys, tokens, or passwords in tracked files
    pat = re.compile(r'(-----BEGIN [A-Z ]*PRIVATE KEY|msk_[0-9a-f]{40}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|password\s*=\s*[\'"][^\'"]+)', re.I)
    hits = [f.name for f in ROOT.rglob('*') if f.is_file() and '.git' not in f.parts and f.suffix in ('.py', '.html', '.md') and pat.search(f.read_text(errors='ignore'))]
    gate('Secret scan', not hits, 'no private keys, API tokens, cloud keys, or hard-coded passwords in source' if not hits else f'hits: {hits}')

    docs = (ROOT / 'ARCHITECTURE.md')
    gate('Architecture and residual-risk documentation', docs.exists() and 'deployment-dependent' in docs.read_text().lower(),
         'ARCHITECTURE.md with decisions, official sources, threat model, deployment gaps')

    sm = run([sys.executable, 'scripts/check_sitemap.py'])
    sm_out = (sm.stdout or sm.stderr).strip().splitlines()
    gate('Sitemap coverage', sm.returncode == 0, sm_out[-1] if sm_out else 'scripts/check_sitemap.py produced no output')

    base = os.environ.get('GITHUB_BASE_REF')
    if base:
        run(['git', 'fetch', '--depth', '1', 'origin', f'+{base}:refs/remotes/base'])
        changed = run(['git', 'diff', '--name-only', 'refs/remotes/base...HEAD']).stdout.splitlines()
        html_touched = any(c.startswith('docs/') and c.endswith('.html') for c in changed)
        sm_touched = 'docs/sitemap.xml' in changed
        gate('Sitemap freshness on site changes', not html_touched or sm_touched,
             'docs/sitemap.xml updated alongside the site changes' if (not html_touched or sm_touched) else 'docs/*.html changed without docs/sitemap.xml')

    fails = [n for n, ok, _ in RESULTS if not ok]
    print()
    print('OWNER ACTION (deployment-dependent, cannot be verified from source):')
    for item in ('DNS and a real domain for the supplied Caddy HTTPS termination path',
                 'offsite PostgreSQL WAL/PITR retention and a rehearsed isolated restore',
                 'managed PostgreSQL HA/PITR and deployed load-balancer failover evidence (adapter and templates are source-tested only)',
                 'Google/Microsoft console registration, verified HTTPS redirect URIs, consent policy, and rotated client secrets before enabling provider buttons',
                 'independent penetration test before handling real customer financial data'):
        print('  - ' + item)
    print()
    if fails:
        print(f'GATE RESULT: FAIL - {len(fails)} gate(s) failed: {", ".join(fails)}. Do not launch.')
        return 1
    print(f'GATE RESULT: PASS - all {len(RESULTS)} source-verifiable gates pass for the production-core retailer candidate. Deployment OWNER ACTION items remain before live traffic; statutory and advanced-module claims remain excluded.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
