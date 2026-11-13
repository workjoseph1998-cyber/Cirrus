# Cirrus Workplace V5: upgrade and operating rules

> Historical release guide. For the current app use [Version 8 upgrade and rollback](version-8-upgrade.md).

Latest behavior: [commercial tools update](commercial-tools-upgrade.md) supersedes earlier draft-value, date-basis, reference-deletion and outcome rules; schema is now 6.

V5 builds on `feature/cirrus-workplace-team-upgrade` and preserves its accounts,
permissions, quotation editing, VM library, imports, attachments and records.
This guide supersedes older navigation, default-discount and summary instructions.

## Upgrade on the existing Windows VM

1. Sign in as administrator and record **Settings / Backup → Data directory**.
   Stop Waitress, including its Windows service/scheduled task if applicable.
2. From the **old application folder**, with its existing data-path configuration:

   ```bat
   .venv\Scripts\python scripts\backup.py backup C:\Backups\Cirrus-before-V5.zip
   ```

   Choose a new archive name. Keep a protected copy outside the VM and retain the
   previous code/configuration. JSON export is not a complete backup.
3. Download branch `feature/cirrus-workplace-v5` as ZIP into a **new code folder**.
   Preserve the current CIRRUS_DATA_DIR / legacy JOSEPH_DATA_DIR configuration.
   Do not overwrite or relocate the data folder. Both variables, if set, must
   resolve to the same directory.
4. Run `setup.bat`, then launch using your existing server configuration (or
   `start.bat` for localhost). Requirements add `tzdata` so Windows has IANA time
   zones. **Existing installations do not run init-admin again.** Fresh installations
   still use `.venv\Scripts\python manage.py init-admin` while the app is stopped.
5. Startup transactionally migrates schema 4 to **schema 5**. Earlier schemas
   still migrate in order. New tables are reference_registry,
   reference_assignments and reference_conflicts. Existing reference numbers,
   quotation IDs/revisions, customers, passwords, ownership, notes and attachment
   files are retained. Case-insensitive legacy reference/revision collisions are
   flagged for review, never deleted or silently renumbered.
6. Check old records/exports, sign in with a colleague account and test access.
   Review References for legacy conflicts and import the team's historical register
   **before issuing the next CIR**. Only references known to this database can be
   protected or used to suggest the next number.

For rollback, stop V5 and restore the pre-V5 archive to a new directory using the
matching old code. Never run schema-4 code against a schema-5 database. Restore of
current backups is supported by V5; the existing 5 GiB uncompressed restore limit
remains. The ZIP contains database + attachments + checksum manifest. Separately
retain launch/environment configuration, service/IIS settings and certificate
recovery material; existing data/backups archives are not nested into that ZIP.

## One shared server and database

Keep Waitress/IIS on the VM and direct all 3–4 employees' browsers to that server's
internal HTTPS hostname. Use an explicit, absolute **local VM disk** path such as
CIRRUS_DATA_DIR=C:\CirrusWorkplaceData, replacing the example with the actual
existing path. Do not point each laptop at a separate copy or host SQLite in a
synchronization/network-share folder. The default LocalAppData path depends on the
Windows service account; changing that account without an explicit data path can
open an empty workspace rather than the old one.

All browser requests use the server process's DATA_DIR, including reference checks,
reservations, quotation saves and imports. The process lock prevents a second
standard app instance from running against the same root. SQLite unique constraints
and BEGIN IMMEDIATE transactions arbitrate reference mutations; frontend checks
are advisory only. Keep existing IIS/HTTPS/allowed-host/firewall settings from
[the Windows hosting guide](windows-internal-https.md). This cloud task does not
change the deployed VM, DNS, certificates, firewall or IIS configuration.

## Shared references

References is a shared metadata register for quotations, proposals and documents.
It does not expose private customer names, quotation values or inaccessible record
links. Administrators and Editors reserve/issue/import; Viewers can read the ledger.
Quotation links are filtered by existing record permissions.

- Enter a custom reference or select **Reserve next CIR**. References
  are trimmed, Unicode-normalized and case-folded for identity. SQLite unique
  constraints also use NOCASE. Existing reserved/issued references give warnings.
- A reservation is valid for **30 minutes**, based on the server clock. Its owner
  can renew it while active. The quotation editor has Check and Reserve / renew
  controls under Quotation details; the reference is editable there and inline.
  For a quotation, saving issues the reference in the same database transaction.
- An expired, unissued reservation can be claimed again by any Editor/Admin.
  Renewal of an expired lease fails; the user must reserve it anew. A stale draft
  cannot save through another user's reservation. An expired reference is not
  assigned silently on save.
- For proposals/documents, reserve and then explicitly **Mark issued**. No proposal
  file is generated by this operation. Issued references never expire and are not
  released when a quotation is deleted or renamed. There is no delete/recycle
  operation for issued history.
- Last issued CIR means the **highest numeric sequence** matching CIRyy-number-suffix
  for the business current year, across all issued document types and imported
  history. Suggested next uses the next sequence after issued and active reserved
  CIR numbers and ends in -1. Suggestions are not reservations; use the atomic
  button when multiple colleagues are working. Year rollover starts a new sequence.
