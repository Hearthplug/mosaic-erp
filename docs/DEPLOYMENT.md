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

## Google and Microsoft sign-in

Email/password remains available. Social sign-in is configuration-aware: a button is disabled until all of its provider inputs are present, so an incomplete deployment never advertises a broken login.

Set the canonical HTTPS origin with no path, plus credentials from each provider console:

- `MOSAIC_PUBLIC_ORIGIN=https://erp.example.com`
- Google: `MOSAIC_GOOGLE_CLIENT_ID`, `MOSAIC_GOOGLE_CLIENT_SECRET`; register the exact web redirect URI `https://erp.example.com/oauth/google/callback` and request OpenID, email and profile scopes.
- Microsoft Entra ID: `MOSAIC_MICROSOFT_CLIENT_ID`, `MOSAIC_MICROSOFT_CLIENT_SECRET`; register the exact web redirect URI `https://erp.example.com/oauth/microsoft/callback`. The app uses the `common` v2 endpoint so deployment owners must select the intended supported account types in Entra. Mosaic validates the tenant-specific v2 issuer returned in the ID token.

Keep client secrets in the deployment secret manager, rotate them under the provider's overlap procedure, and never put them in values files, images or logs. Production needs HTTPS at the public origin. Provider console ownership, consent policy, verified domains, credential issuance and secret rotation are deployment-owned gates.

The locally packaged sign-in graphics come from the providers themselves; see [provider sign-in branding](PROVIDER_BRANDING.md). They do not change the route behavior. The flow uses authorization code, state, nonce and S256 PKCE; verifies signed ID tokens against provider JWKS, audience, issuer and time claims; stores one-time challenges/grants server-side; and keys identities by provider, issuer and stable subject. A provider email never silently creates or merges an account. A new identity must either match a valid invitation with a provider-verified email or be linked once by the existing Mosaic password. Company choice, role binding, revocation and session expiry are unchanged after sign-in.
