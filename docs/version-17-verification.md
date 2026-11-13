# Version 17 — verification and implementation summary

Development environment: Linux, Python 3.12, SQLite, Waitress and real headless
Chromium. All accounts, quotations, attachments and email addresses in checks were
synthetic. The company's Windows VM and live database were not accessed. No real
email was sent and nothing was deployed to the VM.

## Automated checks

- **263 unit/integration tests passed**, including 18 Version 17 tests and the
  existing quotation, catalog, customer, account, approval, reference, deployment,
  SMTP, backup, privacy and file-isolation suites.
- Real Waitress/Chromium acceptance passed: draft save/submission; two independent
  operations decisions; commercial completion; immutable PDF capture; administrator
  sent dialog; recorded actor/recipient/method/revision; sent listing date/filter;
  four reports; historical sent values after a new revision; period/customer/owner
  filtering; actual report PDF folder test, generation and authorized download;
  individual archived deletion covering both revisions and their tracked external
  files; unrelated file/folder/report and issued reference retained.
- Browser email capture: **3 submission + 4 fully approved + 4 sent messages**.
  Sent recipients were the creator and selected approvers, excluding the acting
  administrator and customer. No individual-decision/stage-ready emails, and no
  extra email on refresh. The SMTP transport was replaced by atomic local capture;
  production queue, recipient checks and HTML/plain-text rendering ran normally.
- Unit checks also covered shared addresses differing in case, failed sent-email
  delivery and explicit administrator retry, SMTP-disabled sending records,
  missing fields/PDF, unauthorized actions and idempotent repeated confirmations.
- Deletion checks covered approved/sent/discussion records, all workflow children,
  costing and attachments; multiple families with one locked-file failure; durable
  per-family retry/results; unauthorized retry; in-flight PDF generation after
  deletion; reference reservation and audit retention. Existing accepted-Won and
  contract-link guards remain covered by earlier tests.
- Report checks covered a 36-month quotation still reporting **USD 100/month plus
  USD 50 one-time**, latest-revision family deduplication, pending reviewer counts,
  exact sent snapshots, customer reassignment history, optional service exclusion,
  missing prices, legitimate zeros, non-USD exclusions, invalid date filters,
  viewer/private-record permissions, revoked-source download access, failed PDF
  rendering, unique filenames and collision protection preserving an earlier PDF.
- Report preview CSS was checked against the existing Content Security Policy;
  printable pages use a static stylesheet, while server-rendered PDFs embed the
  same stylesheet. Existing security headers were not weakened.
- The existing Version 14 browser regression also passed against Version 17:
  one/multiple/overlapping support selections, percentages and inline quantity
  recalculation, save/reopen, editable headings, dollar formatting, full red/white
  total row, actual white customer PDF, account safeguards and retained attribution.
- Supplied-source migration check passed: **all 64 existing tables unchanged** on
  schema 15 → 16; accounts, settings/SMTP, approval history, approved PDF and original
  attachment retained; repeat migration safe; legacy sent events created without
  replay emails; SQLite integrity/foreign keys valid; schema-16 full backup restored
  with matching tables/attachment; older source rejected the upgraded schema.
- Python compilation, new JavaScript syntax checks, `pip check` and
  `git diff --check` passed. No dependencies were added. Some inherited tests emit
  non-failing resource warnings for test download handles; no test failed.

Reproduction from an environment containing the existing requirements:

```text
python -m unittest discover -s tests -p "test_*.py"
python tests/v17_browser.py
python tests/v14_browser.py
python tests/v17_migration.py PATH_TO_EXTRACTED_SUPPLIED_VERSION_16_APP
python -m compileall -q workspace_app tests run.py scripts
python -m pip check
node --check workspace_app/static/sent_tracking.js
node --check workspace_app/static/reports.js
```

Browser harnesses use `/usr/bin/chromium`, temporary synthetic databases, local
ports and local SMTP capture. The V17 harness writes evidence to
`CW_BROWSER_ARTIFACTS` or its documented development default. They are development
checks, not scripts to run against the company's production database.

## Rendered inspection

Inspected report register, pending/overview/sent tables, sent dialog and internal
email, deletion confirmation/results, both portal themes at **1536 × 1024** and
**390 × 850**, plus settled theme colors and the mobile drawer transition. No page
horizontal overflow; wide report tables scroll within their container. Report filters
show only date controls relevant to the selected period. The report preview and
actual A4-landscape PDF were inspected; the sample PDF has one page and keeps a
white professional document surface. The existing customer quotation PDF remains
white even when the portal is dark.

These screenshots contain synthetic acceptance-test data, not live customer data:

- [Report register](images/version-17-reports.png)
- [Report register on a small screen](images/version-17-reports-mobile.png)
- [Sent-to-client internal email](images/version-17-sent-email.png)

## Modified files by purpose

| Area | Main files |
|---|---|
| Sent records, email and UI | `sent_tracking.py`, `approvals.py`, `approval_routes.py`, `notifications.py`, `approval_emails.py`, `templates/approval.html`, email template, `static/sent_tracking.js` |
| Archived deletion and cleanup | `quotation_deletion.py`, `archives.py`, `__init__.py`, confirmation/result/starter templates |
| Reports and PDF rendering | `reporting.py`, report templates, `static/reports.css`, `static/reports.js`, `static/report_document.css`, `automation.py`, Settings link |
| Monthly list/comparison and sent filters | `documents.py`, `comparison.py`, quotation-list/comparison templates |
| Schema/version/backup compatibility | `store.py`, `backup.py`, `run.py`, base footer, retained-handover manifest |
| Verification/documentation | `test_v17.py`, `v17_browser.py`, `v17_migration.py`, existing migration/backup expectation updates, README, version index and Version 17 guides/screenshots |

The quotation row-editor scripts, customer quotation template and pricing calculator
were not redesigned or rewritten. Shared server PDF printing was extracted from the
existing renderer without changing quotation HTML/CSS or calculation behavior.

## Limits and VM checks still required

- No Windows Server 2022/IIS service was available here. Verify actual service
  identity, NTFS/share/UNC access, locked-file behavior, existing bindings/hosts,
  installed Windows Edge/Chrome and upgrade/rollback on a test copy first.
- Outlook desktop was unavailable. HTML uses the existing inline table/VML design
  and a plain-text alternative, and was inspected in Chromium; actual Outlook and
  the company's SMTP relay still need a controlled internal test.
- A legacy creator/recipient/method that was never stored cannot be reconstructed.
  Missing historical details are labelled, rather than invented. Enabled SMTP and
  enabled active recipients with current access are required for email delivery.
- Permanent deletion retains pre-existing accepted-Won/contract dependencies; it
  removes tracked owned paths, not untracked manual copies. Cleanup failures require
  retry after the server's file access is corrected. Customer folders stay intact.
- External customer documents, quotation PDFs and report PDFs need their own paired
  filesystem backups. Standard full backups contain the database/attachments and
  external metadata, not those external bytes.
- Old aggregate report downloads are blocked if a source is deleted or access is
  revoked; the snapshot remains on disk. Recreate a report for current authorized
  data. Sent reports preserve historical events; monetary sums count each family
  once using its latest sent event inside the selected range.
- Existing saved customer quotation presentation, including an explicitly enabled
  12-month column, remains unchanged. New report PDFs and comparison summaries use
  monthly fees with one-time charges separate. Drafts are included in quotation
  activity/known fees, with their actual approval status and pricing gaps visible.

See the [upgrade, permissions, backup and rollback guide](version-17-upgrade.md).
