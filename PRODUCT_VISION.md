# Mosaic operational ERP product and acceptance map

## Product promise

Mosaic is a real operational ERP with an interview intelligence layer. The interview activates and configures persistent modules, terminology, fields, workflows, approvals, roles, reports and verified localization. It is not a document generator. Modules that do not fit the customer remain hidden by default, while dependencies stay coherent and can be enabled later through a controlled, audited change.

## Durable high-end scope

- Sales: POS, quotes, orders, delivery, invoices, tenders, promotions, returns, exchanges, refunds and cash sessions
- CRM: leads, customers, segmentation, communications, loyalty, credit limits and collections
- Catalog: products, variants, units, barcodes, price books, discounts, tax classes and bundles
- Procurement: requests, approvals, purchase orders, receiving, three-way matching, supplier terms and payable runs
- Inventory: stores, warehouses, bins, lots, expiry, serials, transfers, counts, reservations, replenishment, valuation and landed costs
- Manufacturing/assembly when relevant: bills of materials, work orders, consumption, output, yield and costing
- Finance: immutable general ledger, receivables, payables, assets, budgets, expenses, cash, banking, reconciliation, multi-currency, consolidation and close
- Local tax: professionally verified invoice, e-invoice, return and filing adapters; unverified adapters fail closed
- Service: warranty, repair, cases, service orders, parts and returns
- People: staff, roles, shifts, time/leave and payroll-provider interfaces; Mosaic does not silently become the payroll authority
- Projects: jobs, milestones, time, cost and project billing when relevant
- Assets/maintenance: asset register, depreciation interfaces, maintenance plans and work orders
- Platform: documents, comments, approvals, notifications, analytics, audit, imports/exports, webhooks, integrations, multi-company/store/currency/language and recovery

## Interview-to-operation contract

Interview answers compile into an `operational_profile` with enabled modules, vocabulary, required master data, workflow states, role matrix, approval thresholds, report set and localization adapters. Applying a profile creates or updates those persistent capabilities. Material finance, tax, legal-entity, currency and numbering changes invalidate professional sign-off. Removing a module with existing transactions is prohibited; it can only be hidden or retired while records stay readable.

## Staged delivery and acceptance

Each stage includes persistent data, authenticated layperson UI and chat commands, APIs, accounting impact, role checks, audit events, validated imports/exports, PostgreSQL tenant isolation/concurrency, backup/restore proof and automated tests.

### Stage 1: retailer core vertical slice

Set up a company/store; enter or import customers, suppliers and products; approve a PO; receive stock; sell/invoice; take exact payment; return/refund; reconcile stock and cash; post immutable accounts; close a period; run trial balance/P&L/balance sheet; back up, restore and continue. This is the minimum gate for saying "real ERP."

Current draft proves persistent master data, PO approval/receiving, stock movements, POS sale/tenders, accounting journals and reports at SQLite core level. It does not yet pass the full gate.

### Stage 2: production retailer

Finish UI/chat/API for every core flow, return/refund and cash-session close, customer/vendor credit, purchase bill matching, stock transfer/count, reorder, robust imports, PostgreSQL RLS/concurrency, failure recovery and an accountant-reviewed sample dataset.

### Stage 3: advanced retail

Variants, price books, promotions, lots/expiry/serials, omnichannel reservations, loyalty, service/warranty, landed cost, budgets, fixed assets, multi-company consolidation, multi-currency revaluation and integration/webhook controls.

### Stage 4: optional enterprise modules

Interview-gated manufacturing/assembly, projects, maintenance, HR/time/payroll interfaces and industry extensions. Each module ships only with its own end-to-end operational and accounting acceptance pack.

### Stage 5: localization

Country/jurisdiction adapters are versioned, cited, tested and signed off locally. Statutory invoices, tax returns, e-invoicing and filing remain disabled until the exact adapter/version is verified.

## Release gate

A representative retailer must be able to set up, import or enter masters, buy/receive, sell/invoice, take payment, return/refund, reconcile stock/cash, close a period, produce accounts, back up/restore and continue after an induced failure. The same run must prove permissions, audit history, PostgreSQL tenant separation, concurrent-write safety and accountant acceptance. Until then every surface says early technical prototype.
