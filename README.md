# Cirrus Workplace — Version 21.1

Complete UX refinement release built from the uploaded V21 live application.

- [V21.1 installation, testing and rollback](VERSION-21.1-INSTALL.md)
- [V21.1 changelog](CHANGELOG-V21.1.md)
- [V21.1 test results and known limitations](docs/V21.1-TEST-RESULTS.md)

Quotation secondary actions now live in **Manage**; the quotation editor and existing filters are preserved. Existing V21 documentation below remains available for architecture, business features and deployment profiles.

---

# Cirrus Workplace V21 — complete live package

On the **same server as V20**, stop V20, extract to a separate folder, run **setup.bat**, then **start.bat**. Setup carries over your existing configuration, accounts, records and files into a separate V21 live copy. Use your existing login. No empty test database or manual initialization commands are required.

Read [START-HERE.txt](START-HERE.txt) or [installation and rollback](VERSION-21-INSTALL.md). The sidebar/dashboard **What’s new in V21** page links to the agreed additions. The footer shows **Version 21 · Live · Build number**.

V20 remains unchanged. Rolling back to it does not synchronize work entered in V21.

See [changelog](CHANGELOG-V21.md), [test results](docs/V21-TEST-RESULTS.md), [security review](docs/V21-SECURITY-REVIEW.md) and [performance measurements](docs/V21-PERFORMANCE.md). GitHub authentication was unavailable; source is committed in the separate local repository.

---

Historical documentation below describes earlier releases and does not replace the V21 setup instructions above.


# Cirrus Workplace — Version 20

A local/internal customer, project and presales application for Cirrus SAL, built with
Python, Flask, SQLite and Waitress for Windows Server 2022. It includes individual
accounts, owner/private work records, named sharing, a service
catalog, shared reference registry, quotation statistics, Cirrus VM profiles, compact live quotation editing and reviewed Excel
quotation import. Frontend assets are bundled; no cloud hosting, API keys, Docker,
external database or paid app service is required.

**Latest release: Version 20.** Use [`version-20`](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-20).
[Download the complete Version 20 app ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/tags/v20.0.0.zip)
while signed into GitHub. See the [version/download index](docs/versions.md).
Older release branches and immutable tags remain available.

## Version 20

Service Catalog and the **Default quotation setup** are now connected explicitly.
Legacy catalog labels are recognized, missing standard services initialize automatically,
and the confirmed Main Site / DR Site structure is populated for every new quotation.
The setup editor stores assignments and inclusion flags; quantities, prices, billing,
pricing models and comments remain in the editable catalog. Saved quotations and
customer-specific VM prices remain snapshots. EDR belongs under Cybersecurity;
Monitoring, connectivity, one-time setup and 8×5 support remain standalone.

Catalog item pages use a compact field/value form. Successful quotation saves show
a clear, dismissible confirmation. Existing quotation scale, margin controls, login,
authentication, approvals, PDF/Excel and pricing behavior are retained.

Read the [Version 20 Windows installation/migration and rollback guide](VERSION-20-INSTALL.md)
and [verification report](docs/version-20-verification.md). Product **20**, SQLite
schema **17** (additive upgrade from schema 16); dependencies unchanged. The complete
app ZIP includes all prior changes. Earlier version branches and tags remain available.

## Version 19

**Latest patch: v19.0.1.** The quotation editor now uses its empty side margins
for actions, with the title in the top navigation and a compact Controls dialog
on narrower screens. At 1908 × 960 it recovers 199 pixels above the sheet while
preserving sheet width, columns, fonts and row heights. This approved layout update
requires no database migration. See the [layout installation/rollback guide](QUOTATION-MARGIN-CONTROLS-INSTALL.md).


The complete application includes all Version 18 quotation improvements and the
latest refinements: saving and approvals grouped on the left, settings and exports
on the right, compact centered quotation layout, exact red **VM Replication** labels,
applicable environment subtotals, generated OS-line cleanup, and a complete editable
standard catalog. New quotations and added catalog rows copy saved default quantities
and prices; existing quotations and customer VM prices remain unchanged.

Unknown service prices remain unpriced. Connectivity Setup stays one-time. Monthly
support rules exclude incompatible one-time services. Login, authentication,
approvals, reporting, PDF generation and IIS/Waitress compatibility are retained.

