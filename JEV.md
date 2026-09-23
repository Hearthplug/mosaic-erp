# Jev AI assist (Preview)

Jev maps the owner's own words to Mosaic-friendly settings in two places:

1. **Interview review** - after the last question, every text answer is shown
   side-by-side: the owner's original words on the left, Mosaic's tidied,
   structured version on the right. Confirmed or edited values are what gets
   saved; the apply path then runs as before.
2. **Plain-language reconfiguration** - on the applied interview screen the
   owner describes a change ("we opened a second shop, customers can pay
   monthly") and Jev proposes concrete setting changes (current -> proposed,
   with the reason). Only ticked changes are applied, through the normal
   profile apply path with an audit event.

## Client

`jev_client.py` speaks the documented System One shape (model `jev-1.13.0`,
POST `/v1/systemone`): Choice (up to 255 options), Score (2-10 levels), Noul
(yes/no), each returning per-option probabilities plus a margin-based
confidence; 429/529 retried with backoff; 64k context guard.

**Mock-first, zero spend.** `MockJevClient` returns faithful shapes with
deterministic keyword-evidence scoring, so the app, CI and the eval harness
run without a key. `HttpJevClient` is constructed only from an owner's own key
(BYOK, `JEV_API_KEY`) - never a shared Hearthplug key. Direct TypeSafe terms
are evaluation-only, so real calls wait for free access.

## Confidence policy

- `>= 0.85` auto-accept (pre-confirmed, still editable)
- `0.50 - 0.85` owner-confirm
- `< 0.50` no proposal is offered; the owner decides
- Non-English answers are never mapped this phase: they route to owner
  confirmation with the original preserved (English-only gate in
  `jev_mapper.looks_non_english`).

## Eval harness

`evals/jev_mapper_labels.json` + `test_jev_eval.py`. Labels are hand-written
ONLY - TypeSafe ToS 1.iv / MCA 2.3(b) forbid using Jev output to train or
evaluate a competing model, so no label or training row ever contains Jev
output. The mock defines the accuracy floor (0.85); the real client must beat
it before Jev features pitch as the differentiator. Evals assert the
non-English route rather than any non-English mapping.

## Marketing honesty

No benchmark numbers are published (terms prohibit it). Jev features are
demoed, not quoted. While the mock backs the flow, UI copy says "Mosaic
tidied/matched" rather than naming a model.

## Answer-shaping chooser

The interview start and the Assistant page both offer the same choice of how
interview words are mapped to settings:

- **Standard (built in)** - default. Deterministic mapping inside Mosaic; nothing
  leaves the workspace and no key is needed.
- **Jev by TypeSafe (your key)** - the owner pastes their own TypeSafe key. It is
  written to per-workspace secret-file storage (never the database, logs, or
  audit details) and used only for mapping calls. TypeSafe is named in text only.
- **OpenAI, Claude, or DeepSeek (your key)** - shown disabled, "Not available
  yet." The API rejects any provider other than `standard` or `jev`, so an
  unwired option can never silently take effect.

The choice is stored per workspace (`ai_answer_prefs`), changeable by the owner
at any time, readable by viewers, and every change is audited. `client_for(wid)`
in `ai_prefs.py` is the single place that picks the mapping client.
