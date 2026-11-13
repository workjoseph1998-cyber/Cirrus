# Cirrus Workplace 21.1 — installation and rollback

This is a complete source distribution, based on the uploaded V21 live package.
Read CHANGELOG-V21.1.md and docs/V21.1-TEST-RESULTS.md before upgrading.

## Windows Server 2022

1. Back up the existing isolated V21 profile using the application's supported backup workflow. Record its Windows service/account and deployment configuration.
2. Stop the existing V21 process and its automatic restart. Leave V20 data, document, export and backup directories untouched.
3. Extract this complete package into a **separate application directory**, outside V20 and outside the existing V21 application folder. Do not overwrite either installation.
4. Under the same Windows account, run `setup.bat`. The unchanged V21 installer preserves an existing live V21 profile rather than recopying V20. For first installation, follow VERSION-21-INSTALL.md and its explicit copy/isolation checks.
5. Run `start.bat` under that same account. Waitress remains on `127.0.0.1:8000` behind your existing IIS proxy. No IIS or database schema change is required by this UX release.
6. Verify sign-in, quotations filters, Manage, customer files, reports, permissions, theme and an existing quotation's editor/calculations/exports in your staging environment before scheduling a production switch.

The editor intentionally retains its original V21 appearance, including its V21 footer; other pages show 21.1. `/v21/version` and BUILD_INFO.json retain their original V21 compatibility/build metadata; use the release commit to identify this source package. The old installation instructions describe V21 behavior; this document takes precedence for V21.1 UX placement.

No deployment to a production server was performed by this task.

## Cloud/Linux development and testing

Python 3.12 was used for verification. Use the existing checkout, not an additional worktree.

```bash
cd /workspace/Cirrus
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests
.venv/bin/python tests/v21_1_browser.py
```

The browser test starts and stops a local Waitress server using temporary synthetic data and requires `/usr/bin/chromium`. It logs in as synthetic roles; no real database or credentials are included. Screenshots/results go to `/tmp/cirrus-v21-1-browser`. Set `CW_BROWSER_ARTIFACTS` to override that directory.

For the separate baseline editor pixel comparison, extract the original uploaded V21 ZIP outside the checkout and run:

```bash
.venv/bin/python tests/v21_1_editor_compare.py /path/to/extracted/cirrus-workplace-v21
```

This starts two temporary synthetic servers and compares quotation editor preview screenshots in light and dark modes. It does not read production profiles.

## Rollback

Stop V21.1, including service recovery, and restart the previous V21 application under the same account and unchanged profile. This release adds no database schema migration. Do not run both versions on the same database or port concurrently. If testing or subsequent business activity changed data, use the supported backup/restore workflow after reviewing which newer records would be lost; do not overwrite database files while a process is running. The source baseline is tagged `v21-baseline`; the complete release is on `feature/cirrus-workplace-v21-1-ux`.
