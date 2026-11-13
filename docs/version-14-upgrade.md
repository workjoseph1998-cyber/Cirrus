# Cirrus Workplace Version 14 — upgrade and operating guide

Based on the complete Version 13 application (`0f8b29b`). Branch:
`feature/cirrus-workplace-v14`. Product **14**, SQLite schema **13**.

Download while signed into the private repository:
https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/feature/cirrus-workplace-v14.zip

This release implements account deletion and the requested quotation heading,
currency, support-selection and total-row changes only. Supplier Quotations and
the withdrawn suggestions are not included.

## Safe Windows / IIS / Waitress upgrade

1. Use the current administrator **Download full backup** action. Keep this
   pre-upgrade backup and record the actual external data path, Windows service
   identity, source path, environment variables and IIS configuration. Separately
   back up external customer PDFs, the persistent deployment file and service secrets.
2. Stop the existing Python/Waitress process or service. Extract the ZIP into a
   **new short folder**, for example `C:\CirrusV14`. Do not overlay the live data
   directory or copy an older `.venv`. Run `setup.bat`; requirements are unchanged.
3. Keep the same external `CIRRUS_DATA_DIR` or legacy `JOSEPH_DATA_DIR`, service
   account, bind, port, allowed hosts, HTTPS, proxy and timezone. Keep IIS host
   preservation and its existing Waitress reverse-proxy destination. **Do not run
   `init-admin` during an upgrade.** Point the existing service/launcher at v14.
