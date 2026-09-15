# hearth CPU transcription provider

For independent Ubuntu VM installation, model preparation, boot services and HTTPS, use [audio VM setup](../operations/AUDIO_VM_SETUP.md). The local development commands below remain available.

This is an optional development provider with a pinned model and isolated environment. It is not an enrolled, signed managed worker. The prepared machine already has the model and service installed. To prepare another local checkout, run from the repository root:

```powershell
uv sync --locked --project runtimes/transcription
.venv/Scripts/python.exe scripts/prepare_transcription_model.py
.venv/Scripts/python.exe scripts/transcription_runtime.py start --model .hearth/models/faster-whisper-small.en
.venv/Scripts/python.exe scripts/transcription_runtime.py status
```

The explicit preparation command downloads approximately 486 MB from the pinned [Systran model revision](https://huggingface.co/Systran/faster-whisper-small.en/tree/d1d751a5f8271d482d14ca55d9e2deeebbae577f), verifying each file against [the manifest](../../runtimes/transcription/model-manifest.json). Normal startup and inference do not download models. The [dependency lock](../../runtimes/transcription/uv.lock) pins faster-whisper and its dependency closure. [faster-whisper](https://github.com/SYSTRAN/faster-whisper) documents CPU int8 execution and local model loading. The upstream adapter/model metadata records MIT licensing; redistribution notices/SBOM and signed packaging remain release work.

The provider listens on `127.0.0.1:1237`. Private state and its controller key are in `.hearth/transcription-provider/`, restricted to the current Windows user by the launcher. Register the loopback address, model `faster-whisper-small.en`, type **hearth transcription provider**, and that private controller credential in Administration. Give it **Local transcription CPU** as a separate resource group, verify it and assign Speech input. The prepared farm already has this assignment. Later starts omit the model path; the hearth launcher resumes a prepared provider automatically.

`hearth.transcription.v1` provides authenticated information and create/status/cancel job endpoints. It is a confirmed-release job protocol, not an OpenAI `/audio/transcriptions` compatibility claim. Multiple implementations and server instances can register independently through the same protocol. The first model recipe is English-only and runs on CPU with four inference threads. Broad language, accent, noise and far-field accuracy qualification remains open.

Browser-origin requests are rejected. Allowed Hosts, a controller key, closed request fields, normalized WAV checks and input digest binding protect the local API. A process lock excludes duplicate job-store users. Jobs are never replayed automatically after restart. Outbound Python socket connection calls are blocked after Windows event-loop initialization; offline-only model loading is explicit. This guard is not operating-system egress attestation. No OS firewall changes or model-server GPU lifecycle changes were made.

The supplied startup helper targets loopback. LAN listening, automatic TLS, signed installation, lifecycle reconciliation, native audio decoder isolation and general provider retention policies need further qualification before a distributed managed recipe is released. Existing-service HTTP consent remains available in hearth when an external compatible provider is configured on a trusted private LAN.

See [microphone/transcription behavior and tests](../implementation/TRANSCRIPTION.md). Test audio is synthetic, with known text; microphone browser tests use an explicitly simulated input source.
