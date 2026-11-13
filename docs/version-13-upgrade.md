# Cirrus Workplace Version 13 — upgrade guide

Built on the complete Version 12 codebase (`15323ec`). Branch:
`feature/cirrus-workplace-v13`. Product **13** uses SQLite schema **12**.

Download while signed into the private repository:
https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/feature/cirrus-workplace-v13.zip

## Windows / IIS / Waitress upgrade

1. From the current application, use the administrator **Download full backup**
   action. Record the actual data directory shown in Settings, Windows service
   identity, environment variables, source folder and IIS configuration. Back up
   external customer PDF folders and service configuration separately. Keep this
   pre-upgrade backup for rollback.
2. Stop the existing Python/Waitress process or service. Extract v13 into a new,
   short path such as `C:\CirrusV13`. Do not overwrite the live data directory or
   copy an old `.venv`. Run `setup.bat`. Runtime requirements have not changed.
3. Preserve the same external `CIRRUS_DATA_DIR` (or legacy `JOSEPH_DATA_DIR`),
   service account, bind/port, allowed hosts, proxy, HTTPS and timezone settings.
   If both data variables are present they must identify the same directory.
   Without an explicit variable, the existing account's
   `%LOCALAPPDATA%\JosephWorkspace` database is reused if present; otherwise the
   default is `%LOCALAPPDATA%\CirrusWorkplace`. Do not guess a new data path.
4. Configure the persistent file below. Keep any existing service/environment
   overrides. Point the existing service at the new source and virtual environment,
   or run `start.bat` using the established account/environment. IIS still forwards
   to the existing Waitress bind/port; retain host preservation and proxy settings.
   **Do not run `init-admin` during an upgrade.**
5. Startup migrates the existing database transactionally to schema 12. It adds
   ordered quotation approver selections, preparation selections and phase/order
   fields on review assignments. Existing rounds, immutable decisions, PDFs,
   discussion, SMTP settings, users, records, catalogs, references and attachments
   remain. Existing quotations inherit their latest round's approvers; quotations
   without a round snapshot the configured defaults without starting a review.
6. Verify existing accounts and business records, a draft save, a complete review,
   exports and a new backup before normal team use. Follow the Windows checklist
   in [verification](version-13-verification.md).

No automatic live deployment is performed. To roll back, stop v13, restore the
**pre-upgrade** full backup into a new external directory with the matching v12
code, and restore the old service configuration. Do not run v12 against schema 12.
Changes made after the pre-upgrade backup need separate reconciliation.

## Persistent allowed hosts and deployment settings

`start.bat`, direct `run.py` and application startup automatically load:

```text
%ProgramData%\CirrusWorkplace\deployment.json
```

On the usual Windows installation this is
`C:\ProgramData\CirrusWorkplace\deployment.json`. It is outside `C:\CirrusV13`
and survives replacing the application folder. If absent, startup creates:

```json
{
  "CIRRUS_ALLOWED_HOSTS": "localhost,127.0.0.1,172.18.69.10"
}
```

This has the same effect as:

```bat
set "CIRRUS_ALLOWED_HOSTS=localhost,127.0.0.1,172.18.69.10"
```

An administrator can create the directory/file once using
`deployment\deployment.example.json`, then grant the Windows account running
Workplace **Read** on the file and folder traversal. Automatic first creation
requires write access to that configuration directory. Keep editing restricted to
administrators. A malformed or unreadable file produces a clear startup error;
it is never replaced by defaults. Restart Workplace after changing it.

**Inherited environment variables take precedence over file values.** Existing
administrator/service host overrides are respected, including ones that omit the
example IP. Edit/remove an inherited override if you intend to use the file instead.
Startup does not rewrite an existing file or save transient overrides into it.

For a different persistent location, set an absolute external path in the service
environment before startup:

```bat
set "CIRRUS_DEPLOYMENT_FILE=D:\CirrusConfig\deployment.json"
```

The file accepts these single-line string keys only:
`CIRRUS_ALLOWED_HOSTS`, `CIRRUS_BIND`, `CIRRUS_PORT`, `CIRRUS_INTERNAL_ACCESS`,
`CIRRUS_HTTPS`, `CIRRUS_TRUSTED_PROXY`, `CIRRUS_ALLOW_HTTP_LAN`, `CIRRUS_DATA_DIR`,
`JOSEPH_DATA_DIR`, `CIRRUS_TIMEZONE`, `CIRRUS_PDF_BROWSER`, `CIRRUS_DISABLE_EMAIL`.
Copy your **actual existing** values if moving them from an old launcher; no bind,
port, data location or proxy value is invented. Paths in JSON need doubled
backslashes, for example `"D:\\CirrusData"`. No commands are executed from the file.

Allowed hosts validate incoming Host headers. They do not open a listener or change
IIS/firewall rules. The default Waitress binding remains `127.0.0.1:8000`; retain
your existing override if different. Keep the existing IIS → Waitress deployment.
SMTP passwords stay in the service's secret environment, **not** this file.

