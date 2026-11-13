# Cirrus Workplace — Version 8

> Historical Version 8 guide. For the current release use [Version 9 upgrade and rollback](version-9-upgrade.md).

Product **Version 8**, database **schema 7**, based on the commercial-tools branch.
No Windows deployment has been performed. Python 3.11+, SQLite, Flask, Waitress,
existing authentication and IIS reverse-proxy configuration are retained. There
are **no new runtime dependencies**. All examples/tests use synthetic data.

## Download and upgrade an existing installation

Download [the complete Version 8 branch ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/feature/cirrus-workplace-v8.zip).
Sign in to GitHub first because the repository is private. Alternatively open
`feature/cirrus-workplace-v8` in GitHub and choose **Code → Download ZIP**.

1. Record the existing external data path and Windows service account. Run from
   the old application directory, with the **same environment variables as the
   production launch script/service**:

   ```bat
   .venv\Scripts\python -c "from workspace_app import data_directory; print(data_directory())"
   ```

   Keep `CIRRUS_DATA_DIR` (or legacy `JOSEPH_DATA_DIR`) unchanged. Both variables,
   if present, must point to the same directory. Never select a fresh empty path
   during upgrade. Do not move the database into the application or IIS folders.

2. Stop Waitress/the application service and prevent further writes. Back up
   using the old application's Python, with those same data-path variables:

   ```bat
   .venv\Scripts\python scripts\backup.py backup C:\Backups\Cirrus-before-Version-8.zip
   ```

   This takes a consistent SQLite snapshot and copies attachments into a verified
   ZIP. It refuses an already-existing backup filename. Keep a separate copy of
   the old application, personal launch/service settings, environment values,
   relevant IIS configuration/certificates and NTFS permissions. Backups contain
   confidential costs, credentials/hashes, private records and signed contracts;
   protect them accordingly. A workspace JSON export is **not** a full backup.

3. Extract the downloaded ZIP into a **new application directory**. Do not extract
   over your external data directory or old application. Run `setup.bat` in the
   new directory. Existing accounts remain in SQLite: **do not run `init-admin`
   for an existing installation**.
4. Update only the application-directory path in your existing personal launcher
   or service command. Retain its data directory, bind/port, allowed hosts,
   trusted proxy and HTTPS settings. Start the app through that existing launcher.
   Keep one Waitress instance using the shared local database; colleagues connect
   through the same IIS URL. Individual workstation copies must not each use
   separate databases. **No IIS configuration change is required by Version 8.**
5. Startup transactionally adds schema 7 tables. It does not rewrite existing
   quotations, match customer names, remove users, replace catalogs, reseed live
   records, move attachments, change accepted values, or release references.
6. Verify login/sharing, existing quotations and revisions, comparison, costing,
   outcomes, customer PDF/Excel and attachments. Then add customer records and
   explicitly link the appropriate existing projects using **Edit project**.
   Existing customer display text remains independently preserved.

## Rollback

Stop the new app first. Keep a backup of its data if it has received new work.
Schema 7 cannot be opened by the old schema-6 application: there is deliberately
no destructive downgrade. From the Version 8 folder, restore the **pre-upgrade**
ZIP to a **new, unused directory**:

```bat
.venv\Scripts\python scripts\backup.py restore C:\Backups\Cirrus-before-Version-8.zip --target C:\CirrusRollbackData
```

Point the old launcher/application at that restored directory, restore its old
application path and start it. Verify the restored data before admitting users.
The restored pre-upgrade snapshot does **not** contain work saved after upgrade;
reconcile that work explicitly rather than mixing SQLite files or overwriting the
original directory. Keep both original and upgraded directories intact.

## Customers, projects and pricing

**Customers → Create customer** creates an independent permission-controlled
record. Link projects explicitly; one customer can have multiple projects. Access
to a customer does not automatically grant access to its projects. Customer
overviews include only projects the signed-in user may read.

Customer/project **Agreed prices & history** stores service catalog or VM/OS
identifier, monthly/one-time billing basis, currency, unit price, inclusive
optional effective dates, active/inactive status and notes. Every save requires
a reason and records before/after values, user and UTC timestamp. Prices can be
edited or deactivated, not silently deleted. Overlapping active effective periods
for the same scope/item/billing/currency are rejected inside `BEGIN IMMEDIATE`.
Stale edits are rejected. Existing standard catalog and VM prices are preserved.

