# Cirrus Workplace Version 17 — upgrade and operation

Version 17 uses **SQLite schema 16**. This is an additive upgrade from the supplied
Version 16 deployment ZIP (schema 15). No runtime packages, account initialization,
SMTP credentials, data paths, IIS rules or Waitress bindings change. Do not run
`init-admin` during an upgrade. Nothing is deployed automatically to the company VM.

## Verified source

The supplied `codex-test-lab-version-16.zip` has SHA-256
`ed1ac8d80ac3aefcccd8475fcad7e5b989c40a98d1b9cf885085ebdf87f4d80e`.
Its internal folder/branding say Version 15. Its application files match commit
`303e1e4446a9bdf65c6ad989b740111c2a3465a4`, including the latest email/studio controls.
Version 17 builds on that actual uploaded code; no newer VM code was discarded.
The `version-16` Git ref records that supplied baseline without rewriting its files.
Product version numbers and SQLite schema numbers are intentionally different.

## Before switching the Windows service

1. In **Settings & backups**, download a full backup. It contains a consistent
   SQLite backup, referenced `attachments`, account records, settings, approval
   snapshots/PDFs, sent history, report metadata and retained consumption history.
   Treat it as confidential. Verify the ZIP opens; keep a pre-upgrade copy.
2. Stop Workplace/Waitress using the deployment's existing service/console method.
   Back up the entire existing external data directory while stopped, plus
   `%ProgramData%\CirrusWorkplace\deployment.json` (or `CIRRUS_DEPLOYMENT_FILE`).
   Preserve the service's environment and SMTP password environment variable through
   your normal protected configuration backup; never put secrets in this repository.
3. Separately back up the configured **Customer Documents**, **quotation PDF** and
   **Reports** filesystem roots. These external bytes are **not included** in the
   application's full-backup ZIP. Copy them while stopped, together with the database
   backup, to preserve file ownership/metadata consistency. Keep the backup destination
   separate from those working folders. The daily application backup has the same
   external-folder exclusion; schedule filesystem backups separately.
4. Keep the previous source folder/virtual environment for rollback. Extract the
   full Version 17 ZIP into a new, preferably short folder, for example
   `C:\Apps\Cirrus-Workplace-V17`. Do not extract over the database or external folders.
   Run `setup.bat` for that release's virtual environment, using the same supported
   Python installation. Dependencies are unchanged. Do not copy a virtual environment
   from another path or reinstall unrelated packages.
5. Retain the **exact existing** `CIRRUS_DATA_DIR`/`JOSEPH_DATA_DIR` and Windows service
   account. The default historical data path remains
   `%LOCALAPPDATA%\JosephWorkspace`; do not rename it for branding. Use the existing
   explicit service data path, especially if setup is run as a different Windows user.
   An unexpectedly empty login/workspace indicates the wrong account/data path; stop
   and correct that path, rather than creating fresh accounts.
6. Point the service command/working directory at the new release and start it using
   the existing launcher. `start.bat` continues loading persistent deployment JSON
   outside the release. Administrator environment overrides still win. Retain allowed
   hosts, bind, port, trusted-proxy, HTTPS/internal-access and time-zone settings.
   Keep IIS reverse proxy and server bindings unchanged. Do not open a second
   Workplace process on the same database.
7. First startup migrates schema **15 → 16** transactionally. Existing records are
   retained. Existing sent flags become legacy sent-history entries; missing historical
   recipient/method values are labelled **Not recorded**, and no old emails are replayed.
8. Sign in with existing accounts. Confirm quotations/customers/attachments and the
   expected external data path, then perform the deployment checks below.

Persistent deployment JSON continues supporting, for example:

```json
{
  "CIRRUS_ALLOWED_HOSTS": "localhost,127.0.0.1,172.18.69.10"
}
```

Retain your existing additional settings; this example is not a replacement file.

## Reports folder and report rules

An administrator opens **Reports → Reports folder settings** (also linked from
Settings), enters an existing absolute Windows path such as `F:\CirrusReports` or a
UNC path, then uses **Test folder access** and **Save Reports folder**. This value is
stored in the existing external SQLite database, not the version folder. Keep it
separate from code, data, Customer Documents, quotation PDF and backup roots.

The Windows account running Workplace/Waitress needs **Modify** rights: read,
create, write, rename and delete temporary files. For a UNC share, grant both share
and NTFS rights and network access to that service identity. Interactive drive
mappings may not exist for services; use an accessible UNC path where appropriate.
IIS's browser user does not access this path directly. Local report/PDF rendering
uses the existing installed Edge/Chrome or `CIRRUS_PDF_BROWSER` executable.

Choose one of four reports, its period/customer/owner filters, and apply them.
**Preview printable report** shows the actual report styling. **Generate & save PDF**
creates a timestamped, unique PDF and provides an authorized download link; no earlier
report is replaced. Folder/rendering failures are shown without a partial final PDF.
Saved PDFs remain fixed snapshots. Regenerate a report for newer data.

| Report | Date basis | Monetary/count basis |
|---|---|---|
| Management overview | Creation for activity/fees; submission for pending; recorded sending for sent; outcome date for Won/Lost | Latest accessible revision per family; pending/sent counts once per family |
| Quotation register | Earliest accessible family creation date | Latest accessible revision; creator, document date, separate monthly/one-time fees |
| Pending approvals | Latest active submitted round's submission date | One row per accessible family, remaining reviewers and calendar days waiting |
| Sent quotations & follow-up | Recorded sending date | Exact sent revision/PDF; all event rows, with fee summaries using latest event per family in range |

