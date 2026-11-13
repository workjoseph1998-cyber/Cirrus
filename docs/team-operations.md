# Cirrus Workplace team upgrade: operator guide

Latest behavior: [commercial tools update](commercial-tools-upgrade.md) supersedes earlier draft-value, date-basis, reference-deletion and outcome rules; schema is now 6.

V5 overrides: see [V5 upgrade and operating rules](v5-upgrade.md) for schema 5, references, statistics, retired navigation and quotation output cleanup.

This guide supersedes older single-user/VM demo-pricing instructions. It describes
code/configuration to install on your Windows Server 2022; it does not claim the VM
or internal network has already been updated.

## Upgrade and first administrator

1. In the existing app, record the data directory shown under Settings / Backup.
   Stop with Ctrl+C. From the **old code folder**, use its existing environment
   configuration and create a fresh full backup:

   ```bat
   .venv\Scripts\python scripts\backup.py backup C:\Backups\cirrus-before-team-upgrade.zip
   ```

2. Download `feature/cirrus-workplace-team-upgrade` into a **new code folder**.
   Retain the previous code/backup for rollback. Do not move/delete data.
3. Keep the same data-directory value. CIRRUS_DATA_DIR is the new name;
   JOSEPH_DATA_DIR remains a supported alias. If both exist, their paths must match.
   A default existing JosephWorkspace database is detected and reused; a fresh
   installation defaults to CirrusWorkplace. Set an explicit path before changing
   Windows/service accounts. Do not point to a new empty directory accidentally.
4. Run `setup.bat`, then (while server stopped):

   ```bat
   .venv\Scripts\python manage.py init-admin
   ```

   Enter a named person's individual administrator username and a strong password
   (12–256 characters). No password is passed on the command line or printed.
   Migration preserves records, revisions and files; existing records are assigned
   to this initial account privately. Existing Personal/Gym notes are marked private.
5. Run `start.bat`, open http://localhost:8000 and log in. Check old notes, files,
   projects and quotes. New sessions expire at restart. Create a second named
   administrator where your operational policy requires recovery, without sharing
   passwords. Administrators can reset other accounts via Accounts.
6. Make a post-upgrade backup. For rollback stop the app, restore the **pre-upgrade**
   archive to a new path, and use the old code with that path. Do not downgrade the
   schema-4 database in place. A restored schema-4 backup retains accounts/ownership;
   an older backup needs initial administrator setup again.

## Accounts and access assignment

Accounts creates Administrator / Editor / Viewer accounts. There is no public
registration or email password reset. Administrator resets/role changes/disabling
revoke active sessions. Login throttling applies after eight failed attempts per
client address within 15 minutes. A valid login does not clear another username's
failures on that address. Sessions expire after 30 minutes idle and 8 hours absolute.
HTTPS deployment sets Secure cookies, with HttpOnly/SameSite=Strict and CSRF.

Administrators manage work records, company catalog, VM library, company settings,
templates, replacement and backup operations. Editors create work records and edit
owned/edit-assigned work. Viewers read owned/shared work and cannot mutate it.
Company catalog and VM library are readable to authenticated users; maintenance is
administrator-only initially. Category maintenance is also administrator-only.

Open a project or quotation → Sharing / assignment. Only the owner or an admin
manages its direct grants. Select named Read or Edit grants. Administrators can
transfer ownership of work records; editors cannot steal ownership by posting IDs.
A Viewer with an Edit grant still cannot write because the role is read-only.

Project grants inherit to linked work notes/quotations. Quotation-only grants do
not expose the private parent project. An assigned editor can update/revise that
quote while keeping its existing project reference; only an owner/admin can move
an existing record to a different project. Creating a new linked record requires
project edit access. A revision inherits source owner, project and named grants;
a duplicate is a separate actor-owned copy and must pass link permissions.
Grant revocation does not remove a user's ownership of records they created.

Personal notes are owner-only regardless of work grants or administrator role.
Choose Visibility=Personal, or use Personal/Gym categories. Privacy is sticky when
notes move out of those categories. Personal records cannot be shared/transferred
through the work-access screen. Ordinary administrator browsing/search/user exports
exclude another owner's Personal records. Server/DB administrators and password-
reset administrators are trusted powers: files are not encrypted per user, and
resetting a password can permit account takeover. Use separate individual logins,
restrict NTFS access and protect backup files accordingly.

## Catalog replacement: explicit and once only

After taking your offline backup, Settings → Replace service catalog once lists
the sanitized mappings. Type REPLACE CATALOG and confirm. The operation first
creates an administrator-only full-instance safety ZIP under data/backups, using
a write barrier to snapshot SQLite and referenced attachments consistently.

It removes current catalog records and installs stable, unpriced CIR- codes for
compute/storage, DC/perimeter firewall, load balancing, WAF, EDR, backup/storage,
support, NOC, SIEM collector/ABS, SOC per EPS, separate VPN per user/node, Internet
and one-time setup. These are reference starters, not a complete company inventory
or real vendor SKUs/prices. Existing quotation values are snapshots and do not
change. VM profiles are separate and retained. Catalog attachments, if present,
are moved into an archived reference note with read grants to current users.
Repeated replacement does nothing; later catalog edits are not silently reset.
Do not delete the operation marker to rerun a destructive reset.

## Company default quotation

Create new quotation loads the saved company template, or sanitized standard
structure before the first save. Production and DR both include generic VM/storage,
security, backup and 8×5 support. DR also includes the reference VPN line. NOC is
per IP; SIEM collector/ABS and SOC per EPS are distinct; VPN user/node lines remain
separate; setup is one-time. SOC capacity is an editable quantity, not a hardcoded
500-EPS entitlement. Initial quantities are zero drafts and prices blank.

