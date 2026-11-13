> Historical feature guide: the current [team operations guide](team-operations.md)
> overrides single-user, demo-pricing and OS-generation instructions below.

# Cirrus quotation studio (quotation schema 2)

The latest upgrade adds compact worksheet spacing and a Cirrus Hosting VMs library.
See [its usage and safe Windows update guide](hosting-vms.md). Database and workspace
export versions are now 3; the quotation document structure remains version 2.

This is an upgrade of Joseph Workspace, not a reset. Notes, catalog, projects,
attachments and settings continue to use the same local data directory. No live
user data or original customer workbook belongs in Git. The bundled logo is the
standalone company logo from the reference; descriptions and prices in tests are
synthetic. Personal contacts, customer identity, quote reference, deadlines,
redacted zero prices and the source's 1,000 setup fee are not seeded.

## Editing

Open Quotations → Create quote, or select an existing quotation. The studio fills
the browser window, with workspace navigation hidden and most of the width given
to the quotation. Use ← Workspace to return. The left pane holds structure and
advanced settings; the right pane is the main editing surface. Drag the divider
or use its Left/Right arrow keys. Small screens have Structure & settings /
Quotation tabs.

Click quantities, prices, services, types, pricing descriptions or comments in
the quotation to edit them directly. Public header fields can also be edited in
place. Changes synchronize with the left controls and recalculate using the server's
Decimal engine without replacing the focused input, so typing is uninterrupted.
Use **+ Add row** in a group, **Copy row**, or **Remove** alongside a row. **Options**
opens that exact row's advanced settings on the left for billing, calculation
mode, eligibility, discounts, internal cost or moving between groups. Catalog
buttons take you to the corresponding catalog picker on the left.

Production, Disaster Recovery, Monitoring, Cyber Security, Connectivity and any
custom category each have a separate table, repeating column header, subtotal
bar and blank space between categories. Blue bands identify groups inside a
category. Copy category includes all its groups/rows and remaps its support fee
references. Remove category removes its groups and cleans calculation references.
For Development or another environment, use **+ Add environment** on the left,
then type its name in the quotation: it includes VM/compute, security, backup
and 8×5 support groups. Add category creates a blank category. New rows default
to quantity 1 and an unpriced fee; zero quantities remain supported drafts.
New environment categories do not automatically join the temporary discount:
choose their eligibility explicitly if required.

Every visible category automatically appears in the summary with monthly,
first-year-before-discount and one-time amounts. Category names, order and
amounts follow edits automatically; there is no manual summary-row maintenance.
The separate first-year recurring total below applies the actual discount period.
Hidden categories retain their charges but stay hidden in customer tables/summary;
exclude their charges as well if they should not be billed.

Save explicitly: live editing does not autosave. Unsaved changes are indicated;
PDF/Excel/CSV exports and duplicate/revision actions are blocked until you save,
to avoid using stale prices.
Navigation warns if edits would be lost. Invalid inputs retain the editable cells
and dim stale computed values while showing the validation reason. Correct the
input to recalculate. Customer print/PDF/Excel/CSV exclude all editing controls.
The direct-editing layout does not rewrite saved category structures. The hosting
library upgrade migrates the database to version 3 without changing quote structure. New DR
defaults include a backup group; add that group manually to an older quote if needed.

- **Quotation details:** title, customer, contact, linked project, freely editable
  reference (1–80 printable characters), revision (1–1,000,000), ISO dates,
  currency, scope and internal notes. The project display name is a per-quote
  snapshot and can be edited independently of the linked project. Number + revision must be unique.
- **Branding snapshot & signatures:** company, logo, address, contact, VAT and both
  signature headings/fields. PNG/JPEG logos must be at most 400 KiB and 2000 × 2000.
  Every quote stores its own branding, including its image bytes in the structured
  document. Changing global settings never changes existing quotes.
- **Formatting, columns & summary:** Cambria/Arial/Calibri, normal/large text,
  A4 landscape/portrait, banner/summary headings, labels, visibility and order.
  Category summary entries are always automatic; aggregate lines remain selectable.
- **Contract, discount & tax:** duration, percentage, eligible rows/sections,
  discount months and optional wording override. Tax mode/rate and wording are
  editable. Blank wording generates consistent text from the configured values.
