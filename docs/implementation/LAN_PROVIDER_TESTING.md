# hearth provider network test

> Addresses, host labels and accounts shown here are illustrative placeholders. Use your own private deployment configuration.

This development build lets one hearth route work among existing model servers. Model applications stay under their owners' control. A provider is an address and model; a capability assignment is an ordered list of those models. A resource group describes one shared GPU. Different capabilities can share a model, and a capability can have several independently hosted choices.

The preferred test topology keeps different specialist models resident on separate machines at the same time, then routes requests to their hosting machines. Give independent GPUs separate resource groups and deliberately group services sharing hardware. Multiple models on one machine are optional. media-worker deliberately shares its GPU between image and geometry services; [multi-server onboarding, residency and concurrent dispatch](DESIGN_COVERAGE.md#same-type-provider-registration-and-resident-models) still need joint qualification. Record loaded models before and after probes and routed work because a compatible endpoint alone does not establish resident-only behavior.

## Build the optional connector packages

Connector ZIPs are generated, ignored artifacts, not downloads included in this source checkout. With Python and the Go toolchain available to [the builder](../../scripts/build_connectors.py), run from the repository root:

```powershell
python scripts/build_connectors.py
```

Outputs are `dist/connectors/hearth-connector-<os>-<architecture>.zip` for `windows-amd64`, `linux-amd64`, `linux-arm64`, `darwin-arm64` and `darwin-amd64`, plus `dist/connectors/manifest.json` with hashes. They are unsigned development packages. Cross-compilation does not qualify execution on every platform. Building does not start a listener or enroll a worker. Existing approved HTTP providers do not need this connector.

## What can run now

See [the dated farm snapshot](CURRENT_STATE.md) for actual assignments. All fourteen bounded profiles are implemented; configuration and feature verification still determine availability.

- Seven text profiles use compatible chat transports. Chat and Coding currently use model-host Qwen. Tool calling requires its separate native call/result probe; text profiles alone do not execute commands or grant filesystem/database access.
- Fooocus on media-worker supplies image jobs. TRELLIS supplies image-to-3D and validated GLBs over a separate protocol. They explicitly share one managed GPU; see [workers](MANAGED_WORKERS.md) and [geometry](LOCAL_GEOMETRY.md).
- Private vision requires a pixel-reading probe. The active Qwen assignment currently lacks that saved feature even though the model advertises vision.
- Speech and English transcription have historical real CPU evidence but no registered providers here. See [audio setup](../operations/AUDIO_VM_SETUP.md).
- Memory indexing/retrieval are built-in private head functions. Semantic knowledge workers remain future work.

## Direct HTTP with an existing service

You can connect LM Studio or another supported server directly without a certificate or connector. On that machine, enable its LAN listening option and allow its actual API port through the firewall for the trusted private network. In hearth Providers, choose **Add server**, enter its private HTTP address such as `http://10.20.30.40:1234`, and check **I’m the administrator and I understand the risks. Allow HTTP for this server.** Give each independent GPU its own resource group, then connect/verify and assign capabilities.

For a server already saved with the old HTTP rejection, use **I understand the risks. Use HTTP** on its card. This saves approval and retries verification. Approval covers all models at that saved address, persists across reloads and can be revoked. The warning covers unencrypted prompts, replies, images and API keys. Moving to another address needs new approval. [Implementation and validation](EXTERNAL_HTTP_PROVIDERS.md) describe the boundaries and the live test against a separate LM Studio machine.

## Optional TLS connector on each model machine

1. Start your existing service. Confirm its exact model identifier and its local API port. Keep it bound to loopback. LM Studio commonly uses `http://127.0.0.1:1234`; use the actual value on your machine.
2. Extract the connector package matching that machine. These are unsigned development binaries. The build manifest includes SHA-256 hashes; signed installation, automatic enrollment and service management are unfinished.
3. Initialize a private connector identity using the machine's private LAN IP or a stable local DNS name. Choose a separate listening port for each model service. Do not copy one connector's keys to another machine.

Windows PowerShell, with the example IP replaced by this model machine's address:

```powershell
$connectorState = Join-Path $env:LOCALAPPDATA 'hearth\connectors\text'
.\hearth-connector.exe --init --dir $connectorState --public-host 192.168.1.40 --listen 192.168.1.40:1240 --upstream http://127.0.0.1:1234
icacls $connectorState /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F"
.\hearth-connector.exe --dir $connectorState
```

Linux or macOS:

```sh
chmod +x ./hearth-connector
./hearth-connector --init --dir "$HOME/.local/share/hearth/connectors/text" --public-host 192.168.1.40 --listen 192.168.1.40:1240 --upstream http://127.0.0.1:1234
./hearth-connector --dir "$HOME/.local/share/hearth/connectors/text"
```

The initialization prints the provider address and public CA fingerprint. It creates `provider-ca.pem`, `server.pem`, `server-key.pem`, `controller.key` and `connector.json` in the private state directory. It refuses to overwrite an existing identity. The CA signing key is discarded. Certificates last one year; use a new identity and update the target trust before expiry or after a hostname change.

If the underlying local service requires a key, add `--upstream-key-file` with the absolute path to its key file during initialization. This is separate from the connector's `controller.key`. For the current hearth image runtime, use its controller key file and local port 1235. Use a separate connector listening port, such as 1241.

The connector opens only the specified listener. It does not change firewall rules or enable a model app's network mode. If the head cannot connect, allow that one connector port from the hearth head's IP in the host firewall. No router port forwarding is needed. With the development QEMU appliance, the model machine normally sees the Windows host's LAN IP as the client. Check the host firewall's observed source address if needed.

The process runs until stopped. On Windows, launch it from your own terminal for this test. Any background launch performed by a helper must use a hidden window. Automatic startup is not installed.

## In hearth Administration

1. Open Providers and choose **Add server** for each machine, including additional servers of the same type. Enter the connector's `https://192.168.1.40:1240/v1` address, actual model ID and provider type. Paste the connector's `controller.key` into the API key field. **Add model to this server** is a separate optional action for another model sharing an existing connection.
2. Expand **Private network certificate**. Paste only `provider-ca.pem`, and compare its SHA-256 fingerprint with the value shown on the model machine. Never paste `server-key.pem`. This trust applies only to that connection; nothing is added to the operating system's trust store.
3. Give the resource group a machine-specific name, such as `Workshop GPU`. Models and image services on the same GPU must use the same group, even if they use different ports. Independent machines should use different groups.
4. For LM Studio, disable Just-in-Time loading and automatic unloading on that server, keep the chosen model loaded, then select **LM Studio · require a loaded instance** and confirm its configuration. Supply the loaded instance identifier. hearth reads `/api/v1/models` before text verification and generation; it stops if that instance is not loaded. Other compatible services may keep **residency unknown**. Use the rebuilt connector packages for this additional read-only endpoint.
5. Confirm the local processing boundary and connect/verify. Verification sends a bounded text request or renders one synthetic image. It does not read private conversations. Successful registration clears the form; add the next machine with its own resource group.
6. Choose a capability under **Give each capability a home**. Add provider choices in order and save. The first verified, idle compatible model receives a new request. Disabled, failed, incompatible and occupied targets are ineligible. Once a request starts, errors and uncertain outcomes never trigger an automatic second generation.

Every capability card opens its assignment and matching connection controls. **Edit connection** changes an existing target's server/model/resource group while preserving assignments. It invalidates prior evidence, so the saved target must pass a new check. Busy or uncertain resource groups cannot be moved. Saved keys are never returned to the browser. A shared address cannot have its credentials or trust silently changed through one of several models.

## Exercise the routes

- Assign planning to one host, writing to another, and coding to a third. Initially all seven text capabilities may point to the current LM Studio model.
- In Private chat, use **Reply with** to force each text specialist. Automatic routing also recognizes direct requests such as “Plan a garden project,” “Write a Python function,” “Summarize this text,” and “Extract the city from this sentence.” This is a conservative English intent matcher; the selector is useful for ambiguous requests.
- The saved turn includes the selected capability, provider/model and configuration revision. Moving a target later does not rewrite its earlier execution identity. The latest route appears beside the model name.
- Join a channel and send `@hearth summarize ...` to exercise specialist routing with channel-only context.
- Ask for an image that requires previous conversation context. This exercises a planning-to-image handoff, including when the two services share a GPU.
- Give a text capability two independent provider choices. While its first resource group is occupied by another hearth request, a new request can use the second. Stop or disconnect an in-progress stream and verify that hearth retains uncertainty instead of duplicating the work elsewhere.
- Successful verification persists without an hourly deadline. The head rechecks qualified connections at startup. After an actual provider failure or configuration change, repair the service and run its capability verification. See [provider lifecycle](PROVIDER_LIFECYCLE.md).

The same-machine Windows/Linux-appliance path and four concurrent loopback HTTP specialists have been tested. A second physical host, firewall behavior on your other systems, and macOS/Linux ARM execution require your LAN test. Cross-compilation alone does not qualify those systems. Loaded-state checks are observations, not atomic reservations; automatic-loading configuration remains operator-declared. See [the implementation and evidence](MULTI_PROVIDER_RESIDENCY.md).

## Connector boundary

The connector accepts authenticated TLS from private addresses, checks the configured Host and rejects browser Origin requests. It forwards only a fixed allowlist of inference operations to one literal loopback IP. No admin API, arbitrary URL, shell, file browsing, provider installation or general proxy is exposed. It strips incoming cookies and controller credentials, replaces the optional local upstream key, bounds request size, rejects redirects and keeps request contents out of logs.

It is an optional external-service bridge, not an enrolled managed worker. The provider operator can still see requests and other applications can still use its GPU. Stronger worker identity, managed lifecycle, exclusive resource observations, signed recipes and enforced offline execution remain separate work.