- In CIR26-155-1, the final -1 remains part of the reference string. Quotation
  revision 2 retains that reference and uses the separate Rev field. Use **New
  revision**, not Create new quotation with an already issued reference. Database
  assignments are unique by normalized reference + revision. Repeating New revision
  from an older version opens its newer revision; use the latest to create another.
- Duplicate quotation creates an independent quotation with the next CIR. Existing
  revision ownership/sharing inheritance is retained. New quotation headers remain
  manually editable. A reference change makes a different grouping for statistics;
  old issued identity remains protected in the ledger.

Historical import accepts UTF-8 CSV or a **single-sheet XLSX**, up to 1 MiB and
5,000 references per operation. A header named Reference, Ref, Reference number or
CIR reference is detected, or enter the exact header name. Review and explicitly
confirm. Only that reference column is imported; no customers/quotations are created.
References are marked issued document history. Repeats skip already-issued entries.
An active-reservation conflict rejects the whole transaction. Formulas must be
exported as literal values. Existing JSON import/export remains additive; accounts,
sharing and the complete ledger travel in full backups rather than staff JSON.
If moving instances, restore a full backup to retain historical issued references.
A standalone/historical issued reference cannot be claimed for a fresh quotation;
import existing quotation records before their standalone reference list, or use
a new reference for an intentional quotation copy.

If migration finds formerly allowed case-insensitive duplicate reference/revision
pairs, References links the accessible conflicting records. An authorized editor
can assign an unused reference or distinct revision. No existing data is dropped.
Until resolution, statistics count that reference once and break equal revision ties
by latest update, then record ID. Invalid records are reported rather than fabricated.

## Statistics and dates

All work statistics use only records the current account can read. The last CIR
and ledger are team-wide metadata. The quotation list, charts and search show one
latest valid saved revision per normalized reference; saved older revisions remain
accessible from References. A malformed latest calculation can fall back to the
previous valid revision, with an invalid-revision warning. A latest cancellation
never revives an older issued amount.

Quoted amount is the saved **full-contract amount**: recurring fees across the
saved duration plus one-time fees, with the saved tax treatment and any historical
pricing adjustments. It is **not recognized revenue** or monthly recurring revenue.
Only fully priced **USD Sent / Accepted** quotations contribute to USD totals and
the average. No currency conversion is invented. Draft, Cancelled and Rejected
records remain in counts but do not contribute values. Unpriced quotes are counted
and omitted from value/average; literal zero is valid and included. Non-USD, unpriced,
draft/cancelled/rejected and invalid counts are shown explicitly. Average divides
by the eligible priced USD count, not all quotations.

Dates use the earliest visible saved creation timestamp in each reference family,
not its latest revision date or an editable header date. Importing an old quote
now therefore counts as a new creation now unless its creation timestamp was
preserved by JSON import. The default period is this year; this month, last month,
all time and custom inclusive ranges are available. Search matches reference,
customer or title. Totals/charts follow date/search filters; This month cards ignore
the date range but retain the search. Charts show up to 24 months (all-time: latest
12) while all-time cards retain the full totals. Empty months show zero.

CIRRUS_TIMEZONE defaults to **Asia/Beirut**, used for month/year boundaries and CIR
suggestions. It can be configured to another IANA zone before launch. Server UTC
creation timestamps remain unchanged; tzdata supplies Windows zone definitions.
No VM-specific timezone change or historical timestamp rewrite is performed.

Other cards report real stored values: accessible quotation/project activity on
Dashboard; total/Active/Completed/updated-within-30-days projects; catalog category
and billing counts; VM profile/family/confirmed/both-OS-price counts; enabled users,
admins, active reservations and accessible work records in Administration. There
is no invented login activity, customer database, margin forecast or revenue metric.

## Quotation cleanup and UI

The visible application is Cirrus Workplace V5 with navy, white and light-gray
controls. Inbox, Knowledge and Personal navigation/list/creation interfaces are
retired. Their existing stored records/attachments and permission checks remain;
authorized historical direct record views, Markdown/JSON exports and backend
compatibility are retained. Project views emphasize quotations.

Both blank and company-default quotations start without temporary discounts.
Customer preview, print/PDF and Excel cost summaries show category fees, final
monthly fee and final one-time fee. Yearly recurring/contract recurring/tax/combined
contract-summary rows and discount-specific rows are suppressed by stable keys,
including on legacy documents. The identified VAT disclaimer/old VAT conditions
and generated discount wording no longer appear. Stored historical calculation
inputs are not rewritten; tax, duration, line prices and old negotiated adjustments
still calculate internally and supply statistics. Excel retains hidden unlabeled
formula-dependency rows so saved calculations and public-input recalculation remain
compatible, without displaying the removed summary lines. Customer support rates
and calculation bases remain protected as in the prior upgrade.

## Limits

The small-team SQLite architecture and same-record last-save-wins behavior remain;
reference uniqueness is protected, but this is not collaborative cell editing or a
full audit system. Large catalogs still use full-record loading. Test real workload
on the VM. References use the server clock; keep it synchronized. Historical import
is reference-only, and registry history is included in full backups, not JSON exports.
No automatic nightly/off-VM backup or actual Windows/IIS deployment is performed.
