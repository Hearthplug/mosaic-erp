# Restore drill

A backup only counts if a restore has been proven. This runbook is the quarterly drill: back up the live database, restore it onto a fresh path, boot the app against the restored copy, and compare measured totals before and after. Every number below is from the drill run on **2026-09-28** against a live store with a supplier delivery and a completed cash sale.

## The drill

1. **Measure the live database.** Record workspace, location and product counts, completed-sale total and numbers, stock units, journal and journal-line counts, audit-event count, and tendered amount:

   ```sh
   sqlite3 "$MOSAIC_DB_PATH" "SELECT (SELECT count(*) FROM workspaces), (SELECT count(*) FROM locations), (SELECT count(*) FROM retail_products), (SELECT COALESCE(SUM(total_minor),0) FROM sales WHERE status='completed'), (SELECT COALESCE(SUM(CAST(quantity_delta AS REAL)),0) FROM stock_ledger), (SELECT count(*) FROM journals), (SELECT count(*) FROM journal_lines), (SELECT count(*) FROM audit_events), (SELECT COALESCE(SUM(amount_minor),0) FROM tender_entries)"
   ```

2. **Take an online backup while the app keeps running.** The backup uses SQLite's online Backup API and is integrity-checked before the file is kept:

   ```sh
   MOSAIC_DB_PATH=/path/to/mosaic.db python3 app.py backup --out /safe/place/mosaic-backup.db
   # -> Backup verified and written to /safe/place/mosaic-backup.db
   ```

3. **Stop the server, then restore.** Restore verifies the backup's integrity and schema before atomically replacing the database file; `--yes` is the deliberate confirmation:

   ```sh
   MOSAIC_DB_PATH=/path/to/mosaic.db python3 app.py restore --from /safe/place/mosaic-backup.db --yes
   # -> Restored ...; integrity and schema verified before replacement
   ```

   For a drill (no live data at risk), restore to a **separate** path and boot a second app instance against it instead of touching the live file.

4. **Prove the restored copy.** Boot the app against the restored database, sign in, and re-measure. Every figure from step 1 must match exactly, and the app must answer real queries: the sales list shows the same bill numbers, the stock register shows the same on-hand per item and store, and the trial balance shows the same account totals.

5. **Record the run** in the table below. If anything mismatches, the backup is not a backup - treat it as an incident, keep the live server untouched, and fix the backup path before relying on it.

## Drill log

| Date | Source | Before = After (all metrics) | App proof on restored copy | Result |
| --- | --- | --- | --- | --- |
| 2026-09-28 | Live store (1 workspace, 1 store, 1 item, delivery of 48, cash sale INV-000001 for $4.86) | workspaces 1, locations 1, products 1, sales total 486, sale numbers [INV-000001], stock units 46.0, journals 1, journal lines 4, audit events 14, tendered 486 | sales-list returned INV-000001 completed $4.86; stock register showed Rice 1 kg 46 at Main store; trial balance showed Cash debit 486 and Inventory credit 300 | PASS |

## Notes

- The backup file contains everything the workspace owns, including sessions and audit events - store it with the same care as the live database.
- PostgreSQL deployments use `pg_dump`/`pg_restore` instead of the SQLite CLI; the drill shape (measure, back up, restore to scratch, prove, record) is identical. See docs/POSTGRESQL.md.
- Days are never locked and books are append-only, so a restored copy can be inspected safely without risking the live store.
