# hearth documentation

Start with [what works and what is missing](implementation/DESIGN_COVERAGE.md). The audit compares the complete design package with the current source and recorded validation as of 13 September 2026. Thirteen of fourteen capability profiles have executable implementations; none of the 61 full release gates is closed.

The active head and runtime test target is **10.20.30.10**. Use [VM operations](operations/ESX_HEAD.md) and [testing](TESTING.md). The laptop head and QEMU appliance are retired; their data remains preserved.

| Need | Document |
|---|---|
| Preview or serve the project website | [Static website](WEBSITE.md) |
| Review product coverage and remaining work | [Design coverage table](implementation/DESIGN_COVERAGE.md) |
| Test the active VM build | [Testing](TESTING.md) |
| Connect model servers on other machines | [LAN provider testing](implementation/LAN_PROVIDER_TESTING.md) |
| Add multiple servers and preserve resident models | [Multiple providers and residency](implementation/MULTI_PROVIDER_RESIDENCY.md) |
| Connect a trusted LAN service without certificates | [External HTTP provider approval](implementation/EXTERNAL_HTTP_PROVIDERS.md) |
| Watch model thinking and steer early | [Thinking previews](implementation/THINKING_PREVIEW.md) |
| Understand reply limits, continuation and model labels | [Reply streaming and identity](implementation/REPLY_STREAMING_AND_IDENTITY.md) |
| Understand images and concurrent model dispatch | [Vision and concurrent farm](implementation/VISION_AND_CONCURRENT_FARM.md) |
| Remove generated pictures from the gallery and private chat | [Image deletion](implementation/IMAGE_DELETION.md) |
| Record or upload speech and review its transcript | [Microphone and transcription](implementation/TRANSCRIPTION.md) |
| Edit memory and use Obsidian vaults | [Private memory](implementation/PRIVATE_MEMORY.md) |
| Register shared MCP tools and connect a local agent/editor | [Shared tools and client API](implementation/SHARED_TOOLS_AND_CLIENT_API.md) |
| Play and save spoken replies | [Read aloud](implementation/READ_ALOUD.md) |
| Install speech/transcription in an Ubuntu VM | [Audio VM setup](operations/AUDIO_VM_SETUP.md) |
| Run the head on a LAN or ESX VM | [Head VM setup](operations/HEAD_VM_SETUP.md) |
| Change an existing head's URL and rebuild certificates | [Head address settings](implementation/HEAD_ADDRESS_SETTINGS.md) |
| Copy just the fresh-farm deployment package | [VM ZIP setup](operations/VM_PACKAGE.md) |
| Maintain the user's deployed VM at 10.20.30.10 | [Current ESX head](operations/ESX_HEAD.md) |
| Understand lasting verification and startup checks | [Provider lifecycle](implementation/PROVIDER_LIFECYCLE.md) |
| Build, check or recover the development stack | [Development guide](DEVELOPMENT.md) |
| Review Git contents and artifact exclusions | [Git repository](operations/GIT_REPOSITORY.md) |
| Find the latest implementation evidence | [Build status](implementation/BUILD_STATUS.md) |
| Check formal release acceptance | [Gate ledger](implementation/RELEASE_GATES.md) and [machine-readable ledger](implementation/release-gates.json) |
| Understand a design decision | [Architecture decision records](adr/) |
| Apply the current logo, name and palette | [Brand guide](brand/BRAND_GUIDE.md), [identity 1.2](implementation/BRAND_REVISION_1_2.md) |
| Maintain branded sign-in | [Identity theme](operations/IDENTITY.md) |
| Switch between workspace and administration with one sign-in | [Single sign-on](implementation/SINGLE_SIGN_ON.md) |
| Prepare or run the CPU transcription provider | [Transcription runtime](runtimes/TRANSCRIPTION_PROVIDER.md) |
| Run or extend the experimental CPU speech provider | [Speech runtime](runtimes/SPEECH_PROVIDER.md) |
| Run or extend the experimental image provider | [Image runtime](runtimes/IMAGE_PROVIDER.md) |
| Register and maintain the dedicated Fooocus machine | [Fooocus on media-worker](operations/FOOOCUS_PROVIDER.md) |
| Work on the repository as a coding agent | [Repository guidance](AGENT_GUIDANCE.md) |
| Find every reviewed document and its purpose | [Document inventory](DOCUMENT_INVENTORY.md) |

## Specifications and historical records

[The original design package](plan/README.md) contains the twelve engineering specifications, ten phase plans, build handoff, source references, brand v1.0 and fourteen rendered diagrams. Its 119 files remain byte-for-byte unchanged. Its old status statements describe the planning date, not today's application.

Current decisions extend that baseline. [ADR 0006](adr/0006-managed-and-external-providers.md) adds existing services alongside managed runtimes. [Brand revision 1.2](implementation/BRAND_REVISION_1_2.md) requires lowercase `hearth` and uses the fireplace as the first h in the combined wordmark. The [hybrid inference video review](plan/VIDEO-REVIEW-IH8XmxiwliQ.md) is an experiment proposal; required local 3D remains in the binding release scope.

[The preparation report](implementation/BUILD_PREPARATION.md) and dated feature reports retain milestone context. Use the coverage audit and current build status to resolve an older report's superseded limits.

Duplicate documents formerly at the repository root, `phases/` and `diagrams/` have moved into the [root-package archive](archive/root-package/README.md). New work should link to the canonical `plan/` copy. The [relocation record](../evidence/documentation/2026-09-13/reorganization.json) lists every move and original digest.

All substantive repository guides now live under `docs/`. Root README and AGENTS files are discovery pointers. Runtime manifests, executable examples, brand SVG/CSS/PNG sources, the [interactive brand gallery](../brand/index.html), generated API contracts and test evidence stay beside their code or assets. Shell examples in the current guides run from the repository root unless explicitly stated otherwise.
