"""One-command local setup for Mosaic ERP.

    python3 install.py

Checks prerequisites, initializes the database and migrations safely,
initializes storage and migrations. Company creation and normal user sign-in happen in the browser;
admin/API keys stay outside everyday product screens.
Safe to re-run: an interrupted or repeated setup continues instead of
duplicating anything. Hosted installation is deployment-dependent - see
docs/ARCHITECTURE.md.
"""
import os, sys
from pathlib import Path

ROOT = Path(__file__).parent

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
    if existing: step(True, 'Existing company data found; nothing changed')
    else: step(True, 'Ready for first company setup in the browser')
    print('\nStart the app:  python3 app.py')
    print('Then open:      http://localhost:8000/signin')

if __name__ == '__main__':
    main()
