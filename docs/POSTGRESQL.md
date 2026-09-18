# PostgreSQL production operations

SQLite remains the zero-dependency evaluation and single-process option. PostgreSQL 16+ is the production backend for concurrent replicas.

## Roles and connection security

Create a dedicated database. Use a schema-owner credential only in the migration Job and a separate runtime credential for the Deployment. Grant the runtime role `CONNECT`, `USAGE` on `public`, DML on Mosaic tables, sequence use, and execute on `mosaic_auth_session(text)` and `mosaic_oauth_users(text,text,text)` after the first migration. Do not give it `CREATE`, superuser, `BYPASSRLS`, or table ownership. Rotate both through your cloud secret manager or External Secrets operator.

`MOSAIC_DATABASE_URL` must come from a Secret. For remote PostgreSQL use `sslmode=verify-full` and the provider CA. Do not commit URLs. The in-process `psycopg_pool` defaults to 1-10 connections per pod; budget `replicas * MOSAIC_DB_POOL_MAX` below the database connection limit. PgBouncer in transaction mode is optional when pod count or connection churn warrants it; session state uses `set_config(..., true)` and is transaction-local.

The application sets the workspace context per transaction. `FORCE ROW LEVEL SECURITY` policies on every tenant table are a second boundary against query mistakes. Authentication uses narrowly scoped key predicates and a `SECURITY DEFINER` session lookup with a fixed search path. RLS does not protect against a stolen database credential that can change roles or bypass RLS, which is why role separation and secret rotation are required.

## Migrations and upgrades

Migrations use a PostgreSQL advisory lock and a version ledger. Helm runs a pre-upgrade migration Job from `database.migrationSecret`; application pods set `MOSAIC_AUTO_MIGRATE=false` and refuse startup on a schema mismatch. Use expand/migrate/contract changes across releases: add compatible columns/indexes first, backfill in bounded batches, deploy readers/writers, then remove old fields in a later release. Use `CREATE INDEX CONCURRENTLY` for large live tables and set lock/statement timeouts in operator automation. Never roll back application code across an incompatible contract migration; restore forward or use the documented compatible image.

## Backup, PITR, HA, and recovery

Use a managed PostgreSQL service with multi-AZ failover, automated backups, WAL archiving/PITR, encryption, monitoring, and tested maintenance procedures. Self-managed operators such as CloudNativePG are optional infrastructure, not bundled by this chart. They require their own support, object storage, and restore drills.

Set retention and RPO/RTO for the business. At least quarterly, restore a backup plus WAL into an isolated database, run `SELECT count(*)`/application readiness checks, verify a sample workspace checksum and audit trail, and record elapsed recovery time. Replicas are for failover/read scaling only; Mosaic currently sends all application traffic to the primary endpoint. A successful template render is not evidence that failover or PITR works in your cluster.

Before an upgrade: verify a fresh restorable backup, database capacity, replication lag, and migration compatibility. On failure, stop writes, decide between forward repair and point-in-time restore, rotate exposed credentials, and preserve audit/log evidence.