Download the **full app ZIP** above; no earlier patch ZIP is required. Read the
[Version 19 installation/upgrade and rollback guide](docs/version-19-upgrade.md)
and [verification report](docs/version-19-verification.md). Run the documented catalog
initialization command with the app stopped. Product version is **19**; SQLite schema
remains **16**, and runtime dependencies are unchanged.

## Version 18

Quotation editor improvements: editable catalog defaults with SOC/NOC minimum
validation, bulk row selection/deletion, persistent group removal, a full-width
quotation with collapsed structure controls and on-demand options, larger environment
subtotals, DR VM Replication/Running pricing with explicit Production links and
quotation overrides, and accessible calculation explanations. Existing quotation
amounts and customer-specific VM prices are preserved; the Version 17 login redesign
is retained. No external CDN or new runtime dependency is introduced.

**Installation requires an explicit catalog initialization command while the app is
stopped.** Read the [Version 18 installation and rollback guide](docs/version-18-upgrade.md)
and [validation report](docs/version-18-verification.md). Product version is **18**;
SQLite schema remains **16**. New pricing metadata uses existing JSON records.

## Version 17

Adds revision-bound **Sent to Client** records and internal milestone email, four
permission-scoped **Reports** with monthly fees and separate one-time charges,
printable previews and timestamped PDFs in a persistent administrator-configured
Reports folder. Comparisons and quotation-list monetary summaries use monthly fees.

Permanent archived-family deletion supports individual/bulk actions even with
approval, discussion and sent history, removes tracked quotation-owned files and
provides per-family cleanup status/retry. Existing permissions, contract safeguards,
reference reservations and audit records remain. The quotation editor, customer
layout and calculations are preserved.

Read the **[Version 17 upgrade/backup/rollback guide](docs/version-17-upgrade.md)**
and [verification results / remaining Windows checks](docs/version-17-verification.md).
Product **17**, SQLite schema **16**, additive migration from schema 15. No new runtime
packages, account initialization, SMTP reconfiguration or IIS/Waitress binding changes.
The supplied Version 16 deployment ZIP matches the latest prior Version 15 code;
its verified baseline is preserved in the `version-16` ref.

## Version 15

Historical release description. Version 17 changes comparisons/reports to monthly fees.

Optional Monitoring is excluded from included charges and support bases, with a
separate yellow customer summary. Compare recurring monthly charges or full
contract values using the same four immediately updated summary cards.

Customers gain a permission-checked **Documents** tab backed by a persistent,
administrator-configured server folder, with nested folders, original-name downloads,
rename/move/delete and explicit replacement/version choices. Customer names may
change without changing their document area. **External document bytes require a
separate backup alongside the application backup.**

The surrounding workspace gains refined light/dark layouts, compact customer headers,
listing density, sticky headers, remembered list position/filters and faster quotation
listing. The internal quotation row editor, keyboard behavior and pricing workflow
remain intact. Consumption stays retired; historical data is retained.

Read the **[Version 15 upgrade and backup guide](docs/version-15-upgrade.md)** and
[verification results / remaining Windows checks](docs/version-15-verification.md).
The latest [approval-email and studio-controls patch](docs/version-15-email-studio-patch.md)
adds professional HTML/plain-text milestone emails, an Approvers & submission dialog
and a compact Quotation options pane. Product **15**, SQLite schema **15**, additive
migration from schema 14. No new runtime packages,
account initialization, SMTP reconfiguration or IIS/Waitress binding changes are required.

## Version 14

Historical release description; its features are retained in Version 15.

Adds administrator-confirmed account deletion while retaining stable historical
identities, linked records and approval decisions. Deleted accounts lose sign-in
access and cannot be re-enabled; current-account and last-administrator safeguards
run on the server.

Quotation headings no longer add `(USD)`. Monthly/one-time fee headings can be
edited per quotation, alongside the existing editable Unit Price label. Customer
HTML/PDF/print and Excel show dollar amounts; Excel retains numeric drivers/formulas.
The entire Total Monthly Fee row is red with bold white text.

The standalone 8×5 support section now has section/service checkboxes and an
internal resolved-base/fee display. It reuses existing saved percentages, targets,
exact calculations and duplicate/cycle protection, preserving historical totals.