Quotation pickers use the quotation **issue date** and currency:

**Project agreed price → linked customer's agreed price → standard price.**

A project’s explicitly linked customer determines inherited pricing. Free-text
customer names never trigger a match. Without a project, an explicitly linked
quotation customer can supply its prices. Catalog and VM pickers show the actual
price and source. Linux and Microsoft Windows are separate VM price entries.
Unconfirmed standard VM prices remain unpriced; explicit agreed prices are valid.
No currency conversion is assumed. Missing applicable prices remain editable blanks.

Selecting a service copies its price into the quotation row. Manual overrides
remain available. Changing the customer, project, price list or standard library
never reprices existing rows. Select a new service/VM or explicitly edit prices to
change them. A user assigned only a quotation can use standard prices; agreed
pricing requires access to the project/customer and is clearly marked unavailable
otherwise. This does not grant access to the underlying customer or its documents.

## Contract & agreed services

Open a project’s **Contract & agreed services**, also linked from the customer
overview. Store initial quotation, accepted Won revision, reference, dates,
currency, renewal, notes and editable services. Each service has contracted
quantity, price, percentage discount, monthly/one-time period, unit/fixed pricing
method and fixed-contracted/actual-consumption billing basis.

- **Save proposed version** creates a new immutable Proposed version.
- **Copy accepted quotation** requires confirmation and the actual accepted Won
  revision belonging to the project. It uses the frozen accepted snapshot, even
  if the editable revision changed afterward. It creates a Proposed version.
  Percentage-dependent support is copied as the accepted fixed customer fee;
  internal percentage drivers and purchasing information are not copied.
- **Approve entered contract** requires confirmation and saves a new Approved
  version, retaining preceding versions. It needs a reference and services.
- Upload signed contracts/supporting documents to a selected version. PDF, PNG,
  JPEG, UTF-8 TXT/MD, maximum 10 MiB each. Uploads validate extensions/signatures;
  they never approve, extract or modify prices. New contract versions retain
  links to earlier documents. Linked historical documents cannot be deleted
  through the ordinary project attachment interface.

Project Read/Edit permissions apply to versions, documents, service terms and
project price tables. Contract approval requires project Edit access; it does not
change authentication roles or automatically populate quotation price lists.

**Promotion boundary:** copying an accepted quotation copies row prices and line
discounts. If that quotation also has a summary/promotion discount, a prominent
review warning is saved in the proposed contract notes. Agree the applicable
contract service rates/discounts explicitly before approval; promotional quotation
terms are not silently averaged into permanent contract prices. The linked
accepted snapshot retains the original policy. No OCR or price extraction occurs.

## Monthly consumption

Open the project’s **Monthly consumption**, choose a month, enter quantities, and
save. A new month uses the newest Approved contract version covering that month.
Proposed contracts never supply charges. Effective contract dates are treated at
month granularity (a month that overlaps the contract is eligible); there is no
daily proration. Supported months start in 1900.

- Fixed-contracted billing uses contracted quantity; Actual billing uses actual
  quantity. A unit charge is quantity × agreed price × (1 − discount/100), rounded
  once per service to cents. A fixed-fee price is charged once if the applicable
  quantity is nonzero. Zero quantities produce zero charge.
- Show contracted/actual quantities, snapshotted agreed price, line discount,
  basis and calculated charge. Highlight actual quantity above contract even
  when contracted billing keeps the charge fixed.
- Only monthly services enter the sheet. Charges exclude one-time services and
  sales tax; these are operational charge estimates, not invoices/revenue.
- **Copy previous month's quantities** copies actual quantities for matching
  stable service IDs. New services start at zero. It never copies old rates into
  a new month or changes saved prices; review and save to commit the quantities.
- On first save, currency, contract version, rows, quantities, rates, discounts and
  charges are stored as a snapshot. Later contract/list changes do not alter it.
  Editing a saved month changes quantities/notes using its existing prices.
  Previous saves remain in monthly history. Stale versions/contract changes are
  rejected. There is no invoice locking or approval/accounting ledger.

The customer overview shows saved current-month charges separated by currency,
number of services above contract, linked projects, approved contract rates,
current customer prices and renewal dates within 30/60/90 days. Missing monthly
sheets do not produce invented charges. Proposed replacements do not hide the
last approved contract. Indicators use accessible project data only.

## Quotation appearance and optional summary discount

