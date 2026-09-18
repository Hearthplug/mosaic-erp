# 360-degree coverage gap report

The v2 dataset covers all 19 implemented story families against 20 risk-weighted dimensions (380 cells). It uses rotated role, organization, workflow-state, and data-quality combinations instead of a misleading full Cartesian product. Accounting, tax, document posting, period close, RBAC, bank reconciliation, imports, statutory boundaries, and assistant secrets have locked cross-company, retry, concurrency, reversal, and failure-recovery cases.

Known honest boundaries remain: statutory filing/adapters, advanced manufacturing, payroll, managed hosting, and the fine-tuned local assistant are unavailable in v1.2.0 and map to guidance or rejection. Synthetic language may not cover every dialect or novel attack. No training-ready claim is allowed unless `validate_dataset.py` and the independent coverage report pass all frozen thresholds. The native acceptance suite remains outside training and checkpoint selection.
