# Mosaic ERP Helm chart

This chart deploys the current SQLite build as one non-root `StatefulSet` with a persistent volume. It intentionally rejects replicas other than one and HPA. A `ReadWriteOnce` PVC is persistence, not high availability.

```bash
helm lint deploy/helm/mosaic-erp
helm template mosaic deploy/helm/mosaic-erp \
  --set image.repository=<namespace>/mosaic-erp \
  --set image.tag=dev > mosaic.yaml
helm upgrade --install mosaic deploy/helm/mosaic-erp \
  --namespace mosaic --create-namespace \
  --set image.repository=<namespace>/mosaic-erp \
  --set image.tag=dev
```

For production, set `image.digest=sha256:...`, configure `persistence.storageClass`, and enable ingress with your installed ingress controller and TLS certificate manager. The chart never creates a TLS certificate, registry credential, or application secret for you.
