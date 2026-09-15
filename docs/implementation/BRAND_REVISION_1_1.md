# Visual identity 1.1: the lowercase hearth

> Historical artwork revision. [Revision 1.2](BRAND_REVISION_1_2.md) supersedes the combined lockup: the symbol is the first h followed by `earth`. The [active guide](../brand/BRAND_GUIDE.md) is authoritative for current artwork.

13 September 2026 UTC. Requested by the user: turn the fireplace surround into a lowercase h with a taller left stovepipe, keep the flame, and detach rather than remove the bottom line.

The current full mark retains its stroke weight, round caps, hearthstone, flame shape and existing colors. The left stroke extends to form an ascender and the arch becomes the h's shoulder. The two legs end seven clear units above the hearthstone on the 128-unit grid. The original flame path is uniformly scaled to 82% and repositioned inside the lower shoulder. The standalone wordmark, typography and palette are unchanged.

Separate simplified favicon and 24-unit control-node drawings preserve the same construction at small sizes. The revision is applied to light/dark/mono marks and lockups, app tiles, PNG exports, the multi-resolution Windows ICO, the icon sprite, the brand gallery, both web applications, the native setup tool and the identity theme resources.

The editable full-size master is [hearth-mark-light.svg](../../brand/logos/hearth-mark-light.svg). [build_brand.mjs](../../scripts/build_brand.mjs) derives variants, raster/ICO exports and synchronized application copies. It renders the gallery in both appearances and checks its images, SVG syntax and horizontal overflow at the existing five reference widths. It also produces [the review sheet](../../evidence/branding/2026-09-13/hearth-h-mark.png).

This user-requested revision updates the active `brand/` assets. The supplied v1.0 artwork remains unchanged in `docs/plan/brand`; historical evidence remains historical. Brand gallery screenshots demonstrate identity rendering, not provider readiness or release acceptance.

Both Vite production builds pass and their updated bundles are synchronized to the running appliance. The identity theme assets are synchronized, its resource-only JAR is rebuilt, and Keycloak was restarted to invalidate its theme caches. Anonymous browser checks with normal HTTPS certificate validation confirm the v1.1 logo on both real application welcome pages and light/dark sign-in screens, plus current app favicons and a 390-pixel login layout. See [live browser evidence](../../evidence/branding/2026-09-13/brand-live.json). No sign-in or account provisioning was needed.

The updated native setup tool compiles to `.hearth/bin/hearth-setup-brand.exe` for verification. The already-running setup process retains its embedded old artwork until it is closed and the normal launcher rebuilds it on the next launch. The web applications and identity screens already serve v1.1.

The gallery checks pass at 1440, 960, 640, 390 and 320 pixels, with no image failures, malformed SVGs or script errors across 47 SVG files. The full mark, both appearances, lockups and 16/24/32-pixel exports were visually inspected. All 119 files in the supplied `docs/plan` snapshot still match the original SHA-256 inventory. No release gate changes result from this artwork revision.
