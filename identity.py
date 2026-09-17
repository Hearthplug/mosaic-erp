"""Provider-neutral identity boundary.

An OIDC adapter must return only a validated principal after completing the
checks documented in OIDC.md. Authorization remains in Mosaic's role model.
"""
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class ExternalPrincipal:
    issuer: str
    subject: str
    email: str | None = None

class IdentityProvider(Protocol):
    def authorization_url(self, state: str, nonce: str, code_challenge: str) -> str: ...
    def validate_callback(self, code: str, state: str, nonce: str, code_verifier: str) -> ExternalPrincipal: ...
