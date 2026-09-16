# Shared tools and client connections

Implemented 14 September 2026 with migration `0020`. hearth now owns a shared MCP gateway and serves a capability-based Chat Completions API. Register upstream tools once in Administration. Private chat and external MCP clients use the same catalog, credentials, approval decisions and invocation receipts.

## Try it on the active VM head

1. Open [Administration, Providers](https://10.20.30.10:8443/#providers). On the resident model you want to use, select **Verify tool calling**. The probe requires an actual native function call and a second reply that consumes its result. Plain chat verification does not enable tools.
2. Open [Administration, Shared tools](https://10.20.30.10:8443/#tools). Register an existing Streamable HTTP MCP endpoint, including its path. The bundled reference service is `http://reference-tools:8096/mcp`. Name it `hearth reference tools`, leave credentials optional, accept HTTP for this internal connection and confirm the local-service declaration.
3. Select **Register and discover**, then review `calculate` and `current_time`. Approve them as **Read only**, choose the intended capabilities, and choose owner-only or all members. Newly discovered or changed schemas are disabled until reviewed.
4. In private chat, select a capability assigned to the verified target and ask: “Use the shared calculator to multiply 137 by 29.” A tool-capable model can discover the operation, inspect its schema, execute it and consume the returned result. Its reply retains the actual model identity; tool activity appears alongside the reply.
5. Open [Workspace, Client connections](https://10.20.30.10/#clients), create a named key with the required capability scopes, and save the key when shown. Enable tool access if the client uses its own functions or hearth MCP.

| Client setting | Active VM value |
|---|---|
| API base URL | `https://10.20.30.10/v1` |
| Protocol | Chat Completions |
| Credential | The user's hearth API key, sent as `Authorization: Bearer ...` |
| Automatic model | `auto` |
| Coding model | `code.implement` |
| Shared MCP endpoint | `https://10.20.30.10/mcp`, Streamable HTTP, same Bearer key |

The active [ESX head](../operations/ESX_HEAD.md) binds its public edge to `0.0.0.0`; use the saved VM address for HTTPS, clients and sign-in. The retired laptop appliance's loopback URLs do not reach this farm. Existing-farm migration and the signed installer remain open. Trust the head's CA in each client runtime; browser trust alone may not configure Python or Node trust. Continue supports `requestOptions.caBundlePath`; Node clients can use a correctly supplied `NODE_EXTRA_CA_CERTS` file. Keep certificate verification enabled.

## Three tools, regardless of catalog size

| Manifest tool | Arguments and behavior |
|---|---|
| `list_tools` | Optional `query` and `offset`; returns up to 40 authorized names, short descriptions, server names and `next_offset` |
| `describe_tool` | `name`; returns the approved input/output schemas, full description, revision, action type, approval requirement and a fresh `invocation_id` |
| `run_tool` | `name`, `arguments`, `invocation_id`; validates and executes the selected operation or returns its existing/pending receipt |

The manifest never expands to include every upstream tool. Names include the registered server identity, so two servers can expose an operation with the same name. New registrations are discoverable without configuring every model harness. Only approved tools allowed for the caller and capability are listed.

The gateway runs in the head's user API process. Upstream tools execute on their own registered services. Its dedicated infrastructure entry links to **Shared tools**; it is not advertised as a text-generating model. The bundled reference service runs in a separate read-only container on an internal network, with no host ports, credentials, user storage or internet route. It provides arithmetic and UTC time as a small test target.

The implementation pins the official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) to `2.2.0` and uses its [Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports). It accepts a Bearer API key rather than implementing MCP OAuth discovery in this milestone.

## Credentials, approvals and interrupted work

The registry has farm scope. Credentials and invocation arguments/results have forced PostgreSQL owner isolation. An administrator's upstream credential is used only for that administrator; other members supply their own under **Workspace, Tools**. Changing a connection invalidates schema approval and every credential's connection binding. Existing member secrets cannot be silently forwarded to a replacement endpoint.

The administrator approves a schema, allowed capabilities, audience and action type. Read-only operations use that standing approval. Write operations require a browser **Approve once** decision over their exact displayed arguments. A model, API key or upstream result cannot approve its own action. The server's own “read only” annotation is descriptive; it does not set hearth policy.

`describe_tool` supplies an invocation ID to reuse for that exact action. An ID is bound to its arguments, tool/server revisions and capability. Completed, failed or uncertain invocations are not automatically repeated. A timeout after dispatch is recorded as uncertain. This prevents hearth from replaying the same ID; it cannot make arbitrary external side effects transactional, or deduplicate a caller deliberately generating a new ID.

Private chat releases the model's resource slot during tool work and human approval. It rechecks authorization, cancellation, memory revisions and target state before resuming the same resident target. Stop/steer prevents subsequent tool dispatch and model continuation. It cannot undo an already dispatched external action. A worker crash leaves a durable receipt; generic restart reconciliation and durable resumption of the entire tool conversation remain unfinished. Private-chat limits are eight model rounds, sixteen facade calls and fifteen minutes per tool turn.

Connections retain private-address checks, DNS pinning, verified HTTPS or explicit per-connection LAN HTTP acceptance, no redirects, bounded schemas/results and no environment proxy inheritance. Acyclic schema-local references are normalized; recursive/external references and regular-expression schemas are rejected in this first profile. The local-only declaration describes operator intent, not an attestation of an arbitrary external server's egress policy. Tools with cloud dependencies are outside this milestone.

## Client API and resident routing

`GET /v1/models` returns ready text capability aliases permitted by the key, plus `auto` when at least one is available. The supported aliases are `chat.general`, `reason.plan`, `code.explain`, `code.implement`, `write.compose`, `text.summarize` and `data.extract`. Unready capabilities are omitted. Actual provider model IDs stay behind those aliases.

`POST /v1/chat/completions` supports text messages, leading system/developer messages, streaming and non-streaming responses, native function calls and matching tool-result messages. Supported generation settings include token caps, temperature, top-p, stop strings, seed, penalties, `reasoning_effort` and text/JSON-object response formats. Reasoning effort accepts `none`, `minimal`, `low`, `medium`, `high`, `xhigh` and `max`; the selected model server must support the supplied value. Requests are limited to 1 MiB, 1,000 messages, 64 declared tools and sixteen function calls per model response. Unknown fields and unsupported formats fail explicitly. This is a documented subset, not full provider API parity.

`auto` uses hearth's existing deterministic intent router; an explicit alias keeps the request within that capability. Both honor eligible targets, verified features and shared hardware admission. Supplying functions requires a target that passed tool calling. There is no automatic model loading or swapping. `X-Hearth-Capability`, `X-Hearth-Model` and `X-Hearth-Run-ID` identify the chosen route; the response's `model` remains the requested alias. [NVIDIA NeMo Switchyard](https://github.com/NVIDIA-NeMo/Switchyard) remains the planned routing/model-selection integration; this milestone does not claim the live router calls it.

External harnesses send their own function schemas and execute returned calls on their local machines. hearth never executes those client functions. Caller-owned schemas may include regular expressions, which pass through as model guidance. The caller must validate arguments against its schema and authorize execution. hearth checks declared function names, complete object-shaped JSON arguments and size/count limits, but never evaluates those caller regexes against arguments. Head-executed shared tools retain their existing full argument validation and no-regex restriction. External/recursive schema references remain rejected on both paths. Add the MCP endpoint separately in the harness to include the three shared gateway tools alongside its local tools. Client conversations are not automatically imported into private chat history or memory. Keys are shown once, stored as hashes, scoped, expiring and revocable; active requests recheck their authority. Keys confer no administrative access.

## Client configuration examples

These settings follow the clients' current documentation. The live protocol and model tests are recorded separately; Hermes, OpenClaw and Continue themselves have not yet been exercised end to end against this build. Set context limits to the capacity of every target eligible for the selected capability.

For Continue, add a model to its private `config.yaml`, using a secret from its supported secret configuration. Explicit `tool_use` enables Agent mode for the capability alias. This example uses the [Continue configuration reference](https://docs.continue.dev/reference):

```yaml
name: hearth coding
version: 1.0.0
schema: v1
models:
  - name: hearth coding
    provider: openai
    apiBase: https://10.20.30.10/v1
    apiKey: ${{ secrets.HEARTH_API_KEY }}
    model: code.implement
    roles: [chat, edit, apply]
    capabilities: [tool_use]
    defaultCompletionOptions:
      maxTokens: 8192
```

For OpenClaw, merge a custom `hearth` provider into the existing config and choose `hearth/auto` or `hearth/code.implement`. Use its Chat Completions adapter as specified in [custom providers](https://docs.openclaw.ai/gateway/config-tools/custom-providers):

```json
{
  "models": {
    "providers": {
      "hearth": {
        "baseUrl": "https://10.20.30.10/v1",
        "apiKey": "${HEARTH_API_KEY}",
        "api": "openai-completions",
        "models": [
          {"id": "auto", "name": "hearth automatic"},
          {"id": "code.implement", "name": "hearth coding"}
        ]
      }
    }
  }
}
```

For Hermes, run `hermes model` and configure a custom compatible endpoint using the same base URL, key and alias. Select Chat Completions when choosing API mode. See [Hermes provider setup](https://hermes-agent.nousresearch.com/docs/integrations/providers) and [model configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models). Its full agent prompts require more context than the small qualification prompts; validate the configured model context before a large repository session.

### Hermes Desktop certificate trust

The inspected Hermes Desktop 0.17.0 installation probes custom endpoints through a Python `httpx.AsyncClient`. Its generic **Could not reach .../v1/models** message also covers certificate validation failures. On this Windows laptop, Python's Windows-backed default SSL context trusted the head, but Hermes's HTTPX/certifi default failed with `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`. This happens before the API key reaches hearth.

For a private CA, supply a CA bundle through `SSL_CERT_FILE` in the selected Hermes profile's `.env`. [HTTPX honors this variable](https://www.python-httpx.org/environment_variables/#ssl_cert_file), including the Desktop onboarding probe. Use the installed Hermes Python environment's existing `certifi` public roots plus the matching public hearth root in the bundle so other HTTPS services keep working. Obtain the hearth root through trusted VM access and verify its fingerprint; do not use an unchecked HTTP download as authority. Preserve existing custom CA settings when extending an already configured client.

Hermes Desktop can have multiple Python backends running at once. Configuring only the named **hearth** profile was insufficient here: that backend loaded its CA and passed its own onboarding probe, while the **default** backend still reproduced the user's exact unreachable error. Check every backend involved in setup, not just a separately launched Python test.

Both the laptop's default and **hearth** profile `.env` files now point `SSL_CERT_FILE` at `certificates/hearth-ca-bundle.pem` under the main Hermes home directory. The bundle is independent of either profile's lifetime. The changes were applied through each running backend's authenticated environment-setting API, so both processes picked them up without another restart. Both environment files were backed up first; model settings, API credentials and system-wide environment were preserved. For manual file edits on a new installation, fully quit and reopen Hermes to reload its environment, then select **Local / custom endpoint**, enter `https://10.20.30.10/v1` and the existing hearth key. Do not remove `/v1` or disable TLS verification.

[Initial transport evidence](../../evidence/client-api/2026-09-15/hermes-trust.json) records verified TLS from a separate Python process: `/health/browser` returns 200 and `/v1/models` without a key correctly returns 401. The [running-backend follow-up](../../evidence/client-api/2026-09-15/hermes-desktop-backends.json) verifies the actual Desktop onboarding and custom-endpoint probes in both processes: the network connection succeeds and the stricter probe correctly rejects a missing key.

The user then confirmed **Connected successfully**. [Authenticated discovery](../../evidence/client-api/2026-09-15/hermes-connected.json) passes through both actual Desktop backends and directly against the VM: the saved key receives HTTP 200 with `auto`, `chat.general` and `code.implement`. Hermes saved the connection in its **default** profile with `auto` selected. The separately named `hearth` profile's model assignment was not changed. A complete agent conversation, local tool use and shared MCP round trip remain unqualified; connection success alone does not close that acceptance work.

Start a client test by asking for a short reply, then a local file read in a disposable project, then a shared calculator call through MCP. Inspect the actual route header and local tool approval. Changing the capability's target in hearth should not require changing the client model alias.

### Hermes chat and tool compatibility

The subsequent real Desktop chat attempt exposed issues beyond discovery. The saved API key remained valid. In the inspected Custom Endpoints editor, **Save** with a blank key preserves the saved credential, but **Test** sends no key when the input is blank and does not resolve the saved `key_env`. That produces a misleading key rejection. Re-enter the existing key when using that Test button; a replacement key is unnecessary. A literal `${HERMES_CUSTOM_HEARTH_API_KEY}` label is a credential reference, not evidence that the secret is missing.

Provider definitions are profile-scoped. This installation's endpoint is saved under **default**; the separate profile named **hearth** has its own configuration. An “Unknown provider” model-switch error occurs in Hermes before a request reaches hearth. The current default profile passes an actual gateway model switch to `hearth` / `auto`; changing another profile's settings or merely listing models does not establish this.

The main Hermes request carries `reasoning_effort` and 37 native tool definitions, including regex constraints. The client API now accepts that bounded request shape. model-host's resident Qwen passes the native function-call/result probe and is qualified for tools. A short authenticated client request returns a real reply, and a separate client-owned function round trip reads a synthetic local file and consumes its contents through the VM. These checks use the existing key and preserve TLS validation.

Full Hermes inference is still blocked by loaded context capacity: LM Studio reports **28,074 prompt tokens against an 8,192-token context** for the captured request. Set the loaded model's context to at least 32,768, preferably 65,536 if the machine can accommodate it, then retest; reduce Hermes's prompt/tools if a larger context cannot fit. Allow room for replies and growing history. hearth does not automatically reload or swap the model. A Hermes context estimate alone does not increase LM Studio's loaded context.

The transport now recognizes LM Studio's explicit pre-generation context rejection inside SSE, returns safe token counts and a `context_length_exceeded` error, releases the request's pool and preserves provider qualification. Non-streaming requests receive HTTP 400; streams carry the same error code and status metadata without a success terminator. Unknown failures or errors after partial output keep their conservative uncertain-execution handling. Provider text and request contents are not echoed into these errors.

[Compatibility evidence](../../evidence/client-api/2026-09-15/hermes-compatibility.json) separates the working small client round trip from the pending full Hermes session. Hermes's auxiliary title generator also requests structured JSON-schema output, which this API subset does not yet support; its title warning is separate from key authentication and the main turn. Complete Hermes local-tool and shared-MCP acceptance remains open.

## Validation and remaining work

[Validation](../../evidence/tools/2026-09-14/validation.json) distinguishes fixture tests, real network MCP, actual resident LAN Qwen and deployed services. The Qwen test performs a client-owned function round trip and a private-chat `list_tools` → `describe_tool` → `run_tool` sequence returning 42 from an actual MCP server. Its loaded model set remains unchanged.

Still open: stdio launchers and signed managed tool packages, per-task filesystem/shell sandboxes, remote toolbox placement/enrollment, OAuth-based MCP authorization, shared-channel tool policy, general specialist delegation, complete crash recovery, and external harness qualification. Responses, embeddings, legacy completions, image/audio APIs and structured-output JSON-schema formats are not provided by this first client endpoint. Existing native hearth media workflows continue independently. No full P5/P6 exit or release gate is claimed.
