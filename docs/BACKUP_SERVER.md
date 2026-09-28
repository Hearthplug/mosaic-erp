# Off-server backups

A backup on the same machine is not a backup; it dies with the machine. Every Mosaic store needs a copy on a second host (or object storage), checked for integrity, and proven restorable by the quarterly restore drill in RESTORE_DRILL.md.

## The pattern

1. **Take the online backup.** SQLite: `Store.backup(out_path)` uses the SQLite Backup API against the live database - no downtime, consistent snapshot. PostgreSQL: operator-managed via pgBackRest/WAL-G or the managed service's PITR (see POSTGRESQL.md); Mosaic already takes a local pre-upgrade copy automatically (keeps 5), which is a convenience, not this off-server copy.
2. **Checksum before it leaves.** Record the SHA-256 of the backup file.
3. **Copy it off the machine.** Any second host or bucket works: `scp`/`rsync` to a backup server, or rclone/restic to object storage. Encrypt in transit (SSH/TLS) and at rest (restic encrypts; for plain copies, the destination must be encrypted storage). The copy holds the whole business - treat it like the database.
4. **Verify the copy.** Re-checksum on the destination and compare. A copy that does not match is deleted and re-sent, never kept.
5. **Schedule and retain.** Nightly is the right default for a shop (RPO: one day). Keep at least 7 nightly, 4 weekly, 3 monthly copies. Alert when the newest off-server copy is older than 25 hours.
6. **Prove it restores.** The quarterly restore drill (RESTORE_DRILL.md) must restore from the off-server copy, not from a local file - that is what proves the second host, the transfer, and the credentials all work when the machine is gone.

## Measured drill, 2026-09-28

Ran the transfer half of the pattern against a live store (SQLite Backup API, simulated second host in a separate directory):

- `Store.backup` against the live database produced a consistent snapshot while the app was running.
- SHA-256 of the backup matched the off-server copy exactly (`9b304371…`).
- The local backup was then deleted and the database restored **from the off-server copy**: `PRAGMA integrity_check` = ok; workspace, sales, stock ledger and audit history all present and matching the live counts (workspaces 1, sales 1, stock ledger 2, audit events 15).
- Boot-level restore proof of the same database generation is in RESTORE_DRILL.md (app served sales list, stock register and trial balance from the restored copy).

## Failure rules

Never overwrite the newest good off-server copy until its replacement verifies. A failed backup or transfer pages the operator; a store without a fresh off-server copy is an incident, not a backlog item. Rotate the credentials the backup user holds; they can read everything.
