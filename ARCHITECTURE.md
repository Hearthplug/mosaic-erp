# Mosaic ERP data architecture

Status: hardened single-node build. Every claim in the "Implemented" sections is
verified by `release_check.py` (75 automated tests plus live-server checks).
The "Deployment-dependent" section lists what source code alone cannot prove.

## Shape

```
browser (static.html)  ──HTTP──>  app.py (stdlib ThreadingHTTPServer)
                                     ├── public compiler API (stateless, no data kept)
                                     ├── workspace API (Bearer key, tenant-scoped)
                                     └── store.py ──> SQLite (WAL) at MOSAIC_DB_PATH
```

The compiler endpoints (`/api/preview`, `/api/configure`, `/api/chat`,
`/api/export`) stay stateless and anonymous: they transform answers into a
blueprint and keep nothing. Only the workspace API (`/api/workspace*`)
persists, and every one of its routes resolves the tenant from the presented
API key - there is no tenant parameter to tamper with.

## Decisions and sources

- **SQLite in WAL mode as the system of record.** Readers do not block writers,
  commits are atomic and crash-safe, and the whole database is one file the
  owner controls - the right fit for a self-hosted single-node product with a
  zero-dependency promise. Sources: <https://www.sqlite.org/wal.html>,
  <https://www.sqlite.org/atomiccommit.html>
- **Online backups through SQLite's Backup API, integrity-checked on write.**
  `python3 app.py backup --out file.db` produces a consistent copy without
  stopping the server; restore verifies `PRAGMA integrity_check` and schema
  version, then atomically replaces the live file.
  Source: <https://www.sqlite.org/backup.html>
- **Schema migrations tracked in `PRAGMA user_version`**, applied in order,
  each inside its own transaction, refused when the file is newer than the
  build. Source: <https://www.sqlite.org/pragma.html#pragma_user_version>
- **API keys over accounts.** A workspace is reached with a 160-bit random
  bearer token (`msk_…`); only its SHA-256 digest is stored, compared in
  constant time, shown once at creation. This follows the stored-secret
  guidance pattern in NIST SP 800-63B (verifiers store salted/hashed secrets,
  never plaintext). Source: <https://pages.nist.gov/800-63-3/sp800-63b.html>
- **Role ladder on keys:** viewer < editor < owner. Writes need editor, key
  management and erasure need owner. Maps to OWASP API Security Top 10 (2023)
  API1 Broken Object Level Authorization and API5 Broken Function Level
  Authorization - every request re-checks both tenant and function level.
  Source: <https://owasp.org/API-Security/editions/2023/en/0x11-t10/>
- **Versioned configurations with optimistic concurrency.** Writes carry
  `base_version`; a stale base is rejected with 409 so two editors cannot
  silently overwrite each other. Old versions stay readable; rollback appends
  a new version instead of rewriting history.
- **Idempotent mutations.** Clients send `Idempotency-Key`; the first response
  is stored and replayed byte-identically (header `Idempotency-Replayed:
  true`), and reusing a key with a different body is a 409. Retries after
  timeouts cannot double-apply a change.
- **Audit trail as an append-only table**, written in the same transaction as
  the change it describes. Every save, rollback, key creation/revocation,
  export, and deletion is recorded with actor and timestamp.
- **Rate limiting**: per-identity token bucket (default 120 req/min,
  `MOSAIC_RATE_LIMIT_RPM`), 429 with `Retry-After`. In-memory by design - a
  single-node guard, not a multi-node WAF.
- **Observability**: one structured JSON log line per request (request id,
  route, status, latency, hashed identity), `X-Request-ID` echo,
  `/health` liveness, `/health/ready` with a database integrity probe, and
  `/metrics` counters and average latencies.
- **Secure defaults**: binds 127.0.0.1 unless `MOSAIC_HOST` says otherwise,
  `nosniff`, `no-referrer`, `no-store` on API responses, CSP on the HTML that
  blocks every external origin, 256 KB request cap, JSON error envelopes.
- **Privacy controls**: `GET /api/workspace/export` downloads everything a
  tenant holds (configs, audit, key metadata - never key hashes);
  `DELETE /api/workspace` with an explicit confirmation header erases the
  tenant and cascades to keys, versions, audit, and idempotency records.

## Threat model (what this build resists)

- Cross-tenant reads/writes: impossible by construction (tenant comes from the
  key), tested with two tenants attacking each other.
- Replay/duplicate writes: idempotency keys, tested.
- Lost-update races: optimistic concurrency, tested.
- Crash mid-write: single-transaction units, rollback verified, integrity
  check clean, data survives restart, tested.
- Key theft from the database: only hashes stored, tested.
- Flood from one client: token bucket 429s, tested.
- Tampered stored config: SHA-256 checksum verified on every read, tested.

## What it does not resist (honest limits)

- Traffic is plain HTTP on localhost - TLS must come from a reverse proxy.
- One node, one file: no high availability, no automatic failover.
- In-memory rate limiting resets on restart and does not cluster.
- The HTML uses inline script/style, so CSP must allow `unsafe-inline` for
  those two directives (all external origins are still blocked).