- **Service sections & rows:** add/rename/duplicate/delete/reorder top-level
  sections and two-level subsections. Each accepts catalog snapshots and custom
  rows. Rows have independent Service / Sub Service / Type fields: these are not
  hierarchy levels. All descriptive fields, custom units and pricing-model
  descriptions are free text. Copying a catalog row requires matching currency.
  Use Move to section to relocate rows; arrows reorder them. Save as catalog item
  prompts for a unique code and copies a custom row without modifying the quote.
- **Terms, signatures & footer order:** edit/add/duplicate text blocks, move or
  remove blocks from output, or restore them. Company/customer signatures and
  footer can be moved or removed independently. Reusable source wording is editable;
  date/year/renewal terms are flagged for review. Generated discount wording uses
  configured months, not an expired deadline. Review all manual legal wording,
  especially annual-renewal text if changing contract duration or tax treatment.

Limits: 100 sections, 2,000 rows, 100 term blocks, 100-row percentage dependency
chains, 1–1200 contract months. These bounds protect a local single-user app;
there is no fixed row count per section. Text fields allow up to 100,000 characters.
Hidden sections remain in calculations; **Exclude all charges** removes their
charges. This distinction is displayed in the editor. Removed targets are cleaned
from eligibility lists; review fees and discounts after a structural removal.

## Prices and exact calculations

Values use Decimal and two currency places, **ROUND_HALF_UP**. Quantities can be
zero (draft, no charge in every method), up to 1,000,000. Numeric drivers are decimal
strings; price/fee/cost must be nonnegative and at most 1,000,000,000,000. Percentages
are 0–100. Draft rows still show that pricing is needed; a zero quantity does not
create a charge. No currency conversion is performed.

Methods:

1. Unit: `quantity × unit price`.
2. Fixed: explicit fixed fee. Quantity greater than zero activates it, but does
   not multiply it. Select this mode explicitly to override a calculated charge.
3. Percentage: `sum(distinct eligible rounded row fees) × percent / 100`.
   Quantity greater than zero activates the percentage fee, but does not multiply it.

An optional line discount (also used for migrated legacy quotes) applies before
rounding the row's final amount. Each row is rounded once to cents. Percentage
bases use those rounded results. Selecting both a section and one of its rows
counts that row once. Parents include descendants. Percentage cycles, references
to removed targets and mixed monthly/one-time dependencies are rejected, including
on inactive rows. Excluded rows/sections return 0 and never contribute. Included
rows return 0 but display **Included — no additional charge**, distinct from a
zero-priced row. Blank active prices remain **Unpriced**, not zero. Any unpriced
contributor makes the affected subtotal/total Unpriced.

Production/DR support defaults to 20% of the initial eligible service subsections,
excluding the support fee itself. Review eligibility for new rows added directly
to the parent section. SOC can be per-EPS (unit) or explicit fixed fee. Cyber
Security sums all its rows, including both VPN variants; no spreadsheet range is
copied. New service rows and catalog prices start unpriced; no setup fee is added.

The temporary discount defaults to 30% on Production, DR and Monitoring for six
months. Let regular monthly be R, eligible monthly be E, discount rate be p,
discount months be D, contract months be M:

```text
monthly discount = round(E × p / 100)
discounted monthly = R − monthly discount
contract recurring = discounted monthly × D + R × (M − D)
first-year recurring = discounted monthly × min(D, 12, M)
                     + R × (min(12, M) − min(D, 12, M))
annualized regular run rate = R × 12   [separately labeled, optional]
```

Discount duration cannot exceed contract duration. Disabling it uses zero discount
months and rate. One-time charges are separate, never multiplied by months or
included in the recurring discount. The combined **contract** total explicitly
covers the whole configured contract plus one-time charges (it is a first-year
combined total only for a 12-month contract).

Tax applies once to contract recurring + one-time, rounded to cents:

- VAT exclusive (default): estimated `base × rate / 100` shown, **not added**;
  final tax is applicable at invoicing. Default rate is 0, not an invented VAT rate.
- Add tax: calculate and add tax to the combined contract total.
- Included: extract `base × rate / (100 + rate)`; do not add tax again.

Manual tax/discount wording overrides are yours to maintain; clear them to return
to generated text. No legal or currency conversion is performed by these rules.

