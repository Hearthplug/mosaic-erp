# Retention and deletion schedule (draft)
Owner: [OWNER REVIEW]. Do not promise immediate deletion or a blanket retention period before backup, legal-hold, tax and accounting duties are checked.

| Data | Proposed rule awaiting owner/legal confirmation | Verification |
|---|---|---|
| Customer workspace and transactions | Retain while active; after termination export on request, then delete active records after [OWNER REVIEW] unless law/hold requires retention. | Exercise export and cascade deletion on a test tenant; verify RLS. |
| Backups and WAL | Rotate after [OWNER REVIEW] days; cannot normally selectively erase one tenant inside historical backup. Restrict restore and reapply deletion on restoration. | Check Neon/backup provider schedules and isolated restore. |
| Security/audit logs | Retain [OWNER REVIEW] months with restricted access and tamper evidence; redact secrets and unnecessary personal details. | Inspect live logger, retention and deletion job. |
| Billing/KYC and support | Payment provider may hold additional records under its own schedule. Retain local records only for the documented legal/accounting purpose. | Confirm final provider, controller/processor roles and DPA. |

Track each deletion request with identity verification, scope, exception, completion and date. Stop changes under a legal hold and document the reason.
