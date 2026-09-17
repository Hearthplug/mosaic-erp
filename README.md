# Mosaic ERP - Your business. Your ERP.

Mosaic ERP is a conversational retail ERP architect. During setup, it interviews the owner in plain language and visibly reshapes the ERP in real time: navigation, dashboard KPIs, business terminology, modules, tax profile, workflows, and team roles all change with each answer.

This is not a fixed dashboard with different labels. The configuration engine produces structurally different systems for grocery, fashion, electronics, pharmacy, beauty and wellness, and specialty retail, across ten tax jurisdictions. Multi-store, omnichannel, credit, batch/expiry, serial/warranty, services/appointments, and team-control capabilities activate only when the operating model calls for them.

## Run

```bash
python3 app.py
```

Open http://localhost:8000. No packages or API key are required.

## Test

```bash
python3 -m unittest test_customization -v
```

48 tests cover partial live configuration, vertical reshaping, ten jurisdiction tax packs, full JSON export, and the conversational tax-configuration layer (view, preview, apply, rollback, refusals, multi-turn jurisdiction switches).

## Product architecture

- **Discovery schema:** a ten-question base interview plus dynamic jurisdiction questions. Picking a country adds the follow-ups that jurisdiction needs - subdivision for the United States, Canada, and the EU, turnover bands in the local currency, registration types, supply reach, and buyer mix. `POST /api/questions` returns the tailored question set for the answers so far.
- **Jurisdiction tax packs:** India (GST 2.0: 5/18/40 slabs, CGST/SGST vs IGST, HSN 4/6 digits by AATO, e-invoicing above Rs 5 crore, e-way bills, composition scheme, LUT exports, TCS), UAE (VAT 5%, AED 375,000 threshold), Singapore (GST 9%, S$1 million), China (VAT 13/9/6, general vs small-scale, fapiao), Vietnam (10% with the 8% reduction to 31 Dec 2026, mandatory e-invoice), Malaysia (SST 5/10 + 8% service tax, RM500,000), UK (VAT 20%, £90,000, MTD), USA (state sales tax, economic nexus, marketplace facilitator, no federal tax), Canada (GST/HST/PST/QST by province, CA$30,000 small supplier), and the EU (VAT Directive floor 15%, member-state rates, OSS, VIES reverse charge). Every pack carries its authoritative source links and a verification date.
- **Conversational compliance control:** after onboarding, the same chat drives tax settings. The engine understands view, change, apply, cancel, export, and rollback intents across country, subdivision, registration, turnover, supply scope, and buyers. Every mutation first returns a structured preview - old and new value, affected modules/workflows/tax fields, validation warnings, source and effective date - and applies only on explicit confirmation. Changes are versioned with an audit trail and one-word rollback; forged or stale pending changes are rejected.
- **Configuration compiler:** deterministic rules choose terminology, navigation, KPIs, modules, workflows, access roles, and the tax pack. Every choice is explainable.
- **Live blueprint:** `/api/preview` accepts partial answers and returns a valid evolving configuration.
- **Final blueprint:** `/api/configure` validates all required answers and produces a versioned configuration.
- **JSON export:** `/api/export` and the Export JSON button download the entire configured ERP blueprint, including the tax profile and audit trail.
- **Production path:** add an LLM for follow-up questions and language, while keeping the rules compiler as the safety and consistency boundary.

## API

- `GET /health`
- `GET /api/questions` / `POST /api/questions` with `{"answers": {...}}` for the tailored set
- `POST /api/preview` with partial JSON answers
- `POST /api/configure` with complete JSON answers
- `POST /api/export` with complete or partial answers; returns the full blueprint as a downloadable JSON attachment
- `POST /api/chat` with `{answers, config, message, pending?, draft?}` for conversational tax configuration

## Market framing

Most conversational ERP agents query or operate software already installed. Broad modular ERPs still require implementation work to translate a business into modules, fields, roles, and workflows. Mosaic ERP targets that translation step: conversational implementation before configuration - and conversational control of the compliance layer after it.

Demand evidence and context:
- [Dun & Bradstreet: Rethinking the Future of India’s Small and Mid-Sized Businesses 2025](https://www.dnb.co.in/files/reports/DNB-Rethinking-the-Future-of-Indias-Small-Mid-Sized-Businesses-2025.pdf)
- [ICRIER Annual Survey of MSMEs in India 2025](https://icrier.org/pdf/Annual-Survey-MSMEs_India_2025.pdf)
- [Zoho Indian Retailer Survey](https://www.zoho.com/news/micro-and-small-indian-retailers-to-invest-in-ai-and-ml-to-stay-competitive-zoho-survey.html)

## Scope

The prototype creates a working, versioned ERP blueprint, not a production financial ledger. Tax profiles are configuration blueprints grounded in the cited authority pages and their effective dates - they are not tax filings, legal or tax advice, or compliance certification. Item-level rates must be confirmed against classification and current notifications, and production rollout needs authentication, tenant isolation, database migrations, backups, audit logs, integration adapters, and review by a local tax professional before reliance.

MIT licensed.
