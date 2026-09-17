# Production deployment

Mosaic supports three distinct paths. The local Python path optimizes for contribution and evaluation. Docker Compose is the single-host production path. Kubernetes/Helm packages the same **single-node SQLite evaluation mode architecture** for clusters. Kubernetes does not make this release highly available.

## 1. Local Python

```bash
python3 install.py
python3 app.py
```

Requires Python 3.10+. Data defaults to `./mosaic.db`; the installer writes the one-time workspace key to `./mosaic-workspace.key`. Protect both files and back them up.

## 2. Docker Compose

Prerequisites: Docker Engine 24+ with Compose v2, a DNS name, and inbound ports 80/443.

```bash
cp .env.example .env
# Set MOSAIC_DOMAIN to a real DNS name.
docker compose build --pull
MOSAIC_VCS_REF="$(git rev-parse HEAD)" docker compose up -d
curl -fsS https://$MOSAIC_DOMAIN/health/ready
```

The app runs as UID/GID 10001 with all capabilities dropped, a read-only root filesystem, a `/tmp` tmpfs, and persistent `/data` volume. Caddy terminates HTTPS. The public image is not yet published, so Compose builds locally unless `MOSAIC_IMAGE` is changed to a verified registry digest.

Backup before every upgrade:

```bash
docker compose exec app python app.py backup --out /data/mosaic-backup.db
docker compose pull
docker compose up -d
```

To roll back, set `MOSAIC_IMAGE` to the prior immutable digest and run `docker compose up -d`. If a schema/data rollback is needed, stop the app, restore the matching integrity-checked backup, then start it. Test restore on a separate volume before relying on it.

## 3. Kubernetes and Helm

Prerequisites: Kubernetes 1.29+, Helm 3.14+, a dynamic storage class, and - for public HTTPS - an ingress controller, DNS, and a TLS certificate or cert-manager issuer.

```bash
helm lint deploy/helm/mosaic-erp
helm upgrade --install mosaic deploy/helm/mosaic-erp \
  --namespace mosaic --create-namespace \
  --set image.repository=<docker-hub-namespace>/mosaic-erp \
  --set image.tag=dev
kubectl -n mosaic wait --for=condition=ready pod -l app.kubernetes.io/instance=mosaic --timeout=120s
```

Prefer an immutable digest:

```bash
helm upgrade --install mosaic deploy/helm/mosaic-erp \
  --namespace mosaic --create-namespace \
  --set image.repository=<docker-hub-namespace>/mosaic-erp \
  --set image.digest=sha256:<verified-manifest-digest>
```

Example TLS values:

```yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-production
  hosts:
    - host: mosaic.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: mosaic-tls
      hosts: [mosaic.example.com]
```

The chart sets startup/readiness/liveness probes, resource requests/limits, pod/container security contexts, a PVC, ConfigMap, Service, optional Ingress/TLS, and a disruption budget. There are currently no application secrets required at startup. OIDC client secrets, when that adapter is implemented, must come from an external Kubernetes Secret or secrets manager and must never be committed to values files.

### Scaling and disruption

Do not increase `replicaCount` or enable HPA. SQLite evaluation mode and the file-backed rate limiter are shared only inside one database file, while a normal PVC is `ReadWriteOnce`. The chart rejects HPA and multiple replicas. `maxUnavailable: 0` protects the lone pod from voluntary disruption, which can make node drains wait. Schedule maintenance deliberately. Real autoscaling, rolling multi-node availability, and automatic failover require the still-unimplemented PostgreSQL/shared-data adapter.

### Upgrade, rollback, backup, restore

1. Run `python3 release_check.py` against the target source.
2. Back up `/data/mosaic.db` with `python app.py backup --out ...` from the pod or a controlled maintenance job, then copy the verified backup to encrypted off-cluster storage.
3. Record the image digest and chart version.
4. Run `helm upgrade --atomic --wait ...`.
5. Check `/health/ready`, logs, and a tenant read/write smoke test.

`helm rollback mosaic <revision> --wait` rolls back Kubernetes resources, not database schema or data. Restore requires stopping the pod, preserving the failed volume, and running `python app.py restore --from <backup> --yes` against a copy or controlled maintenance pod before restart. Rehearse this with your storage provider.

## Image supply chain

`.github/workflows/container-release.yml` tests the source, builds `linux/amd64` and `linux/arm64`, generates BuildKit SBOM and max-mode provenance attestations, scans the built image with Trivy, and signs pushed release digests with GitHub Actions keyless OIDC. Publishing is enabled only after the repository gets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets and the workflow's image namespace is set to the exact approved Docker Hub account.

The workflow and Docker/Kubernetes runtime remain source/static validated in the current development environment because Docker, a Kubernetes API server, and registry credentials were unavailable. Helm lint/template and source tests are locally verified. CI must pass on GitHub before a release is described as container-runtime verified.


## PostgreSQL production checklist

- External PostgreSQL 16+ primary endpoint with TLS verification; multi-AZ/PITR per business RPO/RTO.
- Separate schema-owner migration Secret and least-privilege runtime Secret. No chart-generated passwords.
- Size the per-pod pool against the server limit; add PgBouncer only when connection scale requires it.
- Run the pre-upgrade migration Job, then a rolling Deployment with readiness gating and PDB.
- Route ingress through an operator-owned controller/certificate manager. Configure NetworkPolicy database CIDR and ingress namespace labels for the cluster.
- Export JSON logs and `/metrics`; alert on readiness, 5xx/latency, pool saturation, PostgreSQL connections/locks/lag/storage, backup age, and certificate expiry.
- Restore into isolation and verify application data/audit checksums on a scheduled drill. Deployment templates cannot prove HA, PITR, capacity, or failover.
