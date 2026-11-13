# Version 15 — approval emails and studio controls patch

Base: `cc8a8ff` (Version 15, including the preceding compact UI patches).
Application branding stays **Version 15**. SQLite migrates **14 → 15** automatically.
No runtime dependencies, accounts, deployment bindings or SMTP credentials change.

## What changes

Email and portal notifications are now separate. Portal discussions, mentions,
decisions, stage-ready notices, change requests and approval dots continue normally.
Only two email milestones are queued:

| Stage | Recipients | Subject | Header |
|---|---|---|---|
| Explicit quotation submission | Selected approvers | `Review Required \| Client \| Reference` | Navy: Submission of New Quotation |
| All selected approvers approved | Submitter plus selected approvers | `Fully Approved \| Client \| Reference` | Green: Quotation Fully Approved |

The final recipient set uses the **actual submitter**, not an unrelated quotation
owner. Users and shared email addresses are deduplicated case-insensitively within
each round/stage. Submission includes commercial approvers even while they wait for
operations review; no extra email is sent when that stage becomes actionable.

Each message contains the client, reference, saved title, submitter, submission
time, quotation revision/saved content version, approval status and the selected
approvers. Final messages include each approval's decision time and completion time.
Times use `CIRRUS_TIMEZONE` (Asia/Beirut by default) and show the time-zone abbreviation.
Submission status is explicitly labelled as status **at submission**.

The **Review Quotation** button opens the normal authenticated approval page with
an anchor to that round's retained history. The sign-in/network/VPN footer and plain
URL remain available. No approval actions occur through email links, and nothing is
sent to the customer automatically.

Messages are `multipart/alternative`: plain text plus HTML. The HTML uses inline
styles, table layouts, explicit background colors, system fonts and an Outlook VML
button fallback. It has no scripts, remote images or dependency on portal themes.
Only an explicit metadata allowlist is rendered: quotation rows, internal notes,
costs, margins and reviewer/discussion comments never enter an email snapshot.

## Delivery behavior and duplicate protection

- SMTP stays optional. The existing configured hostname/IP, port, STARTTLS / SSL /
  None choice, blank relay username, sender, password environment variable and
  explicit portal base URL are reused unchanged.
- An approver needs an enabled account notification address. Accounts without one
  still receive portal notifications. Enabling SMTP later does not retrospectively
  email earlier submissions.
- A deliberate resubmission after changes requested/decline starts a new round and
  may send a new submission email. The existing approval workflow and reapproval
  rules are retained: ordinary content edits can reset the portal's review sequence,
  but **do not send submission email**. Full approval of the new saved round can
  send its one completion notification.
- Draft saving, opening either dialog, choosing approvers, page refreshes, discussion,
  individual decisions and unchanged saves do not trigger additional emails.
- Email batches and unique `(round, stage, normalized address)` recipients are
  inserted in the same SQLite transaction as submission/completion. Repeated or
  concurrent actions cannot enqueue another batch for that milestone.
- The background worker claims a pending job atomically and checks current record
  access, active account/address and approval-round validity. Superseded or already-reviewed submission requests are cancelled instead of
  sending a stale review request. Completion messages keep the frozen approved
  version and link to its retained round, even if a later edit started another
  review; the email explicitly limits approval to that saved version. Pending old-policy discussion/decision emails are retired during
  migration; sent email history and portal notifications are preserved.
- A corrected account email can be used at delivery/retry, subject to the same
  per-round recipient uniqueness. Failures remain visible in Approvers & email;
  the existing administrator Retry action is reused. Successful quotation saves,
  comments and decisions are never rolled back by SMTP delivery failures.
- Stable Message-ID values assist mail-client handling. As with any SMTP transport,
  a connection failure after the server accepted a message can leave delivery
  uncertain. There is no automatic retry of failed/running-after-restart messages;
  verify receipt before a deliberate administrator retry. Messages already handed
  to SMTP cannot be recalled after a subsequent quotation edit.

## Studio control placement

**Approvers & submission** is beside **Save quotation** and opens a dialog. The
same active-staff selector, add/remove/reorder controls, selected values and explicit
Save & submit action are reused. The dialog shows saved approval status and the
existing green/white dots. Unsaved selection changes have a separately labelled
white-dot preview for the next submission. Closing/reopening does not reset choices.

