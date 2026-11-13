> Historical feature guide: the current [team operations guide](team-operations.md)
> overrides single-user, demo-pricing and OS-generation instructions below.

# Cirrus Hosting VMs and compact quotations

## VM library

The sidebar's **Cirrus Hosting VMs** section contains the 33 profiles supplied by
the user: Small V1–V6, Medium V1–V7, Large V1–V8, Xlarge V1–V6, and Xxlarge V1–V6.
Core counts and RAM values match the supplied table, including fractional RAM and
Xlarge V4's 65 GB. The five unnamed 32-core entries were labeled Xxlarge V2–V6;
edit their names if your actual naming differs. RAM here is labeled **GB** as in
the source table; the app does not silently convert it to GiB.

Each size has **Linux** and **Microsoft Windows** monthly USD costs. Initial
numbers are deterministic pseudo-random **Demo** values, not actual Cirrus costs
or license prices. Replace them in the portal. Mark a profile **Confirmed** once
its costs are reviewed. A blank cost remains unpriced; zero is an explicit free
price. Both OS costs can be changed on the grouped table; Save visible VM prices
validates all submitted rows in one transaction. An invalid row saves nothing.

Edit specifications to rename a size, change family/cores/RAM, or delete it.
Add VM profile supports new sizes and custom families, which appear automatically
in the picker. Cores must be positive integers, RAM at least 0.001 GB, and costs
nonnegative. Names must be unique. Operating-system labels and the default picker
choice can be edited below the VM table. Linux is the initial default. Normal
restarts/upgrades do not overwrite edited prices or re-add deleted profiles.

## Use a size in a quotation

1. Add a quotation row, or use an existing compute row.
2. In the **Comments** cell, click **VM ▾** (Choose VM). The same picker is also
   available under row Options → Choose hosting VM in the left pane.
3. Choose **Linux** or **Microsoft Windows**, then Small, Medium, Large, Xlarge,
   Xxlarge or a custom family. Select the desired size.
4. The app fills these comment lines:

   ```text
   VM Size: Large V1
   VM Specs: 8 vCPU, 15 GB RAM
   OS: Microsoft Windows
   ```

   It replaces previous VM Size / VM Specs / OS lines and retains unrelated
   comments. It copies the selected OS's monthly cost into the editable Unit Price,
   explicitly uses monthly quantity × unit-price pricing, and sets the unit to VM.
   Existing quantity and included/excluded states are retained; zero-quantity drafts
   do not turn into charges. Existing service/sub-service/type values are retained (blank/new service/type
   values receive Cirrus Compute / IaaS defaults). Any existing line discount stays.
5. Adjust Unit Price for an exception if required. Save the quotation. Later VM
   library edits never change its saved specification or exception price. Choosing
   another VM/OS explicitly copies a new price; no continuous link overrides you.

The picker reloads current library costs when opened and remembers the row’s
recognized VM family and OS. This refresh does not alter a saved row until you
explicitly select a VM.

VM costs are USD. The picker refuses automatic use in a quotation with another
currency; enter a converted price manually if needed. No automatic conversion or
margin is applied: the selected cost becomes the unit price as requested.
Selecting a Demo profile adds `[DEMO PRICE — replace before sending]` to Comments.
Review its price and remove that warning only when appropriate, or confirm the
profile in the portal and select it again. Unconfirmed prices are never presented
as known market prices. The picker does not invent OS licensing entitlements.

## Catalog round-trip fix

Catalog items now store **Type, multiline Comments, pricing-model description,
unit/fixed method, fixed fee, billing period, default quantity and line discount**
in addition to existing fields. Saving from a quotation captures these values;
Copy catalog row restores them. Saved items are available immediately in the picker
without reloading the quotation. Catalog fields remain editable in Service Catalog.
Existing quotes keep their snapshots when catalog items change.

Earlier versions never stored Type/Comments, so there is no hidden copy to recover
from an old catalog entry. Fill those fields in the existing item's edit page, or
save the original quotation row under a new catalog code. The upgrade does not
try to infer VM specifications from unrelated customer quotations. Catalog codes
remain unique; quotation-specific percentage dependencies cannot be made portable
catalog defaults—use Copy row/category for those fees instead.

## Compact worksheet layout

Normal quotations now use compact cell padding, shorter title/category bands,
a smaller logo/header, and 9-point print/XLSX body text. Normal rows grow only for
their actual content. Copy/options/remove controls use small accessible icon
buttons; VM selection lives in Comments. Category tools appear on hover/focus,
and blank Scope is collapsed. Long editor textareas scroll after 180 pixels;
customer print/PDF retains the entire text. The Large text preference remains.
There is no forced one-page shrinking or clipping. Browser zoom/printer/font
settings may still affect your Windows output; preview a PDF before sending it.

## Upgrade without losing data

1. Stop the server with Ctrl+C. In the **old** application folder, keep the same
   JOSEPH_DATA_DIR setting (or leave it unset if you use the default), then run:

   ```bat
   .venv\Scripts\python scripts\backup.py backup C:\Backups\joseph-before-hosting-vms.zip
   ```

   Pick a new filename if it exists. Continue only after backup succeeds.
2. Download branch **feature/hosting-vms-and-compact-quotes** as a ZIP and extract
   into a new application folder, keeping the previous folder for rollback.
3. From the new folder, keep that same data-directory setting and run:

   ```bat
   setup.bat
   start.bat
   ```

4. Open http://localhost:8000. First startup transactionally upgrades the database
   to **version 3**, adds the VM library and initializes missing catalog fields.
   Notes, projects, quotations, attachments, IDs and timestamps are retained. The
   existing v1→v2 quotation migration still runs if required. Review the demo prices.
5. Verify old records and a sample quotation, then make a post-upgrade backup.

SQLite and attachment backups include the VM library automatically. To roll back,
stop the app, restore the **pre-upgrade** backup to a new directory, point the old
code to that copy and restart. Do not use old code against a version-3 database.
Windows batch execution remains unverified in the Linux development environment.

## Portable data

Workspace JSON now exports **version 3**, with a `hosting_vms` array alongside
records/settings. Formats 1 and 2 remain accepted; an old file leaves the VM library
untouched. Imports are additive and never delete missing entries. Identical VM
IDs skip. An incoming profile can replace an untouched starter Demo profile to
support transfer into a fresh installation. Conflicts with locally edited profiles
or duplicate names block the whole import. The preview reports VM additions/default
replacements before confirmation. Workspace exports/backups contain your private
costs; keep them outside Git. Customer PDFs/Excel/CSV contain only the selected
row's snapshotted price/specifications, never the entire VM cost library.
