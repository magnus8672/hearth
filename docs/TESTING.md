# Testing the active hearth farm

Updated 18 September 2026. Use the existing ESXi head at `10.20.30.10`; the workstation's old head and QEMU appliance remain retired. [Current state](implementation/CURRENT_STATE.md) distinguishes implemented features, saved assignments and observed readiness.

## Access and data boundaries

Use [Welcome](http://hearth.example.invalid), [Workspace](https://hearth.example.invalid) and [Administration](https://hearth.example.invalid:8443). SSH maintenance uses `operator@10.20.30.10`, `/opt/hearth`, and `operator@10.20.30.20` for media-worker.

Preserve accounts, MFA, certificates, provider configuration and personal content. Use synthetic content for manual checks and isolated VM storage for automated fixtures. Never run reset/first-Owner fixtures against the live farm, start retired local services or create another farm. Read [development verification](DEVELOPMENT.md) before using old test scripts.

These are procedures, not claims that the documentation refresh reran them. Use accounts with the required grants. Probes and generation perform real work; inspect the pool and selected service first.

## Accounts, SSO and private content

New registration completes password, authenticator and recovery-code enrollment, then reaches a pending workspace with zero permissions. **People** grants access explicitly. **Check access** re-enters sign-in and can reuse MFA SSO. Access changes invalidate old sessions, API keys and execution authority. Test revocation with synthetic accounts; the editor protects the acting account and Owners.

Switching applications should reuse MFA while preserving separate BFF sessions and permissions. Use separate browser profiles for different people. See [approval](implementation/ACCOUNT_APPROVAL.md) and [SSO](implementation/SINGLE_SIGN_ON.md).

Private drafts save without inference. Check persistence and stale edits in two tabs. Memory supports editable notes, source-linked recall, corrections, exclusion, export and reviewed Markdown import. Check a synthetic preference in a fresh chat, correct it and ask again. Continuous Obsidian sync and complete historical deletion remain unfinished.

## Text and vision

Qwen on model-host serves General chat and Coding. Other text profiles currently lack dedicated bindings. Automatic intent routing can use general chat for an unassigned specialist; explicit selection requires an eligible route. Test streaming, refresh, model labels, Enter/Shift+Enter, side notes, thinking, stop and steer.

Text stop prevents publication while the upstream request drains. Do not release a busy/unknown pool just because the browser stopped receiving output. Qualification no longer expires hourly; configuration changes and actual provider failures invalidate it. Startup connection checks are read-only.

Vision is assigned to Qwen but lacks saved pixel-probe qualification in the current snapshot. After an administrator's **Verify vision** probe succeeds, test private image upload/paste/drop, follow-up context and isolation. See [vision](implementation/VISION_AND_CONCURRENT_FARM.md).

## Images and channels

Fooocus on media-worker serves images. Gallery controls include shapes, styles, seed, guidance, sharpness, 20/30/40/60 passes and native/2K/4K output. Larger output is AI upscaling. With synthetic images check progress, cancellation, dimensions, reload, **Use settings**, download and deletion.

Chat supports direct/contextual images and batches of up to four. Variations use descriptions rather than editing original pixels. Joined channels require a new human `@hearth` mention for inference and use channel-only context. Channel images remain shared history. Private gallery deletion removes head-side PNG copies and leaves a chat placeholder; provider files and backups have separate retention.

## Worker queue and 3D

media-worker has **two** approved services, Fooocus and TRELLIS, sharing `media-worker GPU`. Explicit shared mode selects a gallery job's service after the previous process/cgroup releases. The last service stays selected between jobs. Qwen uses the independent `text-pool` pool.

When idle and without interrupting another user, pause the queue, submit synthetic gallery jobs, then resume. Check one active GPU job and waiting-job cancellation. Restore the prior pause/policy state afterward. Only private image/geometry galleries have this durable fair queue; other capabilities retain their existing admission/busy behavior.

In **3D models**, upload a still image or use **Make a model** on a gallery/chat/channel image. Handoff previews a reference copy without changing the original or starting inference. Submit Standard (512) or Detailed (1024), then check preview, GLB download and cancellation. A channel reference produces a private model. Delete only the synthetic result. Independent editor import, broad quality, chat-to-3D and sustained multi-user mixed-load qualification remain open. See [workers](implementation/MANAGED_WORKERS.md) and [geometry](implementation/LOCAL_GEOMETRY.md).

## Audio and clients

Speech/transcription are implemented but have no registered providers here. The [audio installer](operations/AUDIO_VM_SETUP.md) targets Ubuntu 24.04/Python 3.12; adaptation for the head's Ubuntu 26.04 host is separate work. After installation, registration and verification, test saved Read aloud WAVs and reviewed English microphone/PCM-WAV drafts. Transcription never automatically sends a chat turn.

External clients use `https://hearth.example.invalid/v1`, scoped keys and ready aliases such as `auto` or `code.implement`. MCP is `https://hearth.example.invalid/mcp`. Keep TLS validation enabled. Loaded context is currently [redacted capacity] tokens, superseding the historical Hermes 8,192-token observation. Full Hermes/local-tool/shared-MCP acceptance remains open. See [client integrations](implementation/SHARED_TOOLS_AND_CLIENT_API.md).

## Evidence

The [ledger](implementation/BUILD_STATUS.md) links exact recorded checks. The documentation review checked readiness and metadata, not these workflows. All 61 release gates remain open. [Old localhost procedures](archive/status-2026-09-18/TESTING_PRE_REFRESH.md) are historical evidence only.
