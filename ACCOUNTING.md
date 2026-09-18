# Accounting foundation

This module adds an operational accounting core. It does not turn the current UI into a finished accounting product by itself.

## Implemented in the core

- integer-minor-unit money and explicit base/transaction currencies
- chart of accounts and controlled system-account mappings
- immutable posted double-entry journals; corrections use linked reversal journals
- fiscal periods and hard posting locks
- customers/vendors, tax codes, numbered sales invoices, purchase bills, credit notes and debit notes
- draft -> approval -> posting workflow with actor IDs and audit events
- accounts receivable/payable postings, tax rounding, general ledger, trial balance, P&L and balance sheet
- CSV validation-first imports for customers, vendors and accounts
- review state; chart, tax or material accounting-setting changes invalidate it
- database transactions, existing tenant isolation, and existing request idempotency primitives

## Launch verification

Before live use, the business owner can verify with one click after reviewing the evidence; review by a qualified local accountant is recommended the legal entity, opening balances, chart mappings, tax registrations/rates, fiscal periods, numbering, currency rules and example outputs. Mosaic stores who verified it, when, and their note. A material configuration change moves the state from `verified` to `invalidated`; daily transaction entry does not.

## Production-core accounting boundary

Authenticated APIs/UI, payments/refunds, aging, bank matching, migration reconciliation, PostgreSQL RLS/concurrency and accountant-verification hooks are implemented for core retailer operations. Before using a target deployment, a qualified accountant must accept the real chart, openings, source reconciliation, tax settings, example transactions and close reports. An independent recovery/security review remains deployment owned.

Still excluded: statutory invoice layouts, tax returns, e-invoicing, filing and jurisdiction-specific withholding/reverse-charge/close certification until the exact adapter/version is verified locally.

Jurisdiction packs in the blueprint generator are planning inputs, not legal or tax certification. No return or statutory invoice should be filed or issued solely from an unverified pack.

## Controls and recovery evidence

The accounting core uses the existing atomic database transaction boundary, tenant-scoped actors and audit events. Posted journals and lines have database-level update/delete blocks; period locks block back-posting; numbering is allocated inside the write transaction. The SQLite online-backup and restore commands already exercised by the persistence suite include the accounting tables. Production PostgreSQL still requires a restore drill that checks accounting trial-balance equality and acceptance-run checksums after recovery.

Every source migration must record the source control total, row count, posted total and variance. A non-zero variance remains visible as `variance`, not reconciled. Acceptance runs store expected and actual results, differences and a checksum so an accountant can sign off against agreed real sample data.

Statutory adapters are fail-closed. They are `disabled` until the business owner or a named professional verifies a jurisdiction, capability and rules version. Configuration invalidates the overall accounting sign-off.
