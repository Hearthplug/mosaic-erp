# Provider sign-in branding

The sign-in screen packages the providers' published assets as base64 source and decodes their exact bytes at runtime so its strict Content Security Policy does not depend on third-party images.

- `google-signin.png` is Google's pre-approved standard light rectangular "Sign in with Google" asset, downloaded from the current [Google Identity branding guidelines](https://developers.google.com/identity/branding-guidelines). Do not recolor, redraw, crop or replace its text.
- `microsoft-signin.svg` is Microsoft's published light "Sign in with Microsoft" symbol lockup from the current [Microsoft identity platform branding guidelines](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-branding-in-apps). Do not alter its symbol, typography, colors or proportions.

The assets are presentation only. The containing controls remain real HTML buttons wired to Mosaic's provider start routes. Disabled styling may reduce the opacity of the complete approved asset when provider setup is incomplete, but the asset itself is unchanged.

Recheck both provider pages before a later branding update because providers can change their required patterns. Mosaic's decoded runtime copies have these SHA-256 values:

- Google PNG: `892062091f35e69dd838ba4a4f238d37a0562d52ecda6406eb343a1127251409`
- Microsoft SVG: `e06fb6b9c489d5719260945b5b9108f12fedd77e61206229f5fdd77a060e77a8`
