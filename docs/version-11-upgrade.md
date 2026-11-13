# Cirrus Workplace Version 11 — upgrade and operating guide

Branch: `feature/cirrus-workplace-v11`. This extends the complete Version 10
application and Windows setup fixes at `7dfc1eb`; it does not reset the repository
or deploy to the live VM. The simplified updater remains deferred.

Download while signed into the private repository:
https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/feature/cirrus-workplace-v11.zip

## Upgrade the existing Windows installation

1. In the current application, download an administrator **full backup**. Record
   the actual external data path, service identity, startup environment and IIS
   configuration. Stop Python/Waitress before changing application folders. An
   offline alternative, from the old application folder with its existing
   data-directory environment, is:

   ```bat
   .venv\Scripts\python scripts\backup.py backup D:\Backups\before-v11.zip
   ```

2. Extract the new application into a **short, new path**, such as
   `C:\CirrusV11`. Avoid a deeply nested Desktop/Downloads ZIP extraction path.
   Do not copy the previous `.venv`, a test database, or an application ZIP over
   your live data directory.
3. Run `setup.bat` in the new folder. Requirements are unchanged from Version 10;
   no additional runtime package or browser bundle is needed. The included setup
   retains the Windows virtual-environment/ensurepip diagnostic fixes. Machine-wide
   Microsoft Edge or Chrome is used for server PDF exports.
4. Keep the same account, `CIRRUS_DATA_DIR` (or accepted legacy
   `JOSEPH_DATA_DIR`), allowed hosts, bind address/port, reverse-proxy environment
   and IIS configuration. Start with the existing service configuration pointed
   at the new application/virtual environment, or `start.bat`. **Do not run
   `init-admin` during an upgrade.**
5. First startup transactionally migrates SQLite to **schema 10**, adding monthly
   snapshots/history/staged workbooks, independent customer VM catalogs, customer
   archive flags and PDF file ownership. Existing records, quotations, sharing,
   settings, references, attachments and accepted snapshots remain in place.
6. Verify old records and attachments, then test an import and PDF export using
   a test customer. Complete the Windows checklist in the verification guide
   before replacing the production service path permanently.

There is no universal absolute Windows data path: the application retains your
configured directory. Without explicit configuration it reuses an existing
`%LOCALAPPDATA%\JosephWorkspace` database, otherwise
`%LOCALAPPDATA%\CirrusWorkplace`. The account running the service determines
LocalAppData. Never change accounts and assume these resolve to the same folder.

For rollback, stop the application and restore the pre-upgrade full backup into a
new external data directory using the matching old application. Restore the old
service configuration. Do not run old code against the schema-10 live database.

## Monthly consumption workflow

Open a real customer, then **Consumption**. Choose the reporting month explicitly.
Upload XLSX, select the worksheet, review the detected header row and numeric
column mappings (blank means optional/unmapped), then review/edit the rows.
The stepper is Upload → Map columns → Review → Confirm. Source `Date` remains
independent text; month names never infer a year, charge period or proration.

Environment and category are separate. Production/UAT/DR headings change the
environment; subsequent Security Services headings retain that environment.
Merged headings and repeated headers are metadata. Ambiguous classifications,
units and resources require review. Entirely empty rows are skipped. Missing or
unknown numeric values stay blank/raw (`x`, `-`, etc.); explicit zero remains zero.
Each row has its own stable ID, independent of repeated Item/VM text.

In the preview/table:

- Correct environment/category, source values and billing units. The column
  chooser exposes resource semantics, manual overrides and percentage charge bases.
- Classify physical VMs explicitly. Known identities are separated by environment;
  users/IPs/EPS/licensing quantities are not VM counts. Resource totals require
  confirmed VM classification, known cores and RAM in GB, and explicit per-VM or
  whole-row semantics. Conflicting duplicate VM resource descriptions are excluded
  from resource totals until corrected. Partial/unknown totals are labeled.
- Original Unit Price/Total are retained. Missing Total is calculated only when
  quantity and unit price are numeric and billing semantics allow it. Mismatches
  are flagged; a manual total override requires a reason. Missing prices remain
  Unpriced. Percentage support requires an explicit rate and selected charge-base
  rows; cycles are rejected while keeping the editable draft.
- **Apply customer pricing** proposes explicit catalog matches for confirmation.
  It does not infer prices from ambiguous size labels, overwrite numeric prices or
  totals, or convert percentage support into a quantity charge.
- Confirm that prices are USD before committing. This workbook flow is USD-only;
  it does not convert currencies. Up to 3,000 rows and a 10 MiB workbook are
  supported, subject to the existing hardened workbook/ZIP limits.

Saving creates a versioned monthly snapshot and history atomically. Replacing an
existing month requires confirmation. Merge previews retain independent row IDs
and flag possible duplicate descriptions; users must remove unintended duplicates
before confirmation. Re-uploading identical workbook bytes for the same
customer/month is blocked unless explicitly allowed after review. Optimistic
version checks prevent overwriting another user's monthly save.

**Copy previous month** creates an unsaved draft with fresh row IDs and remapped
support bases. It does not invent billing start dates or carry-forward charges.
Historical monthly prices are stored with their rows; later catalog edits cannot
reprice them. The history includes actor, timestamp, filename/sheet, reporting
month, row counts and before/after snapshots. The original workbook is kept as a
protected attachment: staff with customer edit access can download it; read-only
users get the customer-facing saved detail/summary exports instead. Original audit
workbooks cannot be removed through the generic attachment delete action.

Known monthly consumption charges are calculated charges, not invoices, quotation
values or payments. Unpriced/unresolved counts remain visible. Comparisons with
the previous calendar month are labeled incomplete while either month is
unresolved. Existing contract-based consumption remains available through its
existing workspace actions; it is not silently converted or double-counted into
the new workbook snapshots.

