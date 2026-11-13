# Cirrus Workplace Version 12 — upgrade and workflow guide

This extends the complete v11 application (`f134dc9`). Branch:
`feature/cirrus-workplace-v12`.

Download while signed into the private repository:
https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/feature/cirrus-workplace-v12.zip

## Safe Windows / IIS / Waitress upgrade

1. Use the current administrator **Download full backup** action. Record the
   actual external data path, service identity, environment, source folder and IIS
   configuration. Stop the Python/Waitress service before changing code folders.
   An offline alternative from the old application with its existing environment is:

   ```bat
   .venv\Scripts\python scripts\backup.py backup D:\Backups\before-v12.zip
   ```

2. Extract into a **new short path**, such as `C:\CirrusV12`. Do not overlay the
   live data directory or copy the old `.venv`. Run the included `setup.bat` to
   create the new environment. Requirements are unchanged from v11; SMTP uses the
   Python standard library. Installed Edge/Chrome remains the PDF renderer.
3. Keep the **same external data directory** and Windows service account. Preserve
   `CIRRUS_DATA_DIR` or the accepted legacy `JOSEPH_DATA_DIR`; if both are set they
   must identify the same directory. Without an explicit setting, the account's
   existing `%LOCALAPPDATA%\JosephWorkspace` database is reused, otherwise
   `%LOCALAPPDATA%\CirrusWorkplace`. Do not guess a new path or change accounts and
   assume LocalAppData resolves to the same folder.
4. Preserve your current `CIRRUS_BIND`, `CIRRUS_PORT`, `CIRRUS_ALLOWED_HOSTS`,
   `CIRRUS_INTERNAL_ACCESS`, `CIRRUS_HTTPS`, `CIRRUS_TRUSTED_PROXY` and timezone.
   Keep IIS host preservation, HTTPS, reverse-proxy rules and service bindings.
   Point the existing service at the new source/virtual environment, or use the
   existing `start.bat` flow. **Do not run `init-admin` during an upgrade.**
5. Startup transactionally adds **schema 11**. It retains existing SQLite records,
   accounts, ACLs, settings, references, customer/project IDs, tenant catalogs,
   contract/outcome snapshots and attachments. It adds saved-content versions,
   approval rounds/decisions/grants/evidence, discussion/read cursors, per-user
   notifications, email outbox and theme preferences. Existing quotations start
   with no fabricated approval decisions; their older business statuses remain.
6. Sign in as administrator, configure reviewers, verify old quotations/pricing
   and test one review round with existing staff accounts. Follow the Windows
   verification checklist before switching normal team use to the new source.

No live deployment is performed by this release. For rollback, stop the new app,
restore the **pre-upgrade** full backup into a new external directory using the
matching old code and restore the old service configuration. Do not run v11 code
against schema 11 or overwrite the upgraded live database with a test database.

## Reviewer configuration and permission boundaries

Open **Administration → Approvals & email**. Choose two operations reviewers and
one commercial reviewer from existing active Editor/Administrator accounts. All
three must be different accounts. No names or new accounts are installed by the
application. Leaving all defaults blank removes defaults. They apply to future
submissions, not existing rounds.

An owner/administrator or staff member with an existing quotation edit grant can
select reviewers for an individual submission. Reviewers receive a separate,
quotation-only edit grant. It does **not** grant the underlying customer, project,
other revisions, private records or internal margin worksheet. Purchase costs and
private notes are redacted from reviewer-only editor/workspace JSON data, and
preserved server-side when those users edit the quotation. Existing ordinary
sharing permissions continue to apply separately.

Raw quotation attachments retain ordinary sharing permissions because they may
contain supplier/internal documents. A workflow-only grant does not expose or
allow deleting those files. Customer-facing print/Excel output and retained approved
PDFs are available with quotation access. Read-only quotation viewers can inspect
approval progress/history, but cannot read group discussion messages or decide/edit.

Reviewers creating a new quotation revision receive scoped access to that new
revision; approval decisions are never inherited. Existing author ownership and
private prices/costs remain with the source's established permissions.

Previous workflow participants retain a scoped grant for discussions/history until
an authorized manager removes it in **Previous workflow participant access**.
Reassign a current reviewer first. Removing a workflow grant does not revoke
independently assigned owner/project/sharing permissions. Notification links and
email jobs recheck current access. Inactive/demoted accounts do not count as
actionable reviewers; select replacement staff and restart review explicitly.

## Preparation, approval and changes

