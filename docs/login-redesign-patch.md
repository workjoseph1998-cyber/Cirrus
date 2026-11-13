# Cirrus Workplace — login redesign patch

Base: Version 17, commit `45947a1`. The application stays **Version 17**. This patch
changes only the public sign-in page; it needs **no database migration, account
initialization, new Python package, IIS binding change or SMTP change**.

## Files in Cirrus-Workplace-Login-Redesign-Patch.zip

The ZIP opens directly at `workspace_app` (no extra enclosing application folder):

```text
workspace_app/templates/login.html
workspace_app/static/login.css
workspace_app/static/login.js
workspace_app/static/login-cloud-near.webp
workspace_app/static/login-cloud-far.webp
```

It reuses the existing `workspace_app/static/cirrus-logo.png` without changing it.
No databases, customer documents, credentials, configuration, tests or unrelated
application files are included. This instruction document and screenshots are
provided separately so the patch contains only its five runtime files.

## Install on Windows Server / IIS / Waitress

1. Identify the **current running Version 17 application folder**, containing
   `run.py`, `start.bat`, `.venv` and `workspace_app`. Use the folder configured by
   the existing Windows service/launcher, rather than an old extracted ZIP folder.
2. Stop only the Workplace/Waitress service or console process using your existing
   procedure. For a console launch, press Ctrl+C. Do not change IIS's reverse proxy,
   bind address/port, allowed hosts, service account or external data-directory settings.
3. Before copying, back up the five paths listed above **if they already exist** to
   a separate folder, for example `C:\CirrusPatchBackups\Login-2026-11-05`. Preserve
   their relative paths and note which files did not exist. On the unmodified
   Version 17 release, only `templates\login.html` already exists; the other four
   are new. Keep any existing customization backups until verification is complete.
4. Extract the patch ZIP into a temporary folder. Copy its `workspace_app\templates`
   and `workspace_app\static` file contents into the matching folders beneath the
   **running application's root**, overwriting only the listed files. For example,
   the result must be `YOUR_APP\workspace_app\templates\login.html`, not
   `YOUR_APP\workspace_app\workspace_app\templates\login.html`.
5. Start/restart the existing Workplace/Waitress process with the same account,
   environment and deployment settings. Restart is required to clear the server's
   cached login template. An IIS reset is not required for this patch. Sign-in
   sessions may expire on process restart as they already do in the application.
6. Open your usual portal `/login` URL, or sign out first. Use Ctrl+F5 if the browser
   still shows the old design. Test one wrong password and a normal successful sign-in.
   Check password visibility and the page on a small screen. For users who request
   reduced motion, the background should stay still.

Do **not** run `init-admin`, restore a database or replace the external data folder
as part of this patch. Existing accounts and passwords stay unchanged.

## Roll back

1. Stop the same Workplace/Waitress process.
2. Restore the backed-up `workspace_app\templates\login.html`. Restore any of the
   four login asset files that existed before this patch. Delete a new login asset
   only if your installation notes confirm it was introduced by this patch:
   `login.css`, `login.js`, `login-cloud-near.webp`, `login-cloud-far.webp`.
3. Leave the existing Cirrus logo, shared styles/scripts, application code and all
   external data/configuration untouched.
4. Restart the process with the same settings and refresh `/login` with Ctrl+F5.
   No database rollback or migration is involved.

## What changes

- Deep navy scene with two original locally baked cloud textures, slow independent
  drift, atmospheric lighting, a network constellation, floating particles,
  mouse-responsive cloud parallax and a soft cursor glow.
- A responsive glass sign-in card, the existing proportional Cirrus logo,
  **Welcome to Cirrus Workplace** and **Your workspace, connected.**
- Accessible labels, keyboard focus, native username/current-password autofill,
  password Show/Hide, an announced busy state and duplicate-submit prevention.
- Clear, escaped login errors, preserved entered username on failure and an empty
  password field. The initial-administrator guidance remains available when needed.
- The obsolete hardcoded Version 10 login label is removed. No version number is
  displayed on this page, avoiding a stale copied label on future releases.

The native POST, field names, CSRF token, authentication route, redirect/session
logic, throttling and permission checks are unchanged. There are no API calls that
handle credentials, no external fonts/CDNs/animation services, no videos and no new
local credential storage. Login styles/scripts are not loaded by signed-in pages.
The existing Content Security Policy is unchanged: external local CSS/JS plus
Canvas/CSSOM are used instead of inline handlers/styles or an unsafe-inline exception.

## Motion, performance and accessibility

The canvas renders at most 30 times per second on desktop and 15 on small screens.
It uses bounded particle/connection counts and a capped render resolution. Small
screens disable cursor/parallax effects, reduce particles/connections and stop the
far-cloud animation. The two WebP cloud textures together are about 43 KiB.

`prefers-reduced-motion` stops cloud animation, parallax, transitions and the canvas
loop. Visibility changes pause the canvas loop and CSS background animations while
the tab is hidden; returning resumes without a large time jump. Native sign-in
continues working with JavaScript disabled, and the password toggle remains hidden
when JavaScript is unavailable. Background elements cannot intercept pointer events
and are hidden from assistive technology. No new focus trap is introduced.

## Checks performed

Linux development environment, Python 3.12, real local Waitress and Chromium,
temporary synthetic accounts; no company VM or live data was used.

- All **9 existing security tests** passed: sign-in/out, disabled accounts, session
  expiry/revocation, CSRF, throttling, sharing, record isolation and host/proxy checks.
- Browser checked successful desktop/mobile/native-without-JS sign-in; incorrect
  password and disabled account; protected-page redirect and missing-CSRF rejection.
- Checked password-toggle keyboard operation, field Tab order, busy state and a
  second submission being rejected. Verified native submitted field names still
  contain `csrf`, `username`, `password`; no password is echoed after failure.
- Inspected 1536×960 and 1366×768 desktop/laptop layouts, 390×844 mobile and 320×640
  narrow layout, plus the styled error state. No horizontal page overflow. Very short
  screens can scroll naturally; the form is never clipped by a fixed-height container.
- Checked reduced motion, live preference changes and deterministic simulated
  hidden-tab pause/resume. Checked local-only requests, the unchanged CSP and no
  login CSS/JS on the signed-in dashboard. No login-page JS/CSP/resource errors. The unrelated pre-existing dashboard
  favicon request is outside this patch and excluded from login resource checks.
- Measured a one-second desktop animation sample using Chromium's actual canvas
  draw count and main-thread metrics; results accompany the delivered screenshot
  evidence: 29 canvas draws, 40 animation callbacks and 120.7 ms main-thread time
  in a one-second sample at 1536×960. These are development measurements, not a
  Windows GPU benchmark.
- Verified JavaScript syntax, patch member paths/integrity and applying the patch
  to a clean extracted Version 17 source copy without changing other application files.

Native password-manager integration is supported with the correct autofill
attributes; saving/filling real company passwords was not tested. The actual Windows
service/IIS browser path still needs the brief installation checks above. If blur is
unsupported, the card retains its opaque navy fallback and readable form.
