# Cirrus Workplace Version 20 — installation and rollback

Version 20 fixes the connection between Service Catalog and the default quotation
structure. It also includes the compact catalog editor and a visible, dismissible
**Quotation saved successfully** notification after the server commits a save.

The patch baseline is Version 19.0.1, commit
`eec0c537b8478f900a03226c4c2abc16a2a24ab5`. The complete Version 20 GitHub ZIP contains
all earlier application files and these updates; no earlier patch ZIP is required.
Runtime dependencies and Python requirements are unchanged. Database schema is
upgraded additively from **16 to 17**.

## Windows upgrade

1. Stop Cirrus Workplace/Waitress with your normal service/console method. Ensure
   users have finished editing. Keep the exact service account and external data path.
2. Back up the original application directory and deployment configuration. Using
   the original application and its actual data path, create a fresh full backup:

   ```bat
   cd C:\Path\To\CurrentCirrusWorkplace
   set "CIRRUS_DATA_DIR=C:\YourActualDataDirectory"
   .venv\Scripts\python scripts\backup.py backup C:\Backups\before-version-20.zip
   ```

   Replace example paths. The archive must be outside the data directory. If
   JOSEPH_DATA_DIR is set, it must match CIRRUS_DATA_DIR. Back up external Customer
   Documents, quotation PDF and Reports folders separately; their bytes are not
   included in the application's full-instance backup.
3. Choose either installation method:

   - **Patch:** merge `Cirrus-Workplace-Version-20-Patch.zip` into the Version 19.0.1
     application root (containing `run.py` and `workspace_app`). Preserve relative
     paths and replace the supplied files. Keep the current virtual environment.
   - **Complete app:** extract the complete `v20.0.0` ZIP into a new release folder,
     run its `setup.bat`, and retain the existing external data/deployment settings.
     Point the service at that new release folder after initialization.
4. With Waitress still stopped, open Command Prompt in the updated/new app folder
   and run the controlled initialization using the service's actual data path:

   ```bat
   set "CIRRUS_DATA_DIR=C:\YourActualDataDirectory"
   .venv\Scripts\python -m workspace_app.quotation_setup
   ```

   This upgrades the schema, binds existing standard catalog items, creates missing
   defaults, and saves the confirmed default structure. It can be repeated without
   duplicating items or resetting a saved setup. The same initialization also runs
   automatically on first use of the catalog, setup editor or new-quotation flow;
   it no longer depends on remembering the old manual catalog command.
5. Restart Waitress normally. Leave IIS, HTTPS, allowed hosts, SMTP, accounts and
   service permissions unchanged. Do not run `init-admin` during an upgrade.
6. Refresh with Ctrl+F5, then open **Service Catalog → Default quotation setup**.
   Confirm the assignments and use **Save default setup** if making changes.

Initialization recognizes legacy labels such as Security Datacenter FW, Managed
Backup (Agent), Performance - NOC, Cirrus Compute VM and Security - Collector VM.
It retains their record IDs and customized prices. Missing metadata is populated;
a generic legacy `unit` is replaced with the known standard unit. Legacy zero
SOC/NOC minima receive their agreed bundle minima. Connectivity Setup defaults are
classified one-time. Saved quotation data is never restructured or repriced.

If initialization reports ambiguous equivalent catalog entries, resolve the named
conflict rather than deleting unrelated records. Existing catalog item pages remain
editable for repair. A SOC unit price of 1250 is rejected because it is a bundle
amount, not a per-EPS price; the standard rule is 5/EPS, minimum 250 EPS. Review it
in the compact catalog editor and retry initialization. Existing explicit custom
prices are otherwise retained, including foreign-currency items; USD defaults are
not invented for another currency.

## How the two editors work

**Service Catalog** is the source for service/sub-service/type, quantity, price or
fixed/percentage rule, billing, pricing model and comments. Blank prices remain
Unpriced; explicit zero is free. Use Fixed fee for fixed-method items and Support
percentage for percentage-method items. The compact item page has Save, Cancel and
Delete; less-used existing fields remain under Additional catalog fields.

**Default quotation setup** stores only section names, roles, order, catalog IDs and
inclusion flags. It stores no prices or quantities. Expand Assigned services to
choose included items, use Add Group and the arrows to arrange the hierarchy, and
save it for future quotations. Links open the catalog defaults for editing.

