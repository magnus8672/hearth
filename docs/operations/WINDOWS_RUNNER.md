# Windows text runner preview

The Windows AMD64 worker can supervise a resident llama.cpp LLM or the experimental
NCM XSum summarizer. It uses the same signed service recipes and outbound control
leases as the Linux worker. Windows Job Objects contain the engine, HTTPS connector
and their descendants. Switching stops and confirms the previous process tree
before starting the selected backend. Exiting the worker closes its jobs.

This is a development package, not an Authenticode-signed installer or a Windows
Service. The broader installer, enrollment and hardware qualification work remains
open. Existing LM Studio connections remain supported.

## Engines and limits

| Engine | Initial runtime | Exposed behavior |
|---|---|---|
| LLM | Pinned llama.cpp `b11756`, Windows Vulkan | Existing GGUF model, compatible chat and streaming; tools/Vision require separate verification |
| NCM | Pinned HazyResearch XSum, PyTorch CPU by default | One English article of 1–512 GPT-2 tokens; up to 48 output tokens; final answer only |

NCM is not an instruction-tuned chat model. Its released weights are task-specific.
Initial CPU execution produced a summary that invented details, so transport
verification does not establish faithful summarization. Treat it as experimental.
Do not use it as an automatic compactor or general chat/planning target. Windows AMD
GPU acceleration for NCM is not qualified. CUDA is an adapter option only when
separately provisioned and tested; the packaged requirements prepare CPU execution.
The research speed comparisons against diffusion models on an H100 do not predict
performance on a home PC. See [upstream](https://github.com/HazyResearch/ncm),
[paper](https://arxiv.org/html/2610.14162v1) and
[third-party pins/notices](NCM_THIRD_PARTY.md).

## Build and prepare

From a source checkout, run `python scripts/package_windows_runner.py`. It builds
native Windows worker/connector executables and writes the preview ZIP and SHA-256
manifest under `dist/runners/`. Packages contain no private identity, model weights,
addresses or Python installation. Extract the package on the intended Windows PC.

Use an installed Python 3.12 and a new private destination. The setup explicitly
downloads a pinned Vulkan engine, NCM source/checkpoints, GPT-2 tokenizer and CPU
Python dependencies. It creates HTTPS identities and protects the destination with
a current-user/SYSTEM Windows ACL. It does not start a backend or change LM Studio.
Supply your actual address and model path privately:

```powershell
python scripts/prepare_windows_runner.py --home "$env:LOCALAPPDATA\hearth\runner" --public-host $env:HEARTH_RUNNER_ADDRESS --llm-model $env:HEARTH_GGUF_PATH
```

The model alias defaults to `hearth-local-llm`, context to 8192, concurrency to one
and GPU layers to 99. Use `--context`, `--gpu-layers` and `--llm-id` during setup to
choose reviewed values. The source GGUF is preserved in place. Keep the prepared
Python environment and its base interpreter stable: their code/dependency closure
is hashed into the service approval. Updates require a new reviewed recipe.

Default ports are 1240 (LLM HTTPS) and 1244 (NCM HTTPS); only loopback engine ports
1243 and 1242 use HTTP. Permit only the head to reach the HTTPS ports in Windows
Firewall. Do not expose engine ports or permit arbitrary LAN management commands.
Secrets stay in the private installation, never in documentation or command lines.

## Register and adopt

1. Register two provider connections in Administration with one shared resource
   group, initially keeping existing assignments. Use the corresponding identity's
   `provider-ca.pem` and `controller.key`; these are distinct for each connection.
   LLM uses OpenAI-compatible chat with the configured alias. NCM uses **NCM XSum
   summarizer**, model `hazyresearch/ncm-xsum`. An offline initial probe can fail
   until the worker is started; do not mistake registration for readiness.
2. Complete the private `inventory.json` with the registered pool and connection
   UUIDs. Review its fixed executable arguments, file/directory digests, health
   checks and `bundle_directory`. Model names and content cannot supply commands.
3. Copy this inventory to the head and use `scripts/adopt_worker.py` with its
   `--inventory`, `--output` and private `--state`. This console-only tool signs
   the recipe and registers the worker paused. Copy the resulting private bundle
   to the exact Windows `bundle_directory` through a trusted channel. Preserve its
   CA and credential; never put the signing private key on the worker.
4. Start `hearth-worker.exe serve` with the absolute path to that bundle's
   `config.json`. Keep one instance per state directory. The head's **Workers**
   controls can select LLM or NCM, resume admission, pause or unload. A changed or
   expired control lease cannot authorize a new start. A busy or uncertain pool
   must be drained before switching.
5. Verify each provider while it is selected and ready. Assign LLM chat only after
   a real reply succeeds. Assign NCM only to **Summarization** using Ordered
   selection; its different semantics are not interchangeable with chat for
   Switchyard balancing. Keep the worker's policy **Resident** for this preview.

Text/NCM requests do not automatically switch services or join the image queue.
An unavailable selected service returns a visible admission error. This preview
adds explicit managed switching; a universal fair text queue remains roadmap work.
Never run LM Studio with the same GPU allocation while the replacement owns it.

## Use NCM through hearth

Start a fresh private conversation, choose **Summarization** under Reply with, and
paste the article itself. Existing conversation history and image attachments are
rejected rather than silently dropped. Recalled private memory is not sent to NCM.
Inputs above the checkpoint's limit are rejected without truncation. The reply
arrives as a complete summary; hearth does not fabricate token-by-token progress.

Scoped client Chat Completions can select `text.summarize` with one user message
containing the article. System/developer instructions, prior replies, tools and
chat sampling controls are unsupported for NCM and return explicit errors. LLM
targets retain their existing client behavior. The runner's native summary
transport uses `GET /v1/ncm-provider` and `POST /v1/summaries`, with an ID-bound,
model/revision-bound receipt and token counts.

## Verification and recovery

Qualify real replies separately from lifecycle fixtures. Check load, unload,
switching in both directions, a changed executable, dependency injection, loss of
the worker/head, duplicate state ownership, expired leases, client disconnect,
oversized articles and occupied-pool switching. A terminated model process must
not leave a ready provider or an orphan descendant. No interrupted request is
automatically replayed.

To revert, pause/drain and unload the Windows worker in Administration, confirm its
process tree is stopped, then restore the existing LM Studio connection/assignments.
Changing a service recipe requires the same paused, unloaded, stopped-worker
procedure as Linux adoption. The packet/build manifest is an integrity record;
it is not an Authenticode signature or independent release qualification.
