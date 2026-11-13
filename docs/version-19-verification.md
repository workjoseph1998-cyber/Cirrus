# Version 19 verification

## Approved v19.0.1 layout update

- All 272 unit tests passed.
- Dedicated real Waitress/Chromium layout acceptance passed, including unsaved edits,
  settings/options/approval dialogs, saving from margin controls and responsive Controls
  dialogs, save/reopen, PDF and Excel, scrolling, expanded More-menu bounds, mobile
  controls and unchanged non-editor navigation.
- The existing approval/report/PDF browser acceptance passed.
- Before/after at 1908 × 960: sheet top 278.375 → 79 px; quotation viewport
  679 → 878 px. Sheet width stayed 1360 px, all nine measured column widths matched,
  and measured row heights and fonts matched exactly. The quotation stylesheet is unchanged.
- JavaScript syntax, Python compilation and whitespace checks passed.
- The user tested the patch and explicitly approved publication to Version 19.

## Original Version 19 verification

Complete release based on Version 18 commit
`358b39f1285983add4c0ae76db69d016c363c1cf`, including all subsequent quotation
refinements. Login files are unchanged; product branding is updated to Version 19.

- The 271-test Python regression suite passed after the refinements.
- All five focused refinement tests passed, including the subsequently added
  foreign-currency/custom-code catalog case.
- Real Waitress/Chromium refinement acceptance passed: toolbar grouping, centered
  compact width, catalog quantity/price copying, VM comments, exact red replication
  label, Running and Replication calculations, applicable subtotal display,
  save/reopen one-time billing, generated PDF and 390 px mobile controls.
- Current Version 17 browser acceptance passed: approvals, captured emails, exact
  PDFs, reports, responsive layouts and permanent cleanup.
- Catalog initialization CLI ran twice with exactly 19 entries afterward.
- Python compilation, JavaScript syntax and Git whitespace checks passed.

Windows/IIS deployment, real customer data and independent Microsoft
Excel/LibreOffice recalculation were not available. The older browser_smoke.py has
its pre-existing ambiguous Production selector. No live emails, production service
changes or customer data changes were performed by the synthetic checks.