All new monetary summaries/report PDFs and comparison cards use **Quoted monthly
fees — USD/month**, directly from saved recurring charges, with **one-time fees
separate**. A year/quarter filter selects records; it never multiplies fees by 12 or
contract duration. Optional services are excluded; saved explicit discounts still
apply. Missing prices are flagged, genuine zero is valid, non-USD and cancelled
amounts are excluded from USD sums and disclosed. Known sums can be partial; they
are neither revenue nor payments. Report owner filters use current record ownership;
sent customer filters use the stored historical customer. Access is evaluated before
revision grouping, so a hidden newer revision does not disclose private information.

Report downloads require the generator or an administrator **and current access to
all source records**. If a source is deleted or access is revoked, the old aggregate
PDF remains on disk but its portal download is blocked. Generate a new authorized
report. Filesystem access to reports is separately controlled by Windows ACLs.
Customer quotation documents keep their existing saved layout, calculations and
optional 12-month presentation; the monthly reporting rule does not rewrite them.

## Sent to Client

On **Approval & discussion**, a fully approved quotation offers **Mark as sent to
client**. Enter recipient name/email, Email/WhatsApp/Other and optional notes. Email
method requires an email address. The immutable approved customer PDF must finish
capturing first; its existing Retry action handles capture failures.

Confirmation records the acting account, timestamp, reference, exact quotation
revision, recipient/method/notes, approved snapshot and PDF hash. It **does not send
the customer anything or verify delivery**. History remains on the approval page;
quotation lists include sent date and a **Sent date** filter basis. Later edits or
revisions do not rewrite the event/PDF. Sending is recorded once per approved round;
repeated identical requests are idempotent, and differing repeated details cannot
overwrite history. A later approved round can have its own sending record.

SMTP reuses the configured host/port/security (including None), sender, secret
variable, explicit base URL, account addresses and delivery worker. The three email
milestones are:

- Submission: selected approvers.
- Fully approved: actual submitter plus selected approvers.
- Sent to Client: **original quotation creator plus selected approvers**, irrespective
  of who records sending. Subject: `Sent to Client | Client | Reference`.

Users and shared addresses are deduplicated per milestone. No intermediate approval,
comment or stage-ready email is added. Portal notifications continue. Email HTML and
plain text contain customer-facing metadata, never internal costs/margins, quotation
internal notes or sending notes. Sent emails explicitly say the acting user **marked**
the quotation as sent; recipient details are descriptive, not SMTP recipients.

Accounts need active, enabled notification addresses and current quotation access.
Legacy quotations without a recorded creator cannot reliably identify one; they do
not substitute an unrelated current owner. SMTP-disabled operation still records the
event and portal notifications. Failed delivery does not undo sending; administrators
can Retry through Approvers & email. As with existing SMTP, a relay disconnect after
acceptance can leave delivery uncertain: verify receipt before a deliberate retry.
Recipients require normal sign-in and internal network/VPN access.

## Permanent archived-family deletion

Use **Delete permanently** on one archived row, or select families and use **Bulk
actions → Delete selected permanently**. Confirmation lists the families and every
revision, and requires `DELETE`. Edit permission on **every revision** is enforced
on the server. Existing accepted-Won/contract-linked retention safeguards still
apply: reopen the outcome or resolve the contract dependency first. Approval,
submission, discussion and sent history by themselves **no longer block deletion**.

Deletion removes selected families, revisions, attachments, private costing and
workflow/notification records. It cancels their queued jobs and retains deletion
tombstones so an in-flight export or stale save cannot recreate them. Audit entries
and reference registry/reservations are preserved; permanent archived deletion does
not make an issued/reserved number available to another document.

Only **tracked quotation-owned paths** are removed from external storage, including
previous tracked PDF destinations. Customer folders, unrelated files, reports and
untracked manually copied exports are never swept by filename/glob. Existing
symlink/junction/hardlink safeguards remain. If an owned file is locked/unreachable,
the database deletion remains complete but that family's result is **Cleanup pending**
with its exact error. Fix permissions/locks and use **Retry file cleanup** on the
results page, also available at `/quotation-deletions`. The deleting authorized staff
account or an administrator can retry. Results distinguish complete and pending
families; failures are not reported as complete. Retrying removes only remaining
owned files. Coordinate restoration with external-folder backups if deletion must
be undone; deleted PDFs cannot be reconstructed from a post-deletion database.

## Rollback and Windows acceptance

Stop the new service. Restore the **pre-upgrade** backup into a new data directory
using the existing backup tool, or restore the stopped whole-directory copy. Restore
matching external-folder copies if needed. Restore the old service command and
point it at that restored pre-upgrade data path. Never run the older application
against a schema-16 database; it deliberately refuses a downgrade. Start one process,
then verify accounts, attachments and quotation PDFs. Do not overwrite the only
backup or a live database while restoring.

Before production use, on the actual Server 2022/IIS service account:

1. Verify persistent host/bind/port/proxy/data settings, existing logins and permissions.
2. Test reports-folder access, preview, Edge/Chrome generation and portal download.
3. Run an approved test quotation through sent confirmation, checking real configured
   internal email delivery and Outlook rendering; do not send the customer anything.
4. Test archived deletion on disposable records with both revisions and external PDFs;
   deliberately lock one file, verify pending status, unlock and retry. Check unrelated
   customer files remain. Confirm UNC permissions where used.
5. Download/restore a test full backup and verify the separately backed-up external
   folders. Check both light/dark portal themes and a smaller laptop screen.

Development checks and their limits are recorded in
[Version 17 verification](version-17-verification.md).