1. Prepare the quotation in the existing editor. Expand **Approval reviewers &
   submission**, select reviewers and use **Save & submit for review**. Saving
   content and creating its approval round happen in one write transaction.
   Invalid reviewer selections roll back both operations while retaining editor
   inputs. The standalone approval panel can also submit the latest saved version.
2. Both operations reviewers can decide independently and in parallel. Their
   responsibilities are technical scope, services, quantities and related details.
   Commercial is **Waiting** until both approve the current saved content version.
3. Commercial then reviews payment terms, validity, layout, wording and presentation.
   Each reviewer may Approve (optional comment), Request changes (explanation
   required), or Decline (reason required). A decision is immutable within that
   round; corrections use a new round, preserving the original discussion/evidence.
4. A change request/decline stops that round. Correct content and use **Resubmit**
   or Save & submit; all required decisions must be obtained again. To change
   reviewers without changing quotation content, use **Change reviewers / restart
   review**, with a reason. This also resets all three required decisions.
5. Only three approvals of the **current saved content version** show the green
   Approved by all state. This state is separate from Draft/Sent/Won/Lost business
   outcomes and from archive visibility. An unchanged save, discussion/read action,
   private-cost/private-note edit or business-status change does not reset customer
   approvals. Customer-facing scope, pricing, quantity, wording, terms, validity,
   branding/layout, reference/title or other document changes do reset them.
6. Edits during active/completed review preserve previous rounds and automatically
   restart operations review for the new content version when assigned accounts
   remain valid. Otherwise update reviewers and resubmit. After changes-requested
   or declined rounds, resubmission is deliberate. Previous decisions are labeled
   as previous-round/version evidence. Participants receive reapproval notifications.
7. Stale editor submissions cannot overwrite a newer save. Stale approvals cannot
   approve a newer version using an older open panel. Entered quotation/comment
   values are retained on validation errors; review the updated saved document.

Content versions are separate from quotation revision numbers. Editing revision
V1.0 can produce multiple content versions and review rounds. A new quotation
revision starts its own approval history. Field-level before/after evidence, actor
and UTC time are retained for customer-facing edits; private margins remain in
their separate staff tools.

## Approved evidence and recording a send

When all approvals complete, an immutable saved-content snapshot is retained and a
background job captures its customer-only PDF. It renders that frozen snapshot,
even if someone edits the current quotation meanwhile. The snapshot and final PDF
bytes/hash are retained **inside SQLite**, included in full backups. Database
triggers prevent updating an already retained snapshot/PDF or recorded decision.
The manual current quotation PDF/Excel functions remain available.

The approval history provides **Approved snapshot** and **Retained approved PDF**
downloads. Capture failures leave approvals/saved data intact and show **Retry
approved PDF capture**; administrators also see failure attention on the Dashboard.
The approved PDF must be captured before an authorized quotation manager can
**Mark as sent to client**. This records the account/time and protects reference
usage. It sends **nothing to the customer**. Later editing preserves the previously
approved/sent snapshot and PDF and starts reapproval for the new content version.

Approval/discussion history prevents permanent deletion of that quotation. Archive
it instead. Existing deletion safeguards for Won/contract-linked revisions remain.

Automatic customer-folder exports remain separate working copies, using your
existing root/customer mappings, title filename, collision checks, atomic writes
and Retry. Once a current customer-folder copy is approved, its path is protected
too. Changed content with the same filename fails clearly: **change the editable
title for the new version and Retry**. The old approved file is not overwritten,
moved or deleted. Existing unrelated names and different revisions remain protected.
Unchanged saves leave a protected existing file intact. If it is missing, recovery
uses the retained approved PDF once capture succeeds.

## Discussion, notifications and themes

**Approval & discussion** opens inside the quotation editor without replacing its
unsaved quotation state. The standalone approval page shows responsibilities,
progress, decision times/comments and previous rounds. Discussion supports replies
and @mentions chosen from authorized active participants. Messages render as text,
not HTML; cross-quotation reply targets/unauthorized mentions are rejected. Client
request IDs make retried message submissions idempotent. Workflow events are
visually separated from messages with expandable before/after changes.

Discussion/stage state polls every five seconds; the bell and actionable sidebar
badge poll every fifteen seconds while visible. These refreshes do not overwrite
editor values, discussion drafts or decision tokens. New content shows an explicit
review-updated-version prompt before decisions. Discussion read cursors and portal
notification read state are independent, per-account data. The bell and full
Notifications page provide current-access links and Mark as read / Mark all as read.