The initial order is:

1. Main Site — Cirrus Compute (VM, Storage), Security Services (Datacenter FW,
   Perimeter FW, Load Balancer, WAF, VPN), Backup Services (Managed Backup, Backup Storage).
2. DR Site — the same groups and standard service assignments.
3. Monitoring — existing standalone NOC services and optional-item behavior.
4. Cybersecurity Services — existing SIEM Collector VM, SIEM, SOC, VPN user/node,
   plus EDR. The standard EDR item is not duplicated under Main/DR Security.
5. Connectivity Services — Protected Internet and Protected Link.
6. Connectivity Setup — One-Time Fee — one-time setup only.
7. 8×5 Request Fulfillment — existing percentage-support behavior, with explicit
   customer support policies continuing to take precedence.

Keep the Main Site / DR Site / Monitoring behavior selectors when renaming those
categories: the role preserves DR links and optional monitoring behavior independently
of the displayed name. Existing administrator template branding/terms are retained;
new quotation structure and service defaults use the new setup and catalog.

New standard catalog items start at quantity 1. Existing customized quantities are
preserved. SOC remains minimum 250 EPS at the standard 5/EPS; NOC remains minimum
50 IPs at the standard 20/IP. Correct those quantities before saving, or explicitly
exclude the unwanted service. Do not interpret quantity 1 as a valid minimum bundle.

VM rows require choosing the customer's VM size. Generic Compute catalog prices do
not replace customer VM prices. Select the size for Main and DR; DR starts in
Replication only (50%) and retains Running (100%), explicit links and quote-specific
overrides. Customers without configured VM sizes/prices must have them configured
or deliberately exclude the unused row. Unknown non-VM prices remain unpriced.

Catalog/setup edits affect future quotations and newly added rows. They do not alter
saved quotations. Editing a quotation never updates the global catalog or setup.
The existing quotation scale and margin-control layout are retained.

## Verify before normal use

- Edit a catalog quantity/price, assign the service in Default quotation setup, and
  create a quotation for each of two customers. Check structure and copied defaults.
- Select each customer's own VM size and verify the full base price and DR rate.
- Confirm EDR is under Cybersecurity only; Monitoring remains standalone/optional.
- Check monthly, one-time and support charges, and minimum validation.
- Save and confirm the visible saved notification; reopen and check PDF/Excel.
- Change a catalog default, create another quotation, and compare it with an earlier
  saved quotation. The earlier snapshot must be unchanged.
- Check existing approvals, customer VM data, saved quotations and external files.

## Rollback

Schema 17 intentionally prevents older versions from opening the upgraded database.
Stop Waitress and restore the previous application release. Using its original backup
tool, restore the pre-Version-20 archive to a NEW external directory:

```bat
.venv\Scripts\python scripts\backup.py restore C:\Backups\before-version-20.zip --target C:\CirrusRestoredV19
```

Point the old service's CIRRUS_DATA_DIR at the restored directory and align/clear
JOSEPH_DATA_DIR. Restore separately backed-up external folders as needed, then
restart the old application. Keep newer data separately: rollback loses work since
that backup. Do not downgrade the SQLite version number or run old code on the new
catalog JSON. Merely replacing a few Python files is not a complete rollback.

## Verification and limits

Tests use synthetic data, real login/authorization and temporary databases. They
cover legacy catalog reuse, no duplicated standard items, editable setup assignments,
two-customer defaults, catalog-change snapshot isolation, customer-specific VM prices,
DR replication/running/links, optional Monitoring, monthly/one-time/support totals,
minimum validation, schema migration, backup/restore, compact catalog pages and
success notification only after a successful save.

Windows/IIS deployment, real company data and independent Microsoft Excel/LibreOffice
recalculation were not available. No production service or live emails were changed.
Screenshots contain synthetic examples, not your customer data.

Final cloud checks: 278 unit tests, six focused Version 20 tests, the real two-customer
catalog/setup/VM/save-confirmation browser flow, and existing approval/report/PDF
browser acceptance passed. The initialization command ran twice without duplicates.
The user explicitly authorized publication as Version 20 on GitHub.
