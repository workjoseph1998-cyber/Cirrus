# Commercial tools: implementation and validation

All tests use temporary databases and synthetic accounts/amounts. No deployed VM
or customer database was modified. Uploaded request text is not a repository asset.

## Modified components

- `commercial.py`: canonical gross quotation amount, reconciled full-contract
  pre-sales-tax line values and safe total/percentage differences.
- `comparison.py`, `templates/comparison.html`: stable-ID/unique semantic row
  matching, added/removed/modified values, scope/exclusions/terms and change filtering.
- `costing.py`, `static/costing.js`, costing templates: private per-revision
  worksheets, live calculations, target suggestions, optimistic save checks and
  explicit stale-checked price-application preview/confirmation.
- `outcomes.py`, outcome template: six-state family workflow, required decision
  details, accepted revision/value/document snapshots, actor history and permissions.
- `statistics.py`, quotation statistics/list/dashboard templates: priced drafts,
  issue-date activity, outcome-date decisions, separate native currencies, frozen
  won values, pending counts/values, win rate and reason breakdown.
- `references.py`, registry template, quotation delete route: tracked never-sent
  draft recycling, sent/historical protection, unused reservation release and
  administrator-attested older deleted-draft review with audit events.
- `store.py`, `model.py`, `backup.py`, quote/import routes: schema-6 migration,
  save/import/revision hooks, accepted revision identity/deletion protection,
  private worksheet copying, imported-status review and full backup compatibility.
- Editor links, scripts and styles: separate Compare revisions / Internal costing /
  Outcome buttons, terminal workflow controls and a wide responsive staff worksheet.
- README/operator docs and tests: upgrade, accounting/date/permission semantics,
  reference lifecycle and compatibility evidence.

## Results

**80 unit/integration tests**, including 17 commercial tests, pass:

- Priced drafts change quoted amounts; issue-date and outcome-date filters differ
  deliberately; native currencies remain separate, zero/unpriced cases stay explicit.
- Revisions do not double count; accepted value/currency stays frozen when new
  revisions change the latest amount. Schema-5 migration retains an older accepted
  revision beneath a later Draft and does not invent legacy outcome dates/users.
- Required Won/Lost reason/date, accepted family/read permission, actual actor,
  stale outcome updates, accepted identity/delete rules and snapshot confidentiality.
- Quantity/price/line/description and metadata comparison, reorder-safe identity,
  imported unique semantic matches and undefined zero-base percentage handling.
- Full-contract purchase costs, one-time additions counted once, net selling values,
  margin versus markup, target suggestions, zero/unknown inputs and invalid margins.
  Discount and included-tax penny allocations reconcile without charging excluded rows.
- Costing saves do not reprice quotations; application requires an explicit current
  preview/confirmation. Purchase/supplier/private data never enters customer HTML,
  CSV, XLSX XML or staff JSON exports. Viewer/read-only-Editor endpoints are denied.
- Costing copies independently per revision, survives row reordering and preserves
  removed rows as private archived entries. Costing/outcome/version data survives
  full backup/restore; raw existing record JSON survives schema-5 migration.
- Never-sent drafts, including reservation-backed drafts, release on final Draft
  deletion. Internal review followed by Draft remains recyclable. Sent then Draft
  stays protected. Older deleted numbers require an administrator attestation;
  known sent/imported/historical references remain protected. Reservation owners
  can explicitly release unused leases.
- Imported JSON terminal labels without separate outcome history become Under review
  workflow rather than an unaudited new win. Record data remains preserved.

Six real-login browser workflows pass:

1. `commercial_browser.py`: visible priced-draft totals, live private costing,
   explicit suggestion/application preview, no customer leakage, revision comparison
   and Only show changes, actual Won reason/user/accepted revision, newer-revision
   statistics without changing the frozen won value, permissions, reservation-backed
   draft deletion/reuse and mobile worksheet sizing.
2. `quotation_browser.py`: uninterrupted direct editing and row/category operations,
   split/mobile layout, long multipage A4 PDF and matching retained customer totals.
3. `hosting_browser.py`: VM costs/picker/specifications, catalog Type/Comments and
   exception-price snapshots.
4. `browser_smoke.py`: project/catalog/quote creation, archived data/JSON compatibility,
   app-restart persistence and mobile dashboard.
5. `team_browser.py`: administrator-created roles, backed-up catalog replacement,
   templates/sharing/Personal isolation and staged multi-sheet quotation import.
6. `v5_browser.py`: date/search filters, compact charts, reference history/imports,
   duplicate warnings and page KPIs, updated for issue dates and priced drafts.

Seven independent LibreOffice recalculation scenarios pass: nonzero, unpriced,
zero, included tax, public quantity edits, long text and over 100 eligible rows.
Customer support privacy and the V5 unwanted-summary/discount/VAT cleanup persist.
Python compilation, JavaScript syntax, dependency consistency and diff checks pass.
Desktop comparison/statistics/costing screenshots were inspected outside Git.

## Verification boundaries

Windows batch execution and actual IIS/Waitress/DNS/certificate/firewall deployment
were not performed on the user's VM. No IIS changes are needed for the supplied
routes/static assets. This is not a production Windows concurrency/load benchmark.
General quote editing remains last-save-wins; costing/outcome actions add stale
checks. Review the [upgrade guide](commercial-tools-upgrade.md) for historical
reference verification, cost/date bases and import/backup limitations.
