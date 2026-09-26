# Incident response (draft)
Incident owner and backup: [OWNER REVIEW]. Reporting channel: [OWNER REVIEW]. Emergency vendor contacts: [OWNER REVIEW].

1. Triage: record first observation, scope, affected systems and data, timeline and owner; treat unexplained cross-tenant access, exposed secrets or unauthorized changes as urgent.
2. Contain: restrict access, revoke tokens, rotate exposed secrets, isolate compromised workloads. Preserve logs, artifacts and chain of custody; do not destroy evidence during cleanup.
3. Assess: determine impacted tenants, data categories, jurisdictional notification duties and any contractual deadlines with counsel. Do not promise a notification window before those duties are checked.
4. Recover: fix root cause, deploy reviewed code, restore isolated backups if needed, verify tenant isolation and monitor recurrence. Record RTO/RPO actually achieved.
5. Communicate: the incident owner approves accurate customer and regulator messages; track recipients and follow-ups.
6. Learn: within [OWNER REVIEW] days, write a blameless timeline, corrective actions, owners and due dates. Rehearse this plan at least annually and record the drill.
