# Version 11 verification

Development checks use temporary, synthetic databases and workbooks. No live
customer database, exported PDFs or external data directory was modified.

## Checks performed in the Linux development environment

- Full Python suite: **158 tests**, covering existing authentication/sharing,
  reference concurrency, quotation calculations/exports, backup/restore and the
  new customer/consumption features. Old schema/version expectations and PDF path
  expectations were updated for the intentional additive migration/direct-folder
  behavior; existing feature assertions remain.
- New consumption checks cover blank/unknown/zero values, optional columns,
  repeated headers/items/VMs, Production/DR metadata, source month-name Date,
  mismatch and manual overrides, explicit support bases/cycles, environment-specific
  VM identities and confirmed resource semantics. Real import/save checks cover
  original workbook protection, duplicate rejection, deliberate merge, monthly
  isolation, optimistic locking and retention of failed-review drafts.
- Customer-catalog checks cover complete one-time copies, independence from
  general library changes, adding customer-only configurations and rejecting stale
  edits. Customer deletion checks cover roles and dependencies. Staff-only margin
  save and case-insensitive/sanitized/untracked-file PDF collision checks pass.
- Real Chromium against a temporary **Waitress** instance exercises login, the
  Dashboard/customer tabs, quotation selection/Follow-up dialog save, XLSX upload,
  header mapping, editable review, confirmation, saved detail, independent tenant
  catalog and unchanged general-library navigation. The browser downloads actual
  generated consumption **PDF bytes and XLSX**, checks JavaScript errors and tests
  desktop (1500 px) and small-screen (390 px) page widths.
- Desktop and small-screen screenshots of the Dashboard, customer workspace,
  quotations and consumption were reviewed. Tables scroll inside their containers;
  detailed management remains in a dialog. General hosting source/layout/calculation
  files are unchanged; its legacy navigation is intentionally retained there.
- Python compilation, JavaScript syntax, dependency consistency, whitespace and a
  clean extracted-ZIP app smoke check are part of release validation.

Reproduce the automated suite:

```sh
python -m unittest discover -s tests -v
python tests/v11_browser.py
```

The browser helper currently expects development Chromium at `/usr/bin/chromium`
and writes screenshots outside the repository under `/workspace/preservation`.
It is a development check, not a Windows installation command. On a container that
cannot use the browser sandbox the existing `CIRRUS_PDF_NO_SANDBOX=1` test setting
was used; keep the normal sandbox enabled on the Windows deployment.

## Supplied-sample limitation

No consumption sample workbook accompanied this implementation request. The
available earlier attachments are quotation workbooks, with a different structure.
Tests therefore construct realistic synthetic workbooks with the requested
columns/section patterns. **Validation against your actual consumption workbook
remains pending.** No fixture rows are installed as application data. Header-row,
mapping and classification correction are provided for workbook variations.

## Windows Server / IIS / Waitress checks still required

These were not executed on your VM, which is not accessible from this development
environment:

1. Back up the existing instance, extract into a short folder and run setup under
   the intended service account. Confirm the unchanged data path and old records.
2. Confirm IIS reverse proxy, allowed hosts, HTTPS/login/logout and existing
   loopback/service bindings. No binding changes are required by this release.
3. Under the actual Waitress account, test local NTFS/UNC root/customer folders
   and the separate full-backup destination. Test access using the portal actions.
4. Save/re-save a test quotation; check direct title-based PDF output, revision/name
   conflict status, case-insensitive collisions, locked-file failure and Retry.
   Verify existing quotation-ID subfolders have not moved or changed.
5. Verify installed Edge/Chrome can render both automatic quotation PDFs and the
   customer-facing monthly consumption PDF with the service's temp permissions.
6. Upload the actual consumption sample: review mappings, Production/DR context,
   source Date, x/-/zero/missing prices, units and totals before committing.
7. With two staff sessions, test stale monthly/catalog edits and shared references;
   check a read-only user cannot edit/download raw source or see internal costs.
8. Download and restore a full backup into a **new** directory. Check original
   workbooks, monthly history, tenant prices and accounts before switching any
   production service. Exercise daily/weekly retention in its dedicated folder.

This release does not add payment records, renewals/supplier tracking, a task
subsystem or quotation-to-project automation. Existing legacy records/features
remain available. Consumption cannot establish actual paid amounts. Large imports
are bounded, and summary/resource completeness still depends on user-confirmed
classifications and pricing; the portal labels those gaps instead of inventing data.
