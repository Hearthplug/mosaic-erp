"""Smoke-test a packaged Mosaic ERP executable: boot, health, pages, shutdown."""
import subprocess
import sys
import time
import urllib.request

exe = sys.argv[1]
port = '18765'
import os
env = os.environ.copy()
env['PORT'] = port
env['MOSAIC_DB_PATH'] = 'smoke-test.db'
proc = subprocess.Popen([exe], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, env=env)
try:
    base = f'http://127.0.0.1:{port}'
    deadline = time.time() + 60
    ok = False
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + '/health', timeout=2) as r:
                if r.status == 200:
                    ok = True
                    break
        except Exception:
            time.sleep(1)
    if not ok:
        sys.exit('executable did not answer /health within 60s')
    for path, want in (('/', b'Mosaic ERP'), ('/signin', b'MOSAIC'),
                       ('/mosaic-logo.svg', b'<svg'), ('/interview', b'Build my Mosaic')):
        with urllib.request.urlopen(base + path, timeout=5) as r:
            body = r.read()
            assert r.status == 200 and want in body, (path, r.status)
    print('SMOKE_OK health, home, signin, logo, interview all 200 with expected content')
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
