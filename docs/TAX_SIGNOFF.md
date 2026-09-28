# Tax sign-off per country

Mosaic calculates tax only from rules a workspace owner or a tax professional has reviewed and attested. A country is **not** signed off because its pack exists. It is signed off when the attestation and the regression evidence exist for that workspace. Statutory documents (official tax invoices, filings, e-invoicing) stay disabled in every state until a separate adapter review; the sign-off below covers calculation only.

## The gate, in one line

No verified rule for a date, place and transaction = no tax calculated and no statutory document. The system fails closed, by design.

## Sign-off steps for one country

1. **Pull the candidate pack.** `GET /api/tax/checklist?jurisdiction=<country>` returns the source-backed candidate (rates, registration context, authority sources, warnings) plus the ten-point verification list: registration status, effective dates, classification basis, place-of-supply scope, inclusive/exclusive price basis, rounding basis, zero-rated/exempt evidence, reverse-charge conditions, credit restrictions, and invoice/filing fields. Every candidate arrives as `requires_owner_or_professional_review` with the statutory adapter disabled.
2. **Confirm fail-closed.** Before any attestation, run `POST /api/tax/regression` for the jurisdiction. Every case must fail with "No owner- or professionally-reviewed tax rule covers this date, place and transaction". If any case passes before attestation, stop; the gate is broken.
3. **Review like a human, attest like one.** The owner (or their tax professional) checks the candidate against the authority sources, then records the attestation with `POST /api/tax/verify`. The attestation names the reviewer, the review kind (`owner` or `professional`), the verified-on date, effective dates, registration and supply scope, classification basis, price basis, rounding basis, the source URLs, and the known limitations. An owner attestation is accepted and flagged `professional_review_recommended`; a new attestation for the same jurisdiction supersedes the previous one and marks stale statutory artifacts for re-verification.
4. **Prove the math.** Run `POST /api/tax/regression` with measured cases: a round amount, a real-world amount that forces rounding, and the minimum amount. Every case must pass against expected net/tax/gross in minor units, and each result must carry the rule hash it ran against.
5. **Record the sign-off.** Keep the attestation ID, attestation hash, rule IDs, and the regression transcript with the workspace's compliance records. Re-run the drill when rates change, when the pack's effective date moves, or before enabling sales in a new subdivision.

## Recorded drill, 2026-09-28 (United States, California state rate)

Run against a live workspace (First Sale Store, USD) to prove the gate end to end:

- **Step 1** returned the US candidate: one rule `CALIFORNIA_STATE_RATE` 7.25% effective 2026-09-17, pack hash `4e1e56cd…6b`, two authority sources (South Dakota v. Wayfair; Streamlined Sales Tax marketplace facilitator), warning that local district add-ons can apply, state `requires_owner_or_professional_review`, statutory adapter disabled.
- **Step 2** confirmed fail-closed: regression before attestation returned `passed: false` with the expected no-verified-rule error and `statutory_document_allowed: false`.
- **Step 3** recorded an owner attestation marked as drill evidence (reviewer "Restore-Drill Owner (sign-off drill)", limitations noting a real sign-off needs review of live rates and district add-ons): verification `txv_12d45bec91d50448`, attestation hash `81d9097e…00e4`, verified rule `txr_c15ea5f5139961b7`, `professional_review_recommended: true`, statutory adapter still disabled.
- **Step 4** passed all three measured cases against rule hash `a2435c34…9d2`:

| Case | Net | Tax | Gross |
| --- | --- | --- | --- |
| CA 7.25% on $100.00 | 10000 | 725 | 10725 |
| CA 7.25% on $4.86 (rounding) | 486 | 35 | 521 |
| CA 7.25% on $0.01 (minimum) | 1 | 0 | 1 |

- After attestation, `statutory_document_allowed` remains `false`; the sign-off covers calculation only.

## What this does not sign off

Rates change and local add-ons exist (the US pack warns about district taxes; Canada rates follow destination province; UAE e-invoicing phases in from 2026). The attestation's limitations field is where those exclusions live, and the regression drill is how a rate change gets caught. Statutory invoices, filings, and e-invoicing remain adapter-gated and out of scope until their own review.
