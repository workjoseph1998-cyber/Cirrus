# Version 10 verification and change inventory

Built from the complete Version 9 commit `c05d080` on
`feature/cirrus-workplace-document-workspace`, including the later automatic-PDF,
full-backup and customer-specific-folder requirements. All validation used
synthetic/disposable data. No live Windows VM, IIS configuration, customer files
or production database was accessed or modified.

## Results

- **145 automated tests passed** with `python -m unittest discover -s tests -q`:
  the 112 existing tests (updated for intentional schema/UI behavior), 16 document
  workspace cases, 10 automation/backup cases and 7 customer-folder cases.
- **Five browser workflows passed** using real local Waitress and Chromium:
  `documents_browser.py`, `automation_browser.py`, `quotation_browser.py`,
  `hosting_browser.py`, and `team_browser.py`.
- **12 independent spreadsheet scenarios passed** in LibreOffice: the seven
  existing baseline/unpriced/zero/included-tax/edited-quantity/long-text/many-row
  cases, the new hidden-12-month case, and four selected V8 percentage/fixed/
  unpriced policy cases. This does not claim the whole V8 matrix was rerun.
- Python compilation, changed JavaScript syntax, `pip check`, and
  `git diff --check` passed.
- The included server diagnostic passed against a temporary workspace, including
  root/customer/backup folder write/rename/delete tests and real PDF generation.

Representative guarantees exercised:

- Latest revision/family financial aggregation; unpriced vs zero, Cancelled value
  exclusion and count inclusion, non-quotation exclusion, frozen accepted values,
  combined owner/status/type/search/date-basis filters and pagination.
- Six concurrent mixed quotation reservations/document creations receive six
  unique centrally allocated references; the existing case-insensitive uniqueness,
  reservation/expiry, revision, issued-history and concurrent-price tests remain.
- Different-quotation/revision comparison handles changed scope, rows/structure,
  additions/removals, fees and totals. Hidden documents and internal costing remain
  protected from unauthorized users.
- Edited titles persist and drive sanitized print/PDF/Excel/CSV/text names;
  generated revision suffixes update without discarding custom subjects/titles.
- Saved 12-month setting reaches preview, print, actual automatic PDF, Excel and
  CSV without changing pricing. Hidden-column Excel formulas were independently
  recalculated, including preserved one-time fees.
- Archived family confirmation, stale-data/permission checks, accepted Won and
  contract protection, and verified-draft-only reference release remain covered.
- Customer folder mapping/create/test actions require administrators; Windows/UNC
  case handling, root confinement, overlapping destinations, stale settings and
  duplicate customers are checked. Customer renames retain the same mapping ID.
- Missing mapping and missing customer ID never fall back to another folder.
  Reassignment/new mapping sends future PDFs to that customer while retaining old
  external files. A mapping change during rendering cannot publish to the old
  destination.
- Real background PDF generation preserves customer-facing formatting, saved
  title/header/12-month state and excludes private costs/notes. Failure preserves
  the saved quotation/previous PDF and recovers through Retry; generation checks
  prevent an older job overwriting newer content.
- Full portal backup downloads restore accounts, records, registry, settings and
  attachments. SQLite's writer barrier blocks attachment deletion until the
  consistent database/file capture completes. Retention keeps requested daily/
  weekly copies and leaves unrelated files alone. Failed backup/export operations
  retain the last successful result.
- Additive schema-8 → 9 upgrade preserves existing record bytes, timestamps,
  ownership and unknown historical creators, and full backups restore schema 9.
- Browser checks cover dominant list/sidebar dimensions, responsive stacking at
  desktop/tablet/mobile sizes, no page overflow, real manual PDF/Excel downloads,
  VM Linux/Windows rates/pickers/comments, quote snapshot pricing, team sharing,
  personal isolation, catalog safety backup, templates and spreadsheet import.

## Modified files by responsibility

| Area | Files |
| --- | --- |
| Document workspace, metadata, links, history and customer folder routing | New `workspace_app/documents.py`, `export_folders.py`; existing `__init__.py`, `store.py`, `model.py`, `security.py`, `customers.py` |
| Reference/workflow/comparison/archive reuse | `references.py`, `outcomes.py`, `comparison.py`, `archives.py` |
| PDF queue and backup automation | New `automation.py`; `backup.py`, `company.py`, `requirements.txt`, release label in `run.py` |
| Customer quotation presentation/export | `quotation.py`, `quote_routes.py`, `quote_excel.py`, `templates/quotation_document.html`, `quotation_editor.html`, `discount_summary.html`, `static/quotation_editor.js`, `quotation.css` |
| New UI templates | `documents.html`, `document_new.html`, `document_edit.html`, `document_manage.html`, `document_print.html`, `automation_settings.html`, `customer_export_folder.html`, `customer_export_folder_fields.html` |
| Existing UI integration | `customer_workspace.html`, `settings.html`, `archive_confirm.html`, `comparison.html`, `static/app.css`; release labels in `base.html`, `login.html`, `dashboard.html`, `agreed_prices.html`, `consumption.html`, `customer_overview.html`, `project_commercial.html` |
| New browser behavior | `static/documents.js`, `pdf_status.js` |
| New tests/diagnostic | `tests/test_documents.py`, `test_automation.py`, `test_export_folders.py`, `documents_browser.py`, `automation_browser.py`; `scripts/verify_server_automation.py` |
| Updated regressions | `test_commercial.py`, `test_hosting.py`, `test_quotations.py`, `test_v5.py`, `test_v8.py`, `test_v9.py`, `team_browser.py`, `excel_recalculation.py` |
| Documentation | `README.md`, `docs/version-10-upgrade.md`, this report |

Listener, host validation, IIS reverse-proxy and login/authentication behavior
are unchanged. Document authorization extends the existing owner/ACL policy. The Dashboard's only template change is its release label. Existing
SQLite data locations, account permissions and attachment paths are preserved.

## Deployment limits

Windows/NTFS/SMB permissions and installed Edge policies cannot be proved from this
Linux cloud environment. Run the portal folder tests and included diagnostic under
the actual Windows service account, then verify a real saved-quotation export and
a restore into a separate directory. The [upgrade guide](version-10-upgrade.md)
details that procedure, new runtime dependency, root/customer folder mappings,
backup retention, restoration and rollback.

The app continues to use a single Waitress process with its existing workspace
lock. Automatic jobs require the server to be running; large attachment capture
briefly blocks database writers. Full restore has a 5 GiB uncompressed limit.
External PDFs and backups are not deleted with live documents and are not included
as attachments in full-instance backups. Rich Word document editing and the
simplified updater are not included.