## Customer workspaces and independent VM catalogs

Customer tabs organize Overview, Quotations, Consumption, Hosting VMs / Tenant
Pricing, Projects & Related Documents, and Contacts & Activity. Overview names the
latest saved workbook month and its pricing gaps. Existing contracts, pricing
defaults, related records and folder settings remain available. Legacy standalone
project workspaces must be explicitly linked to a real customer before using the
new customer workbook/catalog features; names are not guessed or merged.

New customers receive a complete one-time copy of the current general VM library.
Existing customers are initialized once; unique currently applicable negotiated
VM prices are retained. Customer and catalog-entry IDs remain stable. Customer
edits never update the general library or other customers. Later general-library
changes do not update existing customer catalogs. Add/edit customer configurations
in the familiar catalog interface; submitted stale versions are rejected.

New quotation VM proposals use the selected customer's catalog. Existing dated
customer/project agreement overrides retain their established precedence; the
existing agreed-prices/support-defaults controls remain accessible. Quotes and
consumption already saved retain their own prices. Changing the quotation's
customer clears an incompatible project association and offers explicit repricing
preview; it never silently replaces entered selling prices. An independently
copied Demo price remains Demo until confirmed, preserving existing safeguards.

Administrator **Delete / archive customer** lists dependencies and rechecks them
under a write transaction. Linked quotations, projects, consumption, agreement
history or attachments block permanent deletion. Archive/restore is available;
linked records can be explicitly reassigned through their existing editors where
appropriate. There is no automatic history/file cascade. Generated catalog entries
and abandoned unsaved drafts are owned configuration and may be removed with an
otherwise unused customer. External exported files are never deleted.

## Direct customer PDF destinations

Existing enablement, root/customer mappings, asynchronous generation, Retry,
status and atomic replacement remain. A future export now writes directly to:

```text
F:\Quotations\SaradarBank\CIR26-158-1_SaradarBank-Test Quote Quotation_V1.0.pdf
```

The filename is the saved editable title after Windows sanitization. A persistent,
case-insensitive ownership ledger claims the complete path for one quotation
record/revision. The same tracked version can update its PDF. Another document or
revision with a colliding title, including a sanitization/case collision, fails
clearly rather than overwriting it. An untracked existing file also blocks export.
Give separate revisions distinct editable titles if they would otherwise collide.
Ownership is retained for previously claimed paths, even after record deletion.

Old quotation-ID subfolders/files are left untouched. No migration, move or delete
is attempted. A changed title, customer assignment or folder mapping affects future
exports only; earlier copies stay where they are. Missing customer mappings retain
the saved quotation and show the existing configuration status/link. The worker
still rechecks saved content and destination before publishing atomically.

Folder access uses the **Windows account running Python/Waitress**, not the browser
user. Grant **NTFS Modify** on the root/customer folders and writable browser temp
area; UNC destinations also need share permissions and an account able to
authenticate. Interactive mapped network drives may not exist for a service;
prefer UNC for network shares. Use the existing root/customer **Test folder access**
actions under the real service account. An exclusively open PDF can block Windows
replacement; the last good file remains and Retry is available. Existing server
bindings and host validation are unchanged.

## Backups and privacy

The administrator **Download full backup**, automatic daily/weekly retention and
offline backup/restore implementation are reused. Schema-10 tables, staged
workbooks, history, independent catalogs and ownership claims are in SQLite;
registered original workbooks are included with the attachments. The SQLite backup
API and coordinated attachment capture remain in use. Test restoration into a new
directory, never over the live database.

Keep full backups in their separately configured destination, with access limited
to administrators/service accounts: they contain private records and account
hashes. External customer PDF copies are not part of the internal attachment
backup; include that dedicated disk/share in your separate server backup plan.
Service environment, IIS configuration, browser installation and certificates
also need separate operational backup. The existing restore archive size limit is
5 GiB; plan an administrator-operated storage backup if the workspace grows past it.

Public consumption and quotation output excludes internal costs and margins.
**Pricing & Margin** reuses the existing staff-only cost worksheet/math and explicit
selling-price application flow. Monthly/one-time charges remain separate, zero
selling prices show an unavailable percentage margin, and advanced fields stay
behind Show details. Management opens focused dialogs and list context is retained.
Service Catalog, reference registry and portability remain reachable from the
profile menu; settings and full backups remain administrator-only.

## Main modified files

- `workspace_app/monthly.py`, `templates/monthly*.html` and `static/monthly.js`:
  workbook staging/mapping, snapshot editing/history, calculations and exports.
- `workspace_app/tenant.py`, `templates/tenant*.html`, `relationships.py` and
  `quote_routes.py`: independent customer catalogs and explicit quotation proposals.
- `workspace_app/workspace11.py`, `customers.py`, customer/dashboard templates:
  customer tabs/snapshots, actual-data attention lists, delete/archive review and
  compact staff margin tools.
- `workspace_app/automation.py`, `store.py`, `backup.py` and `__init__.py`:
  direct PDF ownership, schema 10, backup compatibility, routes and access guards.
- `templates/base.html`, quotation/management templates, `static/app.css`,
  `static/documents.js`, `static/management_focus.js`, `static/modern.js` and
  `static/quotation_editor.js`: responsive navigation, focused dialogs and explicit
  customer repricing. General hosting Python/template files are unchanged.
- `tests/test_v11.py`, `tests/v11_browser.py` and existing schema/PDF assertions:
  feature/regression checks. `README.md`, this guide, the verification guide and
  `run.py` identify the new release.
