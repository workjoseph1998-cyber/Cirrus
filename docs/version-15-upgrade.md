# Cirrus Workplace Version 15 — upgrade and operating guide

Based on Version 14 commit `72f7f8ae71dd0b37353893cbe86c7f23ab2a0b71`.
Product **15**, SQLite schema **15** (initial release: schema 14). Canonical branch `version-15` includes the latest
patches; immutable tag `v15.0.0` retains the original release snapshot. The
implementation branch is `feature/cirrus-workplace-v15`.

[Download ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/version-15.zip)
while signed into the private repository. See [all versions](versions.md).

The latest [email and studio-controls patch guide](version-15-email-studio-patch.md)
explains the schema-15 migration, two email milestones and patch-specific rollback.

## Upgrade Windows Server 2022 / IIS / Waitress

1. Download a pre-upgrade **Administration → Download full backup**. Record your
   actual external data directory, service identity and startup command. Separately
   copy external PDF destinations, deployment settings, secrets and IIS configuration.
   If upgrading an already-used v15 installation, include the external Documents
   root as the consistent pair described below.
2. Stop the existing Waitress process/service. Extract into a **new short folder**,
   such as `C:\CirrusV15`. Do not overlay the live data directory or copy an old
   `.venv`. Run `setup.bat`; runtime requirements are unchanged from v14.
3. Retain the same `CIRRUS_DATA_DIR` (or legacy `JOSEPH_DATA_DIR`), Windows account,
   allowed hosts, bind, port, proxy, timezone and IIS upstream. Do not run
   `init-admin` on an upgrade. Point the existing service/launcher at the new code.
