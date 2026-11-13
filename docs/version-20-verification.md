# Version 20 verification

The new focused tests exercise real authenticated HTTP flows and synthetic data:
legacy five-item catalog reuse/custom prices, setup assignment saving, two customer
quotations, default changes vs immutable saved snapshots, no prices in the setup JSON,
VM-selection requirements, SOC/NOC minima, EDR placement, optional Monitoring,
monthly/one-time/support totals, renamed Main/DR roles, explicit DR links and duplication,
compact catalog rendering, successful-save notification, schema-17 migration and
full-instance backup/restore of the setup and bindings.

The real Waitress/Chromium Version 20 acceptance test edits and saves a catalog item,
assigns it through the setup editor, creates and saves quotations for two customers,
uses their separate customer VM prices (100 vs 240 synthetic monthly), verifies DR
replication fees (50 vs 120), corrects minima, verifies EDR only under Cybersecurity,
checks the saved-success notification, then changes a catalog default and confirms
only a future quotation uses it. No JavaScript errors were observed.

The existing approval/report/PDF Chromium acceptance test passed. Windows/IIS,
real company data and independent Microsoft Excel/LibreOffice recalculation were
not available. No live emails or production service changes were performed. Login
assets and the quotation sheet stylesheet remain unchanged.

Final validation: **278 unit tests passed**. All six focused Version 20 tests passed,
as did the real two-customer catalog/setup/VM browser flow and existing
approval/report/PDF browser acceptance. The installation command was executed twice:
schema 17, 19 standard catalog bindings and seven top-level categories remained
without duplicate initialization. Python compilation, JavaScript syntax and Git
whitespace checks passed. The user explicitly authorized publishing Version 20.
