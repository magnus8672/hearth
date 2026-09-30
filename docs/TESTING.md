# Testing hearth

Updated 29 September 2026. Use the deployment explicitly authorized for testing. Hostnames, SSH accounts, hardware and provider endpoints are private configuration, not repository defaults. The [capability overview](implementation/CURRENT_STATE.md) distinguishes implementation from deployment readiness.

## Targets and data boundaries

Obtain workspace, administration, identity and welcome origins from your deployment configuration. Keep credentials and target variables in ignored `.hearth/` files or your shell environment. Read [development verification](DEVELOPMENT.md) before running older scripts; some assume disposable storage or start local services.

Preserve accounts, MFA, certificates, provider configuration and personal content. Use synthetic content and isolated storage on the authorized runtime host. Never run database-reset or first-Owner fixtures against production, start unrequested local services, or create another farm without operator authorization.

These are procedures, not claims that a documentation update reran them. Probes and generation perform real work: inspect occupancy and the selected service first. Use accounts with the required grants.

## Configurable browser and inference targets

The VM browser configuration requires `HEARTH_BROWSER_ORIGIN`. Related tests use `HEARTH_ADMIN_BROWSER_ORIGIN`, `HEARTH_IDENTITY_BROWSER_ORIGIN` and `HEARTH_WELCOME_BROWSER_ORIGIN`; omitted related origins use the same hostname with documented default ports. Override them when using custom ports. This configuration does not start servers.

```powershell
# Supply actual values privately before running on an authorized deployment.
pnpm exec playwright test --config playwright.vm.config.ts
```

Opt-in live inference tests keep their existing `HEARTH_LIVE_*` flags and additionally require `HEARTH_TEST_PROVIDER_URL` and `HEARTH_TEST_PROVIDER_MODEL`. Two-host concurrency also requires `HEARTH_TEST_SECOND_PROVIDER_URL` and `HEARTH_TEST_SECOND_PROVIDER_MODEL`. Missing targets fail explicitly; no household endpoint is built in. Use already resident compatible models. Output containing addresses or loaded-instance identifiers belongs under ignored `.hearth/`, not tracked evidence.

## Accounts, SSO and private content

New registration completes password, authenticator and recovery-code enrollment, then reaches a pending workspace with zero permissions. **People** grants access explicitly. **Check access** re-enters sign-in and can reuse MFA SSO. Access changes invalidate old sessions, API keys and execution authority. Test revocation with synthetic accounts; the editor protects the acting account and Owners.

Switching applications should reuse MFA while preserving separate BFF sessions and permissions. Use separate browser profiles for different people. See [approval](implementation/ACCOUNT_APPROVAL.md) and [SSO](implementation/SINGLE_SIGN_ON.md).

Private drafts save without inference. Check persistence and stale edits in two tabs. Memory supports editable notes, source-linked recall, corrections, exclusion, export and reviewed Markdown import. Check a synthetic preference in a fresh chat, correct it and ask again. Continuous Obsidian sync and complete historical deletion remain unfinished.

## Text and vision

Assign verified models to the text profiles under test. Automatic routing can use general chat for an unassigned specialist; explicit selection requires an eligible route. Test streaming, refresh, model labels, Enter/Shift+Enter, side notes, thinking, stop and steer.

Text stop prevents publication while the upstream request drains. Do not release a busy/unknown pool just because the browser stopped receiving output. Configuration changes and actual provider failures invalidate qualification. Startup checks are read-only.

After **Verify vision** succeeds, test private image upload/paste/drop, follow-up context and isolation. Advertised Vision support is insufficient without pixel-probe qualification. See [vision](implementation/VISION_AND_CONCURRENT_FARM.md).

## Images and channels

A verified Fooocus provider supplies image jobs. Gallery controls include shapes, styles, seed, guidance, sharpness, 20/30/40/60 passes and native/2K/4K output. Larger output is AI upscaling. With synthetic images check progress, cancellation, dimensions, reload, **Use settings**, download and deletion.

Chat supports direct/contextual images and batches of up to four. Joined channels require a new human `@hearth` mention for inference and use channel-only context. Shared attachments do not automatically send pixels to Vision. Verify that a complete image request can reach an independent media worker while a chat model is busy. Private gallery deletion removes head-side PNG copies and leaves a chat placeholder; provider files and backups have separate retention.

## Worker queue and 3D

For explicit shared-GPU configurations, include every service using that GPU in one approved worker pool. The scheduler selects a job fairly before preparing its backend. The prior process/cgroup must release before another service starts. Independently resourced model hosts use separate pools.

When idle and without interrupting another user, pause the queue, submit synthetic gallery and conversation image jobs, then resume. Check one active job per shared GPU, visible waiting states, cancellation and preservation of the selected backend. Restore prior pause/policy state afterward. Text/audio requests do not yet have this universal queue.

In **3D models**, supply a name and still image, or use **Generate model** on a gallery/chat/channel image. Reference handoff must not start inference by itself. Choose a supported TRELLIS or Hunyuan profile, submit, then check saved settings, preview, screen-relative lighting, GLB/OBJ downloads and cancellation. A channel reference produces a private model. Delete only synthetic results. Broad quality and sustained mixed-load qualification remain open. See [workers](implementation/MANAGED_WORKERS.md) and [geometry](implementation/LOCAL_GEOMETRY.md).

## Audio and clients

Speech/transcription require separately registered compatible providers. The [audio installer](operations/AUDIO_VM_SETUP.md) targets Ubuntu 24.04/Python 3.12; check compatibility before installing on another platform. Test saved Read aloud WAVs and reviewed English microphone/PCM-WAV drafts. Transcription must not automatically send a chat turn.

External clients use your workspace origin plus `/v1`, scoped keys and ready aliases such as `auto` or `code.implement`. MCP uses the same origin plus `/mcp`. Keep TLS validation enabled. Context capacity depends on the selected model and provider configuration. Full external-client acceptance remains open. See [client integrations](implementation/SHARED_TOOLS_AND_CLIENT_API.md).

## Evidence

The [ledger](implementation/BUILD_STATUS.md) links recorded checks. Distinguish browser fixtures, real authenticated sessions and live inference; none substitutes for another. All 61 release gates remain open. Follow [repository privacy](operations/REPOSITORY_PRIVACY.md) before publishing results.
