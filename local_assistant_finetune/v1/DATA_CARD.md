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
