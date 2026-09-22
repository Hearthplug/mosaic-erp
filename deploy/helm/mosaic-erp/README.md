# Mosaic ERP Helm chart

Production chart for a stateless, multi-replica Mosaic deployment backed by an external PostgreSQL 16+ service. The chart never creates database users, passwords, TLS certificates, object-storage buckets, or a PostgreSQL cluster.

Create two Secrets outside Helm: `database.secretName` for the least-privilege runtime URL and `database.migrationSecretName` for the schema owner used only by the pre-install/pre-upgrade Job. Use `sslmode=verify-full`. Set `networkPolicy.databaseCIDR` to the database endpoint range or explicitly disable the policy only after reviewing cluster egress controls.

```bash
helm lint deploy/helm/mosaic-erp --strict \
  --set database.secretName=mosaic-db \
  --set database.migrationSecretName=mosaic-db-owner \
  --set networkPolicy.databaseCIDR=10.20.0.0/24
helm upgrade --install mosaic deploy/helm/mosaic-erp \
  --namespace mosaic --create-namespace \
  --set image.repository=hearthplug/mosaic-erp \
  --set image.digest=sha256:REPLACE \
  --set database.secretName=mosaic-db \
  --set database.migrationSecretName=mosaic-db-owner \
  --set networkPolicy.databaseCIDR=10.20.0.0/24
```

HPA is optional and requires Metrics Server plus database capacity for `maxReplicas * dbPoolMax`. See `docs/POSTGRESQL.md` for role separation, migration, backup/PITR, HA, and recovery drills.

## Hosted phone access

Enable ingress only with `config.publicOrigin=https://...` and a matching `ingress.tls` Secret. The chart rejects plain-HTTP hosted configuration. See [the owner guide](../../../docs/HOSTED_ACCESS.md).
