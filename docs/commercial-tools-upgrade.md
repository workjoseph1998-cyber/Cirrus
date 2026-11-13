# Cirrus Workplace: commercial tools upgrade (schema 6)

> Historical release guide. For the current app use [Version 8 upgrade and rollback](version-8-upgrade.md).

This release builds on V5. It preserves the existing branding/navigation, compact
customer quotation editor, unwanted-summary/VAT/discount cleanup, records,
attachments, accounts, record permissions, VM library, catalog and IIS configuration.
The new comparison, costing and outcome data use the same server SQLite database.

## Why the V5 totals and references behaved that way

V5's quoted-value card included only priced Sent/Accepted quotations. Creating a
Draft changed its count but not that amount. The new **Quoted amount** includes all
priced latest USD revisions, including Drafts. Blank prices remain unpriced and do
not invent a value; zero is a valid amount. Dates/filter ranges still matter.

V5 permanently assigned a reference on every save, including drafts, and deletion
kept it as issued history. New tracked, never-sent opportunities release their
reference when their workflow is Draft and their **last draft revision is deleted**.
An opportunity previously Sent/Won/Lost remains protected even after returning to
Draft. Historical/imported references remain protected. Moving an internal draft
through Under review/On hold and back to Draft does not count as sending it.

Existing V5 data has no reliable send-history audit. It is not automatically recycled.
For an older **deleted** reference originally created by the quotation editor, an
administrator can open References → Review older unused draft, verify it was never
sent or externally issued, type its reference and release it. Known sent/completed
history and imported/historical references cannot be released through this review.
Every release records its user/time in the activity ledger. Do not attest an issued
number was unused. New verified draft releases happen automatically on deletion.

Unused active reservations can be released by their owner with **Release unused
reservation**, or expire after 30 minutes. An assigned quotation number requires
quotation deletion; the reservation button cannot bypass assigned/issued protection.
References distinguishes assigned-never-sent drafts from deleted protected history.
Last used CIR includes assigned drafts and issued history. Suggested next uses the
highest remaining occupied sequence; it does not automatically fill older gaps.
A released gap can be entered manually and reserved safely. Concurrent uniqueness
constraints and atomic reservation/assignment remain in force.

## Upgrade on the Windows VM

1. Record Settings / Backup → Data directory. Stop Waitress/the Windows service or
   scheduled task that runs the app.
2. From the old application folder with the **same launch/data-path environment**:

   ```bat
   .venv\Scripts\python scripts\backup.py backup C:\Backups\Cirrus-before-commercial-tools.zip
   ```

   Choose a new archive name, retain the old code and configuration, and copy the
   backup outside the VM. Staff JSON export is not a full backup.
3. Download branch `feature/cirrus-workplace-commercial-tools` as ZIP into a new
   application folder. Keep CIRRUS_DATA_DIR / JOSEPH_DATA_DIR pointing at the existing
   data directory; do not copy a test/empty database over it.
4. Run `setup.bat`, then launch using the existing service/internal configuration
   or `start.bat` for localhost. **Do not run init-admin again** for an existing
   installation. No new runtime packages are required beyond V5 requirements.
5. Startup transactionally upgrades SQLite to **schema 6**. It adds quote_costing,
   quotation_outcomes, quotation_activity and reference_usage. Existing record JSON,
   customer amounts, attachments and ownership are retained. Legacy Accepted maps
   to the latest accepted revision’s Won snapshot even when a newer Draft exists; legacy Rejected/Cancelled maps to Lost for workflow reporting.
   Old outcome dates/users are unknown, never fabricated, and require staff review.
6. Verify old quotations, account permissions, the new tools and statistics before
   colleagues resume editing. Test a restore into a new directory. Full backups
   include private worksheets, outcome snapshots/history and reference-use history.

**No IIS, DNS, certificate, firewall or reverse-proxy changes are needed.** Continue
using the existing internal HTTPS hostname, allowed hosts and localhost Waitress
backend. The cloud task has not installed the update on your VM or tested its IIS.
Keep every colleague's browser pointed at this shared server/database.

