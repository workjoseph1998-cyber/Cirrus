# Cirrus Workplace Version 10 — documents, customer PDFs and complete backups

This builds on the full Version 9 commit `c05d080`, preserving SQLite records,
attachments, settings, existing prices, customer/project IDs, ACLs, accepted
snapshots and the shared reference ledger. Product Version 10 uses **schema 9**.
The Dashboard layout and functions remain unchanged; its release label updates.
The simplified updater remains deferred.

Branch: `feature/cirrus-workplace-document-workspace`.
Download the signed-in GitHub branch ZIP:
https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/feature/cirrus-workplace-document-workspace.zip

## Safe Windows/IIS upgrade

1. Stop the existing Python/Waitress service or console. Keep IIS configuration,
   service identity, environment and the existing external data directory.
2. Make a pre-upgrade full backup using the existing offline command:

   ```bat
   .venv\Scripts\python scripts\backup.py backup D:\Backups\before-v10.zip
   ```

   The existing script uses the configured `CIRRUS_DATA_DIR` / legacy
   `JOSEPH_DATA_DIR`. Do not replace either path with a guessed path. Back up the
   startup/service environment and IIS configuration separately.
3. Extract Version 10 into a **new application folder**. No live database,
   attachments or sample customer records are included in the application ZIP.
4. Create/use its Python environment and install `requirements.txt`, or run the
   existing `setup.bat`. There is one new direct runtime requirement:
   **Playwright 1.56.0**, for maintained headless PDF printing. It uses an installed
   Microsoft Edge/Chrome browser; **do not download Playwright browser bundles**.
   Existing Flask, Waitress, spreadsheet and VM functionality is preserved.
5. Start with the existing `start.bat` or point the existing service to the new
   source/virtual environment. Keep the same service account, data-directory
   variables, binding, allowed hosts, HTTPS and IIS reverse-proxy settings.
   First startup transactionally adds schema 9 tables. It does not rewrite old
   quotation payloads, assign historical creators, reprice quotes or move files.
   Do not rerun `init-admin` during an upgrade.
6. Sign in, verify old quotations/customers/attachments and configure server
   automation below. Both automation features default to **disabled**.

Microsoft Edge installed machine-wide is detected under Program Files / Program
Files (x86); Chrome and user installations are also checked. If needed set
`CIRRUS_PDF_BROWSER` to the full installed browser executable path in the **service
startup environment**, then restart. The service must be able to launch that
browser and use its own writable temporary directory. Automatic rendering embeds
customer CSS/logo, blocks HTTP/HTTPS requests, and does not navigate to the live
server or local HTML files. It exports the same public projection as customer
print, without internal notes, costs, margins, source IDs or support percentages.
The normal manual **Print / PDF** option remains available.

## Root quotation folder and stable customer mappings

In **Settings / Backup → Automatic PDF exports, daily backups & retention**, set
**Root quotation folder** to the actual Windows path, for example
`Q:\Quotations`, and enable automatic PDF export. The disk's display label
“Quotations” alone does not determine its drive letter or folder path. A fixed
local drive is suitable; a mapped network drive may not exist for a Windows
service. Use a UNC path for network shares, such as
`\\fileserver\Quotations\Customers`. The root must already exist.

For each real customer, open their profile's **Quotation export folder** panel:

- Enter an existing folder beneath that root, e.g.
  `Q:\Quotations\SaradarBank`, then **Test folder access** and **Save customer
  folder mapping**.
- Alternatively, use **Create customer folder** explicitly. It suggests a
  sanitized customer name, creates exactly that child folder and maps it. It
  will not adopt an existing directory, overwrite an existing mapping or create
  folders merely because a quotation was saved.
- Mapping is stored against the customer's stable database ID. Renaming the
  customer preserves the association and never creates another folder.
- Customer mappings cannot share or nest inside one another’s folders. Windows paths are
  compared case-insensitively; path traversal and destinations outside the root
  are rejected. Stale mapping/root edits are rejected transactionally.
- A legacy unlinked project workspace must first be linked to a real customer;
  no folder is inferred from its name, project text, quotation title or previous
  export destination.

Root and customer folder settings/actions are administrator-only. They run on the
**Workplace server under the Windows account running Python/Waitress**, not the
browser user's computer or necessarily the IIS application-pool account. Grant
that account **Modify** on the root, customer subfolders and browser temp area:
create subfolders, write, flush, rename/replace and delete test/temporary files.
For UNC paths grant both **share** and **NTFS Modify** permissions. Use a domain
service account or another identity that can authenticate to the share; avoid
assuming an interactive user's drive mappings/credentials apply. The portal tests
exercise subfolder creation, write, flush, rename and deletion under the actual
running account. Files already opened with an exclusive Windows lock can prevent
replacement; the saved quote remains safe and Retry is available.

