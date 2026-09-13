# Release gates

The 61 binding gates retain their original meaning in [the validation plan](../../09-VALIDATION-AND-RELEASE.md). None is fully passed. Foundation and local identity checks provide only the partial evidence described below. Current browser and restart records are in [identity evidence](../../evidence/identity/2026-09-12).

| Gate | Scenario | Status | Evidence or remaining work |
|---|---|---|---|
| E01 | First boot and LAN signup | Partial evidence | Local native Owner provisioning and real HTTPS Member signup/MFA pass. LAN setup, signed installer and other-system trust remain pending. |
| E02 | Start a new worker | Not run | Requires later product implementation and end-to-end validation. |
| E03 | Pair and assign coding | Not run | Requires later product implementation and end-to-end validation. |
| E04 | Restart/change DHCP address | Not run | Requires later product implementation and end-to-end validation. |
| E05 | NAS model transfer interruption | Not run | Requires later product implementation and end-to-end validation. |
| E06 | One local chat | Not run | Requires later product implementation and end-to-end validation. |
| E07 | Unassigned job type | Not run | Requires later product implementation and end-to-end validation. |
| E08 | OpenAI fallback | Not run | Requires later product implementation and end-to-end validation. |
| E09 | Local-only workflow | Not run | Requires later product implementation and end-to-end validation. |
| E10 | Shared toolbox | Not run | Requires later product implementation and end-to-end validation. |
| E11 | Specialist consultation | Not run | Requires later product implementation and end-to-end validation. |
| E12 | Cross-session recall | Not run | Requires later product implementation and end-to-end validation. |
| E13 | Superseded preference | Not run | Requires later product implementation and end-to-end validation. |
| E14 | Delete conversation | Not run | Requires later product implementation and end-to-end validation. |
| E15 | Concurrent users | Not run | Requires later product implementation and end-to-end validation. |
| E16 | Worker loss mid-task | Not run | Requires later product implementation and end-to-end validation. |
| E17 | Controller restart | Partial evidence | One normal guest poweroff/start preserved accounts, draft content/revisions and certificates. In-flight task recovery and abrupt controller-loss behavior remain pending. |
| E18 | NAS/internet unavailable | Not run | Requires later product implementation and end-to-end validation. |
| E19 | Media workflow | Not run | Requires later product implementation and end-to-end validation. |
| E20 | Backup restoration | Not run | Requires later product implementation and end-to-end validation. |
| E21 | Install/update/uninstall | Not run | Requires later product implementation and end-to-end validation. |
| E22 | Budget race | Not run | Requires later product implementation and end-to-end validation. |
| S01 | Spoofed discovery hostname/key | Not run | Requires later product implementation and end-to-end validation. |
| S02 | Replay/steal encrypted enrollment grant | Partial evidence | JWE tamper and binding checks only; durable one-use grants/CSR/revocation pending. |
| S03 | Revoked node on existing stream | Not run | Requires later product implementation and end-to-end validation. |
| S04 | User A requests User B IDs or SSE cursor | Partial evidence | Real PostgreSQL forced RLS and two real Members reject guessed Owner draft IDs. SSE cursors and shared-workspace paths remain pending. |
| S05 | Graph search reveals another user's node/count | Not run | Requires later product implementation and end-to-end validation. |
| S06 | Prompt says to use admin tool/cloud | Partial evidence | Locality and grant policy primitives pass; end-to-end prompt/tool paths pending. |
| S07 | NAS path traversal/symlink/corrupt weights | Not run | Requires later product implementation and end-to-end validation. |
| S08 | Uploaded HTML/SVG/script/tool output | Not run | Requires later product implementation and end-to-end validation. |
| S09 | Forged mTLS identity headers | Partial evidence | Spoofed identity headers cannot authenticate; worker mTLS listener pending. |
| S10 | Malicious tool URL / DNS rebinding | Not run | Requires later product implementation and end-to-end validation. |
| S11 | Tool adds schema/requests wider credentials | Not run | Requires later product implementation and end-to-end validation. |
| S12 | Database pool reuses prior identity | Partial evidence | Real pooled PostgreSQL transactions reset personal identity and fail closed without it. Broader shared/index/stream paths remain pending. |
| S13 | Concurrent deletion and index write | Not run | Requires later product implementation and end-to-end validation. |
| S14 | Copied node certificate | Not run | Requires later product implementation and end-to-end validation. |
| S15 | Unknown paid-call outcome/retry | Not run | Requires later product implementation and end-to-end validation. |
| S16 | User promotes self via role API | Partial evidence | Public login provisioning grants only Member; real Members cannot inspect the admin farm. Role-editing APIs and promotion attack acceptance remain pending. |
| S17 | Cloud access through Graphify ambient env | Not run | Requires later product implementation and end-to-end validation. |
| S18 | IPv6 or alternate admin route bypass | Not run | Requires later product implementation and end-to-end validation. |
| C01 | First node creates Hearth | Partial evidence | Local accelerated stack, console-bound Owner setup, MFA and private drafts work. Explicit Windows trust interaction, signed installer and sustained VM reliability remain pending. |
| C02 | Member needs only head address/port | Not run | Requires later product implementation and end-to-end validation. |
| C03 | All normal settings managed centrally | Not run | Requires later product implementation and end-to-end validation. |
| C04 | Correct service for assigned job | Not run | Requires later product implementation and end-to-end validation. |
| C05 | Pairing proof/envelope integrity | Partial evidence | Go/Python JWE interoperability and narrow tamper cases pass; full enrollment lifecycle pending. |
| C06 | Rogue head or anonymous endpoint | Not run | Requires later product implementation and end-to-end validation. |
| C07 | Untrusted provisioning input | Partial evidence | Python signature/digest checks and revision policy pass; native installer and provisioning still pending. |
| C08 | Setup and browser-origin isolation | Partial evidence | Exact-origin BFFs, one-use callback state, PKCE, secure audience-bound cookies, CSRF, local setup proof/Host/Origin checks and copied-session logout rejection pass. Production helper, LAN/IPv6/alternate routes and complete lifecycle matrix remain pending. |
| C09 | Recovery and single control head | Not run | Requires later product implementation and end-to-end validation. |
| A01 | First provider on Hearth itself | Not run | Requires later product implementation and end-to-end validation. |
| A02 | First provider on a member | Not run | Requires later product implementation and end-to-end validation. |
| A03 | OpenAI-first setup | Not run | Requires later product implementation and end-to-end validation. |
| A04 | Missing/broken provider | Not run | Requires later product implementation and end-to-end validation. |
| A05 | Real agentic management | Not run | Requires later product implementation and end-to-end validation. |
| A06 | Role and history isolation | Not run | Requires later product implementation and end-to-end validation. |
| A07 | Secret and cloud boundary | Not run | Requires later product implementation and end-to-end validation. |
| A08 | Prompt injection and fake approval | Partial evidence | Server-normalized plan digests and typed grant checks pass; real agent injection fixtures pending. |
| A09 | Plans and bounded routine grants | Partial evidence | Grant scope, expiry, revocation, hash and current revision checks pass; durable Apply and execution pending. |
| A10 | Idempotent durable operations | Not run | Requires later product implementation and end-to-end validation. |
| A11 | Agent changes its own provider | Not run | Requires later product implementation and end-to-end validation. |
| A12 | Useful setup and growth before optional services | Not run | Requires later product implementation and end-to-end validation. |

A12 is split across text/tool orchestration in P4 and required media, including local 3D, in P8. Neither part substitutes for the other. The full gate remains open.
