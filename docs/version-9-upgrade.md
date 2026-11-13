# Cirrus Workplace — Version 9

Version 9 builds on the complete Version 8 release, commit `b2fd8b8`, not the
older commercial-tools application. Product **Version 9** uses **SQLite schema 8**.
No Windows VM deployment or simplified updater is included. Runtime packages,
external data-directory selection and IIS/Waitress configuration are retained.

- [Version 8 baseline ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/feature/cirrus-workplace-v8.zip)
- [Version 9 ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/feature/cirrus-workplace-v9.zip)
- [Verification and changed components](version-9-verification.md)

Sign in to GitHub before downloading from the private repository. Alternatively
select the appropriate branch and use **Code → Download ZIP**.

## Safe manual upgrade and rollback

1. From the current application directory, using the **same Windows account and
   environment variables as the running service/launcher**, record the data path:

   ```bat
   .venv\Scripts\python -c "from workspace_app import data_directory; print(data_directory())"
   ```

   Keep `CIRRUS_DATA_DIR` or legacy `JOSEPH_DATA_DIR` unchanged. If both are set,
   they must resolve to the same external folder. Windows service accounts have
   different LocalAppData directories; do not accidentally select a fresh database.
2. Stop the app/Waitress service. Create a full backup from the old code folder:

   ```bat
   .venv\Scripts\python scripts\backup.py backup C:\Backups\Cirrus-before-Version-9.zip
   ```

   This verifies a consistent SQLite snapshot and attachment archive and refuses
   to overwrite an existing backup filename. Keep the old application, personal
   launcher/service configuration, environment values, relevant IIS configuration,
   certificates and NTFS permissions separately. Protect confidential backups.
3. Extract Version 9 into a **new application folder**, outside the data directory.
   Run `setup.bat`. Do **not** run `init-admin` again for an existing workspace.
4. Update only the code-folder path in the existing launcher/service command.
   Keep its data directory, port/bind, trusted proxies, hosts and HTTPS settings.
   Start through that launcher. Schema 8 migrates automatically. Keep one shared
   local SQLite database behind the same IIS URL; colleagues must not run separate
   database copies. This update requires no IIS configuration change.
5. Verify login, representative old quotations/revisions, frozen accepted values,
   costing, attachments, customer/agreement access and exports. Then review any
   support-migration alert shown to administrators. No test data is installed.

For rollback, stop Version 9 and preserve a backup of any new work. Use the new
backup script to restore the **pre-upgrade** archive into a **new unused** directory:

```bat
.venv\Scripts\python scripts\backup.py restore C:\Backups\Cirrus-before-Version-9.zip --target C:\CirrusRollbackData
```

Launch the retained Version 8 code against that restored directory. Never point
Version 8 at a schema-8 database: downgrade is deliberately blocked. A pre-upgrade
snapshot does not contain later work; reconcile that work explicitly. Do not mix
SQLite files or overwrite the upgraded/original data folders. A JSON export is not
a full backup and should not be used for this rollback.

## Quotations first

The quotation page shows compact KPI cards, context-sensitive date/search/visibility
filters and the quotation table. **View monthly statistics** is collapsed below
the list. Year/month fields appear for Selected month/year; Start/End appear for
Custom range. Charts plot contract value by issue month and quotation counts;
these are not recurring-fee charts.

Rows have smaller padding, no redundant Type column and no generated reference/
revision subtitle. Tools are in a per-row menu. References remain searchable, and
references manually written into titles remain ordinary editable title text.

## Three distinct quotation figures

| Figure | Exact basis |
| --- | --- |
| Quoted value | Full saved contract duration, plus one-time charges, with saved discounts/tax treatment, from the latest accessible revision per normalized reference family |
| Monthly quoted fees | Initial payable recurring monthly fees from those revisions, excluding separately added contract tax and one-time fees; tax already embedded in prices stays included; a temporary promotion's regular fee afterward remains visible on the quotation |
| Won value | Frozen accepted full-contract amounts from the explicitly selected accepted revisions |

