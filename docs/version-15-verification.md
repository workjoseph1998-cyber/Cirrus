# Version 15 — verification and limits

This page records the initial Version 15 release (schema 14). See the
[latest email/studio patch verification](version-15-email-studio-patch.md#verification)
for the current schema-15 build.

All checks use synthetic accounts/data in isolated temporary directories on the
Linux development host. No production database, Windows VM, real SMTP delivery or
customer disk was used. Runtime requirements were not expanded.

## Automated and browser checks

- **230 unittest tests:** 206 existing regression tests plus 24 Version 15 checks.
  Run `.venv\Scripts\python.exe -m unittest discover -s tests` from the repository.
  New cases cover optional monthly/one-time/unpriced/zero fees, direct and indirect
  support bases, discounts, save/copy/revision/output consistency, approval hash
  compatibility, both comparison bases, zero/foreign-currency handling, Documents
  permissions/isolation, Windows-safe names and opened-handle prefix normalization,
  links/hardlinks/reparse flags, stale conflicts/deletion, nested file operations,
  transaction rollback/interruption recovery, concurrent writes, persistent roots,
  staged upload cancellation, root separation and backup metadata restoration.
- **Version 15 Chromium + real Waitress:** save/reopen Monitoring, correct support
  and included totals, yellow customer summary in HTML and generated PDF, both
  comparison bases and all four cards, folder creation/upload/version/rename/move/
  download/confirmed subtree deletion, original filenames, actual disk bytes,
  customer read-only access, partial-page browsing, filters/density persistence.
  The content-area refresh preserves a browser sentinel, proving it does not reload
  the entire page. No JavaScript errors or page-width overflow at tested sizes.
- **Version 14 browser regression:** existing editor headings/currency/support
  controls, red/white total row and administrator account deletion pass unchanged.
- **Version 13 browser regression:** variable three/four approvers, two-green/
  one-white dots across pages, keyboard details, resubmission/full approval,
  customer filtering, None SMTP settings and retained approved PDF all pass.
- **Actual v14 → v15 migration:** a database created by archived v14 code with
  accounts, SMTP None, quotation, three completed approvals, discussion, attachment
  and retained PDF was migrated twice. Every original table/column value and
  evidence byte was preserved. Old calculator result fields match the old code;
  existing fully approved content hashes remain current after default normalization.
- Python compilation, JavaScript syntax, dependency consistency, whitespace and
  deployment ZIP integrity/source-only checks accompany packaging.

Real rendered screenshots were inspected at 1536px desktop and 390px mobile,
including dark customer Documents, comparison, customer overview and quotation list;
light customer quotation output retains its professional styling. Small screens
scroll dense tables horizontally without overflowing the whole page. Customer PDFs
remain white regardless of portal theme. These are selected-screen checks, not an
exhaustive accessibility audit or every possible custom template.

## Measured performance

Same Linux development host, temporary SQLite, **300 draft quotations / 30 customers**,
authenticated administrator; five warm sequential samples per case. These are local
measurements, not Windows/IIS/network-share load guarantees.

| Measurement | Version 14 | Version 15 |
|---|---:|---:|
| Waitress + Chromium: filter submit to visible quotation rows, median | 7,778.59 ms | 750.96 ms |
| Flask quotation page response, median | 7,259.50 ms | 564.64 ms |
| Flask Dashboard response, median | 264.60 ms | 215.01 ms |
| Flask Customers response, median | 285.59 ms | 288.47 ms |
| Flask customer Overview response, median | 270.95 ms | 194.36 ms |

The browser quotation-list interaction was approximately **90% faster** in this
fixture. One repeated full-database record scan per quotation family was replaced
with one count pass; redundant notification/approval context scans were removed.
No shared cache bypasses current permissions. Customers timing was effectively flat;
not every page is claimed faster. Flask warm samples exclude one initial cold request.

Switching the comparison basis took **23.6 ms** in the final two-revision browser
fixture; values are precomputed and the cards update locally. Uploads and Documents
browsing were verified functionally, not benchmarked over SMB. Reproduce the Flask
fixture with `python tests/performance_v15.py`; browser checks are in
`tests/v15_browser.py`, `tests/v14_browser.py` and `tests/v13_browser.py` (development
Playwright/Chromium paths may need adapting to the test host).

## Required Windows / IIS deployment checks

Not run here because there is no access to your Windows Server 2022 VM:

1. Existing `setup.bat`/`start.bat`, external deployment.json/environment precedence,
   current allowed hosts including the VM IP, bind/port/proxy and IIS host forwarding.
2. Existing accounts/SMTP configuration/approvals and PDF renderer using installed
   Edge/Chrome; confirm customer output, optional row and manual/automatic export.
3. Configure a local Documents root and, if used, UNC root under the real Waitress
   service identity. Test create/write/rename/delete, duplicate choices and downloads.
   Confirm both share and NTFS rights; no reliance on interactive drive mappings.
4. Actual Windows junction/reparse-point refusal and opened-handle final-path checks
   on local and UNC paths. Prefix normalization and simulated flags are unit-tested;
   actual Win32 APIs cannot execute in Linux.
5. Locked/open files, antivirus intervention, service restart and SMB interruption
   behavior. Process-interruption recovery is tested; power-loss durability is not
   certified. Keep the existing single Waitress instance per data directory.
6. Perform an isolated restore of a **matching database/attachments backup plus
   external Documents tree**, preserving private markers, file bytes and ACLs.
   Test automatic daily backups and separately schedule external document copies.
7. Team review of the selected desktop/mobile themes, shared-customer permissions
   and own custom quotation templates. No real emails were sent during development.

## Explicit limitations and deferred work

- External Documents bytes are **not** included in standard full/daily application
  backups. Use the [stopped-service paired backup procedure](version-15-upgrade.md#back-up-and-restore-external-documents).
- 10 MiB per file, 160-character names and 245-character Windows paths. Portal-managed
  indexing; no automatic import of files placed directly on disk. Root relocation
  after use is blocked; no online relocation wizard.
- Replace discards previous bytes; choose New version to retain both. Pending upload
  choices expire after 30 minutes. No new content-version browsing subsystem.
- Consumption stays retired; its data/workbooks remain retained and exportable for
  handover. No new supplier, task-management or consumption subsystem.
- Recoverable quotation drafts and the simplified updater remain deferred. The
  internal quotation editor and keyboard/row-editing workflow were not redesigned.
- GitHub API access returned Forbidden for release administration. Version naming is
  standardized using preserved-history version branches, tags and the download
  index; existing GitHub Release-page titles could not be inspected or renamed.
