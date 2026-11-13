# Version 20 upgrade and operation

Use the complete [Version 20 installation and rollback guide](../VERSION-20-INSTALL.md).
The full GitHub app ZIP contains all prior updates. The patch targets Version 19.0.1.

Back up with the old application before upgrading. Stop Waitress, retain the exact
external data path/service account/IIS configuration, install the new source, and
run `python -m workspace_app.quotation_setup` using the new virtual environment and
existing data path before restarting. Schema 16 → 17 adds the saved quotation setup
and stable catalog-binding tables. Initialization is repeatable and also runs on
first use. No new runtime dependencies or administrator account creation is required.

Use Service Catalog → Default quotation setup for future quotation structure, and
Service Catalog for default quantities/prices/rules. Select customer VM sizes in each
new quotation and correct SOC/NOC minimum quantities. Saved quotation snapshots are
not repriced or restructured. A successful save now displays a confirmation.

Rollback requires the original application and pre-upgrade data backup restored to
a new directory. Older versions intentionally reject schema 17; do not downgrade the
SQLite version number. External Customer Documents/PDF/Reports need separate backups.