After a quotation save, a durable background job reads its **saved linked customer
ID** and current mapping. Output is:

```text
Q:\Quotations\SaradarBank\quotation-<saved-revision-record-ID>\<sanitized-saved-title>.pdf
```

The subfolder makes identical titles on unrelated quotes and different revisions
safe without changing the requested filename. Subsequent saves of the same
revision/customer/title replace that file atomically using a temporary file on the
same destination volume. A failed job retains the saved quotation and last good
PDF, shows the failure and offers **Retry PDF export**. Editor status polls while a
job is pending; details show the last successful timestamp/destination. An
interrupted job resumes after application restart.

If no mapping exists the status is **Customer export folder not configured**,
with an administrator configuration link. There is no fallback to the root or
another customer's folder. A quote without a linked customer must be assigned one
first. When changing customer, select/clear the customer agreement consistently;
the existing backend prevents mismatched customer/agreement links.

Changing assignment or mapping sends **future exports** to the new mapped folder.
Existing files are never automatically moved/deleted. Changing a title similarly
leaves the older named copy; the new saved title names the next PDF. The worker
rechecks saved content, generation, mapping and root before publication, so a
change during rendering cannot publish to a stale destination. Existing exports
are external copies: archiving or deleting a live document does not remove those
copies or prior backups.

## Complete online and daily backups

**Settings / Backup → Download full backup** is administrator-only. This is a
full-instance backup, including other users' private records and account password
hashes; ordinary workspace JSON is not a full backup. The ZIP contains:

- A consistent `workspace.sqlite` snapshot: records, users/ACLs, settings, VM
  library, customer price/support rules, contracts/consumption, reference registry,
  archived/outcome data, accepted snapshots, internal costing, folder mappings,
  export state and audit history.
- Every registered attachment, including contract attachments and private records.
- An integrity-hash manifest with backup format, application version and SQLite
  schema information.

It reuses the existing SQLite backup API and attachment write barrier. Database
writes pause during snapshot + referenced-file capture; compression runs after
releasing that barrier. Upload files are immutable IDs, and deletion/metadata
changes coordinate through the same SQLite writer transaction. Missing attachments
abort the backup rather than producing an apparently complete archive. Restore
supports up to **5 GiB uncompressed**; online backups reject larger captures.

Configure a **separate, non-nested backup destination** in administrator settings
and test its access. It must also be separate from the source/data directory.
Default retention is **14 daily + 8 weekly** copies, editable in the portal.
One daily copy is made per server-local calendar day (existing `CIRRUS_TIMEZONE`);
the first successful backup in each ISO week is also retained as a weekly copy.
The server must be running. Startup catches up the current day, not missed days;
failed attempts retry hourly, and **Retry / run daily backup soon** requests a
prompt attempt. Status includes the last successful time/path and failure reason.

Archives live in a dedicated `Cirrus-Workplace-full-backups` child directory.
Retention applies only to application-named files there, after a successful
current capture; unrelated files are untouched. Restrict the backup folder to the
service account and administrators, with Modify permissions (including deletion
for retention), plus share permissions for UNC. Keep backups on a separate disk
or protected share. Do not expose that folder through IIS or ordinary users.

Generated customer PDFs, previous backup ZIPs and application code are not
attachments and are not recursively included. Keep/export those external copies
separately if needed; saved quotations can regenerate their customer PDFs.

Restore is deliberately offline into a **new** directory:

```bat
.venv\Scripts\python scripts\backup.py restore D:\Backups\full.zip --target D:\CirrusRestored
```

Never restore over live data. Stop the service, verify the restored content,
point the existing service data-directory environment at it, and restart. Review
automation settings in the restored database before starting a second instance;
its saved paths still point to the original external folders. For rollback to
Version 9, restore the pre-upgrade backup into a new directory and run Version 9
against that copy. Version 9 cannot open schema 9.

## Document workspace and financial definitions

The Quotations page now shows a dominant compact list and narrow responsive Tools
/ Management / Follow-ups / collapsed Insights sidebar. Default date basis is
**creation**, with document-date/last-modified options, combined search/month/year/
range/type/owner/status/visibility filters and 25/50/100-row pagination. Latest
accessible revisions are displayed once per family. Creation means the earliest
reliably stored accessible family timestamp, in the configured timezone. Unknown
creation dates remain unknown and only appear in unbounded date views; they are
excluded from monthly charts. Historical creator/editor/export events are never
invented. Current revision creation/last-modified timestamps remain in details.

The three quotation tools remain Compare, Outcome/workflow, and Internal costing.
Comparison accepts searchable selections across different quotations as well as
revisions, matches stable row IDs then unique semantic signatures, and shows
additions/removals/changes, scope, quantities, selling prices, initial monthly fees,
one-time charges and full-contract totals. Ambiguous imported duplicates are not
guessed. Private costing/margin access remains restricted by existing edit/role
permissions and never enters customer exports.