The dialog submits through the existing quotation form. An unsaved quotation is
successfully saved and versioned in the same transaction before its approval round
and email batch are created. Validation failure commits neither a partial quotation
nor an email. Duplicate/stale checks and existing approval-management permissions
still apply. Assigned reviewers who cannot manage approvers keep their existing
Approval & discussion access without gaining approver-management or private margins.

**Optional Monitoring** and **Show 12-month column** move into the right-hand
**Quotation options** pane. Their existing IDs, event handlers, saved document values
and calculation/preview behavior are retained. On desktop, Options collapses the
narrow pane; that preference is local to the signed-in user's browser. At 1100px or
narrower it opens a small Options drawer. The same controls move between locations;
they are not duplicated or reset on resize.

Internal row editing, keyboard behavior, split-pane resizing, customer pricing,
calculation methods, save endpoints and customer HTML/PDF/Excel layouts are unchanged.
The editor script has only a submit-event guard so a validation-cancelled action does
not suppress existing unsaved-change protection. Portal approval status refreshes
continue without replacing quotation inputs.

## Install on the existing Version 15 Windows / IIS deployment

1. Download a **pre-patch full backup**, keep the current application files, and
   preserve the external data path, service account and deployment settings.
   Separately back up external Customer Documents/PDF roots using the existing
   paired-backup procedure. Full application backups still exclude external bytes.
2. Stop Workplace/Waitress before copying files. Apply every runtime file listed in
   the patch's `INSTALL.txt` to the matching location in the existing Version 15
   application, or extract the latest full Version 15 ZIP into a new short folder.
   Do not replace the database, attachments, `.venv`, deployment.json or service secrets.
3. Restart with the same startup settings. Startup automatically adds
   `approval_email_batches` and `approval_email_recipients`, their uniqueness/immutable
   snapshot protection, and advances schema 14 → 15. Existing records/settings/
   permissions are preserved. Legacy unsent email jobs are marked cancelled so
   intermediate emails cannot unexpectedly replay under the new policy.
4. Refresh the browser with Ctrl+F5. Existing accounts remain valid. There is no
   `init-admin`, package installation, SMTP reset, IIS change or host/bind/port change.
5. Test one synthetic quotation with configured internal accounts/addresses on the
   Windows VM: submit, independently approve, complete, check Outlook HTML and plain
   text, check no intermediate emails, and verify both moved options. Check current
   permitted hosts, internal/VPN links and normal sign-in. No live VM deployment or
   real SMTP delivery was performed during development.

### Rollback

Stop Workplace. Restore the previous application files **and the matching pre-patch
schema-14 backup into a new external directory**, with matching external files if
needed. Point the existing service at that restored data and prior code, then start.
Older Version 15 code refuses schema 15 deliberately; restoring only old Python files
is not a valid rollback. Reconcile post-patch business changes separately.

## Verification

- **245 tests passed** in the final full unittest run, including **15 milestone email
  cases**. The suite covers staged/parallel approvals,
  submission and completion recipient sets, actual submitter, shared addresses,
  duplicate concurrent submits/final decisions, explicit resubmission, no intermediate
  emails, ordinary edit/stale-job cancellation, HTML escaping/private-cost exclusion,
  plain/HTML MIME, disabled SMTP, failures/retry, access checks and backup/restore.
- Real Chromium + Waitress, synthetic accounts, transport replaced by local capture:
  three submission emails; no messages for two individual approvals; four final emails;
  no extra email on refresh/unchanged save; one-approver unsaved save-and-submit;
  dialog selection retention, green/white progress, keyboard details, scoped reviewer
  permissions, optional/support calculation and saved options; desktop/mobile,
  light/dark, and customer PDF remaining white. No real emails were sent.
- Actual archived `cc8a8ff` schema-14 database with approved evidence, SMTP settings,
  accounts and attachments migrated twice. Every original business/settings/history
  value and approved PDF/attachment byte was retained; only legacy unsent email
  statuses changed. Post-migration full backup/restore matched, and old code refused
  the new schema safely.
- Outlook layout conventions and multipart MIME were checked; an actual Outlook
  client, Windows/IIS service, IP relay, TLS handshake and internal/VPN link routing
  still require deployment verification on your VM.

## Main runtime files

`approval_emails.py` (new milestone queue, safe rendering and recipient checks),
`notifications.py` (portal/email separation and multipart SMTP), `approvals.py`
(explicit submit/completion hooks), `store.py` and `backup.py` (schema 15 and restore),
`templates/email/quotation_approval.html`, approval-history anchors, quotation editor
template, `studio_controls.css/.js`, and the small quotation submit guard.
