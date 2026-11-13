# V21 schema and live carry-over

V20 uses schema 17; V21 uses schema 18. The production setup explicitly copies the stopped V20 database with SQLite's backup API through a read-only source connection, then migrates **only the staged independent copy**. Original V20 records/files remain unchanged. Normal startup never migrates.

Schema 18 adds five feature tables:

| Table | Purpose |
| --- | --- |
| `user_favorites` | Individual quotation/customer favorites; user/record deletion cascades |
| `user_recent` | Ten distinct recently viewed records per user; indexed by user/time |
| `quotation_internal_notes` | Staff-only quote notes, author and timestamp; separate from public quotation content |
| `approval_reminders` | Last reminder time per round for serialized cooldown; round deletion cascades |
| `reminder_email_recipients` | Public payload metadata for existing queued notification IDs; email deletion cascades |

Existing quotation JSON, pricing calculations, approved artifacts, decision history and accounts are not transformed by the additive schema migration.

The live-copy step rewrites only storage/configuration metadata in the new snapshot: automation/document roots, customer export mappings, PDF file ownership and pending deletion destinations. Historical exports outside the current export root are copied into the new Recovered folder when available. Existing SMTP settings are retained, but the prior pending/running/failed mail queue is cancelled in the copy so it is not replayed as new mail. New V21 notifications use the original SMTP policy and server environment password.

`setup.bat` uses `%LOCALAPPDATA%\CirrusWorkplaceV21Live`; it does not reuse earlier test profiles. Repeating setup with a recognized live profile does not re-import V20 or migrate existing V21 data. An explicitly requested later V21 schema upgrade uses `scripts/v21.py migrate` and creates a safety backup first. Do not open a schema-18 database with V20 or restore it over V20.

Rollback starts V20's original database and files. New work entered into V21 does not synchronize back. See [installation and rollback](../VERSION-21-INSTALL.md).
