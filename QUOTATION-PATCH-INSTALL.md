# Cirrus Workplace quotation improvements patch

Baseline: Version 17, commit cfc13a3d9542ba8e0423ae1e195f19ba293ba301
(`Redesign Version 17 login with local animated cloud atmosphere`). The cloud
checkout's local branch is `work`. This patch preserves that login redesign.
Apply to this baseline, not an older release or an independently modified tree.

## Windows installation

1. Stop the Waitress process/service using your existing service-management method.
   Leave the IIS configuration unchanged. Ensure nobody is editing quotations.
2. Copy the entire current application release directory to a separate backup
   directory. Record the configured external data directory and deployment settings.
   Back up external customer documents and Reports folders separately.
3. With the original code still installed, run a full-instance backup, using a NEW
   archive filename and the SAME external data path used by the service:

   ```bat
   cd C:\Path\To\CirrusWorkplace
   set "CIRRUS_DATA_DIR=C:\YourActualDataDirectory"
   .venv\Scripts\python scripts\backup.py backup C:\Backups\before-quotation-improvements.zip
   ```

   If the legacy JOSEPH_DATA_DIR variable is configured, ensure it agrees with
   CIRRUS_DATA_DIR. Do not use the example paths without adjusting them.
4. Extract this patch ZIP into the application root. Preserve relative paths and
   replace only the files supplied. It contains no database, customer data,
   credentials, dependency changes or virtual environment.
5. With the server still stopped, initialize the additive editable catalog defaults:

   ```bat
   .venv\Scripts\python -m workspace_app.quotation_defaults
   ```

   This command uses the application's configured external data directory, runs
   inside a transaction and can be repeated. It adds missing catalog entries and
   fills missing fields on equivalent items. Existing customized prices and fields,
   historical quotation snapshots, company templates and customer VM catalogs are
   retained. Ambiguous equivalent entries cause an error rather than a duplicate.
   A SOC unit price of 1250 is rejected: review it in the editable catalog as a
   bundle, not a per-EPS price; standard SOC uses 5/EPS with minimum 250. Resolve
   the named ambiguity using the prior app/catalog, then repeat initialization.
   No separate schema-version upgrade is required; new pricing fields are stored
   in quotation/catalog JSON.
6. Restart Waitress using your existing service configuration. Refresh the browser
   cache (Ctrl+F5). Sign in with your existing account.
7. Verify a NEW quotation: catalog row quantity 1; SOC/NOC minimum warnings and
   blocked saving until corrected; DR VM Replication 50% / Running 100%; customer
   prices; both totals; saved/reopened group removal; PDF and Excel. Open an old
   quotation and compare its amounts against your backup. Do not submit approvals
   or send customer emails solely to test installation.

All unrecognized service prices remain unpriced. New catalog defaults do not
reprice saved quotations. Minimum quantity and unit price are editable catalog
rules; copied quotation rows are snapshots. DR settings and explicit links are
under each VM's row options in Structure & settings. Selecting a DR hosting VM
starts in Replication only mode; pre-existing rows retain their saved pricing
until explicitly changed. Choose a Production link explicitly; names never link
VMs. A manual DR base-price edit activates its override; Reset base-price override
restores linked pricing. Applied percentage remains separately editable.

## Rollback

Stop Waitress. Restore the backed-up application directory. Restore the
pre-patch full-instance data backup to a NEW external directory using the original
backup tool; do not overwrite live data:

```bat
.venv\Scripts\python scripts\backup.py restore C:\Backups\before-quotation-improvements.zip --target C:\CirrusRestored
```

Point the existing service's CIRRUS_DATA_DIR at that restored directory (clear or
align JOSEPH_DATA_DIR), restore external document/report backups if needed, and
restart the original application. Rollback loses work created after the backup;
retain the newer data separately. Do not run original code on new quotation JSON
containing the new pricing fields. Review the restored records before reuse.

## Validation and scope

Development tests use synthetic accounts and temporary databases. The added tests
cover catalog idempotency/custom prices, SOC/NOC minimums, legacy amounts, DR rates,
explicit links and overrides, duplicated links, explanations, and cached Excel
values/formulas. The browser acceptance harness exercises the real Waitress server
and system Chromium, including deletion/save/reopen and responsive rendering.

No Windows server, IIS service, customer dataset, Microsoft Excel installation,
or LibreOffice was available in this cloud environment. Verify Windows deployment
and independent spreadsheet recalculation in your environment. Linux browser PDF
checks are useful evidence, not Windows deployment validation.

The older `tests/browser_smoke.py` has a baseline ambiguous Production selector;
it passed project/catalog creation but cannot complete without a separate test
maintenance change. Use the current Version 17 acceptance workflow for regression
coverage. Optional screenshot artifacts are delivered separately from this patch.

Verified in the cloud on the final patch: 267 unit tests passed; current Version 17
Waitress/Chromium acceptance passed (approval submission, captured emails, exact PDF,
reports, permanent deletion, responsive layouts); quotation-improvements Chromium
checks passed. The additional Excel test verified 228 base / 114 replication cached
values and explicit linked-price and applied-rate formulas. Run the new browser
check with `python tests/quotation_improvements_browser.py` (system Chromium at
`/usr/bin/chromium` in the cloud); synthetic screenshots default to `/tmp`.
