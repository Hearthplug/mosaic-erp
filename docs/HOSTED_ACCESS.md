# Check your shop from anywhere

The Windows or Mac desktop app is the simplest choice for one shop computer. It runs only on that computer. Choose a hosted install when the owner or staff need to open the same shop from a phone or another computer.

Mosaic does not need a mobile app. Its web screens adapt to a phone browser. A hosted install must use HTTPS, a private database, and normal Mosaic sign-in. Never publish port 8000 directly to the internet.

## Pick a host

Start with a free option only for a test shop with made-up data:

- **Oracle Cloud Always Free VM:** enough room for Docker and Caddy when capacity is available. You operate the server, updates, firewall and backups. Oracle says Always Free capacity can be unavailable in a region.
- **Render or Koyeb free web service:** useful for a short test. Their free services can sleep, have low memory and no persistent disk. Do not keep Mosaic's SQLite file there. Render explicitly says its free services are not for production, and its free PostgreSQL expires after 30 days. Koyeb says its free instance is for previews/hobby use, not production.

For real shop records, use a provider with persistent compute plus managed PostgreSQL backups, or get a platform professional to run Kubernetes. Provider prices and free-tier rules change. Check the provider's current price and set a hard spending limit before creating paid resources.

Current provider references used for this guide:

- Oracle Always Free: <https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm>
- Render free service limits: <https://render.com/docs/free>
- Koyeb free instance limits: <https://www.koyeb.com/docs/reference/instances>

## Easiest hosted Docker path

You need a Linux server, a domain such as `shop.example.com`, Docker with Compose, and an external PostgreSQL 16+ database. Point the domain's DNS record at the server first.

1. Copy the Mosaic source to the server.
2. Create two PostgreSQL users: a restricted day-to-day user and a schema owner used for upgrades. Follow [PostgreSQL operations](POSTGRESQL.md). Require `sslmode=verify-full`.
3. Set the public settings without putting secrets in the repository:

   ```bash
   export MOSAIC_DOMAIN=shop.example.com
   export MOSAIC_PUBLIC_ORIGIN=https://shop.example.com
   export MOSAIC_DATABASE_URL='postgresql://...?...&sslmode=verify-full'
   ```

4. Allow inbound TCP ports 80 and 443 in the server firewall. Do not allow 8000. Caddy uses port 80 only to obtain/renew the certificate and redirects visitors to HTTPS.
5. Start Mosaic:

   ```bash
   docker compose up -d --build
   ```

6. On the server, check `docker compose ps`. Then open `https://shop.example.com/signin` on the phone using mobile data, create or sign in to the owner account, close the tab, reopen it and sign in again.
7. Confirm the browser shows HTTPS with no certificate warning. Test sign-out. Test a staff account with only the role it needs.

The supplied Compose file exposes only Caddy. The Mosaic container stays on Docker's private network. Caddy terminates HTTPS and sends HSTS. The application still binds to its container network because that port is not the public security boundary.

## Kubernetes / Helm path

Kubernetes is not the simple option. Use it only with someone who can operate the cluster and database.

Create the runtime and migration database Secrets, install an ingress controller and certificate manager, then install with a canonical HTTPS origin and a TLS Secret:

```bash
helm upgrade --install mosaic deploy/helm/mosaic-erp \
  --namespace mosaic --create-namespace \
  --set image.repository=hearthplug/mosaic-erp \
  --set image.digest=sha256:REPLACE_WITH_RELEASE_DIGEST \
  --set database.secretName=mosaic-db-runtime \
  --set database.migrationSecretName=mosaic-db-owner \
  --set networkPolicy.databaseCIDR=10.20.0.0/24 \
  --set config.publicOrigin=https://shop.example.com \
  --set ingress.enabled=true \
  --set ingress.className=nginx \
  --set ingress.hosts[0].host=shop.example.com \
  --set ingress.tls[0].hosts[0]=shop.example.com \
  --set ingress.tls[0].secretName=mosaic-tls
```

The chart now refuses an enabled ingress unless its public origin is HTTPS, TLS is configured, and the ingress host matches the public origin. Your ingress controller must redirect HTTP to HTTPS. Confirm that behavior before entering real data.

## Before using real shop data

- Use a unique owner password and separate named staff accounts. Do not share the owner login.
- Keep PostgreSQL private and encrypted in transit. Turn on automated backups and test a restore.
- Apply operating-system, container and Mosaic updates promptly.
- Monitor certificate expiry, backups, storage, errors and login activity.
- Register exact HTTPS callback URLs before enabling Google or Microsoft sign-in.
- Treat the browser session as sensitive. Sign out on shared phones and do not use an untrusted device.

## Honest limits

The repository tests the chart, container, HTTPS edge configuration and sign-in API. It cannot certify a provider account, DNS, certificate renewal, database recovery, phone network or target-cluster availability. Those must be checked on the actual hosted installation. Mosaic currently keeps its bearer session in browser storage; the strict same-origin content policy reduces script risk, but an HttpOnly cookie with CSRF protection would be a stronger future design for a public financial system. Use HTTPS, keep extensions and devices trusted, and sign out on shared devices.
