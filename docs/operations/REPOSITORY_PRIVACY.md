# Public repository privacy

Public source, documentation, fixtures and evidence use generic machine roles and illustrative values. `hearth.example.invalid` is a non-operational example hostname; `10.20.30.0/24` is a synthetic private-network fixture range. Neither identifies a deployment. Never run live tests against example values.

Keep actual hostnames, addresses, SSH accounts, device inventories, private certificate material, personal paths and raw diagnostics in ignored `.hearth/` files or private environment configuration. Do not commit secrets, user content, account recovery material or identifying screenshots. Preserve operator-authorized runtime targets privately; source edits do not authorize starting a new farm.

## Evidence

Record new live test output under `.hearth/test-results/` first. Publish only a reviewed summary with test outcomes, versions needed to interpret compatibility, and explicit fixture/qualification limits. Inspect images visually and with OCR before publishing; text searches cannot inspect screenshot pixels. Remove an identifying screenshot rather than retouching it and presenting it as original evidence.

Historical evidence sanitized during the privacy sweep carries a `privacy_note` when structured records changed. Placeholder addresses and role labels in such records are redactions, not a claim that tests ran against those examples. Product requirements, public upstream identifiers and synthetic test data are retained.

Two original design documents contained personal equipment references. The owner's whole-repository sanitization request authorizes the narrowly recorded exceptions in [baseline redactions](../../evidence/privacy/2026-09-29/baseline-redactions.json). The documentation checker verifies exact original or approved sanitized hashes for all 119 baseline files; it does not silently relax snapshot integrity.

## History and publication

Removing a value from the latest files does not remove earlier Git objects. A publication cleanup must review reachable history, commit messages and author metadata as well as current files, and replace or remove identifying media across all affected branches and tags. Keep any original backup private and outside publication paths.

After an authorized history rewrite, collaborators must use a fresh clone or carefully reset to the rewritten branch. Merging an old branch can restore removed data. GitHub pull-request refs, cached commit pages, forks, clones and downloaded artifacts may retain old copies independently of branch updates; inspect them before changing visibility and contact GitHub Support when cached sensitive data needs removal. Never publish the private cleanup backup.

Document and source checks do not prove live inference, hardware performance or release readiness.