Sidebar metrics respect current document filters and permissions:

- Document/draft counts include document types; sent/won counts are quotation
  families, once each. Cancelled is a separate status.
- **Quoted contract value · USD** = latest revision's full saved contract duration
  + one-time fees with saved tax treatment. Drafts are included and identified;
  Cancelled and non-quotation types are excluded. Missing/unpriced and explicit
  zero are distinct; non-USD is not converted.
- **Monthly quoted fees · USD** = latest initial payable monthly recurring fees,
  excluding one-time fees and separately added contract tax. Embedded tax remains.
- **Won contract value · USD** = frozen accepted values for Won families matching
  the selected document filters, not new prices on a later revision. Unknown or
  non-USD accepted values are excluded with a count. This document-workspace view
  uses the chosen document-date basis for filtering; the existing Dashboard and
  customer outcome-date reports retain their established definitions.
- Monthly charts group these filtered quotation families by the chosen date basis.
  Value bars contain full-contract quoted amounts, **not monthly recurring fees**
  or recognized revenue. Count bars include all quotation statuses, including
  Cancelled; USD value bars exclude Cancelled. All dates shows the latest 12 months; bounded ranges show
  up to 24 months. Revisions are not added together as separate opportunities.

Create Agreement/BOQ/DN/Letter/PO/Proposal/Quotation/SLA/SOW via **New document**,
then choose customer/subject. Quotations reuse the existing editor and customer
pricing; other documents have editable text/content/metadata and print/PDF/text
exports, without mandatory pricing sections. Non-quote statuses omit Won/Lost.
Internal Review/Approved are optional internal statuses; there is no external
approval service. Existing Under review/On hold workflow remains compatible.
Ownership, future activity, follow-ups, customer document history and explicit
related-document links are available in Management. Revision creation carries
forward follow-ups/outgoing links while retaining historical records.

Generated titles follow `Reference_Customer-Subject Type_V<revision>.0`.
The established structured reference identifies the **family**: `CIR26-121-1`
keeps its trailing `-1` across revisions. Integer revision 1 → title V1.0;
revision 2 → V2.0. New documents/duplicates allocate a new family reference under
`BEGIN IMMEDIATE` and the existing case-insensitive SQLite constraints. New editor
reservations expire after 30 minutes; the existing renewal/check controls remain.
Manual/custom structured references and historical issued references remain.

Titles are stored independently and never regenerated on ordinary saves or date/
customer changes. Use **Regenerate title** deliberately. New revision/duplicate
only updates recognized generated version suffixes (and a duplicate's leading
reference), preserving edited subjects and fully manual titles. Filenames use the
saved title with Windows-unsupported characters sanitized. Search still includes
the structured reference even if a manual title omits it.

The saved **Show 12-month column** presentation toggle defaults to the prior
appearance for existing quotes; it affects preview, print/PDF, automatic PDF,
Excel and CSV category summaries without changing calculations or one-time fees.
The compact blue/gray logo header uses Messrs./Contact/Project and Date/Ref only.
No removed standard contract/yearly/tax blocks, header revision/validity/currency
fields, VAT disclaimer or standard discount rows are restored. Existing explicit
saved pricing/discount policies and their calculations remain intact.

Archive/restore and confirmed permanent deletion apply to entire selected document
families/revisions, with permission/stale-state checks and attachment handling.
Accepted Won and contract-linked revisions block deletion. Issued/historical
references remain protected. Only verified never-sent quotation drafts retain the
previous authorized reference-release behavior; unrelated document references
stay protected. JSON portability retains records but does not transfer server
paths or separate ledgers; use the full ZIP backup for complete restoration.

## Verification on the deployed Windows service account

Cloud validation uses disposable data with the real Waitress entry point and
Chromium PDF output. No access to your Windows VM or IIS service was available;
actual NTFS/UNC permissions and installed Edge policies must be checked there.
Run portal folder tests in the live process, then optionally run under the same
Windows identity/environment:

```bat
.venv\Scripts\python scripts\verify_server_automation.py --customer-folders
```

This reads the existing configuration, probes configured folders and renders a
synthetic customer PDF in a temporary scratch workspace. It does not save test
records or change live settings/attachments/data location/bindings. Verify one
real quotation save → success time/destination, Retry after a folder-access error,
and a full backup restore into a separate directory before relying on automation.
Use the existing single-process `run.py`/Waitress deployment; do not launch multiple
independent servers against the same data directory. Its process lock is retained.

Limitations: backups run only while Workplace is running; there are no fabricated
missed-day archives or external notifications. Large attachment captures briefly
block writers. PDFs require a working installed browser and service-account temp
access. External PDFs/backups remain after deleting live documents. Other document
types currently use editable plain text, not a Word-compatible rich-text editor.
