# hearth local speech feasibility

Historical preparation record. The subsequent [Read aloud implementation](READ_ALOUD.md) now registers this CPU profile and saves playable audio on private replies. The measurements and next-step list below retain this earlier probe's scope.

13 September 2026. The existing Kokoro model and voice files in the separate `interlocutor` checkout can synthesize speech using the already installed Windows Python packages. The probe does not modify that project, enroll speakers, record a microphone or contact a cloud service. It uses the supplied `af_heart` stock voice. This is development evidence, not an enabled `audio.speak` capability.

The [repeatable probe](../../scripts/probe_existing_speech.py) requires explicit paths to existing model/voice files and an output directory. It selects only ONNX Runtime's CPU provider, blocks Python socket connection calls, and writes a mono 24-kHz PCM WAV plus model, voice and package provenance. No model or package was downloaded. There is no automatic fallback to a browser speech API, hosted voice or another model.

The [measured result](../../evidence/voice/2026-09-13/speech-feasibility.json) records 2.828 seconds to load and 9.406 seconds to synthesize a 5.717-second sample on the development laptop. This run was slower than real time and occurred while other development checks were active. It establishes an offline CPU path without evicting the resident GPU model; it does not establish latency or perceptual-quality acceptance.

Listen to the [speech sample](../../evidence/voice/2026-09-13/hearth-speech-sample.wav). Listening qualification is still pending. Waveform checks passed for finite samples, expected sample rate, duration and non-silent bounded amplitude; those checks cannot judge pronunciation or naturalness.

## Next implementation slice

1. Package an isolated provider with a pinned dependency/model manifest and documented upstream licenses. Existing local files were reused for this probe only; no model redistribution or signed recipe is ready.
2. Add a separate speech protocol with authenticated, bounded synthesis jobs and cancellation/drain receipts. Give CPU speech its own measured resource pool rather than attaching it to the local GPU pool.
3. Qualify configured voices with a known phrase and validated WAV output. Add the `audio.speak` route, owner-scoped saved audio and explicit playback controls on assistant replies. A model's text response must never be mistaken for successful audio generation.
4. Add a separate local transcription provider, bounded audio decoding and a known-recording accuracy check before exposing microphone/file transcription. Nothing in this probe provides speech recognition.

Keep managed deployment and existing-provider registration available as separate paths. The same multiple-server and many-to-many capability rules apply to speech as to text and images. The capability coverage remains nine executable and five assignment-only profiles until real speech dispatch is implemented and qualified.
