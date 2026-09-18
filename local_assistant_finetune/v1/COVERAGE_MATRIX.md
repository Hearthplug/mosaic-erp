# Mosaic implemented user-story coverage matrix v1

Every dataset record must carry `story`, `variant`, `schema`, and `owning_tests`. Required variants for each supported story are: happy path, paraphrase, ambiguity/clarification, invalid value, permission denial, cross-company identifier, cancellation, correction, idempotent retry, and recovery. A row is covered only when its locked test checks intent, required slots, safe fallback, and owner-response usability. Unsupported stories map to `reject` or `guidance`, never a fabricated action.

| Story family | Supported typed-intent families | Owning implementation tests | Boundary |
|---|---|---|---|
| onboarding and company structure | `onboarding.*`, `workspace.config.preview` | `test_onboarding.py`, `test_interview_api.py`, `test_customization.py`, `test_provisioning.py` | preview/apply only |
| roles and RBAC | `workspace.invite`, `workspace.role.update`, `clarify`, `reject` | `test_rbac.py`, `test_operational_rbac_api.py`, `test_auth_experience.py` | deny outside actor scope |
| catalog and locations | `retail.location.create`, `retail.product.create` | `test_retail.py`, `test_retail_api.py` | allowlisted fields |
| procurement and receiving | `retail.purchase.create/approve/receive`, `retail.three_way_match` | `test_retail.py`, `test_representative_retailer.py`, `test_concurrency_erp.py` | state-machine and idempotency checks |
| sales, payments and returns | `retail.sale.create`, `accounting.payment.create`, `retail.return.create` | `test_retail.py`, `test_accounting.py`, `test_recovery_retail.py` | exact tenders and refund controls |
| inventory | `retail.transfer.create`, `retail.count.create`, `retail.stock.status`, `retail.reorder.status` | `test_retail.py`, `test_retail_api.py`, `test_concurrency_erp.py` | no invented product/location IDs |
| suppliers and customers | `accounting.party.create` | `test_accounting.py`, `test_postgres_erp_contract.py` | tenant-scoped identifiers |
| bank reconciliation | `accounting.bank.import`, `accounting.bank.match` | `test_accounting.py`, `test_postgres_erp_live.py` | validation before match |
| accounting and tax | `accounting.setup.preview`, `tax.verify_preview`, `tax.regression` | `test_accounting.py`, `test_tax_engine.py`, `test_tax_verification.py`, `test_tax_all_packs.py` | owner review; professional review recommended |
| invoices and documents | `accounting.document.create/approve/post` | `test_accounting.py`, `test_postgres_erp_live.py` | posting requires preview/permission/state |
| reports and dashboards | `artifact.draft`, `artifact.verify_preview` | `test_artifact_builder.py`, `test_accounting.py` | allowlisted metrics/reports; no raw SQL |
| corrections and reversals | `accounting.journal.reverse`, `workspace.rollback`, `migration.rollback` | `test_accounting.py`, `test_recovery_retail.py`, `test_migration_api.py` | immutable originals and audit trail |
| period close | `accounting.period.create/lock` | `test_accounting.py`, `test_postgres_erp_live.py` | no back-posting after lock |
| imports and exports | `migration.stage/apply/openings/rollback`, `workspace.export`, `retail.export` | `test_migration_api.py`, `test_migration_packs.py`, `test_persistence.py` | validation/reconciliation first |
| Docker deployment guidance | `guidance.docker` | `release_check.py`, `.github/workflows/assistant-validation.yml` | guidance only, no host control |
| Kubernetes deployment guidance | `guidance.kubernetes` | Helm lint/template in `.github/workflows/assistant-validation.yml` | qualified professional required |
| assistant configuration | `assistant.configure/status/test/cancel/rollback`, `reject_secret` | `test_assistant_setup.py` | local unavailable; masked secrets only |
| statutory adapters and filings | `guidance`, `reject` | `test_tax_verification.py`, `test_tax_all_packs.py` | unavailable until exact adapter/version verified |
| advanced manufacturing, payroll, managed hosting | `guidance`, `reject` | `release_check.py` | unsupported in v1.2.0 |
