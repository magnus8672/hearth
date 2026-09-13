# P3: secure NAS library and model staging

Dependency: P2. Outcome: an approved node retrieves exactly its assigned model artifacts from the NAS without receiving NAS credentials.

## Build

1. Implement the storage gateway, dedicated read-only share connector, encrypted transport validation, and registered-mount path. Add the optional fixed-operation privileged helper behind a separate boundary.
2. Build the NAS wizard and quarantined model catalog with manifest validation, source/license metadata, file digests and explicit approval.
3. Sign approved immutable manifests. Implement assignment-scoped mTLS downloads, ranges, expiry/revocation checks, worker partial staging, hash verification and atomic cache promotion.
4. Add cache quotas, pin-aware eviction, disk-space checks, global transfer throttling, download progress, and resumed transfers.
5. Implement model/runtime dependency resolution and compatibility filtering; load actions remain disabled until P4 probes exist.
6. Add approved signed service recipes, immutable runtime package blobs, typed configuration schemas, dependency deduplication, platform matching and central secret references. NodePlan application automatically stages and prepares the selected runtime environment; the member operator never installs Python/Docker or enters NAS details manually. Follow [11](../11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md).
7. Supply a head-local library using the same quarantine, signature/hash, model/license approval and scoped-transfer interface. Approved imports/downloads permit the first local provider before NAS connection. Later NAS migration preserves immutable artifact identity and verified worker caches.

## Prove

E05, E18 and S07. Use a real secure SMB test share and then the intended NAS when supplied. Interrupt a transfer, corrupt a byte, replace a file under the same path, revoke the node mid-download, attempt traversal/symlink escape, and exhaust cache space. Verify the worker has no NAS password in files, environment, logs, or inventory.

An unassigned approved node cannot download arbitrary approved artifacts. An assigned model's dependency set is complete and equally checked. Unsafe formats/custom executable code cannot bypass quarantine through a weight manifest.

C07 validates package tampering, unapproved entrypoints/URLs, recipe traversal and privilege requests. A fake missing Python dependency becomes a visible package/provisioning failure, not a request to configure the member by hand.

## Exit gate

NAS setup and verified resumable delivery pass; all incomplete/incompatible states are visible. If credentials are missing, complete fixture-backed work and list the real NAS gate as blocked.

A verified local library plus secure fixture-backed NAS contract permits independent P4 first-provider/admin-agent work to proceed while actual NAS access is externally blocked. The real NAS release gate remains required and unverified; do not make it a user-onboarding prerequisite.

Next: [P4](P4-LOCAL-INFERENCE.md).