4. `start.bat` and direct startup continue reading the existing external
   `%ProgramData%\CirrusWorkplace\deployment.json`, or the file specified by
   `CIRRUS_DEPLOYMENT_FILE`. Administrator environment overrides still take
   precedence. Do not replace this file with the bundled example. See the
   [v13 persistent-settings guide](version-13-upgrade.md#persistent-allowed-hosts-and-deployment-settings).
5. Start Workplace. The transactional, additive migration creates
   `account_deletions` and advances schema 12 → 13. It does **not** rewrite quotation
   records, support percentages/targets/totals, accounts, SMTP settings, history or
   attachments. Older documents receive default fee headings during validation;
   the defaults do not invalidate unchanged approvals.
6. Sign in with an existing account, check old quotations and accounts, verify the
   changes below and download a new full backup. Complete the Windows checks in
   [verification](version-14-verification.md) before normal team use.

Nothing is automatically deployed to the live VM. For rollback, stop v14 and use the
matching v13 code with a **restored pre-upgrade backup in a new external directory**,
then restore the previous service configuration. Do not run v13 against schema 13.
Reconcile any business changes made after the pre-upgrade backup separately.

## Delete accounts

Open **Administration → Accounts → Delete account** alongside Update access.
The confirmation names the exact account and requires its confirmation checkbox.
GET/opening the page never deletes anything. The POST action validates administrator
permissions, CSRF, target identity, confirmation, current-account and last-active-
administrator restrictions inside a SQLite write transaction. Concurrent account
deletion/access changes cannot leave the workspace without an active administrator.

Deletion removes the account from account management and future staff/email
selection, replaces its password with an unusable random credential, disables login
and revokes existing sessions. It also disables its notification-email preference
and cancels queued/failed deliveries. Other accounts' SMTP settings remain unchanged.

To preserve quotations, projects, sharing, comments, decisions and author names,
deletion retains the account's **stable ID and original username** as a historical
identity. It is not a cascade-delete of the users table. The retained username
cannot be registered again, and the deleted account cannot be re-enabled or reset
through the portal. This differs from Disable, which remains reversible.

Record ownership and sharing stay intact; deletion does not silently reassign or
publish records. Administrators retain their existing access to business records;
personal/private record rules remain. The record-access form can keep a deleted
owner when only changing sharing. Transfer ownership explicitly where appropriate.
Prior approvals/comments retain the deleted person's name. A deleted pending
approver is inactive: replace that selection and resubmit explicitly. No historical
approval is fabricated or erased. Current drafts/default approver selections are
not silently rewritten.

Full backups include retained identities and deletion audit entries (who/when).
Account deletion does not erase old backups or business history.

## Editable headings and monetary display

In the quotation editor, open **Formatting, columns & summary**:

- **Customer table columns → unit_price label** edits Unit Price.
- **Fee column headings** edits **Monthly Fee** and **One-Time Fee** separately.

Those names are the defaults. The app no longer appends `(USD)` to these headings;
old trailing `(USD)` suffixes are suppressed in customer output. Custom headings
are saved in the quotation and retained on duplicate/revision. An existing custom
amount-column label remains an explicit override. A section with monthly rows uses
the monthly heading; a one-time section uses the one-time heading. A mixed table
uses both labels in its existing shared fee column. The cost-summary column
headings use the saved monthly/one-time names too.

Customer previews, current PDFs, print and Excel share the heading policy. CSV
uses saved headings as well. Text is escaped in HTML and written as literal text
in Excel/CSV, so headings are not spreadsheet formulas.

Monetary unit prices, row fees and summary amounts display dollars with two decimal
places, for example **$296.00** and **$0.00**. Unpriced values remain Unpriced, and
included/excluded states retain their labels. An internal support percentage is
not presented as a dollar unit price; the customer sees its resulting dollar fee.
Explicit customer-visible percentage drivers remain percentages.

Excel prices/fees remain numeric cells or formulas using a dollar number format,
not strings containing `$`. Saved values and calculation precision are unchanged;
inline number inputs retain extra saved precision when present. This is display
formatting, not currency conversion; documents retain their saved currency label.
CSV is plain data: values remain numeric text and it cannot carry color/number formats.

The **entire Total Monthly Fee row** has a `#C00000` red background and bold white
label/amount text in customer HTML, print, current PDFs and Excel. Explicit
promotional monthly-total rows use the same style. The earlier summary cleanup and
explicit occasional discounts are preserved.

Already retained approved/sent PDF evidence is immutable and stays byte-for-byte
unchanged. Current print/export output uses the new styling. Existing approved
external filenames retain their collision/protection rules; no old PDF is moved,
deleted or overwritten by the upgrade.

## Configure 8×5 Request Fulfillment

Keep the standalone **8×5 Request Fulfillment** section. Expand its service row in
**Categories & groups**, or use that row's **Options** action in the quotation:

1. For a percentage-based support row, edit **Support / fee percentage %**.
2. Under **Select sections / services in the calculation base**, expand the desired
   category and check its whole section or individual services. Select one or many.
3. The editor shows **Selected base**, percentage and **Fee**, plus a collapsible
   list of the resolved services and their amounts. Changing selections, percentage,
   quantities or prices refreshes this calculation automatically.
4. Save normally. Reopen, duplicate and revision operations retain the percentage,
   stable section/row targets and existing catalog-service selections.

Example: Production $1,000 + Connectivity $100 at 5% yields **$55.00** support.
Monitoring and other unselected services are excluded. Selecting Production and
one of its rows together still counts that row once. Self-including/circular bases
are blocked on the server, not just by the interface.

The existing same-billing-period rule is retained: a monthly support fee uses
monthly charges. For a category containing both monthly and one-time charges,
choose its matching services individually. The checkboxes explain unavailable
whole-section selections. Excluded/included and quantity-zero rows retain their
existing zero-charge behavior; missing prices remain unresolved rather than zero.
The fee's own activation state and line discount still apply.

Existing catalog/VM automatic-inclusion rules remain available in the separate
**Automatically include matching catalog / VM services** expander. They match only
rows in this quotation, do not insert/price services, and count overlaps once.

**Historical support configuration and totals are preserved.** No percentage,
target list, support-key selection or fixed override is changed on upgrade/open.
A historical fixed-fee row remains fixed unless you explicitly change its method.
Multiple existing support rows remain separate. Adjust the appropriate row(s)
deliberately; this release does not consolidate or introduce another fee.
The percentage and base details stay internal and are excluded from customer HTML,
PDF and Excel. Customer Excel keeps the resolved support fee as its existing
numeric snapshot; change its calculation in the portal and re-export.

## Main modified files

- `accounts.py`, account/access templates, `store.py`, notification settings:
  deletion confirmation, server safeguards, retained identities and additive migration.
- `quotation_presentation.py`, `quotation.py`, `quote_routes.py`, `quote_excel.py`,
  customer/discount templates and quotation CSS: saved headings, numeric currency
  display and red/white total styling.
- `support.py`, quotation editor JavaScript and portal CSS: checkboxes, shared exact
  target resolution and editor-only calculation feedback.
- `approvals.py`: default-heading fingerprint compatibility; custom changes still
  follow normal version-bound reapproval.
- Backup/handover/application identifiers, regression tests, browser helper and docs.

No runtime dependencies, data locations, server bindings or SMTP modes were changed.