For example, a saved USD quote with 100/month for 12 months, a 50 setup fee and
10% added tax has a **1,375 quoted value** and **100 monthly quoted fees**. If a
new revision changes the monthly fee to 200, those become **2,695** and **200**;
an earlier accepted revision remains **1,375 Won value** until explicitly changed
through the outcome workflow.

Quoted activity uses quotation issue date. Won values use outcome date. All figures
respect record access and selected dates; revisions are not added together. USD
cards exclude other currencies, which remain separate without conversion. Priced
drafts are included. Unknown prices are excluded from amount sums and counted as
unpriced; a fully priced zero remains a real zero. Quantity-zero rows are inactive
and charge zero, so an empty draft can legitimately have zero value. A monthly amount can be known
while a one-time amount is unknown. Invalid latest revisions stay unknown: Version
9 fixes the earlier fallback that could silently reuse an older revision's value.
Invalid issue dates are included only in All time, outside month charts.

Archiving changes visibility, not historical statistics. Permanent deletion removes
the affected quotations from statistics. These figures are quotation amounts,
not payments received, invoices or recognized revenue.

## Archived permanent deletion

**Archived** view exposes **Delete selected permanently**. Select individual,
current-page or all matching families, then review the reference, affected titles
and every revision. Type `DELETE` to confirm. This is separate from archiving.

The server requires archived state and edit access to **every revision**. An accepted
Won revision blocks the entire selection until its outcome is reopened. A revision
linked to a contract version remains protected too; remove/review those business
links through an appropriate workflow rather than deleting contract history.
Permission, family/quotation content, attachment or internal-cost version changes
invalidate a deletion preview. Blocked selections make no partial changes.

Deletion removes the selected quotation records, per-revision costing, quotation
attachments and stored pre-conversion support documents. It retains minimal audit
and reference history. Issued, sent and imported/historical numbers remain protected.
Only a verified never-sent Draft family's last deletion releases its number, following
the earlier explicit policy. Backups can still contain deleted information; manage
them under your retention policy. Customer/project contracts and their files are
not deleted with a quotation.

## Standalone 8×5 Request Fulfillment

Support is a category alongside Production, DR and Monitoring. The fee remains a
percentage dependency internally: choose a percentage and explicit category/row
bases in the editor. Customer default selections can also include service/VM keys,
so newly added matching items recalculate the fee automatically. Overlapping keys,
rows and category selections count a service once. Percentage cycles are rejected.
The customer sees the resulting service charge; support percentages, eligibility
drivers and internal comments are removed from customer documents/exports. Customer
Excel therefore retains a fixed final support fee; change dependencies in the app
and re-export rather than expecting the private percentage to recalculate in Excel.

Migration moves existing support groups into the standalone category **once**:

- Existing fee row IDs, quantities, individual percentages, exclusions and hidden
  flags are retained. Old Production/DR eligibility continues to include the moved
  fee where it previously did, by expanding those references explicitly.
- Row fees, regular/promotional fees, one-time charges, contract/tax/combined values
  must compare equal before and after conversion. No new support fee is added to
  an existing quotation. Private costing still follows the same row IDs.
- Frozen accepted document layouts are converted with the same check, without
  changing accepted values. Original converted quotation data is retained in the
  migration audit; backups retain the complete original database too.
- Invalid records or a failed equality check are left untouched and reported to
  administrators at **Support layout migration review**. They do not block the
  rest of the upgrade. Repair/save the original quotation to retry; accepted
  snapshots require explicit outcome review.

New quotations use one customer-default support row. Existing quotations/revisions
are not consolidated or repriced. A newly added environment gets a separate support
row explicitly based on its own groups; edit that base if using a single shared
fee instead. Removing a base category removes its eligibility; empty bases charge
zero. Review manual pricing text when changing structure.

## One Customers workspace