- No per-user identity, SSO, or session management: workspace keys are the
  boundary.
- No independent security audit has been performed.

## Deployment-dependent (owner action before any hosted launch)

1. Terminate TLS at a reverse proxy (nginx/Caddy) and forward to 127.0.0.1.
2. Schedule offsite backups (`app.py backup`) and rehearse `app.py restore`.
3. Put the database file on encrypted, snapshotted storage.
4. Add per-user accounts or SSO before inviting teams beyond key sharing.
5. Commission an external penetration test before storing real financial data.
6. Move to a managed client-server database if write concurrency outgrows one
   node (the Store class isolates the schema and SQL to make that a port, not
   a rewrite).

## Usability and installation

- Install is one command (`python3 install.py`): checks Python, applies
  migrations, creates the online-save workspace, writes the recovery key to a
  owner-only file, seeds a working sample business, and prints two next steps.
  Re-running after an interruption continues safely.
- The interface is one guided conversation: plain-language questions, example
  answers, one question at a time, large touch targets (44px on small
  screens), visible focus outlines, screen-reader live regions, and automatic
  retry with clear "saved on this device / saved online / save failed"
  states. No technical vocabulary is required to finish setup.

## Production hardening added in v1.1

Implemented and source-tested:

- Browser code and styling are external files. The server CSP is `default-src 'none'` with same-origin scripts/styles and no `unsafe-inline`.
- Named users have workspace-scoped viewer/editor/owner roles. Passwords use PBKDF2-HMAC-SHA256 with a random 128-bit salt and 600,000 iterations. Session tokens have 256 bits of randomness, only token hashes are stored, sessions expire within 24 hours, and revocation is immediate.
- Rate-limit buckets persist in the database and are shared by every worker pointed at that database. This removes process-local resets. A multi-node deployment must use the same PostgreSQL-backed implementation or an atomic external limiter; separate SQLite volumes do not share buckets.
- The container runs as a non-root user, exposes liveness/readiness checks, and the supplied Caddy configuration terminates HTTPS with automatic certificates for a real `MOSAIC_DOMAIN`. Local mode remains `python3 install.py && python3 app.py` on loopback.
- The OIDC trust boundary and required verification rules are specified in [OIDC.md](OIDC.md). No provider is claimed or enabled.

## Deployment architecture and exact limits

SQLite is the zero-dependency evaluation and simple single-node backend. Production Docker and Helm deployments use `PostgresStore`: bounded per-pod pools, shared session/rate-limit state, advisory-lock serialization of version writes, a schema ledger, and forced row-level security. At least two stateless app replicas sit behind TLS ingress. The database endpoint, multi-AZ failover, PITR, encryption, monitoring, and restore drills are operator-owned. Templates cannot prove these runtime properties.

The SQLite CLI backup/restore path remains tested for local mode. PostgreSQL backup and restore deliberately refuse that file workflow and direct operators to managed snapshots plus WAL/PITR. Run schema changes once with the dedicated migration credential and use expand/migrate/contract changes for zero-downtime upgrades.

Automated tests and `release_check.py` are maintainer-run evidence, not an independent audit. Before sensitive hosted use, commission an independent code review and penetration test. Preserve the report, commit SHA, test commands/results, dependency and secret scans, threat model, and remediation log as the audit evidence pack.

## Container and cluster distribution

The OCI image runs as fixed UID/GID 10001 with a read-only application filesystem, readiness/liveness checks, no shell entrypoint, and a digest-pinned base. Compose drops capabilities, sets `no-new-privileges`, applies resource bounds, and uses Caddy TLS. It requires an external PostgreSQL URL and creates no production credentials.

The Kubernetes manifests and Helm chart use a rolling two-replica Deployment, separate migration Job and credential, startup/readiness/liveness probes, resources, pod security, a disruption budget, topology spread, NetworkPolicy, optional HPA, and optional Ingress/TLS. PostgreSQL itself is intentionally not bundled. Network-policy selectors/CIDRs, certificates, Secrets, database capacity, alerts, and disaster recovery remain cluster-specific.

The release workflow builds amd64/arm64 OCI manifests, emits SBOM and SLSA-style BuildKit provenance attestations, fails on fixed high/critical vulnerabilities, and keylessly signs release digests through GitHub OIDC. Registry publication and runtime claims begin only after the exact registry namespace is approved, credentials are configured, and CI passes.


## Production PostgreSQL boundary

`Store` defines the application repository contract. `PostgresStore` preserves its versioning, idempotency, audit, authentication, rate-limit, and transaction behavior while using a bounded pool and advisory per-workspace write locks. Forced RLS is defense in depth. Production application replicas are stateless; PostgreSQL is the shared consistency boundary. SQLite stays available only for evaluation and simple single-node use. Operator-owned managed services supply database HA/PITR, secret distribution, ingress/TLS, centralized logs/metrics, alerts, and restore drills. See `docs/POSTGRESQL.md`.
