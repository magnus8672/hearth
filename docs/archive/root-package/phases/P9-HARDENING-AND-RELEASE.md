# P9: hardening, packaging, recovery, and release

Dependency: P8 and all unresolved required earlier gates. Outcome: an installable, evidence-backed home farm.

## Build

1. Finish signed Create/Join Hearth installers, managed control-appliance and native supervisor packages, central recipe/NodePlan updates, service lifecycle, diagnostics and redacted support bundles. No manual Docker/VM/Python setup or local member configuration is allowed in the clean-install acceptance path.
2. Complete monitoring, audit export, CA/key rotation, encrypted backup/restore, deletion-ledger restoration and migration recovery.
3. Exercise role and per-user quotas under reference load; implement fair scheduling, bounded spools and background indexing priorities.
4. Finish accessible interface polish, responsive layouts and all offline/error states using real status sources.
5. Publish tested hardware/runtime matrix, capability quality reports, operational walkthrough, release notes, SBOM and evidence index.

## Prove

Run all E01-E22, S01-S18, C01-C09 and A01-A12 checks from [validation](../../../plan/09-VALIDATION-AND-RELEASE.md). Conduct independent clean first-node and member installations across the target host matrix, verify first-provider local-head/member/OpenAI choices, use the admin agent for real authorized setup, pair two physical workers using only head address/port plus proof approval in Hearth, load NAS models, create two users, execute a collaborative request, disconnect a laptop, and restore the control head from backup.

Verify NVIDIA and AMD text inference with measured memory. Test native worker packaging on every advertised OS. Explicitly list untested old Macs/GPUs without claiming support. Recheck provider configuration against current official documentation and settle the actual authorized OpenAI test usage.

Verify user logout/reboot, centrally queued offline edits, automatic modality-specific dependency installation, safe package rollback, and fenced Move/Restore Hearth. A failed join must never create a competing head. The Windows/Linux/macOS setup promise needs real evidence per advertised OS/architecture; a Linux-only demonstration does not complete it.

Review dependency and secret scans. No unauthenticated administration, private-content leakage, credential exposure or local-only egress failure can remain open at release.

An explanatory chatbot without working management actions does not satisfy the admin-agent gate. Verify provider-loss recovery through the manual UI, single-provider replacement/removal, malicious diagnostic/model text, cross-admin history isolation and bounded unattended setup operations. A real OpenAI-first test still requires the user's actual authorized key/budget; do not fabricate evidence when absent.

## Exit gate

All required gates have pass evidence or the release scope is explicitly narrowed without pretending the original full objective is complete. Installation and recovery steps are reproducible. The final report states implemented behavior, verification, supported hosts, actual cloud-test cost, and remaining limitations. Update BUILD_STATUS.md with the released revision and evidence pointers.
