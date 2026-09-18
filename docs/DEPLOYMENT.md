# Production deployment

## Local evaluation

```bash
python3 install.py
python3 app.py
```

Open `http://localhost:8000/signin` and choose **Set up a new company**. The browser uses a revocable user session. Ordinary users do not copy workspace/API keys. SQLite is limited to evaluation and simple single-process use; use `python3 app.py backup --out ...` and rehearse restore on a copy.

## PostgreSQL production

Production Compose and Helm paths require an external PostgreSQL 16+ service. Set `MOSAIC_DATABASE_URL` with `sslmode=verify-full`. Use a restricted runtime credential and a separate schema-owner migration credential. Application replicas are stateless and share sessions, rate limits, tenant data and advisory locks through PostgreSQL.

```bash
helm upgrade --install mosaic deploy/helm/mosaic-erp --namespace mosaic --create-namespace \
  --set image.repository=<approved-registry>/mosaic-erp \
  --set image.digest=sha256:<digest-from-this-release> \
  --set database.secretName=mosaic-db-runtime \
  --set database.migrationSecretName=mosaic-db-owner \
  --set networkPolicy.databaseCIDR=<database-cidr>
```

Do not use an old release digest. Before publish, the release workflow must build this exact tag, test amd64/arm64 images, emit fresh SBOM/provenance, scan, sign and report immutable digests.

## Operator acceptance before live traffic

- configure DNS/TLS, ingress and network policy
- store/rotate runtime and migration credentials in the platform secret manager
- configure managed multi-AZ, encrypted backups and WAL/PITR to the business RPO/RTO
- restore backup+WAL into an isolated database; verify readiness, representative workspace data, audit history and trial-balance equality; record elapsed RTO
- run target-environment load/capacity and failover tests
- export logs/metrics and alert on readiness, errors, latency, pool saturation, locks, lag, storage, backup age and certificate expiry
- complete an independent security review before sensitive financial data

Templates and source CI cannot certify HA, PITR, restore, capacity or failover for a target environment.

## Upgrade and rollback

Run the migration Job once with the owner credential, then roll application replicas using the restricted runtime credential. Use expand/migrate/contract schema changes. Before upgrade, verify a fresh restorable backup and record image/chart versions. If an incompatible migration fails, stop writes and choose a forward repair or PITR restore; a Helm rollback alone does not roll back data.

See [PostgreSQL operations](POSTGRESQL.md).
