# Mosaic ERP - Your business. Your ERP.

Mosaic ERP is a conversational retail ERP architect. During setup, it interviews the owner in plain language and visibly reshapes the ERP in real time: navigation, dashboard KPIs, business terminology, modules, tax profile, workflows, and team roles all change with each answer.

This is not a fixed dashboard with different labels. The configuration engine produces structurally different systems for grocery, fashion, electronics, pharmacy, beauty and wellness, and specialty retail, across 22 tax jurisdictions. Multi-store, omnichannel, credit, batch/expiry, serial/warranty, services/appointments, and team-control capabilities activate only when the operating model calls for them.

## Install and run

One command sets everything up - it checks Python, prepares the database, creates your online-save workspace (recovery key stored in a private local file), and loads a sample business:

```bash
python3 install.py
python3 app.py
```

Open http://localhost:8000. No packages, accounts, or API keys are required - Python 3.10+ is the only prerequisite. Re-running `install.py` after an interruption continues safely. To start over, delete `mosaic.db` and `mosaic-workspace.key`.

## Test

```bash
python3 -m unittest test_customization test_persistence
python3 release_check.py
```

75 tests cover partial live configuration, vertical reshaping, 22 jurisdiction tax packs, full JSON export, the conversational tax-configuration layer (view, preview, apply, rollback, refusals, multi-turn jurisdiction switches), and the persistence/security layer (migrations, tenant isolation, roles, idempotency, versioning, audit, backup/restore, recovery, privacy controls). `release_check.py` runs the full release-readiness gate and exits non-zero if anything fails.

## Product architecture

- **Discovery schema:** a ten-question base interview plus dynamic jurisdiction questions. Picking a country adds the follow-ups that jurisdiction needs - subdivision for the United States, Canada, and the EU, turnover bands in the local currency, registration types, supply reach, and buyer mix. `POST /api/questions` returns the tailored question set for the answers so far.
- **Jurisdiction tax packs:** India (GST 2.0: 5/18/40 slabs, CGST/SGST vs IGST, HSN 4/6 digits by AATO, e-invoicing above Rs 5 crore, e-way bills, composition scheme, LUT exports, TCS), UAE (VAT 5%, AED 375,000 threshold), Singapore (GST 9%, S$1 million), China (VAT 13/9/6, general vs small-scale, fapiao), Vietnam (10% with the 8% reduction to 31 Dec 2026, mandatory e-invoice), Malaysia (SST 5/10 + 8% service tax, RM500,000), UK (VAT 20%, £90,000, MTD), USA (state sales tax, economic nexus, marketplace facilitator, no federal tax), Canada (GST/HST/PST/QST by province, CA$30,000 small supplier), and the EU (VAT Directive floor 15%, member-state rates, OSS, VIES reverse charge). Every pack carries its authoritative source links and a verification date.
- **Extended jurisdiction packs:** Australia, New Zealand, Japan, South Korea, Saudi Arabia, South Africa, Brazil, Mexico, Indonesia, Philippines, Thailand, and Switzerland. Each pack stores official authority links, a verification/effective date, registration and electronic-invoicing checks, transaction-classification warnings, local rates, and invoice metadata. Brazil, Mexico, and Switzerland collect a required state/region/establishment fact; unsafe product, customer, place-of-supply, regime, threshold, and mandate assumptions remain explicit validation steps rather than universal defaults.
- **Conversational compliance control:** after onboarding, the same chat drives tax settings. The engine understands view, change, apply, cancel, export, and rollback intents across country, subdivision, registration, turnover, supply scope, and buyers. Every mutation first returns a structured preview - old and new value, affected modules/workflows/tax fields, validation warnings, source and effective date - and applies only on explicit confirmation. Changes are versioned with an audit trail and one-word rollback; forged or stale pending changes are rejected.
- **Configuration compiler:** deterministic rules choose terminology, navigation, KPIs, modules, workflows, access roles, and the tax pack. Every choice is explainable.
- **Live blueprint:** `/api/preview` accepts partial answers and returns a valid evolving configuration.
- **Final blueprint:** `/api/configure` validates all required answers and produces a versioned configuration.
- **JSON export:** `/api/export` and the Export JSON button download the entire configured ERP blueprint, including the tax profile and audit trail.
- **Workspace persistence:** the Save online button creates a tenant-isolated workspace. Configurations are versioned with optimistic concurrency, every change lands in an append-only audit trail, mutations are idempotent, and one-click rollback, full data export, and confirmed erasure are built in. API keys carry viewer/editor/owner roles; only their hashes are stored.
- **Data architecture:** SQLite (WAL) with transactional writes, ordered schema migrations, integrity-verified online backups and atomic restore, rate limiting, structured request logs with request ids, readiness/metrics endpoints, and secure defaults. Decisions, sources, threat model, and honest limits: [ARCHITECTURE.md](ARCHITECTURE.md).
- **Production path:** add an LLM for follow-up questions and language, while keeping the rules compiler as the safety and consistency boundary. Hosted rollout items (TLS, scheduled offsite backups, SSO, external security review) are listed in the architecture doc.

