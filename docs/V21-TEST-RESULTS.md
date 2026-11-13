# V21 complete live package — verification

All test accounts, settings, databases and files used here are synthetic. No real Windows server, production database or real SMTP service was accessed.

| Check | Result |
| --- | --- |
| Full application unittest suite | **307 passed**, 211.295 seconds |
| Updated focused V21/live/setup/installer suite | **31 passed**, followed by **8 live-copy tests passed** after the final source-schema guard regression was added |
| Live-copy browser suite | **15 scenarios passed**, no JavaScript page errors |
| Original V20 baseline suite | **278 passed** on unchanged source commit `63e5814` |
| Earlier V21 browser checks | **11 scenarios passed**, including dirty/clean navigation, themes and mobile editor |
| Actual Chromium PDF output | Baseline V20 and V21 synthetic quotation text/layout matched exactly |
| Dependency/source checks | `pip check`, Python compilation and diff whitespace checks passed |

The focused suite includes checks added after the 307-test full run; these are not additional distinct tests to sum with the full-suite count. Logs are in `v21-measurements/`.

## Live-copy behavior verified

- Existing V20 login/password hash, role, permissions, quotation content and SMTP configuration survive the copy.
- Source schema stays 17; only the V21 copy becomes schema 18.
- SHA-256 maps of original database/attachment/document/export contents remain unchanged, including after subsequent edits in V21.
- Documents, attachment files and exports are copied into independent V21 roots; saved customer export folders resolve to the copied PDFs.
- Old SMTP backlog is cancelled in the copy, leaving its source state unchanged and retaining the configured policy for new messages.
- Repeat setup preserves an existing live copy and does not overwrite it from V20.
- Occupied port, unknown source schema, linked external storage and failed import paths stop publication; failure cleanup affects only new targets.
- The live launcher ignores earlier test profiles in favor of its live profile.
- The label-free dependency installer creates/reuses its virtual environment in paths containing spaces and rejects missing release files.

## Live browser scenarios

Using a synthetic V20 workspace copied by the real import code and the live app configuration (background workers suppressed), Chromium verified: existing account login; Live footer identity; authenticated feature manifest; copied quotations; dashboard attention; visible What's new page; copy link; favorite; quotation Controls/More links; saved internal notes; reminder button/live messaging; pre-send panel; customer activity timeline; mobile dark layout; unchanged V20 fallback files. Desktop and mobile screenshots were visually reviewed.

Existing calculation, approval, export, account/session, CSRF, document safety, backup/recovery and permission regression suites remain in the full run. The quotation editor body/structure was not redesigned. The historical performance measurements apply to the V21 core and include raw samples/limitations; they do not measure first-time live copying of a real dataset.

## Limitations and unresolved external actions

Windows CMD/PowerShell, actual IIS/service startup/recovery, Windows/UNC ACLs, the installed Edge renderer, real SMTP delivery and full Windows restore/rollback are **unexecuted here**. Linux logic, socket and browser verification is not a claim of Windows end-to-end validation. Existing baseline test file-handle ResourceWarnings remain non-failing.

GitHub authentication is invalid, so no new private remote or GitHub URL is available. Completed source is committed in the separate local V21 repository. The original V20 source checkout remains clean. The downloadable ZIP excludes `.git`, virtual environments, actual databases, credentials and customer files; setup copies your data only on your own server. The ZIP's BAT/PowerShell entries are checked for CRLF line endings and the embedded build manifest identifies the committed release.

Reproduce the full suite with `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`, the focused suite with pattern `test_v21*.py`, and the browser check with `tests/v21_live_browser.py` in this Linux environment. For the server, follow `START-HERE.txt` and `VERSION-21-INSTALL.md`.
