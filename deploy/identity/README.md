# Hearth sign-in theme

The `hearth` login theme extends the pinned Keycloak 26.7.3 `keycloak.v2` theme. It supplies Hearth's original artwork and palette, application context, and plain-language messages. Login, registration, OTP, recovery, validation, accessibility controls and authentication scripts remain inherited from Keycloak. Do not copy passwords or second factors into the React applications.

The development container mounts `themes/hearth` read-only at `/opt/keycloak/themes/hearth`. Run the stack sync after edits, then restart Keycloak to invalidate its theme caches. Apply presentation settings to an existing farm with:

```powershell
uv run --group appliance python scripts/configure_identity.py theme
```

This command updates only the realm's display/theme settings and the two client display names. It does not recreate users, clients, credentials or authentication flows.

To package the same resources as a deterministic JAR:

```powershell
uv run python scripts/package_identity_theme.py
```

The output is `.hearth/packages/hearth-identity-theme.jar`, containing `META-INF/keycloak-themes.json` and `theme/hearth/login/`. A packaged deployment installs the JAR in Keycloak's `providers/` directory and selects the `hearth` login theme. It contains no executable Java provider. Do not install the directory and JAR copies simultaneously. This reference footer uses the current fixed localhost app origins; a future LAN installer must supply its qualified exact origins.

Run the targeted appearance checks with:

```powershell
uv run --group appliance python scripts/identity_theme_qa.py
```

This checks anonymous real HTTPS login pages, then creates a separate disposable identity realm for registration-form, OTP/recovery enrollment and PKCE exchange checks on guest HTTP loopback. It never provisions an account in the user's Hearth farm. The realm is removed afterwards, and the existing account and credential identifiers are verified unchanged. Evidence masks QR secrets and recovery codes. These checks do not replace the broader BFF or release qualification suites.

The original brand files remain authoritative and unchanged. When updating this theme, preserve the matching light/dark SVG variants and check both appearances plus mobile layouts. On a Keycloak version update, review the parent theme's form structure and supported message keys before shipping.

References: [Keycloak theme development and deployment](https://www.keycloak.org/ui-customization/themes), [Firefox third-party root trust](https://support.mozilla.org/en-US/kb/automatically-trust-third-party-certificates).