To edit the reusable template, design a normal quotation (use a clearly labeled
template-design customer/header), then Settings → Company quotation template →
select its structure → Save as company template. Alternatively edit validated JSON.
This is an explicit admin action separate from saving the design quotation.
Header customer/contact/reference/date are not copied. Review comments, technical
names, prices and terms for customer-specific details before saving the structure.
New quotations get deep copies; later changes do not rewrite old quotes. Blank
quotation is available from Quotations or via `/quotes/new?blank=1`.

Monthly discount and Discounted monthly total are suppressed by stable keys in
customer preview/print/PDF/Excel even if an old saved document marks them visible.
The math remains active, including mixed discounted/regular months. Hidden Excel
summary dependencies support totals; they are not protected pricing secrets.

Protected percentage fees (support always, other percentage rows internal by
default) show only description and final charge. No support rate, eligibility or
internal notes are emitted into customer HTML/CSV/XLSX. Customer Excel freezes those
fees as literal values and has no support formulas or hidden rate/basis cells.
It can recalculate public inputs/tax/discounts, but changing service quantities in
that customer workbook does **not** reprice protected support; change quantities
in the app and re-export. Non-support percentage rows can be explicitly made public
in internal controls; tax and discount settings retain their independent wording.

## VM selection changes

New selection writes technical CPU/RAM specifications only; OS selection is an
internal pricing/licensing choice, not generated customer wording. Unconfirmed
profile costs remain in the internal library for review but are not copied as
selling prices; a new library has no seeded prices. Confirm actual costs before
using them, or have an authorized editor enter a price explicitly in the quote.
Existing exception prices remain snapshots until an explicit new selection/edit.

Generated demo notices are stripped from customer output. A legacy row still
marked with that notice is treated as unverified/unpriced unless an editor
explicitly enters/verifies its actual price. Stored historical numbers are not
silently erased. Old `OS:` lines cannot be reliably distinguished from manually
written OS text because the old version stored no provenance. They are conservatively
retained for review; remove unwanted historical generated lines in the normal
editor. New selections no longer generate OS/demo text and do not delete manual
OS wording. Verify old quotations before sending.

## Excel import

Use Quotations → Import quotation from Excel. Upload `.xlsx`; multiple worksheets
require explicit selection. Map the eight columns and header cells. Advanced
section_rows/group_rows maps row numbers to category/group names; skip_rows omits
known non-service rows. Unsupported layouts stay in the owned review area with an
error rather than being silently converted. This is a Cirrus-layout reader, not
an arbitrary spreadsheet engine.

Review detected rows, original source cells, merge handling and issues. The visual
quotation editor can correct the staged draft before returning to review. It does
not save a workspace quotation yet. Backups' merged service label remains Backup
as a Service; BkaaS stays in Type. Empty separator/repeated header/subtotal/summary
rows do not become charges. Source totals are not trusted as extra items.

Supported formula patterns are same-row quantity × unit price and SUM of a service
amount range × a literal percentage. They are translated into the application's
model without executing spreadsheet formulas. Unknown formulas are explicitly
unpriced until the user chooses Unpriced, enters valid pricing/method, excludes,
or removes the row. Missing caches never silently turn into zero. Hardcoded fee
versus per-unit wording, quantities, dated terms, subtotal omissions and annual
summary/discount-period inconsistencies are flagged for review. Recomputed app
values are authoritative after confirmation; cached Excel totals are not imported
as charges. Technical formulas outside those patterns need manual resolution.

Literal zero stays zero. For a redacted template explicitly enable the option and
select zero-price rows to make unpriced. No company/customer prices or identities
are promoted to the catalog/template automatically. Only an administrator's
separate explicit action can do so. Original uploads are not public attachments.

Confirmation atomically creates a private Draft. Duplicate detection hashes sheet
content/merges (not ZIP timestamps); intentional new drafts/revisions require an
acknowledgment. A revision inherits the selected source's audience/owner/project;
it never overwrites its predecessor. Another user's staging URL is inaccessible,
even to an ordinary admin. Jobs expire after an hour and are removed on later
upload/cancel/confirm; the database is not a forensic erasure mechanism.

Limits: 10 MiB file, 20 sheets, 5,000 rows/64 columns per sheet, 100,000 declared
cells, 2,000 merges / 100,000 expanded merged cells, 5 million expanded text characters, 100,000 characters per
cell, 3,000 ZIP entries, 50 MiB total expanded archive, 20 MiB per archive entry,
and compression ratio checks. Macros, macro sheets, embedded active content and
external workbook links are rejected; formulas/links/code are never executed.

## User exports versus full backups

Import / Export JSON is staff data filtered by server permissions, including
internal fields of permitted work. It excludes inaccessible records and cannot
be used to assign arbitrary owners/roles. Editors import new records as themselves;
shared company catalog/settings/VM imports remain admin-only. Full-instance ZIP
backups include all users' records, password hashes, ownership/shares, template,
VM library, staging data and attachments. They must be kept private with server-
admin NTFS permissions; ordinary browser users cannot download those archives.
Restores require a new directory and matching/newer code. A schema-4 restore
retains accounts; legacy schema backups migrate during first-admin setup.

## Network configuration and limits

Follow [Windows Server 2022 internal IIS HTTPS setup](windows-internal-https.md).
Decide your actual private VM address, internal FQDN, approved clients, DNS record
and trusted certificate before configuring. Localhost remains the default. The
app has not been installed on the VM by this cloud task; no LAN connectivity,
DNS/IIS binding or Windows certificate test is claimed.

No SSO/MFA/email invitations, full audit trail, end-to-end personal-data encryption,
arbitrary workbook support or interactive protected-support repricing inside
customer Excel is included. SQLite is appropriate for this small team; simultaneous
edits can overwrite earlier edits because there is no conflict-resolution UI yet.
