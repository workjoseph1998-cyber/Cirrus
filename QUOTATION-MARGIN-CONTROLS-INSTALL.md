# Version 19 quotation margin-controls patch

Baseline: complete Cirrus Workplace Version 19, tag `v19.0.0`, commit
`c7e45aacdc25e72608d2c7c4ba8f19492afcd66e`.

This is an editor-shell layout patch. It does not change the quotation stylesheet,
column definitions, fonts, row sizing, calculations, catalog defaults, pricing,
approval rules, exports, login page, dependencies or database schema. No migration
or catalog initialization command is needed. After user testing and approval, it was published in Version 19 patch tag `v19.0.1`.

## Windows installation

1. Stop the running Cirrus Workplace/Waitress process or service using your normal
   method, after users finish editing.
2. Back up the current application folder. Retain your usual data backups as well.
   Record the existing service configuration and external data path; leave them
   unchanged.
3. Extract `Cirrus-Workplace-V19-Margin-Controls-Patch.zip` into the Version 19
   application root—the folder containing `run.py`, `manage.py` and `workspace_app`.
   Preserve relative paths and replace the supplied files.
4. Restart the existing Waitress process/service normally. Keep the same virtual
   environment, data directory, accounts, IIS/HTTPS configuration and SMTP settings.
5. Refresh the browser using Ctrl+F5 to load the new templates and static files.
   Sign in with an existing account. Do not run `init-admin` or any migration command.

The runtime changes are limited to:

- `workspace_app/templates/base.html`: an optional quotation navigation title slot.
- `workspace_app/templates/quotation_editor.html`: removes the separate heading,
  toolbar and introduction bands and includes the editor-only layout assets.
- `workspace_app/static/quotation_margin_layout.css`: editor shell and control styling.
- `workspace_app/static/quotation_margin_layout.js`: moves the existing live controls
  into the margins or responsive Controls dialog without recreating form state.

The ZIP also includes the browser acceptance test, the corresponding small update
to the existing Version 17 browser harness, and this installation guide. It contains
no database, customer data, credentials, virtual environment or screenshot files.

## Expected behavior and local checks

At wide desktop sizes, Save quotation and Approvers & submission are stacked in the
left sheet margin. Settings, sharing, exports and saved/unsaved status occupy the
right margin. They stay visible while the quotation scrolls inside its iframe.
The title sits in the top navigation bar, whose desktop height is reduced from
68 to 56 pixels. Search, theme, notifications and account controls remain available.

When both margins cannot fit the controls, a **Controls** button appears beside the
navigation title. It opens the same controls in a compact dialog. Close it with its
Close button or Escape. On phones the sheet retains its existing width and horizontal
scrolling; its scale is not reduced. Structure settings open as an overlay and can
be closed with **Close settings**. Closed panels take no quotation space.

After installing:

1. Compare a saved quotation with the pre-patch version: widths, text, rows and prices
   should be unchanged. Confirm the sheet starts much nearer the top of the window.
2. Edit a quantity without saving, open/close settings and options, and confirm the
   edit remains. Open/close Approvers & submission without submitting.
3. Save, reopen, then compare the editor, PDF and Excel values.
4. Scroll the quotation and check both margin groups stay visible without touching
   the sheet. Expand More and confirm its actions fit.
5. Resize the browser. Check Controls, the modal dialogs, theme/account controls and
   the mobile Quotation tab remain accessible without overlap or clipping.
6. Check a non-editor page and the login page retain their previous layout.

## Rollback

Stop Waitress. Restore the previous copies of the two modified templates from your
application backup, and remove the two new `quotation_margin_layout.css` and
`quotation_margin_layout.js` files. Restore the previous browser harness if desired;
the new browser test and this guide can be removed. Restart Waitress and press
Ctrl+F5. No data restore is required for this layout-only patch; preserve any legitimate
quotation edits made while testing.

## Validation evidence

A synthetic quotation was measured before and after at a **1908 × 960** browser
viewport (matching the reference image dimensions), device scale 1, with no browser
zoom or CSS scaling:

| Measurement | Before | After |
|---|---:|---:|
| Sheet width | 1360 px | 1360 px |
| Sheet top | 278.375 px | 79 px |
| Quotation viewport height | 679 px | 878 px |
| Fully visible service rows in the test fixture | 9 | 10 |

All nine measured table column widths matched exactly. The first twelve measured
row heights matched exactly. Body and editable-cell fonts remained
`11px / 13.2px Cambria, Georgia, serif`. The quotation stylesheet is byte-for-byte
unchanged from Version 19.

The dedicated real Waitress/Chromium test verifies the measurements, margin bounds,
scrolling, unsaved-state retention, settings/options/approval dialogs, saving and
reopening, actual PDF generation, cached Excel amounts, responsive Controls dialogs,
Escape, and unchanged non-editor navigation. Responsive checks include widths of
1536 and 390 pixels. The existing approval/report/PDF acceptance test also passed.

Run the dedicated check using `python tests/quotation_margin_layout_browser.py`
in the prepared cloud development environment. Set `CW_BROWSER_ARTIFACTS` to choose
an artifact directory. Before/after metric comparison runs when a previously captured
`baseline-metrics.json` exists there; functional checks run independently of it.
The harness uses temporary synthetic data and system Chromium at `/usr/bin/chromium`.

Windows/IIS deployment and real company data were not available for validation.
No production service, customer record, live email or GitHub ref was changed.

Final results: all **272 unit tests passed**. The dedicated layout acceptance and
existing approval/report browser acceptance both passed. Saving from the responsive
Controls dialog and expanded More-menu bounds were also verified. JavaScript syntax,
Python compilation and Git whitespace checks passed. The original `v19.0.0` baseline remains unchanged; the user subsequently approved
publication of this update as `v19.0.1`.
