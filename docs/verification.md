# Verification: Cirrus Workplace team upgrade

Latest behavior: [commercial tools update](commercial-tools-upgrade.md) supersedes earlier draft-value, date-basis, reference-deletion and outcome rules; schema is now 6.

V5 overrides: see [V5 upgrade and operating rules](v5-upgrade.md) for schema 5, references, statistics, retired navigation and quotation output cleanup.

Validated in the Codex Linux environment with Python 3.12, Waitress, Chromium /
Playwright, openpyxl and LibreOffice. Tests use temporary databases and synthetic
credentials/prices; the uploaded customer workbook is not a fixture or Git asset.

## Automated checks

- **52 unit/integration tests** pass: existing persistence, calculation, migration,
  attachment, backup/restore, revisions and JSON compatibility; real login/logout,
  disabled users, throttling, password-reset revocation, expiry, CSRF, roles,
  guessed record/export/attachment URLs, search/dashboard filtering, Personal
  isolation, initial ownership, project inheritance and quotation-only grants.
- Company tests verify required Production/DR rows, separate VPN units, independent
  template copies and explicit backed-up catalog replacement without changing old
  quotations; repeat replacement creates neither duplicate services nor backups.
- Import tests cover merged backup labels, multi-sheet selection/mapping, custom
  rows, unsupported formulas/missing caches, inconsistent summaries, source limits
  (including oversized merged ranges before workbook allocation), private staging,
  preview/cancel/confirm/replay, explicit redacted zeros, revisions and atomic failure.
- Customer output tests check support descriptions/final charges while withholding
  percentage/basis/internal notes in preview/print HTML, CSV and Excel cells/settings.
  Protected support cells are literal computed fees. Stable discount-summary keys
  stay hidden. Unverified VM prices are not presented as actual charges; generated
  demo notices are removed while manually entered OS text is preserved.
- JavaScript syntax, dependency consistency (`pip check`) and `git diff --check` pass.

## Browser and independent spreadsheet workflows

All browser workflows use real login with the authorization bypass disabled:

- `tests/browser_smoke.py`: project, linked note/question, catalog, live quote,
  customer print, JSON preview/idempotent reimport, restart persistence, mobile.
- `tests/hosting_browser.py`: all 33 profiles, separate Linux/Windows prices,
  family picker, technical CPU/RAM comments, manual OS text preservation, exception
  prices, catalog Type/Comments round-trip, compact rows and saved snapshots.
- `tests/quotation_browser.py`: full-window split, uninterrupted direct typing,
  left/right synchronization, custom rows/categories/groups, copy/reorder/move/
  delete controls, complete DR removal, mobile tabs/divider, long multipage A4 PDF
  end markers, matching saved preview/PDF/Excel totals and no internal-cost leakage.
- `tests/team_browser.py`: administrator-created Editor/Viewer accounts, backed-up
  one-time catalog replacement, company template, private projects, named sharing,
  Personal notes hidden from administrators, multi-sheet Excel staging, unsupported
  formula correction in the visual editor and permission-protected confirmation.
- `tests/excel_recalculation.py`: **7** independent LibreOffice cases: nonzero,
  blank/zero prices, included tax, quantity changes, long text and over 100 rows.
  Expected protected support stays frozen in the customer workbook; public amounts
  recalculate. LibreOffice is a developer check, not an app dependency.

Before/after quotation screenshots were inspected outside Git using the same VM
fixture. The split proportions, colors, typography, column widths, compact rows
and category separation remain; sharing is an additional toolbar control. The old
OS/demo-generation and visible support-driver behaviors are intentionally changed.

The provided Cirrus reference workbook was parsed locally: 35 service rows across
13 categories/groups, with seven review issues including hardcoded SOC pricing,
non-numeric fee quantities, dated terms, omitted VPN subtotal rows and the annual
summary formula. Customer identities/prices were not printed, committed, added to
the global catalog or saved into a workspace during this verification.

## Practical limits

Windows batch execution, Server 2022/IIS/ARR, actual DNS, certificates/client trust,
Windows Firewall, Microsoft Excel and physical Windows printing cannot be tested
here. Configuration examples and setup/upgrade/rollback instructions are provided;
the user's VM and LAN have not been updated or verified.

Cirrus-layout import is conservative, not arbitrary Excel compatibility. Unsupported
formulas require review; formulas/macros/external code are never executed. Customer
Excel protected-support fees must be repriced in the app and re-exported after
quantity changes. Historical OS wording lacks provenance and is retained for manual
review. There is no multi-editor conflict UI, SSO/MFA or full audit trail. Full
backups include all users' data and require trusted server administration.
