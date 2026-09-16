# Testing hearth

## Active test host

All deployment and runtime testing now targets **10.20.30.10**. The laptop is used for source editing, Git and browser/client access. Do not start `Start-Hearth.ps1`, the local QEMU appliance or local hearth-managed providers. The old farm data is retained.

- Begin at [Welcome and certificate download](http://10.20.30.10).
- Use [Workspace](https://10.20.30.10) and [Administration](https://10.20.30.10:8443).
- Maintain the deployment through `ssh operator@10.20.30.10`, then `/opt/hearth` and sudo as needed.
- Register resident providers by addresses reachable from the VM. Laptop loopback and the retired QEMU host bridge are not VM provider addresses.
- Preserve live accounts, conversations, certificates and provider settings. Do not run reset/first-Owner fixtures against the farm, and do not create another farm for tests. Adapt integration fixtures to isolated storage on the VM before running them.

See [current VM operations and limits](operations/ESX_HEAD.md). Historical localhost receipts do not establish that a feature or provider is configured on this fresh VM. Browser certificate onboarding remains a separate unresolved check in the [build ledger](implementation/BUILD_STATUS.md).

## Retired laptop reference

The remaining sections record the former laptop configuration and feature exercises. Their localhost URLs, launcher commands and installed-model assumptions are historical; use the active VM guidance above for current work.

This build supports private chat, side notes, steering, shared channels, local image generation, saved Read aloud recordings and reviewed microphone/WAV transcripts. The prepared configuration uses LM Studio's `openai/gpt-oss-20b` and the separate SDXL image provider. Keep LM Studio running; the launcher starts the image, CPU speech and CPU transcription providers when their local configurations exist. The SDXL files have been downloaded and verified on the prepared machine. Existing Owner, authenticator and conversations are preserved. Provider health must still pass a current check.

Run commands from the repository root, `C:\src\hearth`, rather than from this documentation folder. See [design coverage](implementation/DESIGN_COVERAGE.md) for the complete feature and qualification limits.

## Try the new chat

1. Refresh [your workspace](https://localhost:8444) and open **Private chat**.
2. Press **Enter** to send; **Shift+Enter** inserts a new line. Ask a follow-up, then refresh. Replies arrive incrementally and the conversation stays saved.
3. Open [Administration](https://localhost:8443), then **Providers**, to see the connection, model, shared resource group and verified features. Verification no longer expires hourly. The head checks saved connections automatically at startup; use Verify again after a provider error or configuration change. See [provider lifecycle](implementation/PROVIDER_LIFECYCLE.md).
4. To try another local service, enter its URL and exact model identifier. Use the same resource group for models sharing a GPU. Network servers accept verified HTTPS or saved per-connection administrator consent for private LAN HTTP. This machine's loopback providers use the development appliance's explicit host bridge.

In Administration, each capability card opens its assignment and matching provider controls. **Give each capability a home** saves an ordered list of models; **Edit connection** moves a target while preserving assignments and requiring fresh verification. All fourteen assignments are initially pointed at the existing services. Seven text capabilities, image generation, private image understanding, Read aloud and English transcription can run; memory and 3D adapters remain pending. Use **Attach image**, paste or drop a still PNG/JPEG/WebP into a private chat, then ask about it. Automatic routes pictures and their follow-ups to the verified Vision assignment. The prepared remote Qwen target supports this. See [vision testing and limits](implementation/VISION_AND_CONCURRENT_FARM.md).

Use **Reply with** in Private chat to test a specific text specialist. Automatic routing also recognizes direct planning, coding, writing, summarization and extraction requests. In channels, include `@hearth`. For providers on other machines, use approved direct HTTP, verified HTTPS or the optional portable connector and follow the [LAN setup and test guide](implementation/LAN_PROVIDER_TESTING.md). The packages are in `dist/connectors`; existing model servers can stay on loopback.

**For later** saves private side notes while a response runs. Send a note later, dismiss it with ×, or choose **Steer with this**. Typing a new message during a response also offers **Steer response**. The new direction is saved immediately and starts when the previous backend request finishes. **Return to composer** withdraws it from the queue.

**Stop response** stops visible output while LM Studio finishes processing. You can continue the same conversation afterward; partial replies remain visible but are excluded from the next model context. An interrupted connection keeps the resource group occupied until you check the server and confirm it is idle in Providers. The observed GPT-OSS final JSON header is now handled; other unsupported channel formats still stop the request with a clear error.

## Microphone and transcription

Below the private message composer, choose **Record voice**, allow microphone access, speak and click **Stop recording**. Play the preview if needed, then **Transcribe recording**. You can also **Upload WAV**. Review/edit the transcript, choose **Use in message**, then send or steer using the normal composer. Text is never sent automatically. Cancellation, discard and draft dismissal are available. The microphone stops on navigation and after two minutes.

The first CPU Whisper profile recognizes English and accepts 16-bit PCM WAV recordings up to two minutes and 8 MiB. MP3/M4A/WebM and other languages are not enabled yet. In Administration, **Verify transcription** refreshes the known-recording check if needed. See [transcription behavior and limits](implementation/TRANSCRIPTION.md).

## Read aloud

Open a completed private assistant reply and click **Read aloud**. The separate CPU Kokoro provider makes and saves a recording with its model/voice label. Press Play if browser autoplay is blocked; native controls provide pause, seek and volume. **Stop playback** rewinds, **Save WAV** downloads, and reloading keeps the recording without generating it again. **Stop generating speech** cancels pending synthesis and waits for the current segment to finish. GPU chat can run independently while speech is being prepared.

The first voice is `af_heart`; replies are limited to 6,000 characters with a clear error for longer text. Microphone/WAV transcription is available separately; Markdown-aware speech cleanup is not included yet. If the speech probe expires, open Administration, select Providers and click **Verify speech**. See [Read aloud behavior and limits](implementation/READ_ALOUD.md).

## Shared channels and images

- **Several images:** try “Generate four images of Jeep Gladiator pickups, one each in red, grey, black and army-green.” In your existing image conversation, “make 4 different jeep gladiators in red grey black and army-green please” also works. “Generate the images of each please” uses the earlier discussion. Up to four images render one at a time, with individual progress and downloads. Stop preserves completed pictures and cancels the rest. See [batch behavior and evidence](implementation/IMAGE_BATCHES_AND_CAPABILITY_NAVIGATION.md).
- **Images in chat:** in Private chat, try “Make an image of a little red fox asleep beside a glowing stone fireplace, warm storybook illustration.” It should show progress and return the picture in that conversation. Click it for full size or **Save PNG** to download. Refreshing preserves it, and it also appears in your private Images gallery. **Stop response** and side-note steering work while it renders.
- In a channel, try “@hearth draw a tiny wooden spaceship above a pine forest.” Joined members can see the image inline. The requester can stop it. Channel images stay in channel history and do not appear in anyone's private gallery.
- **Channels:** create a room or join one. Joining reveals its shared history to that farm member. Ordinary messages are for people; include **@hearth** to request an assistant reply using recent channel context. Try a second Member in a private browser window. Private notes and chats never become channel context. These first rooms are open for any member of the farm to join.
- **Images:** describe a picture, choose a shape and create it. The local SDXL provider handles progress and actual job-scoped cancellation. Completed PNGs, seeds and settings stay in your private gallery. **Save PNG** downloads the image; **Use settings** restores its description and seed. Keep prompts short, around 60 words or fewer.
- Both model connections use **Shared local GPU**, so hearth admits one generation at a time across chat and images. If evidence expires, use **Verify chat** or **Verify images** in Administration. Image verification renders a small test picture.

The optional image process starts with the launcher once installed, or directly with `uv run python scripts/image_runtime.py start`. It binds only to `127.0.0.1:1235`; users interact through hearth. See [the new feature boundaries](implementation/NOTES_CHANNELS_IMAGES.md). Image editing, 3D generation, tools and the administration agent remain unfinished.

**Context and variations:** describe a scene in chat, then ask “Please draw what we just discussed.” After the image arrives, try “Make it blue instead.” hearth uses the local chat model to prepare a short prompt before handing it to SDXL. If details are missing, it can ask a question before rendering. In channels, include `@hearth`. Variations generate a new picture from the earlier description; they do not preserve or edit the original pixels. SDXL can miss individual details such as a requested color. See [contextual image behavior and evidence](implementation/CONTEXTUAL_IMAGE_PLANNING.md).

## Start

Open PowerShell in the repository root and run:

```powershell
.\Start-Hearth.ps1
```

Keep the setup console open. It opens a native, loopback-only setup session in your default browser. The session expires after 30 minutes; rerun the command if it expires. The prepared appliance is already installed in this checkout. Startup after a reboot may take a minute.

1. Click **Trust this hearth certificate** after reviewing the displayed fingerprint. This explicit action adds the appliance's local CA to **your Windows user's** trusted roots. Applications using that trust store can then trust certificates issued by this CA. The launcher itself does not install browser trust.
   The setup page then checks Administration, Workspace and Sign-in from this browser. It retries a first failed connection and only offers the app links after all three HTTPS checks succeed. Windows certificate installation and browser readiness are shown separately.
2. Create your hearth name, Owner name, username and password. Passwords need at least 14 characters. Use a fresh username; ordinary registration can never claim Owner.
3. Open **Administration** and sign in. Have your TOTP authenticator ready. Complete authenticator setup and save the one-use recovery codes somewhere safe.
4. You should see your name, the farm overview and 14 catalog capabilities. A connected, verified chat model makes general chat available.

Use these exact addresses after trust and setup:

- [Administration](https://localhost:8443)
- [Your workspace](https://localhost:8444)

The hearth sign-in service is on `https://localhost:8445`. The redirect to that separate origin is expected; its page names the application you are entering. Your existing hearth username, password and authenticator work there.

Zen/Firefox may need another connection after importing a Windows root. If the first visit reports `SEC_ERROR_UNKNOWN_ISSUER`, return to setup and use **Check browser connections**. If needed, fully quit/reopen the browser and rerun the launcher. Persistent warnings have a browser-specific certificate import guide and a download of this hearth's public root in setup. Do not add a website exception. This build binds to host loopback, so these URLs are for this machine, not another LAN device.

## What to test

| Try | Expected result |
|---|---|
| Open your workspace after signing into Administration | A separate sign-in. The admin cookie does not authenticate the user application. |
| Open Private drafts, create a title and some text, then Save | A saved confirmation and a new entry in Your drafts. |
| Refresh, reopen the draft, edit and save | Your text survives refresh and the edit persists. |
| Edit the same draft in two tabs | A stale save is rejected with a conflict message rather than silently overwriting a newer revision. |
| Change appearance | Daylight, Firelight and System persist independently per application origin. |
| Open Capabilities | Fourteen definitions from PostgreSQL. Seven text profiles, image generation, private vision, speech and transcription require fresh compatible probes; unimplemented profiles remain unavailable even when an intended assignment is saved. |
| Register in a private browser window from the user sign-in page | A Member account, authenticator/recovery enrollment, and its own empty personal workspace. Email is optional. |
| Open Administration with that Member | A clear access message and a link back to its workspace. Farm inspection is denied. |
| Sign out, then refresh an old application tab | That application's old session is no longer usable. |

The two applications keep separate sessions. Sign out of each when testing separate people in the same browser, or use a private window. If an authenticator code has just been used, wait for its next code before another sign-in. Keycloak rejects reuse.

Drafts are personal, local-only records. Saving does not send their content to an assistant. Archive removes a draft from the active list; an archive recovery UI is not included yet. Signed managed installation, worker enrollment, tools, image editing, 3D, shared-workspace permissions, role editing and user API keys remain future milestones.

## Stop and resume

```powershell
uv run --group appliance python scripts/appliance.py down
.\Start-Hearth.ps1
```

The guest reserves 8 GiB RAM while running. Its disk, accounts, certificates and drafts persist in ignored `.hearth/`. Keep that folder. Do not remove it to restart the product.

If startup reports a service failure, use the recovery commands in [DEVELOPMENT.md](DEVELOPMENT.md). The reference VM currently needs a documented guest CPU compatibility setting; the installer and long-running release reliability gates remain open. See [ADR 0005](adr/0005-whpx-shadow-stack-compatibility.md).

To remove only this test CA from your Windows user trust store after testing:

```powershell
$hearthTestCert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new((Resolve-Path -LiteralPath '.hearth/certificates/edge-root.crt').Path)
Remove-Item -LiteralPath ('Cert:\CurrentUser\Root\' + $hearthTestCert.Thumbprint)
```

That removes browser trust, not your hearth data. Future visits will require trusting the certificate again.

## Private memory

Open **Memory** in your workspace to save/edit notes, search and correct history, pause recall, and download/import an Obsidian vault. Try a named preference in a fresh chat, edit it, then ask again in another fresh chat. The reply lists its memory sources. Complete instructions and current limitations are in [private memory](implementation/PRIVATE_MEMORY.md).
