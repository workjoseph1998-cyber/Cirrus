# Version 21 — complete live version on your existing Windows Server

This package supersedes the earlier empty test packages. It includes all agreed V21 features and uses your existing accounts, quotations, prices, approvals and documents through an **independent live copy**. V20 stays installed and unchanged as the fallback.

## Download → setup → start

1. Stop V20 on the **same Windows Server 2022** and pause any service recovery/scheduled auto-start during the switch.
2. Extract this ZIP into a separate V21 application folder. Never extract over V20. Run under the Windows account that can read the V20 data, customer documents and exports and write its own V21 live folders.
3. Run **setup.bat**. It installs dependencies into this application's own `.venv`. It automatically reads the existing V20 deployment file for the IIS/network policy and locates the data directory. If the data path cannot be detected, setup asks for the folder containing V20's `workspace.sqlite`; no manual shell commands or JSON editing are required.
4. Setup copies the stopped V20 workspace and upgrades **only the new database copy** to V21. It retains your existing accounts/password hashes, permissions, preferences, customers, quotations/revisions, prices, approval history and report data. Attachments, external customer documents and quotation exports are copied into independent V21 storage. Old V20 backups remain where they are; new V21 backups use the V21 backup root.
5. Run **start.bat**, then open your **existing IIS workplace URL** and sign in with your existing username/password. The backend remains `127.0.0.1:8000`; IIS bindings are unchanged.

Setup requires V20 schema 17 and its existing `.workspace.lock` file. That lock identifies the real data directory used by the V20 launcher. It does not select or silently convert earlier V21 test data. Existing V21 live data is preserved on repeat setup, rather than recopied from V20. Unrecognized destination folders are never overwritten. If setup cannot safely copy a configured document/export location, it stops and reports the reason rather than starting an incomplete workspace.

## See the changes

Check the sidebar footer: **Version 21 · Live · Build `<commit>`**. The authenticated `/v21/version` endpoint also reports the build and feature list. A different version/build means the server is serving a different installation.

Open **What’s new in V21** from the sidebar or dashboard. It links to all the additions:

| Addition | Where to find it |
| --- | --- |
| Copy quotation link, validity countdown, favorite | Quotations list; copy and validity also appear in saved quotation controls |
| Favorites and last ten viewed records | Sidebar: Favorites & recently viewed |
| Internal notes | Saved quotation: Controls → More → Internal notes; also quotation management/approval tools |
| Pending-approver reminder | Saved quotation: Controls → More → Approval & reminders, then Remind Pending Approvers |
| Pre-send verification | Saved quotation: Controls → More → Pre-send check; checks also run before marking sent |
| Customer timeline | Customer workspace: Activity timeline |
| Active/pending/expiring/sent-this-month attention | Dashboard and Needs Your Attention |
| Search and keyboard shortcut | Global search; Ctrl+K / ⌘K |
| Unsaved changes protection | Existing editor and ordinary editable forms |

The pricing editor's structure, Main Site/DR Site, separate Monitoring, Cybersecurity/Connectivity sections, one-time setup, 8×5 support, customer-specific prices, monthly/one-time calculations, margins, exports, approval dots, reports and themes remain the V20 implementation.

## What is copied and what remains separate

The default live destination is `%LOCALAPPDATA%\CirrusWorkplaceV21Live`, with separate `Config`, `Data`, `Documents`, `Exports` and `Backups` subdirectories. The application folder itself remains separate from all runtime storage. Earlier `%LOCALAPPDATA%\CirrusWorkplaceV21` test profiles are not selected by this release's launchers.

During first setup, a temporary socket reservation and the existing V20 storage lock prevent the normal V20 launcher from running concurrently. The source SQLite database is opened read-only and copied with SQLite's backup API. No V20 migration, checkpoint command or application data write is issued. Files are copied without modifying their source contents. Linked/reparse-point/hard-linked storage is rejected. The candidate V21 copy is validated before its directories/profile are published; failed imports clean up only their own new targets.

Database and file destinations saved in the copy are rewritten to V21 locations, including customer export mappings, PDF ownership and pending deletion metadata. Historical PDFs outside a current export root are recovered into V21's `Exports\Recovered` when present. Original source paths are recorded as protected locations. The old unsent/failed email queue is retained as cancelled, so switching does not replay V20 messages; new V21 approval notifications use the retained SMTP policy.

**Live SMTP is enabled according to your retained application settings.** The previous package's forced test suppression is removed for production profiles. SMTP passwords remain in the server environment. If V20's password was supplied only to its old service or console, that environment must also be available to the Windows account/process launching V21. Secrets are not embedded in the ZIP or Git repository. No actual SMTP delivery was performed during development checks.

## Start/stop and rollback

`start.bat` discovers the live profile automatically. It refuses an occupied port, and the Python launcher reserves the actual socket before opening the database. Windows uses `SO_EXCLUSIVEADDRUSE`. V21 does not stop unrelated processes, change IIS, install a service or modify V20's launch configuration.

To roll back:

1. Finish V21 saves/uploads and run **stop-v21.bat** from the V21 folder/account. It verifies the executable, exact script and process start time; it does not kill a process simply because it owns port 8000.
2. Confirm port 8000 is free. If another process owns it, inspect it before continuing.
3. Start V20 with its **original launcher/service and original settings**, and restore any service-recovery/scheduled-start policy paused for testing.
4. Open the same IIS URL and verify the V20 footer and records. No reinstall, schema downgrade or V21-to-V20 data merge occurs.

**Work entered in V21 is not synchronized back to V20.** Rollback returns to the V20 state at the time you stopped it. Retain complete backups and do not record parallel production work in both installations. The stop script terminates its verified V21 process; finish work first so active responses/uploads are not interrupted.

## Backup, recovery and explicit later migrations

After stopping V21, run its complete offline backup command with the V21 virtual environment:

```bat
.venv\Scripts\python.exe scripts\full_backup_v21.py
```

It includes the database, attachments, V21 marker, external documents/ownership metadata and exports, with a SHA-256 manifest. Prior backups, application binaries, profile, environment secrets, Windows ACLs and IIS configuration must be protected separately. Existing portal/automatic backup ZIPs still contain the database and attachments only; they are not complete external-document backups.

For recovery, verify all manifest checksums and extract the complete archive's `data/`, `documents/` and `exports/` into empty V21 roots while V21 is stopped. Prefer the same absolute V21 paths so stored mappings remain valid. Retain damaged folders rather than overwriting them; check SQLite integrity/foreign keys and the V21 profile before restarting. Never restore a V21 archive over V20. The complete archive format is separate from the portal's older ZIP importer.

Normal start never migrates. First setup upgrades only its new V20 snapshot. A subsequent explicitly requested V21 database upgrade uses `scripts\v21.py migrate` against its marked V21 storage and creates a database/attachments safety backup first; also take a complete backup for external files.

## Validation limits

The synthetic live-copy tests verify preserved source file hashes, existing account login, quotation/settings preservation, independent destinations, repeat setup, failure cleanup and occupied-port refusal. Browser checks exercise the live identity and visible V21 tools. Source code, pricing, approval, exports, permissions and recovery regressions are documented in `docs/V21-TEST-RESULTS.md`.

The real Windows CMD/PowerShell/IIS/service behavior, server ACLs/UNC paths, Edge installation, real SMTP delivery and rollback on your VM cannot be executed in this Linux environment. The new package is intended for your live installation; this limitation is a statement of what was tested, not a forced test mode.
