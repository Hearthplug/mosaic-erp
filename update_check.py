"""In-app update check against GitHub Releases.

Free and unauthenticated: the app asks GitHub for the latest published
release of Hearthplug/mosaic-erp at most once an hour (cached on disk
next to the database), compares it with the version stamped into the
build, and the app shell shows a dismissible banner when a newer
release exists. Desktop installers are unsigned, so the honest ceiling
is "download the installer and open it"; Docker users get the one-line
pull command. Offline or API failure means no banner, never an error.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = 'Hearthplug/mosaic-erp'
API_URL = f'https://api.github.com/repos/{REPO}/releases/latest'
IMAGE = 'hearthplug/mosaic-erp'  # Docker Hub: where most pulls happen
CACHE_TTL_SECONDS = 3600
KEEP_BACKUPS = 5


def current_version():
    """Version stamped into this build, or 'dev' for source runs."""
    env = os.getenv('MOSAIC_VERSION', '').strip()
    if env:
        return env
    for root in (Path(getattr(sys, '_MEIPASS', '.')), Path(__file__).parent):
        stamp = root / 'version.txt'
        if stamp.exists():
            text = stamp.read_text(encoding='utf-8').strip()
            if text:
                return text
    return 'dev'


def _parse(tag):
    m = re.match(r'^v?(\d+)\.(\d+)\.(\d+)', tag or '')
    return tuple(int(part) for part in m.groups()) if m else None


def _slug(text):
    return re.sub(r'[^A-Za-z0-9._-]+', '-', text or 'unknown')


def _cache_path():
    db = os.getenv('MOSAIC_DB_PATH', str(Path(__file__).parent / 'mosaic.db'))
    return Path(db).parent / 'update-check-cache.json'


def _fetch_latest():
    req = urllib.request.Request(API_URL, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'MosaicERP-update-check',
    })
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    assets = {}
    for asset in data.get('assets') or []:
        name = asset.get('name') or ''
        url = asset.get('browser_download_url') or ''
        if name.endswith('windows-x64-setup.exe'):
            assets['windows'] = url
        elif name.endswith('macos-arm64.dmg'):
            assets['mac'] = url
    return {
        'tag': data.get('tag_name') or '',
        'url': data.get('html_url') or '',
        'assets': assets,
    }


def latest_release(now=None):
    """Latest published release, cached hourly. None when unknown."""
    now = time.time() if now is None else now
    cache = _cache_path()
    try:
        saved = json.loads(cache.read_text(encoding='utf-8'))
        if now - saved.get('fetched_at', 0) < CACHE_TTL_SECONDS:
            return saved.get('release')
    except Exception:
        pass
    try:
        release = _fetch_latest()
    except Exception:
        release = None
    try:
        cache.write_text(json.dumps({'fetched_at': now, 'release': release}), encoding='utf-8')
    except Exception:
        pass
    return release


def running_in_docker():
    runtime = os.getenv('MOSAIC_RUNTIME', '').strip().lower()
    if runtime:
        return runtime == 'docker'
    return Path('/.dockerenv').exists()


def update_status(now=None):
    """Payload for GET /api/update-check."""
    current = current_version()
    release = latest_release(now)
    status = {
        'current': current,
        'latest': None,
        'update_available': False,
        'release_url': f'https://github.com/{REPO}/releases',
        'docker': running_in_docker(),
        'assets': {},
        'pull_command': None,
        'compose_command': None,
    }
    if not release or not release.get('tag'):
        return status
    status['latest'] = release['tag']
    status['release_url'] = release.get('url') or status['release_url']
    status['assets'] = release.get('assets') or {}
    status['pull_command'] = f'docker pull {IMAGE}:{release["tag"]}'
    status['compose_command'] = 'docker compose pull && docker compose up -d'
    current_parsed, latest_parsed = _parse(current), _parse(release['tag'])
    if current_parsed and latest_parsed and latest_parsed > current_parsed:
        status['update_available'] = True
    return status


def backup_before_upgrade(db_path, version=None, now=None):
    """Copy the database aside before a new version runs migrations.

    A fresh install only writes the version stamp. An upgrade - including
    the first v2.0 start of a v1.x install, which has no stamp - copies
    mosaic.db into backups/ first. At most KEEP_BACKUPS copies are kept.
    """
    version = version or current_version()
    db_path = Path(db_path)
    data_dir = db_path.parent
    stamp = data_dir / '.last-run-version'
    previous = stamp.read_text(encoding='utf-8').strip() if stamp.exists() else None
    if previous == version:
        return None
    backup = None
    if db_path.exists():
        backups = data_dir / 'backups'
        backups.mkdir(parents=True, exist_ok=True)
        when = datetime.fromtimestamp(now if now is not None else time.time(), timezone.utc)
        backup = backups / f'mosaic-{when.strftime("%Y%m%d-%H%M%S")}-before-{_slug(version)}-from-{_slug(previous)}.db'
        shutil.copy2(db_path, backup)
        for old in sorted(backups.glob('mosaic-*.db'))[:-KEEP_BACKUPS]:
            old.unlink()
    try:
        stamp.write_text(version, encoding='utf-8')
    except Exception:
        pass
    return backup


def backup_before_upgrade_from_env():
    """Startup hook for app.py: sqlite installs only; Postgres is managed."""
    url = os.environ.get('MOSAIC_DATABASE_URL', '')
    if url.startswith(('postgresql://', 'postgres://')):
        return None
    db = os.environ.get('MOSAIC_DB_PATH', str(Path(__file__).parent / 'mosaic.db'))
    return backup_before_upgrade(db)
