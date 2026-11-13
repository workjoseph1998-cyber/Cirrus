# Cirrus Workplace 21.2 — Midnight Azure

Based on V21.1 commit `fe6957247234b0e58b21dff4b25cbddd4a36ea82`.

## Shared application shell

- Replace the non-editor sidebar with a dedicated reusable navigation component: navy surfaces, Cirrus branding, consistent SVG line icons, expandable Quotations / Projects & operations / Administration groups, active-page treatment and account-persisted collapse state.
- Preserve all existing destinations, role checks and mobile drawer behavior. Expanding a navigation group in icon mode expands the account-aware sidebar and opens the selected group.
- Move the desktop sidebar toggle into the top bar. Refine the existing search, Quick Create, notification indicator, theme selector and profile menu; add a username-initial avatar. Keep the same existing element IDs and backend handlers.
- Introduce reusable SVG icons and a Midnight Azure system of semantic colors, typography, spacing, 14px cards, 8px controls, subtle borders/shadows, focus states and reduced-motion interactions.
- Apply the system across dashboard, customer workspaces and documents, projects, catalog, reports, approvals, notifications, account administration, forms, dialogs and settings.

## Page presentation

- Compose page headers from the existing title and description, with a relevant icon and breadcrumbs where helpful. Preserve the original customer identity header and its authorized actions.
- Redesign existing dashboard KPIs and activity/approval panels without changing the metrics, business calculations or access scope.
- Add a quotation summary strip using existing permission-scoped document counts, the current user's pending approvals, filtered sent quotation counts and saved favorites. No demonstration values or growth rates are hardcoded.
- Restyle the quotation filter panel while retaining its exact form markup and existing handlers. Refine compact rows, separators, hover treatment, table headers, Manage links, column/density controls, bulk actions and pagination.
- Preserve Manage as the existing grouped management panel: General & exports, Workflow, History and Management. Keep Copy Link, Favorites, Notes, Pre-send Check, approval reminders, comparison/export and authorized archive/restore/deletion workflows.
- Refine account headers/tabs, report monthly/one-time fee cards, export controls, administrative fieldsets, notification menus and approval surfaces through the shared system.
- Provide a coordinated navy dark palette and quieter dark-mode header treatment, rather than inverting white surfaces. Preserve Light / Dark / System preference behavior.

## Protection and verification

- Do not load the premium styles/scripts or shell on either saved/new quotation editors or Excel import staging editors. Preserve their V21.1 appearance and behavior.
- No business modules, database migrations, dependency upgrades, pricing, reports, export content, authentication, account security, SMTP behavior, backups, storage cleanup or Windows launch scripts changed.
- Add real-data/permissions/editor-isolation tests and a cross-page screenshot/browser suite. Record V21.1 before and V21.2 after screenshots using the same synthetic scenario.

See `docs/V21.2-UI-REVIEW.md`, `docs/V21.2-TEST-RESULTS.md` and `VERSION-21.2-INSTALL.md` for evidence, deviations, limitations and rollback.
