# V5 implementation and verification

Latest behavior: [commercial tools update](commercial-tools-upgrade.md) supersedes earlier draft-value, date-basis, reference-deletion and outcome rules; schema is now 6.

All checks use temporary data and explicitly synthetic accounts/amounts. No live
VM/customer database is overwritten and no historical uploaded workbook is committed.

## Main files changed

- `workspace_app/references.py`: schema-5 ledger migration/backfill, normalized
  identity, permanent issued history, leased reservations, owner renewal,
  atomic assignment, accessible revision links, legacy-conflict review and
  historical CSV/XLSX preview/confirmation.
- `workspace_app/statistics.py`: Decimal aggregates, latest valid revision per
  reference, status/currency/missing-price policy, business timezone, creation-date
  filters/month buckets and project/catalog KPIs.
- `workspace_app/store.py`, `model.py`, `security.py`, `backup.py`: schema version,
  reference hooks for every quotation save and JSON import, initial ownership,
  cancellation status, constraints and schema-5 backup/restore. Category-dependent
  validation remains; unrelated saves do not revalidate every legacy quotation.
- `workspace_app/__init__.py`, `accounts.py`, `hosting_routes.py`, `quote_routes.py`,
  `excel_routes.py`: dashboards/list data, retired interfaces, role-preserving
  routes, suggestion/edit/duplicate/revision flows and import integration.
- `workspace_app/quotation.py`, `quote_excel.py`,
  `templates/quotation_document.html`: cleanup policy for old/blank/company cases,
  unchanged pricing math, preserved Excel helper dependencies and support privacy.
- `workspace_app/templates/`: reusable KPI/statistics panels, compact SVG charts,
  reference/register import interfaces, revised navigation/dashboard/project views
  and administration/hosting/catalog summaries.
- `workspace_app/static/app.css`, `quotation.css`, `quotation_editor.js`: navy
  theme, responsive cards/charts, direct-edit reference checks and reservation UI.
- `requirements.txt`, config/deployment examples, README and V5 operator guide:
  Windows timezone data, shared path/setup instructions and compatibility limits.
- Tests: new `test_v5.py` and `v5_browser.py`, plus existing regression fixtures and
  assertions updated for deliberately removed UI/summary lines.

## Automated results

**63 unit/integration tests pass**, including 11 new V5 tests:

- Independent known USD total/average, zero/unpriced/non-USD/Draft/Rejected/Cancelled
  rules; latest revision deduplication and invalid-latest fallback.
- First-creation/revision dates, Beirut UTC boundary, leap-year date handling,
  current/last/custom periods, search and month-chart totals.
- Simultaneous reservations from two separate SQLite connections/users: one wins
  and one is blocked; simultaneous new quotation assignment likewise saves once.
  Direct duplicate reference/revision insertion fails at the SQLite constraint.
- Reservation expiry, renewal, other-user ownership, custom case-insensitive
  identity, historical import collision atomicity, duplicate import, suggested
  next/current-year CIR and permanent protection after quotation deletion.
- New revision re-entry opens the already-created newer version rather than
  creating an accidental extra revision. JSON and Excel import compatibility,
  original ownership/sharing and legacy data checks remain in the prior suite.
- Role/visibility enforcement for aggregate pages and registry writes; retired
  navigation/creation views; old customer output cleanup and unchanged stored math.
- Actual schema-4 backfill preserves formerly allowed case-colliding records,
  flags them and permits unrelated project work. Full backup/restore retains ledger
  and conflict metadata.

Five real-login browser workflows pass:

1. `v5_browser.py`: live saved-data statistics, filters/search, side-by-side compact
   charts, historical CSV preview/import, reference suggestion, custom proposal
   reserve/renew/issue, colleague duplicate warnings and private-value isolation,
   quotation-editor reservation/assignment, customer cleanup, saved-total refresh,
   mobile layout, all requested page KPIs and no JavaScript errors.
2. `quotation_browser.py`: uninterrupted typing, row/category/group controls,
   full-window split, resizer/mobile tabs, long multipage A4 PDF end markers,
   saved monthly/one-time totals and no private-cost/note leakage.
3. `hosting_browser.py`: 33 VM profiles, Linux/Windows costs, family selection,
   specifications, manual OS text, overrides, catalog Type/Comments snapshots.
4. `browser_smoke.py`: project/catalog/quotation creation, archived-note retention,
   JSON round trip, process restart persistence and mobile dashboard.
5. `team_browser.py`: administrator-created roles, backed-up catalog replacement,
   explicit template save, named sharing, archived Personal isolation and staged
   multi-sheet quotation import with visual formula resolution.

**Seven independent LibreOffice recalculation cases pass**: synthetic nonzero,
blank/zero prices, included tax, changed public quantity, long text and over 100
eligible rows. Hidden unlabeled helper rows retain all underlying cached/formula
results, while removed customer summary labels/disclaimers remain absent. Protected
support remains a fixed customer value, as documented in the previous release.

Python compilation, JavaScript syntax, `pip check` and `git diff --check` pass.
Desktop screenshots were inspected for the new statistics and retained split
quotation layout; mobile browser checks verify no horizontal page overflow and
stacked charts. Screenshots contain synthetic data and remain outside Git.

## Limits of this verification

Windows Server 2022 batch execution, IIS/ARR, actual DNS/certificate/client trust,
Windows Firewall and Microsoft Excel/physical printing were not executed here.
The VM has not been upgraded. Tests exercise two-user reference races, not a
production Windows load benchmark. General same-record editing remains last-save-
wins; only reference identity/assignment is protected against the tested races.
Read [V5 operating rules](v5-upgrade.md) before deployment.