Read the **[Version 14 upgrade guide](docs/version-14-upgrade.md)** and
[verification results / remaining Windows checks](docs/version-14-verification.md).
Product Version 14 uses **SQLite schema 13**. No new runtime packages, account
initialization, SMTP changes or deployment binding changes are required.
Supplier Quotations and other suggested improvements are outside this release.

## Version 13

Historical release description; all features below are retained in Version 15.

Choose any number of **Approvers** for each quotation, starting on New Document.
Defaults are preselected and editable; draft saves do not start notifications.
Every selected approver must approve. Optional operations/commercial stages retain
the existing review sequence without requiring exactly three people. Changing the
selection after submission preserves decisions and requires explicit resubmission.

Shared green/white approval dots, counts and keyboard-accessible details appear
across quotation lists, customer quotations, Dashboard and approval pages. A
searchable Customer dropdown combines with existing filters, pagination and bulk
selection. Customers show quotation count and USD quotation value separately.

Windows startup reads persistent deployment settings outside the release folder,
with administrator environment overrides taking precedence. SMTP adds **None
(no TLS)** for ordinary SMTP/IP-authorized relays using any configured host/port;
STARTTLS remains the default. Existing saved SMTP settings remain intact.

Read the **[Version 13 upgrade guide](docs/version-13-upgrade.md)** and
[verification results / remaining Windows checks](docs/version-13-verification.md).
Product Version 13 uses **SQLite schema 12**, migrated automatically and additively
from v12. No new runtime packages, account initialization, binding changes or live
deployment are required. **Back up before upgrading.**

## Version 12

Historical release description; Version 13 makes the approver count configurable.

Adds version-bound quotation approval by two independent operations reviewers and
one commercial reviewer, scoped reviewer editing, immutable approved snapshots/PDFs,
discussion/replies/mentions, per-user notifications and optional queued SMTP email.
The Dashboard and Approvals page distinguish actionable work from waiting stages.
Quotations remain editable; changed customer-facing content requires a new review.

Restores the left sidebar and adds remembered Light / Dark / System preferences.
Customer quotation documents keep their intended light professional styling.
Consumption entry points are retired with their database/history/workbooks retained;
administrators can download a handover archive. Independent customer catalogs,
pricing, existing business outcomes, references, exports and backups remain.

Read the **[Version 12 upgrade and workflow guide](docs/version-12-upgrade.md)**
and [verification results / remaining Windows checks](docs/version-12-verification.md).
Product Version 12 uses **SQLite schema 11**. No new runtime packages, account
initialization, binding changes or automatic live deployment are required.

## Version 11

Historical release description. Its consumption screens are retired in Version 12;
their records remain available through the administrator handover and full backups.

Customer workspaces now include reviewed monthly consumption workbook imports,
independent tenant VM catalogs, executive consumption summaries and customer-only
Excel/PDF exports. Quotations retain their name and existing saved prices; focused
management dialogs and a compact Pricing & Margin worksheet reuse existing tools.
The Dashboard and primary pages share a responsive Cirrus navigation and theme;
the general Cirrus Hosting VMs page retains its layout and calculations.

Automatic PDFs now save directly in the mapped customer folder, using the saved
title. Persistent file ownership prevents different quotations/revisions from
overwriting colliding names. Existing export files remain untouched. Customer
deletion requires an administrator review and is blocked by business history.

Read the **[Version 11 upgrade and operating guide](docs/version-11-upgrade.md)**
and [verification results and remaining Windows checks](docs/version-11-verification.md).
Uses **SQLite schema 10**, with additive migrations and no new runtime packages
relative to Version 10. **Back up before upgrading.**

## Version 10

Compact quotation/document management workspace, searchable cross-quotation
comparison, workflow/follow-up/activity and related-document management, saved
12-month presentation toggle and screenshot-aligned Cirrus headers. Customer PDFs
export asynchronously to administrator-mapped customer folders under a configured
root, using stable customer IDs, atomic writes, collision/revision protection,
clear status and Retry. Missing mappings never fall back to another destination.
Complete administrator-only ZIP backups are available online, with optional daily
and weekly retention in a separate folder.

Read the **[Version 10 upgrade, folder permissions and backup guide](docs/version-10-upgrade.md)**
and [verification results](docs/version-10-verification.md). Uses **SQLite schema 9**.
Playwright is the new runtime dependency for automatic printing with installed
Edge/Chrome; no separate browser bundle or external conversion service is needed.
Existing bindings, data paths, authentication and IIS configuration stay unchanged.
The simplified updater remains deferred. **Back up before upgrading.**