4. Keep `%ProgramData%\CirrusWorkplace\deployment.json`, or the custom
   `CIRRUS_DEPLOYMENT_FILE`, outside application releases. `start.bat` and direct
   startup continue loading it; administrator environment overrides take precedence.
   Do not replace it with the bundled example. See the
   [persistent configuration guide](version-13-upgrade.md#persistent-allowed-hosts-and-deployment-settings).
5. Start Workplace. The automatic transactional migration adds customer document
   metadata, upload staging, audit/commit tables and an approval-history index, then
   adds schema-15 milestone email batches/recipient protection. Legacy unsent email
   jobs are retired; portal notifications and sent history remain.
   Existing quotations, users, SMTP settings, references, approval evidence,
   attachments and retained consumption tables are preserved. No accounts are reset.
6. Check existing sign-in, quotations, support totals, approver dots, exports and
   backups. Then configure Documents storage if desired and perform the Windows
   checks in [verification](version-15-verification.md).

No live VM deployment is performed by this release. For rollback, stop v15 and
restore the **pre-upgrade** application backup into a new external directory using
the matching old code. Restore the corresponding external files and service
configuration. Do not run earlier code against schema 15; earlier Version 15 builds accept only
schema 14. Restore a matching pre-upgrade backup before rollback. Reconcile later business changes
separately; never overlay an older database on a running service.

## Optional Monitoring

Open **Options** and use **Optional Monitoring** in the right-hand Quotation options
pane (an Options drawer on smaller screens). Existing documents
start unchecked and retain their previous amounts. The option identifies Monitoring
sections and their descendants; once saved, stable section IDs retain the association
if a section is renamed. A quotation without a Monitoring section receives a clear
validation message instead of silently ignoring the option.

When checked, Monitoring remains visible and priced but is excluded from included
monthly, yearly, one-time, contract, discount-base and margin totals. Included
percentage-based support cannot select it indirectly through another percentage fee.
Existing support percentages, targets and calculation methods remain unchanged.

A yellow bold **Optional: Monitoring - 24×7 NOC Services** row appears below the
existing monthly/one-time summary totals, showing monthly and yearly (12-month)
prices, plus an optional one-time amount when applicable. Missing optional prices
remain Unpriced without making otherwise-priced included services Unpriced.

Example: Production $1,000, Connectivity $100, Monitoring $200, support 5% targeting
Production and Monitoring. With Monitoring optional, support is $50 and included
monthly charges are $1,150; optional Monitoring is $200/month and $2,400/year.
A separate $296 setup fee gives a 12-month full contract of $14,096.

The flag survives save/reopen, duplication and revisions. HTML, print, current PDF,
Excel and CSV apply the same inclusion policy. Excel uses numeric/formula cells and
currency formatting. CSV carries values/labels without colors. Historical approved
PDF evidence is immutable; toggling the option changes customer-facing content and
requires reapproval under the existing workflow. Default normalization alone does
not invalidate previous approvals.

The internal quotation editor's fields, row controls, cell/keyboard behavior and
editing workflow are preserved. The latest patch relocates the existing option controls and approver setup; see
the [studio controls guide](version-15-email-studio-patch.md#studio-control-placement). The prior simplified summary and red/white monthly
total remain, with explicit occasional discounts still supported.

## Monthly / Total Contract comparison

Choose the basis above the four summary cards:

- **Monthly:** included recurring monthly fees, using the existing recurring
  discount calculation directly; no one-time or optional charges. A limited-duration
  recurring discount reflects the calculated initial monthly fee, not contract value
  divided by term.
- **Total Contract:** the saved contract calculation, including one-time charges
  and existing applicable tax/discount rules, excluding optional services.

Previous, New, Difference and Difference % update together without a page reload;
the URL retains the basis. A zero previous amount yields N/A for a nonzero change
(and 0% for zero-to-zero). Different currencies are identified without inventing
exchange rates. Detailed comparison remains available, labels billing periods, and
marks optional detail values as excluded from summary totals.

## Customer Documents setup and permissions

Open **Administration → Customer document storage** (also linked from each
Documents tab). Configure an absolute server path such as
`D:\Cirrus-Customer-Documents\` or a UNC share. Save, create the root if missing,
and use **Test folder access**. The setting is stored in the existing external
SQLite database, so replacing a code folder does not reset it.

The Windows account running Waitress needs Read, List/Traverse, Create, Write,
Rename and Delete (normally **Modify**) on this root and its descendants. UNC paths
need both share and NTFS permissions. An interactive user's mapped drive may not
exist for a Windows service; use an actual local drive or UNC path. IIS's identity
only needs these rights if it is also the account running Workplace. Limit direct
filesystem write access to that service and trusted administrators.

Customer **read** access permits browsing/downloading; customer **edit** access for
staff permits create/upload/rename/move/delete. Viewer accounts cannot modify.
Administrator-only settings, CSRF and server-side customer/node checks enforce
access. A quotation review assignment alone does not grant access to that customer's
files or unrelated records; internal margin permissions are unchanged.

Each customer receives a physical folder with an initial sanitized name plus a
stable customer-ID-derived suffix, recorded against the customer's ID. Two customers
with the same name have separate areas. Customer renames do not move folders.
The administrator-only Server folder detail shows the actual location.

Use Documents breadcrumbs to browse nested folders. Filename, byte size, upload
UTC time and uploader are shown. Uploads retain names; downloads use attachment
headers and original filenames. On a collision (including Windows-insensitive case):

- **Replace:** updates that file's bytes and metadata, keeping its stable node ID.
- **Save as a new version:** keeps the old file and creates `name (v2).ext`, etc.
- **Cancel:** discards only the pending upload.

Replacement is not a retained-content version history: choose New version when the
old bytes must remain. Duplicate-choice uploads are private to their uploader and
expire after 30 minutes, cleaned on subsequent customer-area access. Folder/file
moves and renames are reflected on disk. Delete requires confirmation, names the
affected item and lists the contained file count. Stale confirmations/replacements
must be reviewed again. No files are deleted merely by deleting/archiving a customer.
Document metadata/audit history blocks permanent customer deletion.

Names reject traversal, Windows reserved names, unsupported characters and private
`.cw-` names. Symlinks, Windows junctions/reparse points and hard-linked files are
rejected. Opened Windows handles are checked against the customer's area. SQLite
transactions, a single-instance lock, atomic renames and per-customer recovery
journals coordinate metadata and disk writes; interrupted process operations are
recovered on next access. Do not remove `.cw-*` ownership/recovery files.

### Limits and operational boundaries

- Maximum upload **10 MiB per file**; existing Waitress request limits are unchanged.
  Names are at most 160 characters, and Windows paths are restricted to 245 characters.
- Portal-managed files are indexed. Copying files directly onto disk does not import
  them. Unexpected files block collisions/deletion; changed bytes fail download
  verification instead of being silently served as the saved document.
- The root must be separate from data, code, PDF and backup folders. Changing it
  after any customer area is allocated is blocked to prevent orphaning files.
  There is no online relocation wizard; restore to the recorded path.
- Existing one-Workplace-process-per-data-directory deployment remains required.
  Process-interruption recovery is tested; sudden-power-loss/network-share durability
  and hostile OS administrators are not claimed to be covered.

## Back up and restore external Documents

**Download full backup and scheduled application backups include SQLite metadata,
accounts, settings, document history and existing application attachments. They do
NOT include bytes under the external Customer Documents root, nor external PDFs.**
The settings screen states this explicitly. An application ZIP is source code, not
a business-data backup.

For a consistent, restorable pair:

1. Stop Waitress and pause other writers to the external document root.
2. With the same existing data-directory/deployment environment, run from v15:

   ```bat
   .venv\Scripts\python.exe scripts\backup.py backup E:\Backups\CW-2026-11-04\workspace.zip
   robocopy D:\Cirrus-Customer-Documents E:\Backups\CW-2026-11-04\CustomerDocuments /E /COPY:DAT /DCOPY:DAT /XJ /R:1 /W:1
   ```

   Substitute real paths; quote any containing spaces. SQLite's backup API and
   integrity/hash verification are reused. The archive destination must be new.
   Robocopy exit codes below 8 are normally successful; inspect output and verify
   all files, including `.cw-*`, were copied. Do not treat a failed copy as a backup.
3. Keep the two outputs together with product/schema version, original root path,
   permissions/service-account notes and a timestamp. Separately back up deployment
   configuration, secrets, IIS and external quotation PDFs. Protect backups as private
   business/account data. Resume the service only after both captures finish.
4. Test restore on an isolated stopped instance, never against the live data folder:

   ```bat
   .venv\Scripts\python.exe scripts\backup.py restore E:\Backups\CW-2026-11-04\workspace.zip --target D:\CirrusRestoreTest
   ```

   Restore the **matching entire CustomerDocuments tree** to the configured root
   on that isolated machine before starting, preserving private marker/journal
   files. Restore ACLs for the actual service account. Do not overlay a mismatched
   tree or point a test instance at production files. Use the restored external
   data directory, then check downloads, folder operations and a new backup.

Restoring an older application archive without the matching external tree can leave
metadata referring to missing/newer bytes; it is not a complete document restore.
No automatic migration, deletion or movement of existing exported PDFs occurs.

## Workspace improvements and retained behavior

Refined navy/teal light and dark surfaces, compact customer headers, clear tabs,
listing density, sticky listing headers, search/sort/pagination and account-scoped
remembered filters/scroll position improve daily navigation. Customer Documents
browsing, filtering and folder/upload actions refresh the content area rather than
the full page. Feedback, processing locks and unsaved form warnings prevent accidental
loss/repeat submissions. Existing quotation unsaved protection remains.

Green/white approval dots, permissions, notifications, accounts, SMTP modes, customer
pricing and the general Hosting VMs interface retain their existing behavior.
Consumption remains retired (no tab/import/edit routes); existing tables/workbooks
remain in backups and the administrator retained-consumption handover. No new
consumption system, supplier quotation system or task subsystem is introduced.
Recoverable quotation drafts and a simplified updater are deferred; no new editor
navigation, Excel paste or internal row-editing behavior is introduced.

## Main changed files

- `optional_services.py`, `quotation.py`, `commercial.py`, `costing.py`,
  `quote_excel.py`, `quote_routes.py`, customer document templates/CSS: optional
  calculation and customer-output policy; minimal outer editor binding.
- `customer_documents.py`, `document_storage.py`, `customer_document_routes.py`,
  Documents templates and `store.py`: external files, ACL checks, recovery and schema14.
- `comparison.py`, `comparison_basis.js`, comparison template: both summary bases.
- `listing_ui.py`, `workspace15.js/.css`, customer/list/dashboard/base templates:
  surrounding interface, pagination/remembered state and partial file browsing.
- `documents.py`, `notifications.py`, approval context: remove repeated full-record
  scans without changing visibility or storing cross-user cached records.
- Version/backup/handover metadata, tests and these guides: product15 and validation.