Customer metadata shows **Date and Reference** only in the live preview, print/PDF
and Excel. Revision, validity and currency remain internal editing/history data.
Currency stays beside monetary values or in their column headings. Monthly total
labels/amounts are red, bold and 12% larger; one-time totals have a pale-yellow
background with dark text, at the same enlarged size. Layout remains compact.
The removed yearly/contract/tax/combined summary rows and old VAT disclaimer stay
hidden. Excel retains hidden calculation dependencies, without those displayed
labels. Existing manually written ordinary terms are retained.

**Show discount in cost summary** is off by default, including company templates.
Enabling it explicitly activates the selected policy and adds original fees,
orange deduction lines and payable fees. Select percentage/fixed, eligible
sections/rows, recurring/one-time/both, full contract/first N months, and an optional
customer description. Disabling it removes the policy's generated rows/wording.
Saved hidden historical discounts retain their old calculations until explicitly
changed; the app does not retroactively reprice historical quotations.

One calculation engine is used by preview, PDFs, exported values, statistics,
accepted snapshots and internal costing. Excel formulas implement the same basis
and were independently recalculated during verification:

- Eligibility expands to row IDs once, so overlapping section/row selections do
  not duplicate deductions. Summary percentages apply once to the eligible **net
  fees after line discounts**, rather than replaying a line discount.
- A fixed amount is **one total discount budget** across selected recurring months
  plus eligible one-time fees, capped at that net basis. It is allocated between
  recurring and one-time fees proportionally. The recurring allocation is spread
  across promotional months to cents: initial months take a cent more when needed.
  Both fee tiers and the regular monthly fee afterward are disclosed. No negative
  fee or duplicated fixed budget is generated.
- Recurring and one-time discounts are applied before the saved sales-tax policy.
  Full-contract amounts and costing use the exact allocated total. Missing prices
  remain unknown; zero is a valid amount.
- Internal costing allocates deductions over eligible positive rows and reconciles
  included-tax rounding. Independent target-margin price suggestions are disabled
  for an active fixed summary budget, because it couples prices across rows;
  explicit worksheet prices and the apply-preview remain available.

## Archiving

The quotation list defaults to **Active**. **Archived** and **All** reveal archived
families. Use individual checkboxes, select the current page (25 families), or
explicitly select every family matching the current search/date/visibility filters.
The toolbar displays family and revision counts; selection is cleared when leaving
or reloading the list. Review the confirmation before Archive/Restore.

The server reloads all revisions, checks edit access to **every revision**, rejects
blocked selections without partial changes, and rejects a changed family/permission
selection after preview. New revisions of an archived family remain archived.
Archived families must be restored before changing their reference identity.

Archiving changes only family visibility and writes audit history. It does not
remove data or release references. Costing, contracts, outcomes, attachments,
accepted values, Won/Lost counts and historical statistics stay unchanged.
Statistics intentionally include archived families even when the list displays
only Active or Archived. Deleting a verified unused draft is the separate,
previously authorized reference-release operation; archiving never invokes it.

## Storage, backups and limits

`<existing data directory>\workspace.sqlite` retains the old records, users, ACLs,
reference registry, costing and outcomes. Schema 7 adds:

| Table | Purpose |
| --- | --- |
| `agreed_prices`, `price_history` | Scoped prices, effective periods, versioned audit |
| `contracts`, `contract_documents` | Immutable contract versions and document links |
| `consumption`, `consumption_history` | Monthly price snapshots and prior edits |
| `quotation_archives`, `archive_history` | Family visibility and archive/restore audit |

Customers and project/customer links use the existing `records` table. Files stay
under the existing `attachments` folder; document metadata still uses `attachments`.
The standard backup includes all new tables and referenced files. Restore accepts
schemas 1–7 into a new directory. Back up the **full instance** for disaster recovery.
The additive staff JSON format remains compatible with versions 1–3 and includes
customer/project/quotation records, not separate costing/outcome/price/contract/
consumption/archive ledgers or signed files. The Import/Export screen explains this.

SQLite serializes writes using atomic transactions. Keep one shared local database
behind Waitress/IIS for the team; do not use per-user copies or a database on SMB.
Customer/project record editing and quotation editing retain the application's
existing last-save-wins behavior; price, contract, monthly sheet, costing, outcome
and archive confirmations reject stale state. No new simultaneous-user/load
capacity claim or Windows/IIS deployment certification is made. There is no FX,
automatic invoice/payment recognition, OCR, or contract-promotion conversion.
