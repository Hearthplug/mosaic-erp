# Mosaic ERP

Mosaic is an interview-native operational ERP for core retailer work. An owner describes the business in plain language; Mosaic provisions the relevant workflows, reports, branding, verification tasks and fine-grained staff roles. The same system then runs persistent buying, receiving, selling, returns/refunds, stock, cash, supplier bills/payments, reconciliation, period close and core accounting reports.

## Scope of v2.1.0

v2.1.0 is an evidence-backed **production-core retailer ERP release**. It is not a claim of complete advanced-retail or enterprise-suite breadth. Since v1.4.1: photo intake that turns paper bills, credit-book pages and stock registers into reviewed books (v2.0.0), the day close with a shareable summary, voice entry, your choice of AI provider per capability with masked key entry, in-app update notices (v2.0.0), natural-language report drafting on the Build screen and the Intel Mac installer (v2.0.1), and in v2.1.0 the per-page pick-first UX across Till, Stock, Buying, Money and Books with plain explanations beside terms, every report as PDF, XLSX or CSV, and plain-language custom reports on the Books page. The fine-tuned local assistant stays in Preview with owner confirmation on every action; Jev by TypeSafe stays available in Preview with the owner's own key.

Implemented and source-tested:

- guided owner interview that provisions an operating model and real controls
- normal email/password sign-in, secure Google and Microsoft OIDC routes, expiring/revocable sessions, secure single-use invitations and company chooser
- action, location, amount and record-state RBAC with segregation-of-duties checks
- products, stores, suppliers/customers, purchase orders, receiving, sales, exact tenders, returns/refunds, transfers, counts and cash close
- purchase bills, three-way match, payments, bank matching, immutable double-entry journals, period locks, aging, trial balance, P&L and balance sheet
- validation-first migration with reviewed openings, reconciliation and correction/rollback guidance
- PostgreSQL 16+ pooling, migrations, `FORCE ROW LEVEL SECURITY`, restricted runtime role, atomic domain commands and cross-replica locks
- strict same-origin CSP, audit history, request limits, health/readiness and metrics
- answer-shaping chooser: Standard built-in mapping by default, optional Jev by TypeSafe (Preview) with the owner's own TypeSafe key, and OpenAI, Claude and DeepSeek each available with the owner's own key from that provider; every interview answer and setting change still requires owner confirmation

Explicitly excluded:

- statutory invoice formats, tax filing, e-invoicing or jurisdiction certification without a separately verified local adapter/version
- advanced modules such as held carts, promotions, printable fiscal receipts, deep batch/expiry/serial operations, landed cost, manufacturing, payroll and broad enterprise-suite replacement
- managed hosting, database HA/PITR, target-cluster failover/capacity evidence or an operator restore certificate

## Download the desktop app