The Dashboard shows **My pending approvals** and **My submitted quotations**.
Approvals filters distinguish actionable Pending from Waiting, Approved, Changes
requested, Declined and Submitted by me. A commercial assignment is not an
actionable pending review until both operations approvals exist.

The left sidebar includes Quotations, Approvals, Customers, Projects, Service
Catalog, Hosting VMs / Customer Pricing and Reports. Workspace tools retain archives,
references and portability; administration/settings/backups remain restricted.
Desktop navigation collapses, the editor normally uses a narrow rail, and smaller
screens use a closable drawer. The visible Light / Dark / System choice is stored
per account. Portal themes do not enter customer document/PDF/Excel styles.

## Optional SMTP notification email

Email defaults to **disabled**. Portal notifications work regardless of SMTP.
Administrators configure the host/port, STARTTLS or TLS/SSL, From address, optional
SMTP username, password **environment-variable name**, explicit portal origin and
per-account email enablement/addresses. Set the password in the environment of
the actual Windows Python/Waitress service, typically `CIRRUS_SMTP_PASSWORD`, and
restart that service. Setting it only in an unrelated IIS pool/browser session is
insufficient. Passwords are never stored in the database, repository, workspace
JSON or full backups. SMTP configuration/recipient metadata is administrator data;
workspace JSON uses its existing allowlist and excludes it.

Set the explicit origin to your real internal URL, e.g.
`https://workplace.cirrus.local`. Links require normal login and current access;
there are no unauthenticated approve/decline actions. Internal hosting requires
network or VPN access unless you separately configure external access. Existing
allowed-host/bind/proxy restrictions remain; enabling email does not publish the
portal or change IIS.

Messages contain customer, quotation reference/title, action/update and a portal
link. Only configured account recipients are used; quotations are never emailed
to customers automatically. A durable outbox decouples email from saves, comments
and decisions. Failures are shown to administrators with **Retry delivery** and on
the Dashboard. Verify receipt before retrying an uncertain interrupted delivery:
SMTP cannot guarantee exactly-once delivery after a server disconnect. Interrupted
jobs are marked failed rather than blindly resent; portal events are deduplicated.

`CIRRUS_DISABLE_EMAIL=1` disables actual SMTP delivery for staging/development.
The production sender also refuses delivery when `app.testing` is true. All release
tests used disabled SMTP or injected memory senders; **no real emails were sent**.
SMTP verification under the real service account remains a VM check.

## Retained consumption handover and backups

Consumption is removed from customer tabs, active statistics, import/upload actions,
project/customer links and navigation. Old customer/project consumption routes,
including writes, return **410 Retired**. Their blueprints cannot be used to create
new monthly workbook records. Historical consumption tables, staged workbooks,
source attachments and audit history remain intact; shared VM catalog/pricing
initialization code is retained.

An administrator opens **Settings & backups → Retained consumption handover →
Export retained consumption for handover**. The consistent ZIP includes the legacy
and workbook snapshot/history/draft tables as JSON, original and staged workbooks,
source metadata, customer/project identities and actor usernames, with a checksum
manifest. Reporting periods and source Date remain separate/raw. It does not
delete records or export passwords, unrelated quotations or private margins.
Give this private archive to the other team through your normal approved process.

Full online/offline backups and daily/weekly retention remain unchanged and include
all new SQLite data/evidence plus attachments. Keep their destination separate from
PDF folders. Back up the service environment/IIS/certificates and external customer
PDF disk separately. Approved PDF blobs grow SQLite over time; the existing restore
archive limit is 5 GiB, so monitor backup size and plan server-level archival if
needed. Restore tests must use a new directory, never the live instance.

## Main implementation files

- `approvals.py`: schema/version evidence, rounds, decisions, scoped grants, audit,
  progress and actionable queues. `approval_routes.py`: panels, discussion,
  approval artifacts, reports and background immutable-PDF capture.
- `notifications.py`: per-user notifications/read state, preferences, SMTP settings,
  outbox and administrator retry. `retained_consumption.py`: handover archive.
- `security.py`, `store.py`, `quote_routes.py`, `costing.py`, `documents.py`,
  `archives.py`, `relationships.py`, `automation.py`, `backup.py` and `__init__.py`:
  save/access/migration/backup integration and approved external-file protection.
- Portal/approval/dashboard/customer/editor templates and `static/portal.css`,
  `portal.js`, `approval.js`, editor/submission scripts: navigation, themes,
  review/discussion UI and retirement of active consumption entry points.
- `tests/test_v12.py`, `tests/v12_browser.py`, existing regression fixtures,
  README/release guides and `run.py`: verification and release identification.
