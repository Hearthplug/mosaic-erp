# Data card: Mosaic typed intents v1

## Purpose
Synthetic supervised examples for mapping an owner's words to a non-executing Mosaic intent. It is not accounting advice and contains no transaction values from real businesses.

## Coverage
Assistant setup/status, dashboard/report/statutory-definition drafts, owner verification preview, explanation, clarification, and deterministic rejection of direct writes, deletion without review, prompt injection, secret disclosure, raw SQL, unknown fields, and cross-company identifiers. The first tuned model is English-only. Hindi, Kannada, and other languages are deferred to separately versioned future datasets and acceptance suites; no multilingual support is claimed here.

## Generation and review
Examples are authored from the versioned Mosaic allowlists and threat cases. Synthetic names and identifiers are reserved per split. Every unsafe example maps to a reject or clarification intent. Generated expansions must pass the validator and human review before use.

## Exclusions
No customer data, production accounting data, emails, chats, invoices, credentials, keys, access tokens, or realistic secret values. Do not ingest logs or support conversations.

## Limits
Synthetic phrasing may underrepresent dialects and novel attacks. The locked native tests, application controls, and fail-closed product gate remain required.

## 360-degree v2 coverage
The generated English-only set has 380 cells: all 19 implemented story families crossed with 20 risk dimensions. Roles, organization shapes, lifecycle states, and data quality are rotated pairwise across cells. The locked test split reserves cross-company, idempotent retry, concurrency conflict, post-state reversal, and failure recovery for every story, including every high-risk accounting, tax, security, import, and assistant-secret family. Unsupported v1.2.0 features stay guidance/refusal cases.

## Training readiness
Training may start only when the committed `validation_report.json` says `passed: true`, all 380 story-dimension cells exist, all 50 high-risk locked cells exist, all owning test paths resolve, schema validity is 100%, secret findings and split/native-suite overlap are zero, and a reviewer confirms the gap report. Locked test and native-suite results may not influence checkpoint choice.
