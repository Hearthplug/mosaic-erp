# OIDC integration boundary

Mosaic does not ship or pretend to be an identity provider. The local account/session flow is implemented now. A production OIDC adapter must validate an authorization-code + PKCE callback against the configured issuer metadata, exact issuer and audience, signature/JWKS, nonce, state, expiry, and allowed redirect URI. It must map the stable `(issuer, sub)` pair to a Mosaic user and role; email alone must never be the identity key. The adapter should then mint the same revocable `mss_` session used by local login, keeping authorization inside Mosaic.

Operator-provided settings: issuer URL, client ID, client secret from a secret manager, redirect URI allowlist, and explicit group-to-role mapping. No provider is enabled until those values and callback implementation are supplied and tested against that provider.
