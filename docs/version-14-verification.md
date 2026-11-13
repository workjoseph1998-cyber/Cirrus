# Version 14 verification and remaining VM checks

All checks use temporary synthetic accounts, quotations and databases. The live VM
and business data were not accessed or changed. No real emails were sent.

## Development checks performed

- **206 automated tests passed**, including the existing quotation calculations,
  simplified summaries, explicit discounts, accounts/access, variable approvals,
  history, discussion, references, pricing/catalogs, exports, SMTP modes,
  persistent settings and full backup/restore regression suite.
- **11 v14 tests** cover administrator-only named confirmation, current-account and
  last-administrator checks, concurrent administration, revoked sessions, rejected
  re-enable/reset/re-registration and backup restoration of deleted identities.
  Original records, ownership, ACLs, comments and decisions remain unchanged;
  joins still resolve historical author/approver names. Sharing changes can retain
  a deleted owner rather than silently selecting another account.
- Support checks cover one service, multiple services, overlapping section/row/
  catalog-key selection, missing versus zero prices, percentage/quantity/price
  changes, exclusions and server-side self/cross-billing protection. Production
  $1,000 + Connectivity $100 at 5% produces $55, excluding Monitoring. The base and
  fee persist on save/reopen, duplicate and revision.
- Saved custom/default headings are checked in customer HTML, editor output,
  CSV and Excel. Dollars are display formatting; Excel numeric drivers/formulas
  and cached exact amounts remain numeric. Unpriced/zero distinctions, internal
  support privacy and the earlier removed wording are retained. Red/white styling
  covers normal and explicitly discounted monthly totals.
- A database created using the **actual v13 commit `0f8b29b`** was migrated twice.
  Every original column value in every original table remained identical, including
  support selections and all calculated totals, SMTP None settings, password
  hashes, approval decisions/messages and immutable PDF bytes. Attachment bytes
  were unchanged. Default headings did not invalidate its existing full approval;
  repeated migration was idempotent and foreign-key checks passed.
- Real **Waitress + Chromium** verification checks the support checkboxes with one,
  multiple and overlapping targets, changes percentage and inline quantity, saves
  and reopens, edits headings and verifies dollar output. It checks the entire red
  total row's computed background, white text and bold font, and generates an
  actual customer PDF from the rendered print document.
- Browser verification submits a real approval, records the staff decision/comment,
  deletes that account through its named confirmation screen, rejects its old
  session and verifies the author name/decision/message remain visible. It also
  checks that the signed-in administrator cannot delete itself.
- Changed screens were rendered and visually inspected in light/dark mode at
  **1550 px desktop** and **390 px mobile**. The support controls and account
  confirmation remain usable, customer paper stays white, and no JavaScript errors
  or page-level horizontal overflow were observed.
- The existing v13 real-browser workflow also passes against v14: New Document
  creation, draft selection without notifications, three/four approvers, mixed
  approval dots, resubmission, retained approved PDF, customer filters and SMTP None.
- Python compilation, all **18 JavaScript files**' syntax, dependency consistency
  and Git whitespace checks pass. A clean extracted deployment archive renders
  the main pages with product 14/schema 13 and loads the external deployment/data
  paths. Listed/unlisted host checks pass. The source ZIP contains no live database,
  accounts, attachments, virtual environment or environment-secret file.

Run the main checks in a development environment:

```sh
python -m unittest discover -s tests -v
python tests/v14_browser.py
python -m compileall -q workspace_app scripts run.py
```

The browser helper uses `/usr/bin/chromium` and writes development screenshots
under `/workspace/preservation`; it is not a Windows installation command.
SMTP is disabled during browser testing with `CIRRUS_DISABLE_EMAIL=1`.

## Windows / IIS / Waitress checks still required

These require your actual Windows server, service identity, network and disks and
were not performed in this Linux development environment:

1. Verify the pre-upgrade full backup. Extract into a new short path, run setup,
   keep the same external data path/account and verify existing users/records.
2. Confirm startup still reads your existing persistent deployment file and keeps
   administrator overrides, allowed hosts, bind/port, proxy, HTTPS and IIS rules.
3. Test deletion with disposable staff accounts and your team's actual ownership/
   sharing arrangement. Check attribution and replace any deleted pending approver
   deliberately. Keep an active administrator signed in.
4. Open representative historical support quotations and compare saved totals
   before any edits. Test a draft with Production + Connectivity at 5%, save/reopen,
   duplicate/revision and check exact base selection with your actual catalogs.
5. Verify default/custom headings, dollar amounts and the red/white monthly row in
   installed Edge/Chrome, Windows PDF capture/automatic customer-folder exports and
   Excel. Check protected approved files and actual local/UNC folder permissions.
6. Retain SMTP configuration and optionally perform an authorized real relay test;
   no transport or delivery settings are changed by v14. Verify current export/
   backup jobs, then download and test-restore a full backup into a new directory.

## Practical limits

Account deletion deliberately retains historical identity and business data. It is
not anonymization or a physical purge, and earlier backups remain unaffected.
Monthly support retains the existing billing-period validation; mixed sections use
explicit matching services. CSV cannot store visual styling. Retained approved PDF
evidence stays immutable even though current exports use the new display styling.
No production load benchmark, real relay test or Windows/IIS certification is
claimed. The existing deployment, archive limits and permissions remain in effect.
