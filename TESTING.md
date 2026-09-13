# Try Hearth locally

This build is ready for an accounts-and-workspaces test on this Windows machine. It provides real Owner setup, authenticator enrollment, recovery codes, Member registration, separate admin/user sessions, the capability catalog, and persistent private drafts. It does **not** generate assistant replies yet. No model downloads or paid provider calls are needed.

## Start

Open PowerShell in this folder and run:

```powershell
.\Start-Hearth.ps1
```

Keep the setup console open. It opens a native, loopback-only setup session in your default browser. The session expires after 30 minutes; rerun the command if it expires. The prepared appliance is already installed in this checkout. Startup after a reboot may take a minute.

1. Click **Trust this Hearth certificate** after reviewing the displayed fingerprint. This explicit action adds the appliance's local CA to **your Windows user's** trusted roots. Applications using that trust store can then trust certificates issued by this CA. The launcher itself does not install browser trust.
   The setup page then checks Administration, Workspace and Sign-in from this browser. It retries a first failed connection and only offers the app links after all three HTTPS checks succeed. Windows certificate installation and browser readiness are shown separately.
2. Create your Hearth name, Owner name, username and password. Passwords need at least 14 characters. Use a fresh username; ordinary registration can never claim Owner.
3. Open **Administration** and sign in. Have your TOTP authenticator ready. Complete authenticator setup and save the one-use recovery codes somewhere safe.
4. You should see your name, the farm overview and 14 capabilities marked **Unassigned**.

Use these exact addresses after trust and setup:

- [Administration](https://localhost:8443)
- [Your workspace](https://localhost:8444)

The Hearth-branded sign-in service is on `https://localhost:8445`. The redirect to that separate origin is expected; its page names the application you are entering. Your existing Hearth username, password and authenticator work there.

Zen/Firefox may need another connection after importing a Windows root. If the first visit reports `SEC_ERROR_UNKNOWN_ISSUER`, return to setup and use **Check browser connections**. If needed, fully quit/reopen the browser and rerun the launcher. Persistent warnings have a browser-specific certificate import guide and a download of this Hearth's public root in setup. Do not add a website exception. This build binds to host loopback, so these URLs are for this machine, not another LAN device.

## What to test

| Try | Expected result |
|---|---|
| Open your workspace after signing into Administration | A separate sign-in. The admin cookie does not authenticate the user application. |
| Create a draft with a title and some text, then Save | A saved confirmation and a new entry in Your drafts. |
| Refresh, reopen the draft, edit and save | Your text survives refresh and the edit persists. |
| Edit the same draft in two tabs | A stale save is rejected with a conflict message rather than silently overwriting a newer revision. |
| Change appearance | Daylight, Firelight and System persist independently per application origin. |
| Open Capabilities | Fourteen definitions from PostgreSQL, all explicitly Unassigned. No fake model readiness. |
| Register in a private browser window from the user sign-in page | A Member account, authenticator/recovery enrollment, and its own empty personal workspace. Email is optional. |
| Open Administration with that Member | A clear access message and a link back to its workspace. Farm inspection is denied. |
| Sign out, then refresh an old application tab | That application's old session is no longer usable. |

The two applications keep separate sessions. Sign out of each when testing separate people in the same browser, or use a private window. If an authenticator code has just been used, wait for its next code before another sign-in. Keycloak rejects reuse.

Drafts are personal, local-only records. Saving does not send their content to an assistant. Archive removes a draft from the active list; an archive recovery UI is not included yet. Provider setup, worker enrollment, inference, shared workspaces, role editing and API keys remain future milestones.

## Stop and resume

```powershell
uv run --group appliance python scripts/appliance.py down
.\Start-Hearth.ps1
```

The guest reserves 8 GiB RAM while running. Its disk, accounts, certificates and drafts persist in ignored `.hearth/`. Keep that folder. Do not remove it to restart the product.

If startup reports a service failure, use the recovery commands in [DEVELOPMENT.md](DEVELOPMENT.md). The reference VM currently needs a documented guest CPU compatibility setting; the installer and long-running release reliability gates remain open. See [ADR 0005](docs/adr/0005-whpx-shadow-stack-compatibility.md).

To remove only this test CA from your Windows user trust store after testing:

```powershell
$hearthTestCert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new((Resolve-Path -LiteralPath '.hearth/certificates/edge-root.crt').Path)
Remove-Item -LiteralPath ('Cert:\CurrentUser\Root\' + $hearthTestCert.Thumbprint)
```

That removes browser trust, not your Hearth data. Future visits will require trusting the certificate again.
