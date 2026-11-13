# Version 12 verification and remaining deployment checks

All tests use temporary synthetic accounts, quotations, files and SQLite databases.
No live business database or Windows VM was changed. No real emails were sent.

## Development environment checks performed

- **176 automated tests passed**, including the existing quotation calculations,
  explicit discounts, simplified output, revisions, references/concurrent
  reservations, sharing, internal costing, exports and full backup/restore suite.
- A database created using the actual v11 code at `f134dc9` was upgraded with v12.
  Existing records, password hashes/accounts, settings, general/customer catalogs,
  reference assignments, business outcomes, retained consumption and original
  attachment bytes remained identical. New saved-content versions were seeded
  without fabricating any approval rounds or decisions.
- New workflow checks cover independent parallel operations decisions followed by
  commercial approval, changes/declines with required reasons, explicit resubmission,
  reviewer replacement/revocation, live progress and duplicate-decision rejection.
- Saved-content changes invalidate prior approvals, restart the sequence and retain
  prior evidence. Unchanged saves and private-cost/business-status changes do not
  reset customer approvals. Stale saves/decisions are rejected. Save & submit is
  atomic even when reviewer selections fail validation.
- Reviewer-only grants allow quote editing without customer/project access or
  private costs/margins. Private fields survive reviewer edits. Raw attachments
  retain their prior sharing boundary. Read-only viewers do not see group messages.
  Revision creation retains scoped access without inheriting approval decisions.
- Replies, participant-only mentions, unread cursors, safe message rendering,
  idempotent message requests, notification ownership/deduplication, current-access
  link checks, actionable Dashboard counts and waiting-commercial counts pass.
- Disabled SMTP leaves portal actions intact; the actual sender refuses to contact
  SMTP in tests. Failure/retry is exercised with injected senders. SMTP credentials
  are not included in workspace exports. No external gateway was used.
- Approved snapshots/PDF bytes remain unchanged after edits, cannot be updated via
  normal database writes, and survive full backup/restore. Failed capture can retry;
  marking sent waits for its PDF. Previously approved customer-folder files cannot
  be overwritten by changed content using the same title.
- Consumption GET/POST/import entry points are retired; old snapshot/source/history
  data remains. Handover is administrator-only and contains retained records/files.
  Legacy tests now exercise retirement/preservation instead of expecting active
  consumption editing. Schema/manifest expectations reflect product 12/schema 11.
- Browser verification uses real **Waitress and Chromium**, multiple staff sessions,
  complete operations → commercial → retained approved PDF → manual sent workflow,
  live stage/discussion refresh, unsaved editor values surviving panel refresh,
  and unsaved discussion drafts surviving panel close/reopen.
  It downloads actual retained PDF bytes and generates a customer PDF. Customer
  paper stays white while the portal is dark.
- Light/dark screens were rendered and inspected at desktop **1500 px** and mobile
  **390 px**. The sidebar/drawer, quotation list, editor, customer/pricing, reports,
  approval/discussion pages and notification/theme controls were exercised. No
  JavaScript errors or page-level horizontal overflow remained in the browser run.
  System mode was also checked against emulated light/dark OS preferences.
- Release checks include Python compilation, JavaScript syntax, dependency
  consistency, whitespace checks and startup of a clean extracted application ZIP.

Reproduce the main automated suite:

```sh
python -m unittest discover -s tests -v
python tests/v12_browser.py
```

The browser helper expects development Chromium at `/usr/bin/chromium` and writes
screenshots to `/workspace/preservation`. It is not a Windows installation command.
Container PDF checks used the existing Linux-only `CIRRUS_PDF_NO_SANDBOX=1` option;
leave the normal browser sandbox enabled on Windows. SMTP was disabled for browser
tests with `CIRRUS_DISABLE_EMAIL=1`.

## Windows / IIS checks still required on your VM

These require your actual server/account/network and were not executed here:

1. Create and verify a pre-upgrade full backup. Extract v12 to a short path, run
   setup, retain the real external data path and verify existing records/accounts.
2. Verify the unchanged Waitress bind/port/service account, IIS HTTPS/proxy and
   allowed-host environment. Check login/logout and intended LAN access.
3. Use three existing staff accounts to configure real default reviewers. Test
   operations in parallel, commercial waiting/activation, stale reviews, changes,
   resubmission and permission boundaries with the team's actual sharing setup.
4. Confirm installed Edge/Chrome can capture approved PDFs under the service's
   writable temp directory. Test local/UNC customer-folder permissions, existing
   collision handling, approved filename protection and Retry on a locked file.
5. If email is wanted, configure SMTP/account addresses and the explicit internal
   portal URL. Provision its password in the **Waitress process environment**.
   Perform an authorized test with your actual mail service and verify TLS, sign-in
   links, VPN/internal reachability, failure status and careful manual retry.
6. Test Light/Dark/System with the team's supported Windows browsers and keyboard
   navigation. Confirm manual customer PDF/Excel presentation and the earlier
   simplified summary remain correct with your real templates.
7. Download a new full backup, restore into a new directory, and check accounts,
   attachments, retained consumption, decisions/messages and approved PDF hashes.
   Check daily/weekly retention and separately back up the external quotation disk.
8. Export the retained consumption handover and let the receiving team validate its
   real workbook/data conventions. No missing sample workbook is invented or seeded.

## Practical limits

SQLite and the existing single-instance Waitress deployment remain. This release
does not claim a production concurrency/load benchmark or Windows/SMTP certification.
Polling is lightweight and permission-filtered, not a real-time push service. SMTP
delivery can be uncertain after disconnects; portal notifications remain the
authoritative workflow record. Approved PDFs increase database/backup size; the
existing 5 GiB restore limit still applies. Default reviewer selection is explicit
configuration, not an imported directory/group-membership integration.