For rollback, stop the app, restore the **pre-upgrade** backup to a new directory
and use the matching prior application code. Do not downgrade a schema-6 database
in place. V6 backup/restore accepts schemas 1–6; the existing 5 GiB uncompressed
restore limit remains. Back up launch/service/IIS/certificate configuration
separately; the application ZIP backs up SQLite and attachments with checksums.

## Compare revisions

Open a saved quotation → **Compare revisions** (also available in the quotation
list). Choose two accessible revisions of the same reference. The page shows added
items in green, removed items in red, modified fields, quantities, selling drivers,
line fees, scope/exclusions/descriptions/terms and full quotation totals/difference.
**Only show changes** removes unchanged item rows. Reordering alone is not an item
addition/removal; moving groups or changing inclusion/visibility is a recorded change.

Rows match by their saved item IDs. Imported revisions with new IDs use only unique
service/sub-service/type/unit/billing matches. Repeated ambiguous items are shown
as added/removed rather than guessed. Hidden/excluded items remain comparable with
flags, while private purchase costs/internal support drivers are not emitted.
Both selected revisions require server read permission; another family's revision
is rejected. USD difference is shown only for USD-to-USD comparisons, with no FX
conversion. Percentage difference from zero/unpriced prior totals is undefined.

## Internal costing: separate and staff-only

Open **Internal costing** from the saved quotation or quotation list. Only an
Administrator or Editor with edit access to that exact revision can view, calculate,
save or apply costs. Viewer accounts and Editors with Read-only grants cannot open
it. The worksheet is never embedded in the customer quotation.

Each line captures description, purchase quantity, supplier and quotation reference,
unit purchase cost, purchase billing, shipping/documentation/implementation/other
costs, selling unit/fixed driver, target margin, supplier validity and private notes.
Calculated columns and cards show full-contract cost, selling value, profit and
margin. All amounts use that quotation's currency; no conversion is attempted.

- Purchase cost = purchase quantity × unit purchase cost × contract months for
  monthly purchasing (×1 for one-time purchasing), plus the four additional costs.
- Additional costs are **one-time line totals**, added once—not once per unit or
  per month. Put each charge on one line only; totals sum each line once.
- Purchase quantities are independent of quotation quantities. They initially
  match, but applying selling prices never overwrites customer quantities.
- Selling values use canonical quotation pricing across the saved duration and
  historical adjustments, **excluding sales tax**. Included sales tax is removed;
  added tax is not profit. This net basis differs deliberately from the gross
  quotation/outcome cards. Line allocations reconcile to the canonical net amount.
- Profit = selling value − total cost. Margin = profit ÷ selling value ×100.
  Markup divides by cost and is different. Zero selling values have undefined
  margin; blank purchase prices are unknown, not zero.
- Suggested net selling total = total cost ÷ (1 − target margin ÷100). Targets must
  be nonnegative and strictly below 100. A unit/fixed driver is calculated from the
  quotation billing/quantity/discount/tax basis. Rounding may introduce cent-level
  differences; the explicit application preview is authoritative. Quantity zero
  and percentage-based services have no direct suggested selling driver.

Typing calculates privately without saving the customer quotation. **Save internal
costing** stores only that revision's private worksheet. **Save and use target margin
suggestions internally** updates its proposed selling drivers, still without changing
customer prices. Then select **Preview applying selling prices**, review old/new
prices and dependent fees, check confirmation and **Apply selling prices to quotation**.
Only selling unit/fixed prices change; private fields and purchase quantities do not
enter the customer document. The accepted Won revision cannot be repriced this way;
create another revision. Unsaved worksheet changes are not applied by the preview.

A changed worksheet/quotation after opening or preview causes a stale-version error
instead of applying unseen changes. New revisions copy existing costing into an
independent worksheet. Row IDs retain supplier entries across reordering; removed
rows' costs remain archived privately and are excluded from totals. Imported revisions
with unrelated IDs retain old copied rows as archived rather than guessing mappings.
Private costing and outcome data travel in full backups, not staff JSON exports.

