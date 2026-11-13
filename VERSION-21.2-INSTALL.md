# Version 21.2 — installation, testing and rollback

This is the complete source distribution. It uses the same Python dependencies,
V21 profile isolation, Waitress and IIS architecture as V21.1.

## Windows Server 2022 (operator steps; not executed in this cloud task)

1. Back up the isolated V21 profile through the supported backup workflow. Record the Windows account, service configuration and existing profile location.
2. Stop the V21.1 application and pause service recovery or scheduled restart. Do not change V20 data, documents, exports or backup settings.
3. Extract `Cirrus-Workplace-Version-21.2.zip` into a separate application directory. Keep the V21.1 application directory for rollback. Never extract over V20 or V21.1.
4. Under the same Windows account, run the unchanged `setup.bat`. The existing installer preserves an established V21 live profile. For a first V21 installation, follow `VERSION-21-INSTALL.md` and its explicit copy/isolation requirements.
5. Run the unchanged `start.bat` with the same account/profile. The backend remains `127.0.0.1:8000` behind the existing IIS reverse proxy. No new schema migration or IIS configuration is required by this UI release.
6. Hard-refresh the browser to load the new CSS/JavaScript. Check the **v21.2** non-editor sidebar footer. Verify login, navigation, filters, Manage, customer documents, reports, approvals and permissions in staging before scheduling a production switch.

The quotation editor deliberately retains the exact V21.1 shell, including its
original V21 footer. Original V21 compatibility/build metadata remains unchanged;
the Git release commit identifies this source distribution. Never run V21.1 and
V21.2 against the same database or backend port simultaneously.

## Cloud development / verification

Use the existing isolated checkout; do not create an extra worktree unless explicitly requested.

```bash
cd /workspace/Cirrus
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests
.venv/bin/python tests/v21_2_browser.py
.venv/bin/python tests/v21_1_browser.py
.venv/bin/python tests/v21_browser.py
```

The browser suites use `/usr/bin/chromium` and temporary synthetic databases.
They start/stop their own local Waitress servers on ports 8043, 8042 and 8041.
No production profile, database or real SMTP credentials are required. The new
suite writes screenshots and results to `/tmp/cirrus-v21-2-browser` by default;
use `--output /path` to change it.

For before screenshots, extract the V21.1 source outside the checkout and run:

```bash
.venv/bin/python tests/v21_2_browser.py --source /path/to/v21.1 --output /tmp/cirrus-v21-2-before
.venv/bin/python tests/v21_1_editor_compare.py /path/to/v21.1
```

The editor comparison checks the visible preview in light/dark mode, excluding
Chromium's native scrollbar gutter. Protected-file hashes and the existing
calculation/export/approval tests provide additional regression coverage.

## Rollback

Stop V21.2 and disable its automatic restart, then restart the preserved V21.1
application under the same account and profile. V21.2 adds no schema change.
The previous source remains on `feature/cirrus-workplace-v21-1-ux` at
`fe6957247234b0e58b21dff4b25cbddd4a36ea82`. V21.2 lives separately on
`feature/cirrus-workplace-v21-2-premium-ui`.

If business activity has changed data since the upgrade, decide whether a restore
is necessary before using the supported backup workflow. Do not overwrite a live
database or silently discard newer records. The original uploaded application
also remains tagged `v21-baseline`.