Full application backups include SQLite settings and attachments, but do not
include this external deployment file, IIS/service configuration, environment
secrets or external customer PDF disks. Back those up separately.

## SMTP modes

Open **Administration → Approvers & email**. Available security modes are:

| Mode | Connection |
| --- | --- |
| STARTTLS | Ordinary SMTP connection, then STARTTLS with certificate validation |
| TLS / SSL | SMTP over TLS from connection start, with certificate validation |
| None (no TLS) | Ordinary SMTP; no STARTTLS, SSL connection or TLS context |

All modes use the saved hostname/IP and port. No relay address or port is hardcoded.
A blank username skips SMTP authentication, allowing an IP-authorized relay. With
a username, the normal configured password environment variable is used. None
provides no transport encryption; select it deliberately for your relay.

STARTTLS remains the default for new configurations. Upgrades do not rewrite saved
SMTP configurations. Portal notifications work when email is disabled or fails;
delivery failures retain the administrator Retry action. The explicit portal base
URL and sign-in/authorization rules are unchanged. Internal links still require
network/VPN access. No real emails were sent in development.

## Selecting approvers and submitting

- **New Document → Quotation** shows an Approvers panel beside the form. Add/remove
  active Editor/Administrator accounts and reorder the selection. Duplicates are
  blocked in the interface and validated on the server. Defaults are preselected
  once and can be edited; changing defaults does not rewrite saved selections.
- Choose any number (up to 100) for a draft. Submission requires at least one.
  Continue carries the selection into the editor using an account-bound preparation.
  **Save quotation** stores a draft selection without assigning review tasks or
  sending review notifications. **Save & submit for approval** saves the exact
  version and starts its review in the same database transaction.
- The existing stage model remains optional per approver. All selected Operations
  approvers act independently in parallel. Commercial approvers become actionable
  after every selected Operations approval. Commercial-only and Operations-only
  selections work too. **Every selected approver** must approve for Approved by all.
- The editor's **Approvers & submission** and the approval page allow managing the
  selection. Changing people, order or stages after submission records an audit
  event and supersedes the current round. Existing decisions/PDFs remain in history;
  current dots turn white and show **Resubmission required**. New selected staff do
  not get assignments until an explicit resubmission.
- Content edits retain the existing v12 version-bound reapproval behavior. Changed
  current content cannot reuse prior green dots; unchanged saves/discussion/read
  state do not reset approvals. Stale decisions and stale selection saves are
  rejected. Changes-requested/declined rounds require deliberate resubmission.
- Review assignments grant quotation-only editing/review access. They do not
  expose unrelated customers, quotations or private margins. Historical participant
  discussion grants remain until explicitly revoked, as in v12. Only current
  participants receive the new round's workflow assignment/completion notifications.

## Approval indicators, filtering and customer statistics

The Quotations table now shows **Approvals**. The same summary is used in Dashboard
pending/submitted work, customer quotation lists, Approvals and quotation panels.
Every selected approver has a dot in saved order: **green** means approved and
**bordered white** means not approved. Text shows `2 out of 3 approved`. Hover or
keyboard focus reveals the name, decision status and decision time where present;
the summary opens the approval page. Declines/changes appear separately as text,
not another dot color. Never-submitted quotations show **Not submitted**. Previous
rounds never provide approval credit for changed content or selections.

In Quotations, use **Find customer** to search the dedicated **Customer** dropdown,
then Apply filters. All customers is the default. Customer combines with title/
reference search, date, owner, type, business status and visibility. Pagination and
bulk matching use the same filters. Stable customer IDs distinguish equal names;
unlinked legacy customer text is explicitly labeled as legacy. A quote-only staff
member can filter customer names on accessible quotations without gaining profile
access.

Customers has separate **Quotation count** and **Quotation value (USD)** columns.
Existing permissions and calculation rules remain: the latest valid revision per
family, the existing listing reporting period (current month), USD eligibility and
unpriced/canceled handling. These are quotation amounts, not payments or revenue.

## Main changes

- `deployment_settings.py`, `scripts/start_workplace.py`, `start.bat`, startup/network
  integration and the example deployment file: persistent nonsecret settings.
- `approvals.py`, `approval_routes.py`, `store.py`, quotation/document routes:
  additive migration, ordered selections, variable stages/counts, version safety,
  current participants and draft preparation.
- `notifications.py` and workflow settings: configurable SMTP transport and defaults.
- Shared indicator/selector templates and scripts, quotation/customer/dashboard/
  approval templates and portal styles: consistent dots, Approvers UI, customer
  filtering and separate statistics columns.
- Backup/handover/version identifiers, tests, README and release guides.

Existing quotation calculations, customer pricing, manual/automatic exports,
immutable approved evidence, reference rules, backups and retired consumption
handover remain. The Cirrus Hosting VMs page is unchanged.
