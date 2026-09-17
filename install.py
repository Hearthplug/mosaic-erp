"""One-command local setup for Mosaic ERP.

    python3 install.py

Checks prerequisites, initializes the database and migrations safely,
creates an online-save workspace (recovery key written to a private file),
and loads a sample business so the first screen already shows a working ERP.
Safe to re-run: an interrupted or repeated setup continues instead of
duplicating anything. Hosted installation is deployment-dependent - see
docs/ARCHITECTURE.md.
"""
import os, stat, sys
from pathlib import Path

ROOT = Path(__file__).parent
KEY_FILE = ROOT / 'mosaic-workspace.key'

SAMPLE = {
    'name': 'Asha Pharmacy', 'vertical': 'Pharmacy', 'country': 'India',
    'locations': '2–5 stores', 'channels': ['In store', 'Own website'],
    'inventory': 'Batch / expiry', 'sales': 'POS software',
    'credit': 'Customer + supplier', 'staff': ['Cashiers', 'Store managers', 'Accountant'],
    'priority': 'Inventory accuracy', 'turnover': '₹1.5 – 5 crore',
    'registration': 'Regular', 'supply': 'Within my state', 'buyers': 'Consumers',
}

def step(ok, msg):
    print(f'[{"ok" if ok else ".."}] {msg}')

def main():
    print('Mosaic ERP setup')
    if sys.version_info < (3, 10):
        sys.exit('Python 3.10 or newer is required. Install it from python.org and re-run.')
    step(True, f'Python {sys.version_info.major}.{sys.version_info.minor} found')

    import app  # creates the store and applies migrations on import
    db = os.getenv('MOSAIC_DB_PATH', str(ROOT / 'mosaic.db'))
    step(True, f'Database ready (schema up to date): {db}')

    existing = app.STORE._db.execute('SELECT id,name FROM workspaces ORDER BY created_at LIMIT 1').fetchone()
    if existing:
        step(True, f'Already set up - workspace "{existing[1]}" ({existing[0]}) exists; nothing changed')
        if not KEY_FILE.exists():
            step(False, 'Recovery key file is missing. Create a new key from the app or restore your backup.')
        print('\nStart the app:  python3 app.py\nThen open:      http://localhost:8000')
        return

    wid, key = app.STORE.create_workspace(SAMPLE['name'], label='Installer owner key')
    KEY_FILE.write_text(
        'Mosaic ERP online-save recovery key\n'
        f'Workspace: {wid}\n'
        f'Key: {key}\n'
        'Keep this file private. It is the only copy - the server stores only a hash.\n')
    KEY_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    step(True, f'Online-save workspace created; recovery key saved to {KEY_FILE.name} (private to you)')

    config = app.configure(dict(SAMPLE))
    app.STORE.save_config(wid, dict(SAMPLE), config, 0, 'Sample business (installer)', 'installer')
    step(True, f'Sample business loaded: {SAMPLE["name"]} ({SAMPLE["country"]} tax profile)')

    print('\nDone. Two commands from here:')
    print('  1. python3 app.py')
    print('  2. Open http://localhost:8000 in any browser')
    print('To remove everything later: delete mosaic.db and mosaic-workspace.key')

if __name__ == '__main__':
    main()
