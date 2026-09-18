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

Source candidate: commit [`2a23c70db26f0fa0bde55b821087483622a0b351`](https://github.com/Hearthplug/mosaic-erp/commit/2a23c70db26f0fa0bde55b821087483622a0b351), successful [source/deployment and PostgreSQL CI](https://github.com/Hearthplug/mosaic-erp/actions/runs/35330488106), and successful [Pages deployment](https://github.com/Hearthplug/mosaic-erp/actions/runs/35330487505). Fresh archives, checksums, container images, immutable digests, signatures, SBOM/provenance and vulnerability-scan evidence remain required from the final v1.2.0 tag before publication. v1.1.0 evidence must not be reused.

## 1.1.0

Earlier blueprint/configuration release. Existing v1.1.0 artifacts and evidence remain historical and are not evidence for 1.2.0.
