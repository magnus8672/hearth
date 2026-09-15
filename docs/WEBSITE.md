# hearth project website

The standalone [single-page website](../website/index.html) presents the finished product in present tense, as explicitly requested by the user. It covers the home AI cloud, smaller specialist models, capability routing, collaboration, security, multi-user spaces and incremental growth. The group chat is an illustrative example. Engineering readiness remains recorded separately in the [coverage audit](implementation/DESIGN_COVERAGE.md); marketing copy is not release evidence. There are no benchmark or minimum-VRAM claims.

## Serve it

From the repository root:

```powershell
pnpm dev:website
```

Open [the local website](http://127.0.0.1:8765). This command uses Python's static server and binds to loopback. No application stack, model service, database, credentials, package installation or frontend build is needed to serve the page directly:

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory website
```

For hosting, upload only the contents of `website/` to any static web server. Keep `index.html`, `styles.css`, `script.js` and `assets/` together. Relative asset paths support a domain root or subdirectory. The website has no server-side routes, analytics, forms, external fonts, API requests or CDN dependencies. Do not expose the repository root or development appliance as the website document root. Public deployment is not part of this change.

## Maintain it

Edit copy and the original inline home-lab illustration in [index.html](../website/index.html), responsive layout in [styles.css](../website/styles.css), and illustrative routing/appearance controls in [script.js](../website/script.js). All content is present in HTML; JavaScript only enhances it. The System / Light / Dark choice is stored in a website-specific browser preference and tolerates blocked storage.

Six assets in `website/assets/` are byte-for-byte copies of the current [brand masters](brand/BRAND_GUIDE.md): the light/dark integrated lockups, dark mark, favicon, semantic token CSS and icon sprite. After a deliberate brand revision, refresh those copies from `brand/logos/`, `brand/tokens/` and `brand/icons/`. The website checker detects drift. The illustration's coal/copper hub is a fixed dark illustration surface with its matching dark logo.

Maintain the finished-product, present-tense voice. Keep lowercase `hearth`, the integrated fireplace-h lockup and the exact tagline. Keep development status in the engineering documentation rather than the marketing page. The laptop illustration uses a shared hinge with the keyboard projecting toward the viewer; its keys and trackpad share the base plane's projection.

## Verification

With the local website running and the repository's Playwright/Chromium dependencies installed:

```powershell
pnpm check:website
uv run python scripts/check_docs.py
```

The website check covers both appearances at 320, 390, 768, 1024 and 1440 px, images and requests, all routing choices, keyboard activation, navigation targets, appearance persistence and system updates, blocked browser storage, 200% text enlargement, JavaScript-disabled reading, and brand asset equality. It records screenshots and [results](../evidence/website/2026-09-13/validation.json). It makes no inference calls and does not qualify any product release gate. Screenshot inspection complements these checks; a full assistive-technology audit remains outside this website verification.
