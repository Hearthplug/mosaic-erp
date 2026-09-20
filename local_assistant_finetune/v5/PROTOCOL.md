# Experiment 5 protocol: structural fixes after the experiment-4 development failure

Experiment 4 kept every v3 guarantee and added family-disjoint development data. Its
development gates still failed closed (exact match 0.8894, minimum intent recall 0.5833,
one actionable false positive). The recorded failure review showed three causes:

1. Destructive or bulk-record-editing phrasing (purging, wiping, erasing records) was routed
   to actionable intents instead of REJECT or CLARIFY.
2. The model emitted labels outside the 21-label map on near-neighbor prompts (for example
   a retail product-creation prompt answered as a stock or purchase intent).
3. The weakest intent boundaries were product creation vs stock checks, workspace
   configuration preview vs purchase orders, journal reversal vs bank statement import, and
   assistant cancel vs other assistant intents.

Experiment 5 changes only the data, prospectively:

- Fresh destructive and bulk-record-editing hard negatives across retail, accounting,
  staffing, and customer-money domains. Clear record destruction, evasion, and falsification
  map to REJECT; ambiguous targets ("the old entries", "the things we discussed") map to
  CLARIFY. Machine-checked minimum quotas apply.
- Fresh contrastive near-neighbor families for each boundary above: paired families that
  share surface wording but differ in label, so the model must learn the deciding feature.
- Additional fresh train families for the six weakest experiment-4 intents
  (ACCOUNTING_JOURNAL_REVERSE, ASSISTANT_CANCEL, WORKSPACE_CONFIG_PREVIEW, REJECT, GUIDANCE,
  MIGRATION_STAGE).

Everything else is inherited unchanged:

- The frozen v3 contract, gates, fail-closed rendering, and evaluation code are untouched.
- Splits stay family-disjoint: train and development never share a base template or a
  non-enum slot value.
- No experiment-4 development prompt, prediction, or failure artifact is encoded, copied,
  or selected against. All base templates and value pools are newly authored.
- Independence is machine-checked against every consumed prior dataset: v3
  train/development, v3 hidden, and v4 train/development. The v4 dataset now joins the
  consumed set and is never regenerated for training.
- The hidden test is generated independently on the runner after development gates pass,
  is scored exactly once, and no post-test tuning or checkpoint reselection is allowed.
- On any missed gate the experiment fails closed and the failure is reported honestly.
