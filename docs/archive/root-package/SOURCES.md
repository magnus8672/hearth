# Sources and upstream boundaries

References checked on 12 September 2026. They support the upstream facts below. Hearth-specific workflows, defaults, API contracts, security policies and acceptance targets are proposed design decisions, not features claimed to exist in those upstream projects. Revalidate APIs and pin exact versions during P0.

| Source | What it establishes | Boundary for Hearth |
|---|---|---|
| [NeMo Switchyard repository](https://github.com/NVIDIA-NeMo/Switchyard) | Embeddable model-selection library and gateway integration paths | Does not supply Hearth enrollment, NAS authorization, multi-user memory or agent lifecycle |
| [DNS-SD, RFC 6763](https://www.rfc-editor.org/rfc/rfc6763) | Standard network service discovery records | Discovery metadata is not authenticated node identity |
| [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture) | Host/client/server model and local/remote transports | Hearth still enforces task and user authorization; negotiate supported protocol versions |
| [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | Graph extraction/querying, Obsidian output and configurable inference backends | Semantic passes can call providers; isolate scopes and configure backend explicitly |
| [Obsidian storage](https://help.obsidian.md/Files+and+folders/How+Obsidian+stores+data) | Notes are stored in local Markdown files | Vault storage is not a multi-user transactional security service |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | Local inference engine and several hardware backends | Probe each binary/GPU/model combination; never assume older hardware support |
| [Keycloak OIDC](https://www.keycloak.org/securing-apps/oidc-layers) | OIDC integration and identity endpoints | Application resource RBAC and workspace isolation remain Hearth responsibilities |
| [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) | Row policy support and owner/superuser bypass considerations | Use restricted application roles and tests covering background execution |
| [OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) | Deny-by-default, least privilege and repeated access checks | Enforce at API, tools, retrieval and artifacts, not only visible navigation |
| [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https) | HTTPS management including local deployments | DNS and browser trust still need a setup workflow |
| [step-ca](https://smallstep.com/docs/step-ca/) | Private certificate-authority tooling | Hearth must bind issuance to approved enrollment and enforce immediate revocation |
| [Microsoft SMB security](https://learn.microsoft.com/en-us/windows-server/storage/file-server/smb-security) | SMB encryption and signing/integrity features | Verify actual NAS negotiation; no silent plaintext downgrade |
| [OpenAI Responses migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses) | Responses integration and tool-oriented API usage | Hearth owns durable state and local tool execution |
| [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data) | Retention varies by endpoint, feature and account | `store=false` is not a blanket zero-retention guarantee |
| [OpenAI image tool](https://developers.openai.com/api/docs/guides/tools-image-generation) | Conversational image-generation API pattern | Capability support must be checked for configured models/accounts |
| [Diffusers](https://huggingface.co/docs/diffusers/index) | Image generation pipeline library | Pin each pipeline and model; verify hardware and license |
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) | Local transcription implementation | Validate chosen model and actual host performance |
| [Kokoro ONNX runtime wrapper](https://github.com/thewh1teagle/kokoro-onnx) and [Kokoro model card](https://huggingface.co/hexgrad/Kokoro-82M) | A concrete local speech path | Approve model, voice assets, phonemizer/runtime dependencies and licenses separately |

## What was intentionally not assumed

No fixed “best small model” ranking, GPU specification based on a laptop name, universal Graphify tenancy support, automatic private-CA browser trust, guarantee of cloud zero retention, or guaranteed compatibility across future upstream releases. The implementation learns device capabilities, uses versioned manifests/evaluations, and displays unverified states explicitly.

The design requires no MoE slicing. Specialization comes from selecting and evaluating suitable deployments and surrounding them with the appropriate tools, context and task recipes. Shared-model role caches and hybrid local placement remain measured experiments in the linked video review.

## Revision 1.1 setup references

- [QEMU accelerator matrix](https://www.qemu.org/docs/master/system/introduction.html) and [Windows WHPX](https://www.qemu.org/docs/master/system/whpx.html) establish relevant virtualization backends. Hearth's managed packaging, first-run flow, guest images and supported host releases still need implementation and validation.
- [JWE, RFC 7516](https://www.rfc-editor.org/rfc/rfc7516) defines encrypted authenticated message representation. The proposed one-time proof/enrollment workflow in [11](../../plan/11-INSTALLATION-AND-CENTRAL-MANAGEMENT.md) is Hearth design work, not an upstream ready-made enrollment service.
