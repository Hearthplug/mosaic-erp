# Real ERP acceptance plan

The target is a persistent operational retail ERP. The interview/chat is only onboarding and an operating shortcut. It must configure and call the same durable modules as every screen and API. Country packs are inputs, never the deliverable.

## Stage 1: transaction spine (draft branch, partially implemented)

- durable catalog, locations, parties and role-controlled users
- append-only inventory movements and live stock by product/location
- purchase order approval and partial/full receiving
- completed POS sale and exact tender control
- billing/accounting journal, periods, sign-off and reports
- backups, imports, audits, idempotency and explicit correction flows

Acceptance: purchase 10 units, receive them, sell 2, persist stock 8, record tender, post invoice/COGS/tax journals, and recover the same balances from backup.

## Stage 2: full daily operations

- barcode/search POS UI, held carts, discounts, cash sessions and receipt output
- sales returns/exchanges/refunds with stock disposition
- customer/vendor credit limits, statements, collections and payable runs
- reorder suggestions, stock transfer, counts, shrinkage, batches/expiry and serials
- purchase bills matched to orders/receipts; landed cost and verified costing policy
- dashboards, alerts, printable documents and end-of-day close

## Stage 3: production and localization gates

- PostgreSQL schema/RLS for every ERP table plus concurrent order/stock/numbering tests
- verified local statutory invoice, tax, e-invoice and filing adapters
- real source-system import reconciliation and accountant acceptance packs
- restore, failover, security, performance and independent controls review

The current public release remains an early technical prototype until all acceptance gates for the intended first country and retail workflow pass.