## API

Public, stateless (nothing is stored):
- `GET /health` · `GET /health/ready` (database integrity probe) · `GET /metrics`
- `GET /api/questions` / `POST /api/questions` with `{"answers": {...}}` for the tailored set
- `POST /api/preview` with partial JSON answers
- `POST /api/configure` with complete JSON answers
- `POST /api/export` with complete or partial answers; returns the full blueprint as a downloadable JSON attachment
- `POST /api/chat` with `{answers, config, message, pending?, draft?}` for conversational tax configuration

Workspace API (Bearer key, tenant-scoped, rate-limited, idempotency-aware):
- `POST /api/workspaces` - create a workspace; the owner key is shown once
- `GET /api/workspace` · `GET /api/workspace/config[?version=N]` · `GET /api/workspace/versions` · `GET /api/workspace/audit`
- `PUT /api/workspace/config` `{answers, config, base_version, summary?}` - versioned save (editor+), stale bases rejected with 409
- `POST /api/workspace/rollback` `{version}` - restore an old version as a new one (editor+)
- `POST /api/workspace/keys` / `DELETE /api/workspace/keys/{id}` - mint and revoke viewer/editor/owner keys (owner)
- `GET /api/workspace/export` - full tenant data export (editor+)
- `DELETE /api/workspace` with `X-Confirm-Delete: <workspace_id>` - complete tenant erasure (owner)

Data operations:
- `python3 app.py backup --out backup.db` - consistent online backup, integrity-verified
- `python3 app.py restore --from backup.db --yes` - verified, atomic restore (stop the server first)

## Market framing

Most conversational ERP agents query or operate software already installed. Broad modular ERPs still require implementation work to translate a business into modules, fields, roles, and workflows. Mosaic ERP targets that translation step: conversational implementation before configuration - and conversational control of the compliance layer after it.

Demand evidence and context:
- [Dun & Bradstreet: Rethinking the Future of India’s Small and Mid-Sized Businesses 2025](https://www.dnb.co.in/files/reports/DNB-Rethinking-the-Future-of-Indias-Small-Mid-Sized-Businesses-2025.pdf)
- [ICRIER Annual Survey of MSMEs in India 2025](https://icrier.org/pdf/Annual-Survey-MSMEs_India_2025.pdf)
- [Zoho Indian Retailer Survey](https://www.zoho.com/news/micro-and-small-indian-retailers-to-invest-in-ai-and-ml-to-stay-competitive-zoho-survey.html)

## Scope

Mosaic creates working, versioned ERP blueprints with a hardened, tenant-isolated persistence layer - it is not a financial ledger and does not replace accounting systems. Tax profiles are configuration blueprints grounded in the cited authority pages and their effective dates - they are not tax filings, legal or tax advice, or compliance certification. Item-level rates must be confirmed against classification and current notifications, and reliance needs review by a local tax professional. The build passes a source-verifiable release gate (`release_check.py`); the remaining deployment-dependent steps before any hosted launch (TLS, scheduled offsite backups, SSO, external security review) are listed in [ARCHITECTURE.md](ARCHITECTURE.md).

MIT licensed.
