# Mosaic ERP

Mosaic is an interview-native operational ERP for core retailer work. An owner describes the business in plain language; Mosaic provisions the relevant workflows, reports, branding, verification tasks and fine-grained staff roles. The same system then runs persistent buying, receiving, selling, returns/refunds, stock, cash, supplier bills/payments, reconciliation, period close and core accounting reports.

## Scope of v1.2.0

v1.2.0 is an evidence-backed **production-core retailer ERP release candidate**. It is not a claim of complete advanced-retail or enterprise-suite breadth.

Implemented and source-tested:

- guided owner interview that provisions an operating model and real controls
- normal email/password sign-in, secure Google and Microsoft OIDC routes, expiring/revocable sessions, secure single-use invitations and company chooser
- action, location, amount and record-state RBAC with segregation-of-duties checks
- products, stores, suppliers/customers, purchase orders, receiving, sales, exact tenders, returns/refunds, transfers, counts and cash close
- purchase bills, three-way match, payments, bank matching, immutable double-entry journals, period locks, aging, trial balance, P&L and balance sheet
- validation-first migration with reviewed openings, reconciliation and correction/rollback guidance
- PostgreSQL 16+ pooling, migrations, `FORCE ROW LEVEL SECURITY`, restricted runtime role, atomic domain commands and cross-replica locks
- strict same-origin CSP, audit history, request limits, health/readiness and metrics

Explicitly excluded:

- statutory invoice formats, tax filing, e-invoicing or jurisdiction certification without a separately verified local adapter/version
- advanced modules such as held carts, promotions, printable fiscal receipts, deep batch/expiry/serial operations, landed cost, manufacturing, payroll and broad enterprise-suite replacement
- managed hosting, database HA/PITR, target-cluster failover/capacity evidence or an operator restore certificate

## Shop PC or anywhere access

Use the Windows desktop installer or local Python path when Mosaic should stay on the shop PC. Use the hosted Docker/Helm path when the owner and staff need to check the same shop from a phone or another computer. The hosted UI runs in the phone browser; there is no separate mobile app. Hosted access requires HTTPS and external PostgreSQL. See [check your shop from anywhere](docs/HOSTED_ACCESS.md).

## Start locally

```bash
python3 install.py
python3 app.py
```

Open `http://localhost:8000/signin`, choose **Set up a new company**, and enter the company name, work email and a password. Mosaic signs the owner in and opens the business interview. Ordinary users never handle workspace or API keys.

SQLite is for evaluation and simple single-process use. It includes an integrity-checked local backup/restore path. PostgreSQL is required for concurrent production replicas.

## Production deployment

Use an external PostgreSQL 16+ service and the supplied Compose or Helm path. Runtime and schema-migration credentials are separate. Operators must provide TLS/DNS, secret management, managed database HA/PITR, monitoring, capacity testing and an isolated restore drill against the exact target environment. See [hosted access](docs/HOSTED_ACCESS.md), [deployment](docs/DEPLOYMENT.md), [PostgreSQL operations](docs/POSTGRESQL.md), and [identity-provider deployment](docs/DEPLOYMENT.md#google-and-microsoft-sign-in).

The reviewed v1.2.0 product tree is [`8235d04bd53ed402e862bc2b77d832e7adc382de`](https://api.github.com/repos/Hearthplug/mosaic-erp/git/trees/8235d04bd53ed402e862bc2b77d832e7adc382de?recursive=1). Release-infrastructure commit [`5d6c3fc94a4c55ef2f8add3a0bf17b0732b0f91b`](https://github.com/Hearthplug/mosaic-erp/commit/5d6c3fc94a4c55ef2f8add3a0bf17b0732b0f91b) adds the independent publication gate without changing that reviewed product tree; its successful [source/deployment and PostgreSQL CI](https://github.com/Hearthplug/mosaic-erp/actions/runs/35393974456) verifies the product plus publication-workflow parent on September 19, 2026. This documentation update cites those prior verified inputs and does not claim that run tested this docs-only commit. Fresh v1.2.0 archives, checksums, image digests, signatures, SBOM/provenance and vulnerability-scan evidence must still be generated and verified before publication. No v1.1.0 artifact is evidence for v1.2.0.

Google and Microsoft controls use provider-published sign-in assets and real configuration-aware OIDC routes. Live activation remains deployment-owned: the operator must provide a canonical HTTPS domain, register exact callbacks with each provider, select the Microsoft account type, complete required consent/domain review and provision rotated secrets. Unconfigured controls remain disabled.

## Tax review

Candidate jurisdiction packs are sourced and versioned inputs. Calculations stay fail-closed until the business owner or a named professional attests the exact jurisdiction, effective dates, sources, rules and regression cases. Professional review is recommended, not mandatory. Statutory output remains disabled separately. Mosaic does not provide legal or tax advice.

## History

v1.1.0 remains the earlier blueprint/configuration release: <https://github.com/Hearthplug/mosaic-erp/releases/tag/v1.1.0>. Its artifacts and evidence apply only to that release.

MIT licensed.
