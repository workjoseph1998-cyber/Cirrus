# Version 21.1

- Restore compact quotation rows by moving Copy Link, Favorites, Internal Notes, Pre-send Check and validity information out of the table into Manage. Preserve all original columns, title editing, selection, approval indicators, tools drawer, density control and filters.
- Group Manage into General & exports, Workflow, History and Management. Expose existing approval reminders and family archive/restore actions through their existing authorized backend handlers. Permanent deletion continues through the existing archived-family review.
- Refine the existing left navigation with section labels, consistent active/hover/focus treatment and spacing. Preserve its server-saved account collapse preference, existing pages, mobile drawer and role-aware Quick Create.
- Group existing global search results by type, with clear empty states, icons, arrow-key traversal and Escape. Retain Ctrl+K / Command+K and existing backend permission checks.
- Add account-scoped optional column selection and reset, sort/page-size preferences, list-return query/scroll restoration and detail breadcrumbs. Keep essential title, selection and action columns visible.
- Improve bulk-selection feedback, confirmation before bulk changes, native-submit processing feedback, double-submit protection, inline native validation and automatic form focus. Extend existing unsaved-change protection to implicit text fields and record forms.
- Apply restrained blue-accent refinements through a separate stylesheet excluded from the quotation editor. Remove the listings' fixed vertical height, retain horizontal table scrolling where needed, and support desktop/laptop/tablet layouts in both themes.
- Add synthetic authorization/action tests, protected-source/filter manifests, browser UX checks and an independent baseline editor screenshot comparison.

No business modules, database schema, calculation formulas, export templates, Windows setup/start scripts, authentication or storage cleanup logic were changed. No production data or server was accessed.

See docs/V21.1-TEST-RESULTS.md for measured results and limitations.
