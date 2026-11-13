# Version 18 verification

Based on Version 17 commit `cfc13a3d9542ba8e0423ae1e195f19ba293ba301`, preserving
the completed login redesign.

- Full Python suite: 267 tests passed.
- New pricing suite: four tests passed (catalog idempotency/custom prices,
  minimum quantities/legacy amounts, DR links/overrides/duplication, cached Excel
  values and linked-price/rate formulas).
- Real Waitress/system Chromium quotation checks passed: new catalog defaults,
  DR mode switching, calculation popovers, collapsed structure and option toggles,
  group removal, selected deletion, recalculation, save/reopen, PDF generation and
  mobile rendering; no JavaScript errors.
- Current Version 17 acceptance passed: approvals, captured milestone emails,
  generated PDFs, monthly reports, mobile layouts and permanent cleanup.
- Python compilation, JavaScript syntax and Git whitespace checks passed.

Windows/IIS deployment, real customer data and independent Microsoft Excel or
LibreOffice recalculation were not available. The legacy browser_smoke.py has a
pre-existing ambiguous Production selector; it does not complete. Current acceptance
coverage is recorded above. No real emails or production deployment were performed.