## Version 9

Quotations appear immediately below compact KPIs/filters; monthly charts are collapsed
below the list. Contract quoted value, monthly quoted fees and frozen Won values
are separate. Archived families support confirmed permanent deletion with accepted
revision, contract, permission and reference safeguards.

Customers unifies the visible customer/project workflow while retaining agreement
records and permissions. It includes date-filtered calculated charges, quotations,
consumption, compact price overrides, support/discount defaults, contracts and expiry
indicators. Support is a standalone 8×5 section with unchanged-fee migration checks.

Read **[Version 9 backup, upgrade, rollback and operating guide](docs/version-9-upgrade.md)**
and [verification results](docs/version-9-verification.md). Product Version 9 uses
**schema 8**, with no new runtime packages or IIS changes. The simplified updater
is deferred. The verified [Version 8 baseline ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/feature/cirrus-workplace-v8.zip)
remains available; this release builds on that exact app.

## Version 8

Adds customer/project agreed pricing, immutable proposed/approved contract versions
and documents, monthly consumption snapshots, optional customer-facing discounts,
and quotation-family bulk archive/restore. Customer metadata is limited to Date
and Reference; revision/currency/validity data stays internal. Earlier commercial
tools, accepted snapshots, permissions and reference protection are retained.

Historical **[Version 8 backup, upgrade, rollback and operating guide](docs/version-8-upgrade.md)**
first and [verification results](docs/version-8-verification.md). Product Version 8
uses **database schema 7**. No IIS changes or new runtime packages are required.
Existing data stays in its configured external directory. No deployment is included.

## Commercial tools update

The latest update includes priced drafts in quoted amounts and uses quotation issue
dates for activity. It adds revision comparison, private per-revision costing/margin
with explicit selling-price application, and family-level Won/Lost tracking with
frozen accepted values. Verified never-sent drafts release their references after
the last Draft revision is deleted; sent/historical numbers remain protected.

Read [commercial tools upgrade and operating rules](docs/commercial-tools-upgrade.md)
for the prior schema-6 release, old Windows installation, old-reference review, costing access/math,
accepted snapshots and statistics rules. **No IIS changes are required.**

## V5 foundation

V5 adds compact permission-filtered quotation statistics, month/date filters,
monthly charts and a transactional shared CIR/custom reference registry. Import
historical references before using the suggested next sequence. Issued references
remain protected; reservations expire after 30 minutes. Blank and company-default
customer summaries omit discount text, old contract/yearly/tax summary lines and
the identified VAT disclaimer. Existing pricing inputs/records are preserved.
Navigation now emphasizes quotations, projects, catalogs, hosting and administration.

Historical [V5 upgrade and operating rules](docs/v5-upgrade.md) superseded
older UI/summary/default-discount instructions. It explains statistic eligibility,
revision grouping, timezone boundaries, reference renewal and backup migration.

## Install or upgrade on Windows

Requires 64-bit Python 3.11+ with its `py` launcher and a current Edge/Chrome/Firefox.
For an existing installation, **stop the app and back up from the old code folder
first**, keeping the existing data-directory configuration:

```bat
.venv\Scripts\python scripts\backup.py backup C:\Backups\cirrus-before-team-upgrade.zip
```

Download the latest branch ZIP into a **new** application folder (or fetch/switch
that branch in a clean clone). Do not overwrite the data directory. From the new
folder, run:

```bat
setup.bat
start.bat
```

For a **fresh installation only**, run `.venv\Scripts\python manage.py init-admin`
while stopped, before starting the app. The console prompts for the first administrator's individual username and password
(12+ characters). There are **no default passwords or public registration**. Stop
the app before running the console setup. First setup assigns all existing records
to that account privately, detects Personal/Gym notes, and retains records/files/
revisions. Open **http://localhost:8000**, then sign in. On later starts, just run
`start.bat`; do not create another initial administrator.

Use a named person's administrator account, not a shared password. Accounts →
Create account adds colleagues; roles and sharing are described below. Network
access stays **disabled** until deliberately configured.

## Data location and the rename

