# Cirrus Workplace Version 19 — full app installation and upgrade

Download the complete `v19.0.1` ZIP from GitHub. It contains the full application,
all Version 18 changes and the subsequent quotation refinements. No earlier patch
ZIP is required. It contains no customer database, account credentials or virtual
environment. Runtime dependencies are unchanged; SQLite schema remains 16.

## Updating an existing Version 19 installation

The `v19.0.1` layout update requires no database migration, catalog initialization,
new dependency or data change. Follow the [margin-controls installation and rollback
guide](../QUOTATION-MARGIN-CONTROLS-INSTALL.md). The full app ZIP includes this update;
the original `v19.0.0` remains available for rollback. Keep the current data paths,
IIS configuration and service account unchanged.

## Existing Windows installation

1. Stop Waitress using the existing service/console method. Back up the current
   release, actual external data directory and deployment configuration. Back up
   external Customer Documents, quotation PDFs and Reports separately. Create and
   verify a full-instance backup with the original app's `scripts/backup.py`.
2. Extract the full Version 19 ZIP into a NEW release folder, such as
   `C:\Apps\Cirrus-Workplace-V19`. Do not extract into the data directory.
3. Run `setup.bat` from the new folder using the supported Python installation to
   prepare its virtual environment. Retain the exact existing service account,
   external data path, deployment JSON, allowed hosts, HTTPS and proxy settings.
4. With Waitress still stopped, open Command Prompt in the new application folder
   and initialize the editable catalog with the actual service data path:

   ```bat
   set "CIRRUS_DATA_DIR=C:\YourActualDataDirectory"
   .venv\Scripts\python -m workspace_app.quotation_defaults
   ```

   Replace example paths. If JOSEPH_DATA_DIR is set, it must agree with
   CIRRUS_DATA_DIR. The command is repeatable and preserves customized catalog
   defaults. Unknown prices remain blank. Resolve any reported ambiguous catalog
   entries before continuing; do not invent prices or delete customer VM entries.
5. Point the existing service's application path/working directory at the new
   release, retaining all other configuration, and restart it normally. Leave IIS
   bindings unchanged. Do not run `init-admin` during an upgrade.
6. Refresh the browser with Ctrl+F5 and sign in with the existing account. Compare
   saved quotation amounts against the backup. Check catalog defaults, both DR
   modes, exact VM Replication labels, one-time Setup totals, PDF/Excel and approvals.

The [refinement installation guide](../QUOTATION-REFINEMENTS-INSTALL.md) explains
catalog behavior, migration edge cases and the validation checklist. Its patch-copy
step is unnecessary when using this complete Version 19 release.

## Fresh installation

Extract the full app into a new folder and run `setup.bat`. Choose an external data
folder, set CIRRUS_DATA_DIR consistently for every command and the eventual service,
then run `.venv\Scripts\python -m workspace_app.quotation_defaults`.
Create the first administrator interactively using
`.venv\Scripts\python manage.py init-admin`, then start with `start.bat`.
There are no default passwords. Configure internal HTTPS access through the
existing Windows/IIS deployment guide; GitHub publication does not deploy a VM.

## Rollback

Stop Waitress. Use the old release and its original backup tool to restore the
pre-upgrade full-instance backup into a NEW external data directory. Point the old
service back at the old release and restored data, retaining the matching deployment
configuration. Restore separately backed-up external folders as needed. Preserve
newer data separately; rollback loses work since the backup. Do not run older code
against newer catalog JSON, which includes additional support-pricing fields.

Windows service installation and independent Microsoft Excel/LibreOffice
recalculation require validation on your own server.
