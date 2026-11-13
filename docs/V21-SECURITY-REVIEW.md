# Live carry-over update

The user's updated requirement authorizes using V21 as the live application with the old configuration. The package now copies existing V20 data into an independent live V21 workspace rather than starting empty. Production mode preserves SMTP policy and allows new messages using the existing server environment secret; automated tests still use synthetic data/in-memory senders and do not send live emails.

The import reserves port 8000 and locks the EXISTING source storage lock without creating/writing it; SQLite source access is read-only. Only the staged snapshot is migrated. Document/export roots and saved destinations are remapped, linked storage rejected, copied integrity checked and new folders published only after validation. Import failures remove only their own unpublished destinations. Prior pending/running/failed SMTP queue items are cancelled in the copy to prevent replay. Source-hash regression checks verify the original database, attachments, document and export contents stay unchanged, including after independent V21 edits.

The source must be the stopped V20 schema-17 workspace. A missing source/data location is reported rather than replaced with empty test data. Earlier test profiles are not selected by live launchers. A visible build identity and authenticated `/v21/version` feature list help identify a stale server instance. Live migration details are in `VERSION-21-INSTALL.md`.

Remaining limits: actual Windows/IIS/service and UNC behavior, real SMTP delivery, complete Windows restore and real-server rollback are unexecuted. V21 edits do not synchronize back to V20. Old backups stay with V20; V21 starts its own backup history. Server environment credentials limited to the old service account may need to be made available to the V21 launching account. No credentials or actual production data are embedded in the source archive.

The historical review below records the core V21 changes and earlier test mode. Its forced-test-mode statements are superseded by this live update; original authorization, CSRF, private-note/export and path-safety controls remain.

---

# V21 source and regression security review

Scope: V20 baseline `63e5814` plus V21 changes, synthetic temporary SQLite/storage and local Chromium. This is source review and automated regression testing, not a penetration test, external audit or certification. No production accounts, server, credentials, documents or database were accessed.

## Reviewed controls and changes

| Area | Review / validation |
| --- | --- |
| Authentication/session | Existing hashed passwords, login rate limits, idle/absolute session timeouts and session-version invalidation retained. V21 has a separate HttpOnly/SameSite cookie; secure cookies follow the explicit HTTPS profile. Existing account/session regressions exercised. |
| Record authorization | Favorites, history, notes, search, timelines, reminders and pre-send routes use server-side identity and existing ACLs. Viewer shortcut mutation is narrowly allowed; it grants no record write permission. Revoked/deleted records are filtered at render time. Internal notes require original staff edit access, not just a workflow grant. |
| Permission-query optimization | Ownership/ACL/grant snapshots exist only during a single record-list filtering/redaction evaluation, for one connection/current user. Mutation checks occur outside that scope. Existing role, owner, project, reviewer-grant, personal-note and redaction tests remain applicable. |
| CSRF/XSS/SQL | New POST routes use existing CSRF enforcement; missing tokens rejected. Note text uses Jinja autoescaping and a 4,000-character limit. New SQL values are bound parameters; dynamic table identifiers are fixed internal constants. Existing CSP and parameterized repository operations retained. |
| Documents | Existing safe filenames, size limits, anti-traversal checks, ownership markers, symlink/reparse checks, hard-link checks, upload conflict handling and recovery journals retained. Search reads filenames from metadata only, filters by customer access, and links to permission-checked folder views. |
| Exports/private data | Notes live in a separate table, never in customer quotation projections. PDF/Excel/CSV regression tests check that note sentinels are absent. Existing cost/margin privacy and approved-snapshot integrity tests retained. |
| Reminders/audit | Write permission plus staff scope required. Database write transaction serializes cooldown and queuing. Pending decisions only; delivery rechecks recipient activity, access, round and decision. Existing audit records capture the reminder request; no approval decision updates. Email payload contains existing public metadata, omitting notes/prices/margins. |
| SMTP | Existing secure transport modes and sanitized failure handling retained. Real SMTP is blocked by the forced V21 test profile; automated mail tests use in-memory senders. No live mail test performed. |
| Isolation | V20 fallback defaults were unsafe for running an isolated test copy: V21 replaces implicit discovery with a mandatory profile, separate cookie, empty-root initialization and explicit-only migrations. Startup validates schema using a read-only SQLite connection before application startup. Profile/destination tests cover production overlap, inherited V20 settings, linked roots, unexpected existing databases and occupied ports. |
| Stale export cleanup | Confirmed an inherited isolation hazard: saved PDF ownership/deletion paths can still reference old production exports after configuration changes. V21 validates those persisted paths at startup and checks the isolated export root again before deleting any external PDF. A regression seeds a simulated production PDF and verifies it remains byte-for-byte unchanged with cleanup left pending. Backup namespace paths are checked for links too. |
| Process safety | Launcher reserves the actual socket before DB opening, so a failed contender cannot migrate/access the DB first. Windows script checks exact V21 command/interpreter/start time instead of killing a port owner. Actual Windows process behavior remains unverified. |
| Backup/recovery | Corrected backup restore schema whitelist for schema 18. Added a complete offline archive format that includes external documents/exports, hashes exact archived bytes and takes the application lock. Existing portal backups remain database/attachments only and are documented accordingly. |

No additional confirmed remote-code-execution, SQL-injection or authentication-bypass finding was established by this bounded review. That is not evidence of absence. Known compatibility/isolation risks identified above were addressed; no broad dependency advisory scan or exploitation assessment was performed. Dependency pins were retained to preserve the tested runtime; `pip check` reports compatible installed requirements.

## Remaining risks and operational requirements

- The real V20 paths and Windows ACLs are unknown. An administrator must list every production location and deny the V21 service account access to them. A mislabeled or manually marked production copy cannot be distinguished from an intended sandbox solely by application code.
- While switched, the existing IIS URL serves V21 to whoever the existing IIS/network policy permits. Restrict the test audience at IIS/network level if needed. V21 does not publish the site or change access rules.
- The IIS host/proxy/HTTPS settings, Edge renderer, Windows Server process controls, UNC access and rollback service recovery must be rehearsed on the VM. No claim of Windows validation is made.
- `stop-v21.bat` terminates its verified process; finish saves/uploads first. SQLite transactions and document journals support recovery, but stopping in-flight work can interrupt responses.
- Browser copy success does not grant access to its recipient. Clipboard failures use a manual selectable-link fallback. Read-only viewers use existing permission-checked quotation destinations.
- History is limited to ten distinct records; timeline is limited to 250 visible events; search returns at most 100 matches and does not index document contents.
- SMTP delivery may be uncertain on transport interruption; inherited retry semantics are retained. Email is disabled for this sandbox, and no credentials were copied.
- Portal backup ZIPs omit external documents/exports. Use the new offline complete archive or a coordinated administrator backup, protect the profile/source/ACL configuration separately, and verify restoration. Full manual Windows recovery was not executed here.
- Local source and ZIP checks did not detect common private-key/GitHub/AWS access-key patterns. This is not exhaustive secret detection; repositories and archives must remain private. No valid GitHub credential was available to create the requested remote.
