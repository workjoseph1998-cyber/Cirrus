## Complete live carry-over release

Per the updated requirement, the default package is a live V21 installation on the existing Windows server, not an empty test workspace. Setup reads V20 configuration, locks/reserves the stopped source, creates a read-only SQLite snapshot, copies attachments/documents/exports, remaps stored destinations and migrates only the independent V21 copy. Existing accounts, prices, approvals, records, preferences and SMTP settings are retained. Prior-version email backlog is cancelled rather than replayed. Earlier test profiles are not launched; normal startup still never migrates.

Added clear Live/build identity in the footer, an authenticated feature manifest, and a visible What’s new in V21 guide. Internal notes, pre-send checks and approval/reminder links are exposed in the existing quotation Controls → More menu; the editor body/structure is unchanged. All previously agreed V21 additions remain included. Windows ZIP packaging retains the repaired label-free installer and verified CRLF scripts.

V20 remains the unchanged rollback copy. Work entered in V21 does not synchronize back to it. Live configuration copying and SMTP permission do not imply that real Windows/IIS or real mail delivery were executed in the development environment.

## Windows setup batch-label repair

Removed the CMD `call :install` subroutine that failed on the reported Windows server. The batch entry point now directly invokes a Python dependency installer and then the existing V21 account/storage setup. Windows release packaging explicitly converts all BAT and PowerShell files to CRLF inside the ZIP, independent of Git archive line-ending behavior. Fresh/repeat installer checks passed in paths containing spaces; missing release files fail without creating an environment. No V20 source/data changes.

## Setup/start correction

The Windows ZIP now follows the V20 install flow: run setup, create the initial V21 login when prompted, then run start. Setup creates the isolated profile/storage automatically and copies only available IIS/network policy from the existing deployment. Start discovers that profile automatically; no manual environment variable or initialization command is required. Reruns preserve recognized V21 data; no existing database is silently migrated. V20 stays on the same server as the installed fallback.

# Cirrus Workplace Version 21

Based on the latest available local V20 source, commit `63e5814` (including the V20 quotation margin-control refinement). All work is in a separate local repository and branch `feature/cirrus-workplace-v21`. The original checkout and remote were not changed. GitHub CLI authentication is invalid, so creation of `workjoseph1998-cyber/cirrus-workplace-v21`, remote publication and a new repository URL are unavailable.

## Workflow and navigation

- Copy direct quotation links from the list, editor, management and approval screens. Clipboard success appears only after copying succeeds; browsers without clipboard access get a selectable URL. Access remains governed by the destination's normal permissions.
- Validity badges show remaining days, Valid, Expiring Soon (today through seven days) or Expired; missing/invalid dates show a neutral state. Uses the configured local business date.
- Per-user quotation/customer favorites and last ten distinct successfully viewed records. Shortcuts are filtered against current permissions and existing records each time.
- Staff-only quotation notes, separate from approval discussion, retain author and timestamp. Notes are stored outside quotation content and excluded from PDF/Excel/CSV exports.
- Pending-approver reminders reuse portal notifications, SMTP configuration, the email queue and existing email template. One-hour cooldown is serialized in the approval transaction; only Pending decisions are selected. Delivery rechecks active users, access, current round and pending status. Reminder requests enter the existing audit stream; decisions are untouched. The V21 sandbox suppresses real SMTP delivery.
- Pre-send confirmation panel checks customer association, validity, calculable required pricing, all approvals for the current saved version, and the retained approved PDF. The same checks run server-side before recording sending; the existing recipient/method/sent-date workflow and immutable approved evidence remain authoritative.
- Customer activity combines visible quotation/document creation/revision metadata, existing document events, approval/sent events and customer document audit events without duplicating history. Shows the latest 250 events.
- Dashboard links/counts cover active latest quotation revisions, actionable pending approvals, quotations expiring within seven days and quotations sent this local month. Existing financial calculations remain unchanged; no new yearly totals were added.
- Global search covers accessible quotation/customer/project/document titles and metadata plus permitted external customer-document filenames. No content indexing or filesystem crawl. Up to 100 matches; normal download routes recheck access. Ctrl+K / ⌘K focuses search without losing form state.
- Ordinary edit forms use consistent dirty-state navigation protection, including radios and files. Existing specialized quotation-editor and upload safeguards remain in place. Normal save errors and CSRF handling remain server-authoritative.

## Stability, performance and deployment

- Family grouping avoids a repeated full-list scan per latest quotation revision.
- Batched record ownership/ACL/workflow-grant reads replace repeated permission queries during list filtering/redaction. Cache scope is a single evaluation and current connection/user; it is reset before subsequent mutation checks. No cross-request authorization cache.
- Schema 18 adds five tables plus supporting indexes and cascading cleanup for user shortcuts/record notes/reminder round ownership. Existing quotation/pricing data is unchanged.
- V21 startup requires an explicit isolated JSON profile and preinitialized schema; normal startup never migrates. Fresh initialization refuses nonempty data/storage directories. Explicit migrations require a V21 marker and a safety backup.
- Separate test roots for database/attachments, external documents, exports and backups. Profile validation rejects overlaps with declared V20 paths, application storage, linked directories and hard-linked database files. Runtime destination checks reject imported/restored production export/document paths, including stale PDF ownership and pending deletion metadata. External PDF cleanup rechecks the export root before deletion.
- `start-v21.bat` / `stop-v21.bat` reuse the existing loopback Waitress/IIS endpoint with port and process identity guards. No service installation, V20 termination, IIS reconfiguration or deployment occurs.
- V21 uses a separate session cookie and forces real SMTP off in the sandbox.
- Existing database/attachment backups support schema 18 and identify application version 21. A separate offline complete-backup command includes external documents and exports with SHA-256 checksums.
- Added deployment/profile examples, explicit migration instructions, same-server switch/rollback guide, security review, benchmark data and test report.

## Compatibility retained

The internal editor structure, Main Site/DR Site layout, separate Monitoring category, Cybersecurity/Connectivity services, connectivity one-time setup, 8×5 Request Fulfillment, customer-specific service/VM prices, monthly/one-time calculations, margins, PDF/Excel layout, approval dots/rounds, reports, sent tracking, document storage model, account roles and theme preferences retain the V20 implementation. The editor adds only a copy-link control; it was not redesigned.

Review `docs/V21-TEST-RESULTS.md` for observed results and unexecuted Windows/IIS checks. This release is an isolated test candidate, not a production deployment or a security certification.
