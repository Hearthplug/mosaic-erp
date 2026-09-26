# Vendor register (draft)
Owner: [OWNER REVIEW]. No entry below establishes a signed DPA or approved subprocessor.

| Vendor | Known/possible purpose | Review required before customer data |
|---|---|---|
| Render | App hosting, runtime logs, secrets | Verify actual region, access, DPA, retention and incident terms. |
| Neon | Hosted PostgreSQL | Verify actual region, role separation, encryption, backup/restore, DPA and deletion terms. |
| GitHub | Source and CI, not intended customer data | Require MFA, least privilege, branch protection and secret hygiene. |
| Google/Microsoft | Optional OIDC identity | Check credentials, user consent, scopes, account types and their privacy terms. |
| UptimeRobot | Availability monitoring, if enabled | Check endpoint/metadata sent and vendor retention. |
| Payment provider [OWNER REVIEW] | Subscription payments, KYC and taxes as applicable | Confirm selection, data roles, DPA, fees, payouts and subprocessor list. |
| BYOK AI endpoint chosen by customer | Customer-directed processing when enabled | Explain what data is transmitted and get customer approval before enabling. |

Add vendor contacts, region, contract/DPA, security review date, subprocessors and exit plan to a restricted operator register.
