# Structured workspace import: versions 1, 2 and 3

Latest behavior: [commercial tools update](commercial-tools-upgrade.md) supersedes earlier draft-value, date-basis, reference-deletion and outcome rules; schema is now 6.

V5 overrides: see [V5 upgrade and operating rules](v5-upgrade.md) for schema 5, references, statistics, retired navigation and quotation output cleanup.

Encoding: UTF-8 JSON. Top-level object must contain exactly:

```json
{
  "format": "joseph-workspace",
  "version": 3,
  "records": [],
  "hosting_vms": [],
  "settings": {"company": "CIRRUS SAL", "payment_terms": "", "delivery_terms": ""}
}
```

Each record contains exactly `id` (UUID string), `kind`, `data` (object),
`created` and `updated` (ISO-8601 timestamps, UTC with offset recommended).
Kinds: `note`, `project`, `catalog`, `quote`, `category`.
Field definitions are centralized in `workspace_app/model.py:FIELDS`; keys not
listed there are rejected, except quote `number`, `revision`, `lines`, and the v2 `document` object.
All ordinary field values are strings; optional text defaults to `""`.

Required fields:

| Kind | Required |
| --- | --- |
| note | title, type, status |
| project | name, customer, status |
| catalog | code, name, unit, currency, status |
| quote | title, customer, date, currency, status, tax, number, revision, lines |
| category | name |

Use exact enum values from `NOTE_TYPES` / `STATUSES` in model.py. Dates are
`YYYY-MM-DD`. Numeric catalog fields and quote tax/line values are decimal strings;
optional cost/price is `""`, not zero or null. Currency is three letters.
Quote references are 1–80 printable characters; revision is an integer 1–1,000,000.
Automatic references use `Q-` plus 12 hexadecimal characters. Lines are objects with `description`, `unit`,
`quantity`, `price`, `cost`, and `discount`. No precomputed totals are imported.

`project_id`, `category`, `subcategory` and category `parent` reference record
UUIDs, not display names. Targets must already exist or be included in the same
file. A subcategory must belong to the specified top-level category. Categories
support two levels. `tags` is comma-separated text. Notes use `source_url`;
projects use newline-separated `references`; URLs must be HTTP(S).

See `examples/chatgpt-import.json` for a complete note and
`examples/starter-catalog.json` for categories, a subcategory, and catalog entries.
Use a fresh UUID for each new record and avoid customer details in files committed
to Git. The UI previews before confirmation; saving validates everything again
inside one write transaction. Identical IDs skip; conflicting IDs reject the
whole import. Natural catalog-code and quote-number/revision collisions also
reject. A failure leaves no partial records. Exports omit attachment metadata and
file bytes; use a full backup to move attachments. Local settings win over imports.


## Structured quotations in format 2

Other record kinds are unchanged. Quote `data.document` has `version: 2`, ordered
`sections`, `contract_months`, `discount`, `tax`, `columns`, `summary`,
`summary_title`, `branding`, `company_signature`, `customer_signature`, `format`,
`banner`, `project_name`, `terms`, and `bottom_order`. Legacy `lines` may remain for preservation,
but the document is authoritative for structured pricing and customer output.
See the complete validation in `workspace_app/quotation.py:validate_document` and
[quotation calculations/limits](quotation-studio.md). Export a quote from the app
for a current example of the complete nested format.

A section has `id`, `name`, `parent`, `hidden`, `excluded`, `rows`. Parent is an
empty string or a top-level section ID. A row has `id`, `service`, `sub_service`,
`type`, `quantity`, `unit`, `pricing_model`, `unit_price`, `fixed_fee`, `percent`,
`method` (unit/fixed/percent), `billing` (monthly/one_time), `state`
(priced/excluded/included), `discount`, `targets`, `comments`, and optional-price
`cost` (key required, empty string allowed). All numeric drivers are strings;
durations and quote revision are integers. Document IDs use letters/digits/underscore/
hyphen and must be unique across sections, rows and terms. Targets are `s:<id>`
or `r:<id>`; overlaps deduplicate, broken references and cycles reject the batch.

Tax has `mode` (exclusive/added/included), `rate` and `wording` (blank generates it).
Discount has `percent`, `months`, `enabled`, `targets`, `wording`. Branding embeds
an optional PNG/JPEG data URI in `logo`; quote logo bytes travel with structured
exports. Normal attachments remain outside JSON. Terms contain `id`, `title`,
`text`, `visible`; bottom_order lists selected term IDs and the reserved blocks
`company_signature`, `customer_signature`, `footer` in output order.

The app exports format 3 and accepts formats 1, 2 and 3. Version-1 quotations are
adapted to deterministic structure before preview/ID comparison, retaining old
line data and mapping legacy amounts to one-time billing with added tax. They do
not reset the workspace. Imports remain additive, atomic and conflict rejecting;
quotes with an incompatible structure never partially save. Exports include
internal data and must be kept private; customer outputs use a separate projection.


## VM library and catalog additions in format 3

Top-level `hosting_vms` is required in version 3. It is a list of objects with
exactly `id` (UUID) and `data`. VM data contains string fields `name`, `family`,
`vcpu`, `ram_gb`, `cost_a` (Linux), `cost_b` (Microsoft Windows), and `price_status`
(Demo/Confirmed). Costs can be empty or nonnegative decimal strings, rounded to
cents; RAM is GB. The VM library permits up to 2,000 profiles. Its import is
validated in the same transaction as workspace records; conflicts with locally
edited IDs reject the batch. Untouched starter profiles can be updated by import.
The preview reports those updates. Missing profiles are not deleted.

VM settings add `hosting_cost_a_label`, `hosting_cost_b_label` and
`hosting_default_basis` (a/b). Old settings/imports remain accepted. Catalog data
adds optional-default string fields `type`, `comments`, `pricing_model`, `billing`
(monthly/one_time), `method` (unit/fixed), `fixed_fee`, `quantity`, and `discount`.
Old catalog entries are normalized additively before duplicate comparison.
Quotation document structure remains version 2: VM selection saves explicit
comment text and editable price snapshots, so it does not require a live profile
reference. No external calls or quotation price rewrites occur on library edits.


## Team access in Cirrus Workplace

The JSON format name and version remain unchanged for backward compatibility;
they do not control the application name. SQLite schema version 4 is separate
from JSON export version 3. Exports contain only records the signed-in user can
read. Ownership, passwords and sharing grants are not transferred by JSON. New
records belong to the importing user; existing hidden IDs and conflicting values
are rejected. Viewers cannot import. Only administrators can import company
catalog/categories, VM profiles or global settings. Other users export an empty
settings object and VM list, and can import their own work records.

Notes have an optional `visibility` string (`Work` or `Personal`); Personal/Gym
category ancestry also makes a note private. Privacy remains sticky after a
category is renamed or a private note is moved; do not use JSON as a way to
downgrade another user's privacy. Existing private records remain private.

Quotation rows accept optional booleans `unverified_price` and
`customer_percentage`, both false by default. An unverified selling price is not
a confirmed charge. Percentage rows are internal by default; the editor can mark
a non-support percentage explicitly customer-facing. Support rates and their
bases always remain internal. Customer downloads use the sanitized projection;
staff JSON contains internal pricing and must be kept private.

Full administrator backups, unlike these filtered exports, include accounts,
sharing, the company template, imported drafts and every user's attachments.
See [team operations](team-operations.md).