## Customer output and Excel limitations

Preview and browser Print / Save as PDF use **the same HTML/CSS and calculation
results**. Defaults follow the workbook's Cirrus logo, blue column/title bands,
gray/red section headings, wrapped text, summary, terms, signatures and company
footer. A4 landscape is the default, table headers repeat and content flows across
pages. Browser print supports portrait as selected. Disable browser-added URL/date
headers if desired. Browser fonts and printer margins can differ on your Windows
VM; verify a sample PDF before sending a quotation.

Customer HTML, PDF, Excel and CSV omit internal costs, margins and internal notes.
JSON workspace backups/exports are for you and intentionally retain internal data.

Excel export contains editable quantity and row-driver cells and formulas for
unit/fixed/percentage fees, support dependencies, discounts, mixed discount periods
and tax. The **Pricing settings** sheet contains public calculation drivers, not
internal cost sheets. Formula results are cached from Decimal for readers without
a calculation engine; Excel is instructed to recalculate on open. Long row text
is continued on additional rows rather than truncated. Repeated print headers,
landscape/portrait, company logo, terms and footer are included.

Explicit limitations:

- Excel keeps the eight canonical workbook columns. Custom labels and visibility
  are retained; the editor's custom column order applies to HTML/PDF, not XLSX.
- In Excel, F is the driver: unit price, fixed fee or percentage according to the
  row's method. Method, billing, state and eligibility are exported snapshots;
  change these in the app and re-export. Quantity, driver, line-discount, tax and
  period inputs recalculate; editing informational method/state labels does not.
- Summary formulas can occupy hidden rows when their output is deselected; do not
  delete them if you want dependent totals to recalculate. No XLSX reimport exists.
- XLSX uses Excel numeric cells and its rounding, which have finite precision.
  The app's Decimal result remains authoritative for extremely large/high-precision
  values; exports that exceed 15 significant input digits or 10 trillion in totals
  are refused with an explicit error rather than producing different totals.
  Independent LibreOffice checks cover ordinary nonzero prices, changed
  quantities, blanks, zeros and included tax. No proprietary Microsoft Excel
  automation was available here.
- Signatures are text fields, not digital signatures. Excel lays signature/term
  blocks sequentially; browser PDF provides the customer page layout.

## Upgrade an existing Windows installation safely

1. Stop Waitress with **Ctrl+C**. Keep the old code until the new copy is verified.
2. Set your existing custom data directory if used. Do not choose a different path:

   ```bat
   set "JOSEPH_DATA_DIR=C:\JosephWorkspaceData"
   .venv\Scripts\python scripts\backup.py backup C:\Backups\joseph-before-direct-editing.zip
   ```

   For the default data folder, leave JOSEPH_DATA_DIR unset. Pick a new backup
   filename; the command refuses overwrite. Verify a restore into a new test
   directory if this is your first backup. The archive covers SQLite and files.
3. Get branch `feature/hosting-vms-and-compact-quotes` into the code directory, preserving
   your live data folder outside it. With a Git clone and clean local code:

   ```bat
   git fetch origin
   git switch feature/hosting-vms-and-compact-quotes
   git pull --ff-only
   setup.bat
   start.bat
   ```

   If downloaded as ZIP, extract the branch into a **new application folder** and
   run setup.bat there; use the same existing JOSEPH_DATA_DIR. Do not overwrite or
   move your data directory or copy a running database.
4. Open http://localhost:8000, check old notes/projects, then open an old quotation,
   create a new one and print a sample. If upgrading from database version 1,
   first startup transactionally upgrades user_version 1 → 2; IDs, timestamps, attachments and original legacy
   line data are retained. Quotes gain structure and a branding snapshot captured
   from current settings at upgrade. Legacy lines had no billing period, so they
   migrate as **one-time** to preserve original totals; review/change billing if
   your old quote actually described a recurring service. Old tax remains added.
5. Make a new post-upgrade backup. To roll back, stop server, use the previous
   code, restore the **pre-upgrade** backup into a new directory, point
   JOSEPH_DATA_DIR to that copy, and start. Do not run old code on the v2 database.

Windows .bat execution and Windows printer output still need VM verification;
the development environment used Linux. No application was publicly deployed.
