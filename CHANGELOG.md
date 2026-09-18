# Changelog

## 1.2.0 - release candidate

Production-core retailer ERP candidate:

- interview provisioning for workflows, reports, branding, verification tasks and operational roles
- persistent retail/accounting transaction spine and layperson operations/migration screens
- normal sign-in, company chooser, secure invitations, role-correct landing, revocable sessions and configuration-aware Google/Microsoft OIDC
- provider-published Google and Microsoft sign-in assets; unconfigured controls stay disabled and configured controls use real authorization routes
- fine-grained RBAC enforced on operational APIs
- PostgreSQL forced RLS, restricted runtime role, atomic commands and concurrency/failure acceptance
- professionally attested tax-calculation boundary; statutory outputs remain disabled

Release boundaries: target-environment restore/HA/capacity/security certification is operator owned; statutory/local claims require separate professional verification; advanced modules are excluded.

Reviewed product tree: [`8235d04bd53ed402e862bc2b77d832e7adc382de`](https://api.github.com/repos/Hearthplug/mosaic-erp/git/trees/8235d04bd53ed402e862bc2b77d832e7adc382de?recursive=1). Release-infrastructure commit [`5d6c3fc94a4c55ef2f8add3a0bf17b0732b0f91b`](https://github.com/Hearthplug/mosaic-erp/commit/5d6c3fc94a4c55ef2f8add3a0bf17b0732b0f91b) adds the independent publication gate without changing that reviewed product tree. Its [successful CI](https://github.com/Hearthplug/mosaic-erp/actions/runs/35393974456) verifies the product plus publication-workflow parent, and its [successful Pages deployment](https://github.com/Hearthplug/mosaic-erp/actions/runs/35393973681) is dated September 19, 2026. This docs-only update cites those prior verified inputs and does not claim they tested this commit. Fresh archives, checksums, container images, immutable digests, signatures, SBOM/provenance and vulnerability-scan evidence remain required before publication. v1.1.0 evidence must not be reused.

## 1.1.0

Earlier blueprint/configuration release. Existing v1.1.0 artifacts and evidence remain historical and are not evidence for 1.2.0.