- **Windows:** [MosaicERP-windows-x64-setup.exe](https://github.com/Hearthplug/mosaic-erp/releases/download/v2.1.0/MosaicERP-windows-x64-setup.exe) - run it and Mosaic opens in your browser at a private localhost address, with a proper uninstaller. A portable build ([MosaicERP-windows-x64.exe](https://github.com/Hearthplug/mosaic-erp/releases/download/v2.1.0/MosaicERP-windows-x64.exe)) is also available. The app is not code-signed yet; if SmartScreen shows "Windows protected your PC", choose **More info**, then **Run anyway**.
- **Mac (Apple Silicon):** [MosaicERP-macos-arm64.dmg](https://github.com/Hearthplug/mosaic-erp/releases/download/v2.1.0/MosaicERP-macos-arm64.dmg) - open the dmg, drag Mosaic ERP to Applications, then right-click the app and choose **Open** on first run (the app is not signed with an Apple Developer ID yet).
- **Mac (Intel):** [MosaicERP-macos-x64.dmg](https://github.com/Hearthplug/mosaic-erp/releases/download/v2.1.0/MosaicERP-macos-x64.dmg) - same steps as Apple Silicon.

Both desktop apps include the optional local assistant Preview: on first run the app downloads the assistant model (about 1.2 GB, sha256-verified) in the background, and everything else works while it downloads.

To check the same shop from a phone or another computer, use the hosted path instead: [check your shop from anywhere](docs/HOSTED_ACCESS.md). The hosted UI runs in the phone browser over HTTPS; there is no separate mobile app.

## Start locally

```bash
python3 install.py
python3 app.py
```

Open `http://localhost:8000/signin`, choose **Set up a new company**, and enter the company name, work email and a password. Mosaic signs the owner in and opens the business interview. Ordinary users never handle workspace or API keys.

SQLite is for evaluation and simple single-process use. It includes an integrity-checked local backup/restore path. PostgreSQL is required for concurrent production replicas.

## Production deployment

Use an external PostgreSQL 16+ service and the supplied Compose or Helm path. Runtime and schema-migration credentials are separate. Operators must provide TLS/DNS, secret management, managed database HA/PITR, monitoring, capacity testing and an isolated restore drill against the exact target environment. See [hosted access](docs/HOSTED_ACCESS.md), [deployment](docs/DEPLOYMENT.md), [PostgreSQL operations](docs/POSTGRESQL.md), and [identity-provider deployment](docs/DEPLOYMENT.md#google-and-microsoft-sign-in).

Current release: [v2.1.0](https://github.com/Hearthplug/mosaic-erp/releases/tag/v2.1.0), with honest per-release notes and the evidence each gate produced. Earlier releases keep their own artifacts and evidence; no earlier release's evidence is reused for a later one.

Google and Microsoft controls use provider-published sign-in assets and real configuration-aware OIDC routes. Live activation remains deployment-owned: the operator must provide a canonical HTTPS domain, register exact callbacks with each provider, select the Microsoft account type, complete required consent/domain review and provision rotated secrets. Unconfigured controls remain disabled.

## Tax review

Candidate jurisdiction packs are sourced and versioned inputs. Calculations stay fail-closed until the business owner or a named professional attests the exact jurisdiction, effective dates, sources, rules and regression cases. Professional review is recommended, not mandatory. Statutory output remains disabled separately. Mosaic does not provide legal or tax advice.

## History

- v2.1.0: per-page pick-first UX across Till, Stock, Buying, Money and Books with plain explanations beside terms, live Today to-dos, low-stock filter, sales date range, note-and-coin till counter, every report downloadable as PDF, XLSX or CSV, plain-language custom reports on the Books page (offline parser, always shows what it understood), and XLSX import on Move in.
- v2.0.1: natural-language report drafting on Build from a checked allow-list, clean recovery from expired sign-ins, and the Intel Mac installer (MosaicERP-macos-x64.dmg) alongside Apple Silicon.
- v2.0.0: photo intake for paper bills, credit-book pages and stock registers with review before posting, day close with shareable summary, voice entry (OpenAI key or compatible transcription server), per-capability AI provider choice with masked key entry, in-app update notices with pre-upgrade backup, more chart-of-account and tax templates.
- v1.4.1: OpenAI, Claude and DeepSeek wired into answer shaping and reconfiguration with the owner's own key (masked key field, per-workspace secret storage, audit event, owner-only), Standard still the default.
- v1.4.0: answer-shaping chooser (Standard built in by default, Jev by TypeSafe in Preview with the owner's own key) and Jev-assisted interview review and plain-language reconfiguration, with owner confirmation on everything.
- v1.3.4: Windows NSIS setup installer with proper uninstall alongside the portable build.
- v1.3.3: interview Apply fix and accounting auto-provisioning.
- v1.3.2: one-download Mac desktop app and hardened hosted HTTPS path.
- v1.3.1: one-download Windows desktop app with the assistant Preview bundled, Mosaic logo across the UI, download section on the product page.
- v1.3.0: fine-tuned local assistant in Preview (owner-confirmed drafts, measured frozen-contract evidence) on top of the production-core release.
- v1.2.0: production-core retailer ERP release candidate.
- v1.1.0: earlier blueprint/configuration release: <https://github.com/Hearthplug/mosaic-erp/releases/tag/v1.1.0>.

Each release's artifacts and evidence apply only to that release.

MIT licensed.
