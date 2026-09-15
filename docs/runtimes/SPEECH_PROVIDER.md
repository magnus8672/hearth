# hearth development speech provider

For independent Ubuntu VM installation, model preparation, boot services and HTTPS, use [audio VM setup](../operations/AUDIO_VM_SETUP.md). The local development commands below remain available.

This optional provider uses an isolated Python environment and the existing Kokoro ONNX/stock-voice files. It is an explicitly started development process, not a signed or enrolled managed worker. Normal requests never download models or change residency.

From the repository root:

```powershell
uv sync --locked --project runtimes/speech
.venv/Scripts/python.exe scripts/speech_runtime.py start --model C:/src/interlocutor/kokoro-v1.0.onnx --voices C:/src/interlocutor/voices.bin
.venv/Scripts/python.exe scripts/speech_runtime.py status
```

Later starts can omit the two paths; the helper keeps the explicit configuration in private `.hearth/speech-provider/`. The local hearth launcher also resumes this prepared provider when its configuration exists. The model and voice bytes must match [the manifest](../../runtimes/speech/model-manifest.json). The separate [dependency lock](../../runtimes/speech/uv.lock) pins the environment. No model files are copied or redistributed by setup. The provider loads at startup and listens on loopback port 1236. The development appliance maps that saved host-loopback address through its existing QEMU maintenance environment.

Register `http://127.0.0.1:1236`, model `kokoro-82m-v1.0-onnx`, provider type **hearth speech provider**, with its controller credential from `.hearth/speech-provider/controller.key`. Keep the key private. Assign it a separate **Local speech CPU** resource group, verify it, then assign **Speech output** to that model. The prepared instance is already registered. A verified deployment receipt is linked from [Read aloud](../implementation/READ_ALOUD.md).

`hearth.speech.v1` exposes authenticated provider information and bounded create/status/cancel/audio job endpoints. It is a job protocol with confirmed release, not an OpenAI `/audio/speech` compatibility claim. The first recipe exposes one stock voice. Browser origins are rejected. Outbound Python socket connection calls are disabled after Windows' internal event-loop setup; explicit offline model loading is enforced. This application guard is not a replacement for a production operating-system egress boundary. No OS firewall or other application's runtime was changed.

The provider job store has a 1-GiB WAV budget and 1,000-job development limit. It retains request receipts across restart and never replays unfinished synthesis automatically. Stop requests drain the current bounded text segment before release. The process uses hidden-window startup on Windows. A full service installer, authenticated lifecycle management, signing, storage pruning and automatic TLS enrollment remain future managed-worker work.

[kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) documents its MIT adapter license and the Kokoro model's Apache-2.0 license. The [upstream model card](https://huggingface.co/hexgrad/Kokoro-82M) also records Apache-2.0 for its weights. The locked dependency closure includes the eSpeak phonemizer; its notices and redistribution obligations must be included when a distributable runtime is packaged. This slice installs dependencies and reuses local model files; it does not publish a bundled runtime or claim a completed license/SBOM release gate.
