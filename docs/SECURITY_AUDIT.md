# Security self-audit

Quarterly self-audit against the security policy. This is a self-audit, not an independent attestation; the policy requires an independent security review before sensitive financial data. Record each run with its evidence.

## What to check, with the 2026-09-28 measured run

Run against a live local instance (First Sale Store workspace) and the working tree at main.

**1. Response headers.** `curl -D -` on `/` showed: `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`. HSTS is sent by the Caddy edge in the hosted deployment (see HOSTED_ACCESS.md), not by the app on localhost.

**2. Authentication boundary.** No token on a protected endpoint: 401 `Missing or invalid Bearer API key`. Invalid token: identical 401, no existence leak between the two. Valid owner token: 200. Sign-in attempts return a generic 401 for unknown and known addresses alike.

**3. Brute-force resistance.** Measured live: 12 rapid bad password attempts against one address returned 401 ten times, then 429 from the account-scoped limiter (10 per minute, 60 per hour; the identifier is hashed so the limiter table holds no email, and the bucket survives restarts and IP rotation).

**4. Authorization.** `_auth` enforces viewer/editor/owner minimums; operational routes additionally check per-action RBAC for non-owners with location and amount limits. Covered by test_operational_rbac_api (OK this run).

**5. Test evidence.** test_csp_ui, test_auth_experience, test_operational_rbac_api, test_persistence: all OK.

**6. Dependency and image scanning.** CI gates: `pip-audit` on requirements (latest main run: success) and Trivy image scans on PRs and releases with HIGH/CRITICAL exit codes (latest main container runs: success). Do not bypass a failing gate without a written risk decision in the PR.

**7. Tenant isolation.** SQLite: every query is workspace-scoped in code, covered by persistence and RBAC tests. PostgreSQL: FORCE ROW LEVEL SECURITY on every tenant table plus a restricted runtime role (see POSTGRESQL.md).

**8. Secrets and logging.** Request logs carry a truncated hash of the credential, never the credential. Sessions and API keys authenticate by hash. Production secrets belong in the platform secret manager per DEPLOYMENT.md.

## Known boundaries (unchanged by this audit)

Localhost has no TLS; TLS terminates at Caddy in hosted deployments. RLS does not defend a stolen database credential that can change roles; role separation and rotation are required. This audit does not cover the host OS, Docker daemon, or the operator's own machines.
