# Cirrus Workplace — Version 8 verification

Product Version 8 / SQLite schema 7. Validation used temporary synthetic databases
on the Codex cloud environment. No production database, signed customer document,
Windows service or IIS deployment was accessed or changed.

## Modified components

| Files | Result |
| --- | --- |
| `workspace_app/relationships.py` | Schema-7 migration definitions; customer overview; agreed-price precedence/history; immutable proposed/approved contracts; permission-controlled documents; monthly consumption snapshots/history |
| `workspace_app/archives.py` | Permission-checked, atomic family archive/restore, matching-filter selection, stale confirmation detection |
| `workspace_app/summary_discounts.py` | Percentage and capped fixed-budget discounts, post-line-discount basis, recurring/one-time allocation and cent tiers |
| `store.py`, `model.py`, `security.py`, `accounts.py`, `__init__.py` | Additive migration, customer/project links, validation, import order, retained restricted links, ownerless sharing compatibility, pagination and permission checks |
| `quotation.py`, `commercial.py`, `costing.py`, `comparison.py`, `company.py` | Compatible document extensions, canonical totals, net costing allocations, policy comparison, explicit opt-in template defaults |
| `quote_routes.py`, `quote_excel.py` | Customer metadata and totals, public projection, formula exports and optional CSV discount summary |
| `backup.py` | Schema-7 backup restore compatibility; existing backup format/data path retained |
| `templates/{agreed_prices,price_fields,customer_overview,project_commercial,consumption,archive_confirm,discount_summary}.html` | New commercial interfaces |
| `templates/{base,dashboard,detail,edit,list,quotation_document,quotation_editor,quote_statistics,portability}.html` | Version 8 navigation/branding, links, restricted-customer retention, archive toolbar/filters, quotation layout and export notice |
| `static/{contracts,consumption,archives}.js` | Editable service rows, consumption previews, explicit archive selection |
| `static/quotation_editor.js`, `static/{app,quotation}.css` | Current scoped picker prices/source, context-race protection, manual overrides, remembered VM OS without altering manual notes, optional discounts and compact styling |
| `run.py`, `README.md`, `docs/version-8-upgrade.md` | Version 8 launch label and current installation/backup/rollback/operating instructions |
| Prior commercial-tools/V5 guides | Marked as historical and linked to the current guide |
| `tests/test_v8.py`, `tests/v8_browser.py`, `tests/v8_excel_recalculation.py` | New storage/permission/calculation/concurrency/browser/formula checks |
| Prior unit/browser tests | Update schema expectations and picker labels to current behavior; keep regression coverage |

## Automated results

- **98 unit/integration tests passed**, including all 80 previous tests and 18
  Version 8 checks. Covers real schema-6 migration without rewriting raw records;
  legacy customer-text preservation; standard/customer/project pricing, dates,
  currencies, zero prices, Linux/Windows separation, stale price updates and two
  concurrent overlapping price inserts (one wins, one rejects); contract approval,
  accepted snapshot copying, upload permissions and historical-file retention;
  fixed/actual consumption, previous-month quantities and historical rates;
  discount allocation/caps/cent tiers and costing reconciliation; full backup and
  restore of all new tables/files; archive/restoration, blocked partial access,
  family changes after confirmation, all-matching counts and pagination.
- Existing reference reservation/duplicate-assignment race tests still pass.
- Quote-only editors retain standard pickers and revision creation without access
  to project pricing. Editing an assigned project retains its restricted customer
  link. Viewer/read-only Editor restrictions remain effective.
- Python compilation, JavaScript syntax checks, dependency consistency (`pip check`)
  and `git diff --check` passed. No runtime requirement changes.

Command:

```bash
python -m unittest discover -s tests -q
```

## Browser results

Seven Playwright workflows passed using real authentication and Waitress:

1. `v8_browser.py`: customer/project price tables; source/price pickers; editable
   quotation snapshots; Linux/Windows prices; explicit discount; Date/Reference-only
   metadata in preview and generated PDF; contract proposed/upload/approve/history;
   monthly fixed charge/overage/previous month; renewals; bulk archive/restore and
   all-matching selection; mobile customer page; no JavaScript exceptions.
2. `commercial_browser.py`: priced-draft statistics, live costing, margin, explicit
   selling-price application, comparison, accepted values across revisions,
   permissions and never-sent reference recycling.
3. `quotation_browser.py`: direct cell editing, category/row copy/reorder/move,
   split/mobile editor, multi-page PDF, long content, no private output and saved
   preview/PDF/Excel total parity.
4. `hosting_browser.py`: all 33 VM configurations, independent OS prices, retained
   comments/licensing notes, remembered OS, exception prices, catalog round trip
   including Type/Comments, master price changes leave quotes unchanged.
5. `browser_smoke.py`: project/catalog/quotation creation, retained legacy records,
   safe customer print, JSON round trip, restart persistence and mobile dashboard.
6. `team_browser.py`: accounts, backed-up catalog replacement, populated templates,
   ownership/sharing/personal isolation and reviewed atomic multi-sheet import.
7. `v5_browser.py`: actual USD/revision statistics, date filters, compact charts,
   reference import/reservation and cross-user conflicts, KPIs and mobile layout.

Example developer command (Playwright/Chromium are verification tools, not app
runtime dependencies):

```bash
CHROMIUM_PATH=/usr/bin/chromium python tests/v8_browser.py
```

## Spreadsheet calculations

Seven existing LibreOffice recalculation cases passed: baseline, unpriced, zero,
included tax, an edited Excel quantity, long text and many rows.

The Version 8 matrix verified 22 additional cases: percentages and fixed budgets,
recurring/one-time/both, full/temporary periods, caps, disabled policy, included tax
and missing prices. The independent script invalidates formula caches before
LibreOffice conversion, then checks 16 calculation values against the canonical
Decimal engine, rather than relying on the server's exported cached values. Missing-price checks
include an unknown fixed-budget rounding helper and a zero-percent policy; both
were verified after correcting their Excel/Python blank-versus-zero handling.

```bash
python tests/excel_recalculation.py
python tests/v8_excel_recalculation.py
```

## Practical limits

See [the upgrade/operating guide](version-8-upgrade.md) for exact calculation and
permission rules, deployment preservation, backup/rollback, and known boundaries.
In particular: quoted values/consumption are not revenue/invoices; currencies are
not converted; monthly billing does not prorate partial months; copied quotation
summary promotions require explicit contract-rate review; JSON is not a full
instance backup; ordinary quote/project record edits retain last-save-wins. No
Windows/IIS deployment or production concurrency/load benchmark is claimed.