`CIRRUS_DATA_DIR` sets the dedicated data directory outside application source.
Legacy `JOSEPH_DATA_DIR` is still accepted. If both are set, they must point to the
same location. Keep an existing value unchanged during upgrade. By default, the
app reuses `%LOCALAPPDATA%\JosephWorkspace` if its database exists; otherwise a new
installation uses `%LOCALAPPDATA%\CirrusWorkplace`. Linux uses the equivalent under
home. The application name changes without moving or hiding existing data.

**Write down the current data path before switching Windows/service accounts**;
their LocalAppData folders differ. Configure an explicit path when using a service
account. `config.example.bat` shows a non-secret example. Data contains SQLite,
attachments, staged imports and administrator backup archives. Protect it with
NTFS permissions; never put it under an IIS-served folder or Git checkout.

Database schema 11 upgrades versions 1–10 transactionally. Workspace JSON remains
backwards compatible with formats 1–3. The legacy JSON format identifier remains
`joseph-workspace` for interoperability; the visible application is Cirrus Workplace.
No live customer database or uploaded reference workbook is stored in this repo.

## Accounts, roles and sharing

- **Administrator:** manages accounts, shared catalog/VM library, company settings,
  explicit catalog replacement, company template, backups and all work records.
- **Editor:** creates work/personal records and edits owned or edit-assigned work.
- **Viewer:** reads owned or explicitly shared/project-inherited work, without editing.

Work records are owner-private by default (other administrators can manage work).
Sharing / assignment on a project/quotation grants named Read or Edit access.
Project access is inherited by linked work notes/quotations; it does not expose
Personal notes. Sharing a quotation alone does not grant its project. New revisions
inherit their source's owner, project and direct grants; duplicate copies belong
to the actor and must satisfy project-link permission rules.

V5 retires Inbox/Knowledge/Personal browsing and note-creation interfaces. Existing
notes/attachments remain stored and available through authorized direct record
views and exports. Personal/Gym records retain owner-only protection against other
users and ordinary administrator browsing. Server/database/password-reset admins
remain trusted powers; this is not an encrypted personal vault.

Passwords use salted scrypt hashing. Sessions require an enabled account, expire
after 30 minutes idle / 8 hours absolute and at server restart, and are revoked on
password/access changes. HTTPS mode sets Secure cookies; HttpOnly/SameSite and
CSRF protection apply throughout. Login is throttled after repeated failures.

## Quotations, catalog and VM library

Create new quotation copies the administrator-editable **company template** with
neutral quantities and unpriced services: Production/DR compute, storage, security,
backup and support; Monitoring; SIEM/SOC and distinct VPN user/node lines;
Connectivity and one-time setup. A **blank quotation** option is available.

The full-window split studio preserves the latest compact layout, direct cell
editing, row/category copy/add/remove controls, blue group bands, live Decimal
calculations, VM selection and customer print/PDF/Excel/CSV output. Changes are
snapshots per quote. Saving a quotation never changes the company template.

Administrator Settings → **Replace service catalog once** performs the explicitly
authorized replacement after creating a full-instance SQLite/attachment backup.
It installs sanitized, stable `CIR-` mappings, without source customer data/prices;
old quote snapshots and VM profiles remain untouched. Repeating it does nothing.
Catalog attachments, if any, are archived into a reference note rather than deleted.
Replacement never runs silently at startup. Manage the resulting catalog normally.

Settings → **Company quotation template** accepts a design quotation or advanced
validated JSON. Review/remove customer-specific comments/prices before explicitly
saving. Header identities are excluded; new quotes get independent copies.

Customer cost summaries show category fees, final monthly fee and final one-time
fee. The old yearly/contract/tax/combined and discount summary lines, generated
discount wording and identified VAT disclaimer are suppressed. Saved historical
pricing calculations remain intact. New blank/company-template copies have no
initial temporary discount. Internal support percentages/bases/notes remain
protected; customer Excel stores protected support fees as fixed values.

VM selection generates technical CPU/RAM specifications, not OS/demo notices.
Only confirmed actual VM costs become selling prices; unconfirmed profiles leave
prices unpriced. Existing VM costs stay available internally for review. Manual
price overrides are allowed and saved. Old OS wording cannot be reliably separated
from manual text, so historical OS lines are retained for review rather than
silently deleted; new selections no longer generate them. Generated demo notices
are removed from customer projection and their unverified selling prices masked.

