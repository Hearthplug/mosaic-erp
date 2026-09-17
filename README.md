# Mosaic ERP - Your business. Your ERP.

Mosaic ERP is a conversational retail ERP architect. During setup, it interviews the owner in plain language and visibly reshapes the ERP in real time: navigation, dashboard KPIs, business terminology, modules, workflows, and team roles all change with each answer.

This is not a fixed dashboard with different labels. The configuration engine produces structurally different systems for grocery, fashion, electronics, pharmacy, beauty and wellness, and specialty retail. Multi-store, omnichannel, credit, batch/expiry, serial/warranty, services/appointments, and team-control capabilities activate only when the operating model calls for them.

## Run

```bash
python3 app.py
```

Open http://localhost:8000. No packages or API key are required.

## Test

```bash
python3 -m unittest discover -s tests -v
```

The suite covers partial live configuration, grocery, fashion, pharmacy, electronics, beauty, multi-store, omnichannel, credit, roles, and invalid final submissions.

## Product architecture

- **Discovery schema:** nine owner-friendly questions capture the first operating model.
- **Configuration compiler:** deterministic rules choose terminology, navigation, KPIs, modules, workflows, and access roles. Every choice is explainable.
- **Live blueprint:** `/api/preview` accepts partial answers and returns a valid evolving configuration.
- **Final blueprint:** `/api/configure` validates all required answers and produces a versioned configuration.
- **Production path:** add an LLM for follow-up questions and language, while keeping the rules compiler as the safety and consistency boundary.

## API

- `GET /health`
- `GET /api/questions`
- `POST /api/preview` with partial JSON answers
- `POST /api/configure` with complete JSON answers

## Market framing

Most conversational ERP agents query or operate software already installed. Broad modular ERPs still require implementation work to translate a business into modules, fields, roles, and workflows. Mosaic ERP targets that translation step: conversational implementation before configuration.

Demand evidence and context:
- [Dun & Bradstreet: Rethinking the Future of India’s Small and Mid-Sized Businesses 2025](https://www.dnb.co.in/files/reports/DNB-Rethinking-the-Future-of-Indias-Small-Mid-Sized-Businesses-2025.pdf)
- [ICRIER Annual Survey of MSMEs in India 2025](https://icrier.org/pdf/Annual-Survey-MSMEs_India_2025.pdf)
- [Zoho Indian Retailer Survey](https://www.zoho.com/news/micro-and-small-indian-retailers-to-invest-in-ai-and-ml-to-stay-competitive-zoho-survey.html)

## Scope

The prototype creates a working, versioned ERP blueprint, not a production financial ledger. Production rollout needs authentication, tenant isolation, database migrations, backups, audit logs, integration adapters, and country-specific accounting and tax review.

MIT licensed.
