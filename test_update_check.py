"""In-app update check: version compare, hourly cache, offline silence, pre-upgrade backups."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import update_check

LATEST = {
    'tag': 'v2.0.0',
    'url': 'https://example.test/releases/v2.0.0',
    'assets': {'windows': 'https://example.test/win.exe', 'mac': 'https://example.test/mac.dmg'},
}


class UpdateCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {
            'MOSAIC_DB_PATH': str(Path(self.tmp) / 'mosaic.db'),
        })
        self.env.start()
        for key in ('MOSAIC_VERSION', 'MOSAIC_RUNTIME', 'MOSAIC_DATABASE_URL'):
            os.environ.pop(key, None)
        self.fetch = mock.patch.object(update_check, '_fetch_latest', return_value=dict(LATEST))
        self.fetch.start()

    def tearDown(self):
        self.fetch.stop()
        self.env.stop()

    def test_parse_versions(self):
        self.assertEqual(update_check._parse('v2.0.0'), (2, 0, 0))
        self.assertEqual(update_check._parse('1.4.2'), (1, 4, 2))
        self.assertIsNone(update_check._parse('dev'))
        self.assertIsNone(update_check._parse(None))

    def test_current_version_env_wins(self):
        os.environ['MOSAIC_VERSION'] = 'v1.4.0'
        self.assertEqual(update_check.current_version(), 'v1.4.0')

    def test_current_version_dev_default(self):
        self.assertEqual(update_check.current_version(), 'dev')

    def test_update_available_when_newer(self):
        os.environ['MOSAIC_VERSION'] = 'v1.4.0'
        status = update_check.update_status()
        self.assertTrue(status['update_available'])
        self.assertEqual(status['current'], 'v1.4.0')
        self.assertEqual(status['latest'], 'v2.0.0')
        self.assertEqual(status['release_url'], LATEST['url'])
        self.assertTrue(status['assets']['windows'].endswith('win.exe'))
        self.assertEqual(status['pull_command'], 'docker pull hearthplug/mosaic-erp:v2.0.0')
        self.assertEqual(status['compose_command'], 'docker compose pull && docker compose up -d')

    def test_no_update_when_current(self):
        os.environ['MOSAIC_VERSION'] = 'v2.0.0'
        self.assertFalse(update_check.update_status()['update_available'])

    def test_no_update_when_running_newer(self):
        os.environ['MOSAIC_VERSION'] = 'v2.1.0'
        self.assertFalse(update_check.update_status()['update_available'])

    def test_dev_never_nags(self):
        status = update_check.update_status()
        self.assertEqual(status['current'], 'dev')
        self.assertFalse(status['update_available'])

    def test_offline_fails_silent_and_negative_caches(self):
        calls = []

        def boom():
            calls.append(1)
            raise OSError('offline')

        self.fetch.stop()
        with mock.patch.object(update_check, '_fetch_latest', boom):
            status = update_check.update_status()
            self.assertFalse(status['update_available'])
            self.assertIsNone(status['latest'])
            update_check.update_status()
        self.assertEqual(len(calls), 1)  # second call served from the negative cache
        self.fetch.start()

    def test_fresh_cache_hit_skips_network(self):
        cache = Path(self.tmp) / 'update-check-cache.json'
        cache.write_text(json.dumps({
            'fetched_at': time.time(),
            'release': {'tag': 'v3.1.0', 'url': 'https://example.test/v3.1.0', 'assets': {}},
        }), encoding='utf-8')
        os.environ['MOSAIC_VERSION'] = 'v3.0.0'
        self.fetch.stop()
        with mock.patch.object(update_check, '_fetch_latest', side_effect=AssertionError('network called')):
            status = update_check.update_status()
        self.assertEqual(status['latest'], 'v3.1.0')
        self.assertTrue(status['update_available'])
        self.fetch.start()

    def test_stale_cache_refetches(self):
        cache = Path(self.tmp) / 'update-check-cache.json'
        cache.write_text(json.dumps({
            'fetched_at': time.time() - update_check.CACHE_TTL_SECONDS - 10,
            'release': {'tag': 'v9.9.9', 'url': '', 'assets': {}},
        }), encoding='utf-8')
        os.environ['MOSAIC_VERSION'] = 'v1.4.0'
        self.assertEqual(update_check.update_status()['latest'], 'v2.0.0')

    def test_docker_flag_from_env(self):
        os.environ['MOSAIC_RUNTIME'] = 'docker'
        self.assertTrue(update_check.running_in_docker())

    def test_desktop_runtime_overrides_autodetect(self):
        os.environ['MOSAIC_RUNTIME'] = 'desktop'
        self.assertFalse(update_check.running_in_docker())

    def test_backup_fresh_install_writes_stamp_only(self):
        result = update_check.backup_before_upgrade(Path(self.tmp) / 'mosaic.db', version='v2.0.0')
        self.assertIsNone(result)
        self.assertEqual((Path(self.tmp) / '.last-run-version').read_text(encoding='utf-8'), 'v2.0.0')
        self.assertFalse((Path(self.tmp) / 'backups').exists())

    def test_backup_first_run_of_old_install(self):
        db = Path(self.tmp) / 'mosaic.db'
        db.write_bytes(b'v1 data')
        result = update_check.backup_before_upgrade(db, version='v2.0.0', now=1700000000)
        self.assertIsNotNone(result)
        self.assertEqual(result.read_bytes(), b'v1 data')
        self.assertIn('before-v2.0.0-from-unknown', result.name)
        self.assertEqual((Path(self.tmp) / '.last-run-version').read_text(encoding='utf-8'), 'v2.0.0')

    def test_backup_on_version_change(self):
        db = Path(self.tmp) / 'mosaic.db'
        db.write_bytes(b'live data')
        (Path(self.tmp) / '.last-run-version').write_text('v1.4.0', encoding='utf-8')
        result = update_check.backup_before_upgrade(db, version='v2.0.0', now=1700000000)
        self.assertIn('before-v2.0.0-from-v1.4.0', result.name)
        self.assertEqual(result.read_bytes(), b'live data')

    def test_backup_same_version_is_noop(self):
        db = Path(self.tmp) / 'mosaic.db'
        db.write_bytes(b'live data')
        (Path(self.tmp) / '.last-run-version').write_text('v2.0.0', encoding='utf-8')
        self.assertIsNone(update_check.backup_before_upgrade(db, version='v2.0.0'))
        self.assertFalse((Path(self.tmp) / 'backups').exists())

    def test_backup_prunes_to_five(self):
        db = Path(self.tmp) / 'mosaic.db'
        db.write_bytes(b'live data')
        backups = Path(self.tmp) / 'backups'
        backups.mkdir()
        for i in range(7):
            (backups / f'mosaic-2022010{i}-000000-before-v1.0.0-from-v0.9.0.db').write_bytes(b'old')
        update_check.backup_before_upgrade(db, version='v2.0.0', now=1700000000)
        remaining = sorted(backups.glob('mosaic-*.db'))
        self.assertEqual(len(remaining), update_check.KEEP_BACKUPS)
        self.assertEqual(remaining[-1].read_bytes(), b'live data')

    def test_backup_from_env_skips_postgres(self):
        os.environ['MOSAIC_DATABASE_URL'] = 'postgresql://db.example/mosaic'
        self.assertIsNone(update_check.backup_before_upgrade_from_env())
        self.assertFalse((Path(self.tmp) / '.last-run-version').exists())


if __name__ == '__main__':
    unittest.main()