Projects disappear from navigation. Customer workspaces contain **Quotations**,
**Consumption**, **Agreed prices**, and **Contract / initial quotation** tabs. The
underlying project/agreement records, IDs, fields, attachments and permissions are
retained, including old direct URLs. Dashboard links use the customer workspace.

Existing linked projects appear as agreements/environments within their customer.
Unlinked legacy projects appear as their own customer workspaces. Names are not
fuzzily matched. Duplicate visible names are flagged; **Review customer link** lets
an authorized user explicitly link an old agreement after reviewing identities.
This does not delete or merge customer records, rewrite quotation text or grant
new access. Historical quotation identities remain editable/revisionable; the
current project link determines the workspace where a quotation family is listed.
Actual customer-record consolidation remains a separate reviewed operation.

New customers created in the UI receive their agreement workspace in the same
transaction, so contracts/consumption are available. Older customers without an
agreement receive one when **Create quotation** is explicitly used. When multiple
agreements already exist, choose one rather than guessing or merging their data.
Customer access does not silently grant access to all agreements: use existing
**Agreement sharing** where necessary. Purchase costs/margins and supplier expiry
are available only to staff with edit access to the relevant quote.

Customer indicators offer This month, Last month, This year, Custom and All time:

- Monthly calculated charges use saved consumption in the selected period's final
  calendar month; All time uses the current calendar month.
- Period consumption charges sum accessible saved billing-month snapshots whose
  month overlaps the selected dates. No daily proration is invented.
- Quotation count and Won value use the quotation/outcome date bases above.
- Currencies remain separate. No saved consumption means no invented charge. The
  interface labels calculated charges explicitly; there is no payment ledger.

Search by customer name/text and sort by name, current-month calculated USD charges
or recorded renewal date. Non-USD charges remain visible, without an invented FX
ranking. Contract expiry/renewal and authorized supplier-price expiries highlight
past dates and dates within 90 days.

## Compact pricing and defaults

The agreed-price table initially shows only existing overrides. Choose **Add / edit
service** for another catalog item or VM/OS configuration. Columns are Service,
Billing, Cirrus default and Customer price. Blank deactivates the current override
and inherits the standard rate; explicit zero remains zero. Linux/Windows VM rates
are distinct and the standard Cirrus Hosting VMs library is retained.

Existing agreement-level overrides retain Version 8 priority over customer prices.
Advanced effective dates, currencies and before/after price history remain available.
Changing the compact table requires a reason and rejects stale snapshots. Future-
dated agreements may require editing through the advanced effective-date interface.

Customer support percentages, default bases and discount rules are stored with
history. Agreement-specific default policies, if set through an old independent
workspace, retain priority after linking; review those separately when needed.
Defaults are copied only into new quotations. The customer page's Create quotation
uses the customer context; template rows with explicit catalog identities and new
service/VM selections use applicable agreed prices. Arbitrary manual template text
is not guessed into a catalog match. Manual exceptions remain editable, and saved
quotations, revisions and accepted values retain their own price/policy snapshots.

Pricing/default and consumption forms warn about unsaved changes. Copying an old
month is itself unsaved until saved, even if no field is edited afterward. Saving
one customer form asks before discarding dirty changes in another form.

## Storage and limits

Everything continues in `<existing data directory>\workspace.sqlite` and the existing
`attachments` folder. Schema 8 adds `customer_preferences`, `customer_policy_history`,
`support_migrations` and `support_migration_issues`; existing tables remain intact.
Full backups include these records. Staff JSON exports remain additive and retain
quotation/customer/project data, but omit these separate ledgers and attachments;
they are not instance backups.

Version 8's explicit contract approval, price snapshots, comparison, internal
costing, exports, authentication and shared reference constraints remain. There
is no simplified updater, actual payment ledger, FX conversion, daily proration,
automatic destructive merge or Windows/IIS deployment in this release. General
quotation/customer/project edits retain last-save-wins behavior; commercial tables,
outcomes, archive/deletion previews and other existing version checks remain guarded.
