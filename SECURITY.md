# Security evidence pack

Run `python3 release_check.py` on a clean checkout. Archive its output with the commit SHA. The gate covers configuration behavior, tenant isolation, role enforcement, hashed passwords and sessions, strict CSP/static assets, shared limiter behavior, migrations, transaction rollback, restart persistence, backup/restore, HTTP security headers, dependency inventory, secret patterns, and a local load smoke test.

This is automated maintainer evidence, not an independent security audit. Report vulnerabilities privately to the repository owner. Do not include live tokens, passwords, customer data, or exploit details in a public issue.
