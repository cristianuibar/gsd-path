# Guide: sign and notarize the OpenGSD Path macOS app

Goal: a user downloads the `.dmg`, opens the app, and macOS does not show
"Apple could not verify OpenGSD Path".

Without the Apple secrets the build is ad-hoc signed
(`bundle.macOS.signingIdentity` is `"-"` in
`daemon/app/src-tauri/tauri.conf.json`), and macOS shows that dialog. macOS
needs two things:

1. **Signing** with a *Developer ID Application* certificate.
2. **Notarization**: Apple scans the signed app and issues a ticket.

Tauri 2 does both during `tauri build` when the right environment variables are
set. Variable names below are from the Tauri docs:
<https://v2.tauri.app/distribute/sign/macos/>.

Steps 1 to 4 are for the Apple account holder (account and secrets). Step 5
describes the release workflow. Step 6 is the check.

---

## Step 1. Join the Apple Developer Program

1. Go to <https://developer.apple.com/programs/enroll/> and enroll (USD 99 per
   year). You can enroll as an individual or as an organization. An
   organization needs a D-U-N-S number, and its name is what users see as the
   developer.
2. Wait for Apple to approve the enrollment.
3. Only the **Account Holder** role can create Developer ID certificates. Use
   that Apple account for step 2.

## Step 2. Create the Developer ID Application certificate

On your Mac:

