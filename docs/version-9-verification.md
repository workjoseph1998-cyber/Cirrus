# Cirrus Workplace — Version 9 verification

Built on Version 8 commit `b2fd8b8` and schema 7. Product Version 9 uses schema 8.
All validation used synthetic data in temporary databases. No production database,
Windows VM, IIS service or uploaded customer workbook was changed.

## Modified components

| Files | Changes |
| --- | --- |
| `statistics.py` | Separate latest-revision contract/monthly metrics, zero/unknown counts, invalid-latest handling without older-price fallback, native-currency separation |
| `templates/{quote_statistics,monthly_statistics,list}.html`, `static/{app.css,statistics_filters.js}` | Compact KPIs/filters/rows, context-sensitive date fields, per-row tool menus, collapsed charts below the quotation list |
| `archives.py`, `templates/archive_confirm.html` | Archived-only permanent family deletion; affected-title/revision preview; typed confirmation; all-revision permissions; accepted/contract guards; data/cost/file stale checks; issued references retained |
| `support.py`, `quotation.py` | Checked, idempotent standalone support conversion; eligibility-preserving move; new-quote customer defaults; service-key bases; union/cycle validation; private public projection |
| `customers.py` | Combined customer workspace/directory, preserved legacy agreement views, explicit link review, date-filtered charges/quotes/Won metrics, compact override API, audited policies and expiry indicators |
| `templates/{customers,customer_workspace,customer_pricing,customer_date_fields,customer_link,support_migration_review}.html` | Customer tabs, pricing/defaults, indicators, sorting/searching, reviewed links and migration exceptions |
| `static/{customer_pricing,unsaved}.js` | Compact add-service pricing, dirty-state protection, cross-form discard confirmation, copied-consumption protection |
| `store.py`, `model.py`, `backup.py` | Schema 8, import compatibility/conversion, preserved historical customer identities, migration audit cleanup, full-backup restore compatibility |
| `__init__.py`, `quote_routes.py`, `company.py`, `relationships.py` | Customer navigation/routes, atomic new-customer agreement creation, template catalog identities, agreed-price prefilling, existing permissions and data guards |
| `templates/{base,dashboard,login,project_commercial,consumption,agreed_prices}.html`, `run.py` | Version 9 branding/logo, customer links, date-aware copy-month action, unsaved forms; legacy templates retain compatible routes |
| `tests/test_v9.py`, `tests/v9_browser.py` | New metrics, migration, customer, deletion, permissions, concurrency/stale-state and UI coverage |
| Prior tests/browser scripts | Updated schema/layout expectations while retaining earlier workflow checks |
| `README.md`, `docs/version-9-upgrade.md` | Current download, upgrade, rollback, operating rules, storage and limitations |

## Test results

**112 automated unit/integration tests passed**: all 98 earlier cases with updated
schema/layout expectations, plus 14 Version 9 cases. Coverage includes:

- Latest-family full-contract versus monthly values; zero versus missing prices;
  invalid newest revision does not reuse an older price; date/permission/currency
  filtering and frozen accepted amounts.
- Standalone support migration with unchanged row/regular/discount/contract/tax
  amounts; hidden/excluded parents; idempotence; frozen accepted values and private
  costing bytes retained; migration audit/full-backup restore; automatic service
  keys deduplicated with category/row eligibility.
- Archived deletion, every-revision authorization, accepted Won protection,
  contract links, typed confirmation, stale document/internal-cost checks,
  protected sent references and release of verified unsent drafts only.
- Explicit legacy-customer linking, preserved quotation identities and revision
  creation after linking, no family double count across customer workspaces.
- Compact blank/zero price behavior, customer-policy snapshot isolation,
  customer-date charge totals, direct quotation creation, new-customer agreement
  creation, denied unauthorized policy changes and earlier access controls.
- Existing real SQLite duplicate-reference reservation races and scoped price
  overlap transaction tests remain part of the suite.

```bash
python -m unittest discover -s tests -q
```

Eight Playwright workflows passed using actual login and Waitress:

| Workflow | Result |
| --- | --- |
| `v9_browser.py` | Quotations visible before collapsed charts; compact menus/rows; reference search and editable manual title prefixes; separate financial metrics; archived deletion and Won block; current customer prices; one standalone support fee with editable internal percentage; dirty-form/discard protection; customer date filters, monthly copying, expiry privacy, search/sort and mobile layout |
| `v8_browser.py` | Customer/project price precedence and Linux/Windows prices; editable snapshots; optional discount; customer preview/PDF metadata; proposed/upload/explicitly approved contracts; consumption snapshots and archiving |
| `commercial_browser.py` | Priced drafts, private costing, target margins, explicit price application, revision comparison, frozen Won values, quote-only permissions and never-sent reference recycling |
| `quotation_browser.py` | Direct/sustained typing, category/row copy/reorder/move/delete, standalone support with new environments, fullscreen/mobile panes, multi-page PDF/long content, privacy, export totals and save/reopen |
| `hosting_browser.py` | All VM configurations, separate OS prices, remembered OS, retained manual comments, exception prices, Type/Comments catalog round trip and unchanged saved prices after library changes |
| `team_browser.py` | Accounts, backed-up catalog replacement, company templates, sharing/personal isolation and reviewed atomic multi-sheet import |
| `v5_browser.py` | Revision/date/currency statistics, expandable compact charts, reference import/reservation/cross-user conflicts, KPIs and responsive layout |
| `browser_smoke.py` | Project/catalog/quote creation, preserved legacy notes, safe customer print, additive JSON round trip, restart persistence and mobile dashboard |

Independent LibreOffice checks passed for **11 spreadsheet scenarios**: seven
existing baseline/unpriced/zero/included-tax/edited-quantity/long-text/many-row cases,
plus four cache-cleared percentage/fixed discount and missing-price cases. Version
8's other discount cases remain covered by canonical engine and export tests; the
entire 22-case optional matrix was not repeated for this release.

```bash
python tests/excel_recalculation.py
V8_EXCEL_CASES=percent-10-both-temporary,fixed-50-both-temporary,unpriced-fixed,unpriced-percent-zero python tests/v8_excel_recalculation.py
```

Python compilation, JavaScript syntax checks, `pip check` and whitespace validation
passed. Runtime requirements and IIS/network configuration files were not changed.

## Limits and operational review

See [Version 9 upgrade/rollback and operating rules](version-9-upgrade.md). No Windows
or production load benchmark is claimed. Customer figures are calculated charges,
not actual payments; no FX/proration/payment ledger was added. Duplicate names are
reviewed explicitly, without a destructive automatic customer merge. Existing
agreement-specific overrides/policies retain precedence. Customer Excel keeps
support as the fixed final service fee; edit dependencies in the portal and export
again. Generic record editing retains its existing last-save-wins behavior. The
simplified updater is deferred.
