# Real ERP acceptance plan

Mosaic's target is a persistent operational ERP. The interview is onboarding and configuration, not the deliverable.

## Production core retailer candidate - implemented

- persistent masters, buy/approve/receive, sell/tender, return/refund, transfer/count, cash close
- supplier bills, three-way match, payment, bank match, immutable journals, period close and core reports
- authenticated layperson screens, migration/reconciliation, audit and correction paths
- interview-provisioned action/location/amount/state RBAC on real APIs
- PostgreSQL forced RLS, restricted runtime role, atomic commands and concurrency controls
- representative SQLite recovery and PostgreSQL reconnect/failure/concurrency acceptance

## Deployment gates - operator owned

For each target deployment: TLS/DNS and secrets, managed PostgreSQL HA/PITR, monitoring, capacity/failover evidence, an isolated restore drill with data/audit/trial-balance checks, and an independent security review appropriate to the data and exposure.

## Statutory/localization review gates

Statutory invoice, tax return, e-invoice and filing adapters remain disabled until the exact jurisdiction, capability and rules version are verified by the business owner or a named local professional (professional review recommended) and pass transaction regressions.

## Advanced modules - out of this release

Held carts, promotions, printable fiscal receipts, deep batch/expiry/serial operations, landed cost, manufacturing, payroll and broad enterprise-suite modules require their own persistent vertical slices and acceptance evidence before being claimed.