1. Open **Keychain Access → Certificate Assistant → Request a Certificate From
   a Certificate Authority**. Enter your email and name, select **Saved to
   disk**, and save the `.certSigningRequest` file.
   (Apple's steps: <https://developer.apple.com/help/account/create-certificates/create-a-certificate-signing-request>)
2. Go to <https://developer.apple.com/account/resources/certificates/list> and
   click **+**.
3. Select **Developer ID Application**. Do not select "Developer ID Installer"
   or "Apple Distribution"; those are for `.pkg` files and the App Store.
4. Upload the `.certSigningRequest` file, then download the `.cer` file.
5. Double-click the `.cer` file to add it to your login keychain.
6. Get the exact identity name. You need it in step 4:

   ```bash
   security find-identity -v -p codesigning
   ```

   The line looks like
   `"Developer ID Application: Your Name (ABCDE12345)"`. The ten characters in
   brackets are your **Team ID**.

## Step 3. Export the certificate and make the notarization key

### 3a. Export the certificate as `.p12`

1. In Keychain Access, open **My Certificates**.
2. Expand the "Developer ID Application" entry so you see its private key.
3. Right-click the entry, select **Export**, select format `.p12`, and set a
   strong password. Keep this password; it becomes a secret in step 4.
4. Encode the file as one base64 line:

   ```bash
   openssl base64 -A -in ~/Desktop/certificate.p12 -out ~/Desktop/certificate-base64.txt
   ```

### 3b. Create an App Store Connect API key (for notarization)

This is the better choice for CI. It has no two-factor prompt and you can
revoke it.

1. Go to <https://appstoreconnect.apple.com/access/integrations/api>.
2. Create a **Team key** with the **Developer** access level.
3. Download the `AuthKey_XXXXXXXXXX.p8` file. Apple lets you download it only
   once.
4. Write down the **Key ID** (the `XXXXXXXXXX` part) and the **Issuer ID**
   shown at the top of the page.

Alternative: your Apple ID plus an app-specific password
(`APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID`). Use one method, not both.

## Step 4. Add the repository secrets

Run these yourself. Each command reads the value from a file or asks you to
paste it, so the value does not appear in your shell history.

```bash
gh secret set APPLE_CERTIFICATE --repo open-gsd/gsd-path < ~/Desktop/certificate-base64.txt
```

```bash
gh secret set APPLE_CERTIFICATE_PASSWORD --repo open-gsd/gsd-path
```

```bash
gh secret set APPLE_SIGNING_IDENTITY --repo open-gsd/gsd-path
```

(paste the full name from step 2.6, for example
`Developer ID Application: Your Name (ABCDE12345)`)

```bash
gh secret set APPLE_API_KEY --repo open-gsd/gsd-path
```

(paste the Key ID)

```bash
gh secret set APPLE_API_ISSUER --repo open-gsd/gsd-path
```

(paste the Issuer ID)

```bash
gh secret set APPLE_API_KEY_P8 --repo open-gsd/gsd-path < ~/Downloads/AuthKey_XXXXXXXXXX.p8
```

| Secret | Value |
|---|---|
| `APPLE_CERTIFICATE` | base64 text of the `.p12` file |
| `APPLE_CERTIFICATE_PASSWORD` | the `.p12` export password |
| `APPLE_SIGNING_IDENTITY` | `Developer ID Application: … (TEAMID)` |
| `APPLE_API_KEY` | App Store Connect Key ID |
| `APPLE_API_ISSUER` | App Store Connect Issuer ID |
| `APPLE_API_KEY_P8` | contents of the `.p8` file |

`APPLE_API_KEY_P8` is a name for this repo. Tauri wants a file path in
`APPLE_API_KEY_PATH`, so the workflow writes the secret to a file first.

After this, delete `certificate.p12` and `certificate-base64.txt` from the
Desktop. Store the `.p8` file and the `.p12` password in your password manager.

## Step 5. The release workflow (done in the repository)

`.github/workflows/app-release.yml` does this in the two macOS jobs:

1. **Set up Apple signing** runs `daemon/app/scripts/macos-signing-setup.sh`.
   - No Apple secrets (forks, local builds): it does nothing, and the build
     keeps the ad-hoc signature from `tauri.conf.json`.
   - Some secrets but not all: it fails and names the missing ones, so a
     half-configured repository never ships a build that looks signed but is
     not notarized.
   - All six: it imports the certificate into a temporary keychain, checks the
     keychain holds `APPLE_SIGNING_IDENTITY`, writes the `.p8` key to a
     temporary file, and exports `APPLE_SIGNING_IDENTITY`, `APPLE_API_KEY`,
     `APPLE_API_ISSUER`, and `APPLE_API_KEY_PATH` for the build.
2. **Build** passes the identity on the command line, because the config file
   sets `"-"` and the Tauri docs do not say which one wins. Tauri then signs
   the app and notarizes it with the `APPLE_API_*` variables.
3. **Check** fails the job unless `codesign` shows your Developer ID and
   `xcrun stapler validate` finds the stapled notarization ticket. It also
   prints the `spctl` result, for information only, because Gatekeeper may be
   turned off on the runner.
4. **Clean up** deletes the temporary keychain and the key file, even when an
   earlier step failed.
5. The pre-release note says "macOS builds are signed and notarized" when the
   certificate secret is set.

The CI job `app-release-scripts` tests the setup script on macOS, Windows, and
Linux with a stand-in for the `security` command. The real keychain and Apple's
notary service are first used on the next `app-v*` tag.

The updater key (`TAURI_SIGNING_PRIVATE_KEY`) is separate and not changed. An
installed tester build (ad-hoc) can update to a signed build, because the
updater checks the updater signature, not the Apple one.

## Step 6. Release and check

1. Push a new tag, for example `app-v0.1.1`. The existing `app-v0.1.0` files
   stay unsigned; do not move that tag again.
2. In the workflow log for each macOS job, look for the signing lines and for
   the notarization result. Notarization usually takes a few minutes and can
   take longer.
3. Download the `.dmg` from the release **in a browser** (so macOS sets the
   quarantine flag), install the app, and run:

   ```bash
   codesign --verify --deep --strict --verbose=2 "/Applications/OpenGSD Path.app"
   ```

   ```bash
   spctl --assess --type execute -vv "/Applications/OpenGSD Path.app"
   ```

   ```bash
   xcrun stapler validate "/Applications/OpenGSD Path.app"
   ```

   Expected: `valid on disk`, then `accepted` with
   `source=Notarized Developer ID`, then `The validate action worked!`.
4. Open the app with a double-click. No Gatekeeper dialog must appear.
5. Test one update from the signed build to a later signed build.

## Things to check on the first signed build

- **Hardened runtime.** Notarization needs it, and signed Tauri builds use it.
  The app starts the Python daemon as a child process. If the app or the
  daemon fails to start only in the signed build, the app needs an
  entitlements file (`bundle.macOS.entitlements`). This is not tested yet.
- **Bundled files.** The bundle carries `.py` files as resources, not extra
  binaries, so no extra binary needs its own signature today. That changes if
  a compiled helper is added later.
- **The `.dmg` file.** If macOS still warns on the disk image itself, the
  `.dmg` also needs a signature and a stapled ticket. Check with
  `spctl --assess --type open --context context:primary-signature -vv <file>.dmg`.

## Problems you may see

| Symptom | Cause | Fix |
|---|---|---|
| `no identity found` | The name in `APPLE_SIGNING_IDENTITY` does not match the certificate | Copy the name again from `security find-identity -v -p codesigning` |
| `MAC verification failed` on import | Wrong `.p12` password | Set `APPLE_CERTIFICATE_PASSWORD` again |
| Notarization returns `Invalid` | Apple rejected a file in the bundle | Get the log: `xcrun notarytool log <submission-id> --key <p8> --key-id <id> --issuer <issuer>` |
| `401` or `403` from notarization | Wrong Key ID or Issuer ID, or the key has no Developer access | Check the three API secrets |
| Dialog still appears | You tested an old `.dmg`, or the ticket is not stapled | Download the new release again and run the three check commands |

## Windows (separate work)

The Windows installer shows a SmartScreen warning for the same reason. It
needs a code-signing certificate (for example Azure Trusted Signing, or an
OV or EV certificate). This guide does not cover it.
