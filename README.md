# Mosaic ERP

Mosaic is an interview-native operational ERP for core retailer work. An owner describes the business in plain language; Mosaic provisions the relevant modules, workflows, reports, branding, verification tasks and fine-grained staff roles. The same system then runs persistent buying, receiving, selling, returns/refunds, stock, cash, supplier bills/payments, reconciliation, period close and accounting reports.

## Scope of this candidate

The `accounting-foundation` branch is an evidence-backed **production-core retailer ERP candidate**. It is not a claim of complete advanced-retail or enterprise-suite breadth.

Implemented and tested:

- guided owner interview that provisions an operating model and real controls
- normal email/password sign-in, expiring/revocable sessions, secure single-use invitations and company chooser
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

## Start locally

```bash
python3 install.py
python3 app.py
```

Open `http://localhost:8000/signin`, choose **Set up a new company**, and enter the company name, work email and a password. Mosaic signs the owner in and opens the business interview. Ordinary users never handle workspace or API keys.

SQLite is for evaluation and simple single-process use. It includes an integrity-checked local backup/restore path. PostgreSQL is required for concurrent production replicas.

## Production deployment

Use an external PostgreSQL 16+ service and the supplied Compose or Helm path. Runtime and schema-migration credentials are separate. Operators must provide TLS/DNS, secret management, managed database HA/PITR, monitoring, capacity testing and an isolated restore drill against the exact target environment. See [deployment](docs/DEPLOYMENT.md) and [PostgreSQL operations](docs/POSTGRESQL.md).

Source verification for this candidate is tied to commit `5ee8b96254eddd2c676af874a07ffa57e2c94b75` and CI run <https://github.com/Hearthplug/mosaic-erp/actions/runs/35326493761>. A published image, digest, SBOM, signature, vulnerability scan and download archive do not exist for this candidate yet. Generate and verify them from the final release tag rather than reusing v1.1.0 artifacts.

## Tax and professional verification

Candidate jurisdiction packs are sourced and versioned inputs. Calculations stay fail-closed until a named local professional attests the exact jurisdiction, effective dates, rules and regression cases. Statutory output remains disabled separately. Mosaic does not provide legal or tax advice.

## History

v1.1.0 remains the earlier blueprint/configuration release: <https://github.com/Hearthplug/mosaic-erp/releases/tag/v1.1.0>. Its artifacts and evidence apply only to that release.

MIT licensed.
