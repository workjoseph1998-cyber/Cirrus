# Cirrus Workplace Version 18 — quotation refinements patch

Apply to Version 18 commit `358b39f1285983add4c0ae76db69d016c363c1cf` (tag
`v18.0.0`). This is a refinement patch, not a new major version or a production
server deployment. The completed login page is unchanged.

## Windows installation

1. Stop the existing Waitress process/service and ensure editing has stopped.
2. Back up the complete application release directory and the actual external data
   directory. Preserve external Customer Documents, quotation PDF and Reports folders
   separately, plus deployment JSON and the service's existing configuration.
3. Using the original application, create a full-instance backup with a fresh name:

   ```bat
   cd C:\Path\To\CirrusWorkplace
   set "CIRRUS_DATA_DIR=C:\YourActualDataDirectory"
   .venv\Scripts\python scripts\backup.py backup C:\Backups\before-v18-refinements.zip
   ```

   Replace all example paths. If JOSEPH_DATA_DIR is configured, it must agree with
   CIRRUS_DATA_DIR. Use the same data directory and Windows account as the service.
4. Extract the patch ZIP into the Version 18 application root, preserving paths and
   replacing only the supplied files. Dependencies are unchanged; do not replace the
   virtual environment, data directories, deployment settings or IIS configuration.
5. With Waitress still stopped, run:

   ```bat
   .venv\Scripts\python -m workspace_app.quotation_defaults
   ```

   The command adds missing generic standard services and fills missing defaults in
   one transaction. It is safe to repeat. It preserves customized quantities, prices,
   methods, comments and billing types. Equivalent custom catalog codes are reused;
   ambiguous equivalents cause an error instead of duplicate entries. Resolve the
   named ambiguity using the backed-up application and repeat the command. A SOC
   price of 1250 stored as a per-EPS price is rejected for review; standard SOC is
   5/EPS with minimum quantity 250. NOC remains 20/IP with minimum quantity 50.
   There is no separate SQL migration; schema remains 16.
6. Restart Waitress with the existing service configuration. Leave IIS/HTTPS, host
   validation, accounts and SMTP settings unchanged. Do not run `init-admin`.
7. Refresh the browser with Ctrl+F5, sign in, and verify the checks below.

## Catalog and pricing behavior

The standard catalog now covers Storage, Datacenter FW, Perimeter FW, Load Balancer,
WAF, VPN (user and node), Managed Backup, Backup Storage, SIEM Collector VM, SIEM,
SOC, EDR, NOC, Protected Internet, Replication Link / Protected Link, Connectivity
Setup and Working Hours Support, plus a generic unpriced Compute placeholder.
Customer-specific VM names are never promoted into the global catalog.

New catalog entries start at quantity 1. Existing edited quantities are preserved
and copied into new quotations and newly added rows, along with their price/rule,
billing type, pricing model and comments. Existing saved quotations are not repriced.
VM selection continues using the customer-specific size/pricing source.

Unknown Protected Internet, Protected Link, VPN-node, generic Compute and setup
prices are deliberately blank (shown as **Unpriced**). Enter authorized prices in
the editable catalog; do not assume that the screenshot's 500 setup example is a
global price. New Working Hours Support uses the existing application's 20% rule;
its catalog percentage is editable, and an explicit customer support-percentage
policy continues to take precedence. Existing customized fixed support rules remain
fixed. Select the intended monthly services in the quotation's support row settings;
one-time setup cannot be mixed into a monthly percentage calculation.

Initialization does not overwrite a saved company template. Standard rows carrying
the catalog identity use the current catalog when creating a new quotation. A
manually authored template row without a catalog identity retains its custom row
mapping; add it through the catalog picker to create an explicit catalog snapshot.

The displayed VM label is exactly **VM Replication**, in red, with no rate suffix.
The percentage remains in the calculation/popover. Running retains full pricing.
Only the dedicated generated `Operating system: ...` line alongside `VM Size:` and
`VM Specs:` is removed on display or VM selection. Manual notes and VM size names
are preserved, and OS information used by VM selection/pricing remains internal.

## Verification after restart

- Save/approval controls are on the left; settings and export actions are on the
  right. On narrow screens controls wrap and the Quotation tab opens the table.
  The table scrolls horizontally on phones to retain every pricing column.
- Quotation content is centered, compact, and capped at 1360 px; no zoom or page
  scaling is applied. The structure panel remains collapsible.
- Monthly-only environments have no zero one-time subtotal; one-time-only sections
  have no zero monthly subtotal. Both-zero shows one Total. Unpriced totals remain
  visible, and underlying calculations are unchanged.
- Check setup appears under One-Time Fee, contributes only to one-time totals, and
  remains correct after save/reopen, duplication and PDF/Excel export.
- Compare an existing quotation's prices and totals with the pre-patch backup.
- Check catalog changes affect a new quotation/newly added row but leave a saved
  quotation unchanged. Check SOC/NOC minimum validation and both DR modes.
- Confirm existing approvals and customer VM selection/prices remain available.

## Rollback

Stop Waitress. Restore the pre-patch application directory. Using the original
backup tool, restore the pre-patch backup into a NEW external directory:

```bat
.venv\Scripts\python scripts\backup.py restore C:\Backups\before-v18-refinements.zip --target C:\CirrusRestoredBeforeRefinements
```

Point the service's CIRRUS_DATA_DIR at that restored path, align/clear the legacy
JOSEPH_DATA_DIR, and restart the original Version 18 code. Restore separate external
folder backups as needed. Keep newer data separately: rollback discards changes
made after the backup. Use the matching pre-patch database/catalog, because the
older catalog validator does not recognize the new support-percentage field.

## Checks and limits

The added unit tests exercise the complete catalog, custom quantities/prices,
repeat initialization, template mappings, subtotal states (including unpriced),
OS-line cleanup without snapshot changes, one-time save/copy/export classification,
monthly percentage isolation and red Excel replication labels.

The real Waitress/Chromium refinement test checks toolbar groups, centered width,
catalog copying, VM comments, both DR modes, applicable subtotal strips, saving and
reopening, generated PDF and mobile controls. Screenshots use synthetic records.
Run it with `python tests/quotation_refinements_browser.py`; cloud Chromium is at
`/usr/bin/chromium`. Set `CW_BROWSER_ARTIFACTS` to choose a screenshot directory.

Windows/IIS, real customer data and independent Microsoft Excel/LibreOffice
recalculation were not available in the cloud. Validate those on your server before
relying on production output. No live emails, production data changes or IIS
configuration changes were performed by these checks.

Final cloud results: the 271-test regression suite passed; all five focused
refinement tests passed (including the additional custom-code/foreign-currency
case); current Version 17 approval/report/PDF/browser acceptance passed; the
refinement browser check passed on desktop and 390 px mobile. Python compilation,
JavaScript syntax and Git whitespace checks passed. The initialization CLI ran
twice with exactly 19 entries afterward. Login files were unchanged.
