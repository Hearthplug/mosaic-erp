# Changelog

## 1.3.2

- One-download Mac desktop app for Apple Silicon (unsigned, right-click > Open on first run) with the same bundled assistant Preview as Windows
- Hardened hosted HTTPS path: Helm fails closed without a single canonical https publicOrigin plus TLS; Compose requires MOSAIC_PUBLIC_ORIGIN with the app port private behind Caddy
- Modern Ledger app UI merged
- Windows desktop app refreshed on the same release

## 1.3.1

- One-download Windows desktop app (unsigned; SmartScreen guidance applies): onefile exe, per-user data dir, assistant Preview provisioned on first run with sha256-verified downloads, CI-built and smoke-tested
- Mosaic logo across the app UI; download section on the product page

## 1.3.0

- Fine-tuned local assistant in Preview: understands, drafts and explains ERP actions on the shop's own machine; every action requires the owner's explicit confirmation of the exact rendered payload. Measured on the frozen development contract: all constrained outputs schema-valid, every tested unsafe request failed closed, label accuracy 84 to 86 percent
- Evidence-backed production-core retailer release; boundaries unchanged from 1.2.0

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