## Outcomes, accepted values and history

Open **Outcome / workflow**. States are Draft, Under review, Sent, On hold, Won, Lost.
Won/Lost require a suggested reason (or Other), an actual outcome date and optional
notes. Won additionally requires an accessible, fully priced accepted revision of
the same reference. Zero is allowed; unpriced is not. The server records the actual
signed-in user and timestamp; submitted user IDs are ignored. Future outcome dates
are rejected. Workflow belongs to the reference family, not each revision independently.

Won stores a **frozen accepted quotation document, currency and amount**. Creating
or editing a later revision changes current quoted value but not the accepted value.
The outcome page links **View frozen accepted quotation**. Editing reason/date does
not recalculate an existing accepted value. Explicitly selecting another accepted
revision (or checking the replacement option) records a new decision in history.
An accepted Won revision cannot be deleted, renumbered or moved to another reference
without reopening/changing its outcome. Direct price edits cannot overwrite its
frozen snapshot; history retains the accepted value at decision time.

Outcome/history pages require quotation access. Edit actions require edit access;
Viewers read permitted workflow information but cannot modify it. Accepted document
and value access also checks the accepted revision, so sharing only a newer revision
does not expose an otherwise private older revision. Every workflow/outcome change
records old/new values, date/time and user. Internal costing events expose no supplier
or cost fields in the workflow history. Conflicting outcome updates require reload.

Ordinary quotation header status controls handle nonterminal workflow states. Won/Lost
must be recorded through Outcome; finished opportunities must be reopened there.
New revisions retain the family's outcome. Importing a staff JSON quotation marked
terminal without its separate workflow history creates an Under review workflow,
not an unaudited new Won/Lost decision; the record itself is preserved. Full restore
retains the original outcome/history rather than reconstructing it from JSON.

## Statistics and date basis

The quoted amount is the existing **full-contract customer quotation amount**:
recurring fees over the saved duration plus one-time fees, with saved tax treatment
and historical pricing adjustments. The short tooltip explains this basis. It is
neither revenue recognition nor invoiced revenue. USD totals include only USD;
other currencies have separate native quoted/won/lost amounts without conversion.

- Total count and quoted value: one latest valid saved revision per reference,
  including priced drafts. Unpriced families count but add no invented amount.
- Quotation activity, monthly amount/count charts and pending figures use the
  latest revision's **quotation issue date**, not creation or last-edit timestamps.
- Won/Lost counts and values use **outcome date**. A quote issued in September and
  won in October can therefore have zero October issue count but one October win.
- Won quotation value uses its accepted frozen amount; Lost value uses the latest
  saved quotation amount. Win rate = Won ÷ (Won + Lost), regardless of currency,
  with undefined/no-outcome rate shown as a dash. Pending is Under review/Sent/On hold.
- Filters offer this month, last month, this year, selected month/year, custom and
  all time. Legacy outcomes without a recorded date appear only in All time and
  are flagged for review. Reasons are counted in a small Won/Lost breakdown.
- All work figures respect record permissions. A user without access to the accepted
  revision sees an unavailable accepted value rather than its private amount.

The existing hidden unwanted summary rows, old VAT disclaimer/discount wording,
compact tables, customer support privacy and export styling remain unchanged.

## Known limits and verification

There is no external supplier document authoring, currency-rate engine, accounting
integration or full collaborative quotation editor. General quotation edits remain
last-save-wins; costing saves/applications and outcome edits have stale-version
checks. Old deleted V5 numbers need human verification because send history did not
exist. Duplicate imported rows without stable identity cannot be matched speculatively.
Large catalogs still use the existing full-record loading design.

Tests use only temporary synthetic data. Unit/integration coverage includes cost and
margin math, independent revision worksheets, explicit application/confidentiality,
comparison/reordering, outcome reasons/permissions/history/date filters, accepted
snapshots, draft recycling and schema-5 migration/backup restore. Browser workflows
cover the commercial path plus prior quotation/VM/import/permission regressions.
Windows/IIS deployment and real VM load cannot be verified from this Linux environment.
