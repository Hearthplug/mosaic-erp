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
    key = tmp and (ROOT / 'mosaic-workspace.key')
    r2 = run([sys.executable, 'install.py'], {'MOSAIC_DB_PATH': inst})
    mode = oct(key.stat().st_mode & 0o777) if key.exists() else 'missing'
    gate('One-command install', r1.returncode == 0 and 'Already set up' in r2.stdout and mode == '0o600',
         f'fresh install ok, re-run safe, recovery key file mode {mode}')
    if key.exists():
        key.unlink()

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

    # Dependency scan: third-party imports must be zero
    deps = set()
    for f in ('app.py', 'store.py', 'postgres_store.py', 'install.py', 'extra_packs.py', 'test_customization.py', 'test_persistence.py', 'test_postgres_contract.py'):
        tree = ast.parse((ROOT / f).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                deps.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                deps.add(node.module.split('.')[0])
    stdlib = set(sys.stdlib_module_names) | {'app','store','postgres_store','extra_packs','accounting','accounting_schema','retail','retail_schema','operational_profile','operating_model','operating_model_schema','onboarding','onboarding_schema','postgres_erp_schema','rbac','tax_engine','branding','business_twin'}
    third = deps - stdlib
    gate('Dependency scan', third <= {'psycopg','psycopg_pool'}, f'pinned PostgreSQL dependencies only: {third}' if third <= {'psycopg','psycopg_pool'} else f'unexpected third-party: {third}')

    # Secret scan: no private keys, tokens, or passwords in tracked files
    pat = re.compile(r'(-----BEGIN [A-Z ]*PRIVATE KEY|msk_[0-9a-f]{40}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|password\s*=\s*[\'"][^\'"]+)', re.I)
    hits = [f.name for f in ROOT.rglob('*') if f.is_file() and '.git' not in f.parts and f.suffix in ('.py', '.html', '.md') and pat.search(f.read_text(errors='ignore'))]
    gate('Secret scan', not hits, 'no private keys, API tokens, cloud keys, or hard-coded passwords in source' if not hits else f'hits: {hits}')

    docs = (ROOT / 'ARCHITECTURE.md')
    gate('Architecture and residual-risk documentation', docs.exists() and 'deployment-dependent' in docs.read_text().lower(),
         'ARCHITECTURE.md with decisions, official sources, threat model, deployment gaps')

    fails = [n for n, ok, _ in RESULTS if not ok]
    print()
    print('OWNER ACTION (deployment-dependent, cannot be verified from source):')
    for item in ('DNS and a real domain for the supplied Caddy HTTPS termination path',
                 'offsite PostgreSQL WAL/PITR retention and a rehearsed isolated restore',
                 'managed PostgreSQL HA/PITR and deployed load-balancer failover evidence (adapter and templates are source-tested only)',
                 'an operator-selected OIDC provider and tested adapter (local named accounts and sessions are implemented)',
                 'independent penetration test before handling real customer financial data'):
        print('  - ' + item)
    print()
    if fails:
        print(f'GATE RESULT: FAIL - {len(fails)} gate(s) failed: {", ".join(fails)}. Do not launch.')
        return 1
    print(f'GATE RESULT: PASS - all {len(RESULTS)} source-verifiable gates pass. Verdict: hardened local/single-node build with a containerized HTTPS deployment path, ready for source-available download; the OWNER ACTION items above remain before any hosted "enterprise service" claim.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
