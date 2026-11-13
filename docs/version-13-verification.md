# Version 13 verification and remaining Windows checks

All tests use temporary synthetic databases/accounts/files. No live VM or business
database was changed. **No real emails were sent.**

## Development verification

- **195 automated tests passed**, including the existing quotation pricing,
  discounts/simplified customer output, revisions/references, access permissions,
  immutable snapshots/PDFs, discussion/notifications, exports and full backup/restore
  checks.
- **19 Version 13 tests** cover draft selections with no notifications; one, three and
  four approvers; multiple commercial approvers; Operations-only and Commercial-only
  rounds; all-selected approval; concurrent submissions/decisions; requests for
  changes/declines and resubmission; duplicate/inactive selections and stale edits.
- Shared progress tests verify two green and one white dot across list, Dashboard,
  customer and approval views, including name/date details and keyboard focus.
  Selection changes and content edits remove current approval credit while retaining
  old decisions. Notifications go to the selected current participants; new people
  are not assigned while merely saving a draft/changed selection.
- Combined Customer/search/date/type/owner/status filters were checked with
  pagination and bulk matching: exactly the 26 matching families were archived,
  leaving the other customer's records active. Count/value columns retain USD and
  latest-revision rules, including non-USD and unpriced records.
- Persistent settings tests cover first creation outside the application directory,
  environment-over-file precedence, preservation across restarts/releases, invalid
  files, host validation and startup-loader ordering. Windows path construction is
  tested with an injected ProgramData directory; no Windows server is emulated.
- SMTP tests inject mock transports at different arbitrary hosts/ports. None opens
  ordinary SMTP without TLS or authentication when the username is blank. STARTTLS
  and SSL use their respective transports with certificate contexts. The portal
  saves None with a nondefault relay port; existing failure/retry and disabled-email
  behavior remain covered. No real SMTP endpoint was contacted.
- A database created using the **actual v12 commit `15323ec`** was upgraded. Every
  original column value in every original table remained identical, including two
  real review rounds, immutable decisions/PDF, SMTP configuration, account hashes,
  private records and attachment metadata. Attachment bytes were unchanged. Current
  progress correctly remained **1 out of 3** in the original approver order.
- Real Waitress/Chromium verification creates a quotation through New Document,
  changes/reorders the selected defaults, saves without notifications, submits,
  approves two Operations reviews and shows **2 green / 1 white**. It exercises
  the keyboard tooltip, Dashboard/customer summaries, searchable Customer filter,
  explicit resubmission with four approvers and full approval. It downloads an
  actual retained customer PDF and saves None SMTP settings with email disabled.
- Desktop **1500 px** and mobile **390 px** screens were rendered and inspected in
  light/dark themes. Approvers sits beside the creation form on desktop and stacks
  on mobile. Dots remain visible; no page-level horizontal overflow or JavaScript
  errors were observed. Customer print paper remains white with the portal dark.
- Python compilation, all **18 JavaScript files**' syntax, dependency consistency
  and Git whitespace checks pass. A clean extracted deployment archive starts with
  product 13/schema 12; Dashboard, New Document, Quotations, Customers, Approvals and
  settings render successfully using an external persistent settings/data path.
  The configured IP host is accepted and an unlisted host is rejected. The archive
  contains source/deployment files, with no live database, attachments, accounts,
  virtual environment or environment-secret file.

Reproduce the main checks using the configured development environment:

```sh
python -m unittest discover -s tests -v
python tests/v13_browser.py
python -m compileall -q workspace_app scripts run.py
```

The browser helper uses development Chromium at `/usr/bin/chromium` and writes
screenshots under `/workspace/preservation`; it is not a Windows setup command.
Browser test SMTP is disabled with `CIRRUS_DISABLE_EMAIL=1`.

## Required checks on your Windows VM

These require the actual Windows account, IIS, network and disks and were **not**
performed in this Linux development environment:

1. Take/verify the pre-upgrade backup. Install into a new short path, preserve the
   external data directory and service identity, and confirm existing records.
2. Create/read the external deployment JSON under the actual service account.
   Start through `start.bat`, restart the process/VM and confirm allowed hosts load.
   Verify an inherited administrator override wins. Switch release folders and
   confirm the same file/settings load. Retain IIS hosts, HTTPS, proxy, bind/port.
3. Run the team's real selected-approver scenarios, including different counts,
   parallel Operations reviews, Commercial waiting, declines, resubmission and
   editing permissions. Check real sharing and private-margin boundaries.
4. Verify None against the intended IP-authorized relay's actual hostname/IP/port
   and service-account/network policy, then STARTTLS/SSL if used. A real email test
   should be deliberate and addressed to your staff. Verify links/login, failure
   reporting and Retry; portal actions must survive mail failures.
5. Confirm installed Edge/Chrome PDF capture, customer-folder/UNC permissions,
   title collision protection, retained PDFs and automatic exports under the
   service account. Verify Light/Dark/System in supported Windows browsers.
6. Download a fresh full backup and restore into a new test directory. Confirm
   approver selections/history, accounts, attachments and settings. Check scheduled
   backup destination/retention and separately back up external configuration/PDFs.

## Limits

This retains the existing single-instance SQLite/Waitress model and polling;
it is not a production load benchmark or Windows/IIS/relay certification. One
quotation supports up to 100 distinct approvers; rendering many dots naturally
wraps. Completed approval evidence still increases database/backup size and the
existing 5 GiB restore archive limit remains. SMTP cannot guarantee exactly-once
delivery after an ambiguous disconnect. No installer/updater or automatic live
deployment has been introduced.