See [the quotation guide](docs/quotation-studio.md) and
[the VM/catalog guide](docs/hosting-vms.md) for established controls. The latest
[team operations guide](docs/team-operations.md) takes precedence where account,
privacy, pricing or template rules changed.

## Import and export

Quotations → **Import quotation from Excel** uploads a supported Cirrus `.xlsx`.
Choose worksheet, adjust column/header/category mapping, review source cells and
issues, and optionally use the normal visual quotation editor for the staged draft.
Unknown formulas/missing caches require explicit unpriced/edited/excluded decisions.
Subtotals never become charge rows; the app recomputes totals and flags omissions/
annual-period inconsistencies. Literal zeros stay zero unless the user explicitly
marks a redacted template and selects zero prices to convert.

Only explicit confirmation creates a private draft/new revision, in one transaction.
Imports detect repeated worksheet content and never overwrite an existing quote.
Staging is owned, expires in one hour, and the original is not made a public file.
This is **Cirrus-layout import with mapping**, not arbitrary Excel compatibility.
Files/macros/external links and expansion/cell/text counts have strict limits.

Import / Export provides permission-filtered staff JSON export and atomic additive
JSON import; notes/projects also export Markdown. Staff JSON can include internal
pricing: it is not a customer document. Shared catalog/settings/VM imports are
administrator-only. Full-instance backups include **all users'** data and are
separate administrator/OS operations. There is no automatic ChatGPT integration.

## Backup, restore and rollback

Stop the app. Run backup with the same configured data path; choose a fresh archive
filename. Backups include SQLite (accounts/ownership/template included) and files
with integrity hashes. Restore refuses an existing target:

```bat
.venv\Scripts\python scripts\backup.py backup C:\Backups\cirrus-workplace.zip
.venv\Scripts\python scripts\backup.py restore C:\Backups\cirrus-workplace.zip --target C:\CirrusRestored
set "JOSEPH_DATA_DIR="
set "CIRRUS_DATA_DIR=C:\CirrusRestored"
start.bat
```

Archives are private and limited to 5 GiB uncompressed restore in this version.
Test restore before relying on a backup. For rollback, restore the **pre-upgrade**
backup into a new directory and use the corresponding previous code. Never run
old code on a newer schema or overwrite the original data folder. First-admin setup
is needed only when a restored older database has no accounts. Passwords/ownership
are retained when restoring a schema-6 backup; sessions are intentionally invalidated.

## Internal access using IIS HTTPS

Default is localhost only. For colleagues, use
[Windows Server 2022 internal HTTPS setup](docs/windows-internal-https.md) and the
example configs under `deployment/`. Configure your actual internal DNS A record,
VM address, allowed hostname, certificate/trust, restricted Windows Firewall scope
and IIS HTTPS binding. IIS proxies to localhost Waitress; only that configured
local proxy is trusted for protocol/client-IP headers. Forwarded hosts are ignored.
Do not publish or port-forward this application to the internet.

The cloud task has **not** configured your VM, IIS, DNS, certificate or LAN access.
Windows batch/IIS steps can only be documented here and require your verification.

## Development and checks

Python 3.11+, `pip install -r requirements.txt`, then use a data path outside the
checkout. `python manage.py init-admin` creates your local initial account; run
`python run.py` with no debug server. Core modules separate store, identity/access,
company templates/catalog, quotation math, Excel reader/routes and customer export.

```sh
python -m unittest discover -s tests -v
# Optional developer browser tools, not required for normal use:
python -m pip install playwright==1.56.0
python -m playwright install chromium
python tests/browser_smoke.py
python tests/quotation_browser.py
python tests/hosting_browser.py
python tests/team_browser.py
python tests/v5_browser.py
python tests/commercial_browser.py
# Optional independent recalculation check, requires LibreOffice:
python tests/excel_recalculation.py
```

Tests use temporary databases and explicit synthetic accounts/prices, never live
company credentials or customer files. Legacy calculation/storage tests isolate
identity via an explicit test-only switch; security and team workflows exercise
real login/roles/authorization with the switch disabled. No environment setting
can enable that test bypass. See [verification](docs/verification.md) for evidence
and remaining limitations. There is no SSO/MFA, rich-text/drawing editor, arbitrary
spreadsheet engine or multi-user concurrent-editor conflict UI in this release.
