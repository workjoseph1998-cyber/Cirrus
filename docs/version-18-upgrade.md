# Cirrus Workplace Version 18 — installation and rollback

Read the complete [quotation patch installation and rollback instructions](../QUOTATION-PATCH-INSTALL.md).
For the complete Version 18 download, extract into a new release directory, install
its unchanged requirements using the supported Python environment, retain the exact
existing external data directory/service account/deployment configuration, and run
`python -m workspace_app.quotation_defaults` with the service stopped before restart.
Do not run `init-admin` on an existing installation. SQLite schema remains 16;
new pricing metadata is stored in existing JSON records. Keep the Version 17
source and a pre-upgrade full data backup for rollback.

No company VM, IIS configuration, DNS, certificates, SMTP settings or production
service was changed by publication to GitHub.
