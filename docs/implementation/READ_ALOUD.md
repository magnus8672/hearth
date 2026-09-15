# hearth Read aloud

Implemented 13 September 2026. Completed private assistant replies now have a **Read aloud** control. It sends that saved reply's text to the assigned `audio.speak` provider, saves a validated WAV with the reply, and records the speech model and stock voice. Reloading or replaying that audio does not generate another job. Existing text, vision and image routes keep their assignments.

## Try the prepared build

Refresh [your workspace](https://localhost:8444), open a private conversation, and click **Read aloud** beneath a completed reply. The local CPU provider prepares the recording. Playback starts if the browser permits it; otherwise press Play on the audio controls. Pause/seek/volume use native controls, **Stop playback** rewinds, and **Save WAV** downloads the private recording. Starting another recording pauses audio already playing in this page. A saved recording stays paused after reload.

**Stop generating speech** is separate from playback. It requests cancellation, waits for the currently synthesizing segment to finish, and retains the resource reservation until the provider confirms release. Text generation can continue on an independent GPU pool during CPU speech.

The prepared provider is `kokoro-82m-v1.0-onnx` with the stock `af_heart` voice. It is loaded once at startup on the CPU. No text-model load, unload or swap is part of Read aloud. Administration supports multiple speech servers and ordered many-to-many capability assignments using the same connection, revision, HTTP-consent and resource controls as other providers. The [activation receipt](../../evidence/speech/2026-09-13/activation.json) records the prepared farm change.

## Implementation and boundaries

Migration `0016` adds forced owner/farm RLS for speech jobs. Each job belongs to one conversation and assistant message. The API accepts a request identifier, never replacement text, arbitrary audio URLs, a model path or provider authority from the browser. Only completed, nonempty assistant replies can be spoken. The provider receives that reply text, not the rest of the conversation or its pictures. Stored route receipts preserve the original speech model identity after configuration changes.

Admission selects a verified idle `hearth.speech.v1` target assigned to `audio.speak`; an unavailable route returns a useful error. The first provider profile supports replies up to 6,000 characters and ten minutes of mono 24-kHz, 16-bit PCM audio. Oversized text is rejected explicitly without truncation. One speech job per account runs at a time. The development store limits each account to 100 jobs and a 256-MiB audio budget, with space reserved for a maximum-sized result before dispatch. Completed speech is reused for that message.

Provider receipts bind the job, model, voice and input digest. Audio must match the result digest and frame count, decode as the supported WAV profile, stay within 32 MiB, and contain a non-silent signal. These checks establish a valid audio artifact, not pronunciation or semantic quality. The provider probe synthesizes a fixed known phrase and validates the result. Listening and wider speech-quality acceptance remain separate.

Session revocation, archive, provider changes or cancellation prevent publication. Lost receipts/deadlines fence the resource pool as unknown and do not replay inference. A provider restart marks unfinished jobs interrupted; an exclusive local process lock prevents two processes sharing the same job store. Old job IDs cannot be reused with new text. Audio reads require the user's active workspace session and correct conversation, with no-store and nosniff headers. Provider credentials remain encrypted in the control database and do not reach the browser.

## Validation

The [real Read aloud test](../../evidence/speech/2026-09-13/live-read-aloud.json) used the actual CPU Kokoro process, authenticated job transport and restricted PostgreSQL/BFF APIs. Text and identity were explicit fixtures in a disposable farm. It generated a 2.837-second recording and restored matching audio and model/voice information in a fresh session. The [WAV](../../evidence/speech/2026-09-13/live-read-aloud.wav) is available for listening.

Regressions cover authorization, CSRF, cross-owner/conversation isolation, immutable input/identity, idempotency, cancellation/drain, independent pools, session revocation, manifest mismatch, unknown execution, restart without replay, unsupported/silent/truncated audio, receipt substitution and body limits. Browser tests play a valid WAV, stop/rewind it, reload without a second synthesis, cancel generation, and register two independent speech servers. Desktop/mobile screenshots were inspected. See [deployment and qualification](../../evidence/speech/2026-09-13/validation.json) for exact counts and hashes.

This is private-chat Read aloud. Microphone capture, transcription, shared-channel speech, streaming audio, voice selection/cloning, speech-aware Markdown cleanup, general retention/deletion and production managed-worker packaging remain unfinished. The current raw reply text may include code or Markdown punctuation in spoken output. There are ten executable capability profiles and four assignment-only profiles. All 61 full release gates remain open.
