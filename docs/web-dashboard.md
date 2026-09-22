# Web Dashboard

B2M uses a server-rendered Tabler UI with client-side enhancements for live scan feedback, table filtering, B21 label editing and background status updates. Assets are bundled locally; the normal UI does not depend on a public CDN.

## Dashboard

The dashboard combines operational status with shortcuts into the main data sets:

- Mealie connection and last item sync,
- known and connected scanners,
- retry queue depth,
- total, linked, pending and unknown barcodes,
- current Mealie shopping-list counts,
- frequently used Foods, Recipes and Actions,
- recent multi-target scan events.

Open pages receive scan updates through Server-Sent Events. The notification bell flashes as soon as a physical scanner request is received; final routing results arrive independently afterwards.

## Barcodes

The barcode list and detail view are the central place for scan identity and routing. A barcode can route to one or more enabled targets rather than being limited to a single food mapping.

A target can represent a Food, Recipe or Action. The detail UI shows target order, destination lists and routing status. Legacy mappings are maintained for compatibility where required.

## Items

The Items table shows the synced Mealie food catalog plus manually created items. Server-side filters cover barcode linkage, scan history, source and category; sorting covers name, update time, last scan, scan count, barcode count and category. The search field filters the currently returned rows in the browser.

The filter controls are wired through the external page script so they remain compatible with the strict Content Security Policy. Changing Filter, Category, Sort or Order submits the GET filter form and preserves the chosen state.

Item detail pages show barcode mappings and scan statistics. Mealie-backed foods can be updated against Mealie; local items can be managed inside B2M.

## Recipes

Recipe targets use the Mealie recipe ID. A scan routes the complete recipe to the configured shopping-list destination rather than adding its ingredients one-by-one in B2M.

## Actions

Actions use stable `ACTION:<id>` codes and configurable webhook requests. The Request Builder provides Light, TTS, Timer, Automation and Data examples with structured field editing rather than requiring JSON to be written manually.

See [Actions & Home Assistant](actions.md) for Parameters, Payload, Headers, generated IDs and the Home Assistant automation helper.

## Labels

The Label Generator builds a reusable queue from Generic, Food, Recipe, Action and Custom codes. It supports browser printing and direct B21 Pro printing.

B21 mode includes physical roll profiles, RFID association, print calibration, direct object dragging/resizing, precise geometry values and text typography. See [Labels & B21 Pro Printing](b21-printing.md).

## Activity and notifications

Activity keeps the historical scan/routing log. The notification dropdown is intended for recent items requiring attention. Live scan toasts group repeated equivalent events instead of flooding the browser with duplicates.

## Settings and personal appearance

Deployment/system settings remain administrative. Appearance is different: every signed-in account has a **Personal appearance** page and stores its own theme override.

The global/deployment theme is only the fallback. A user can independently choose dark/light mode, accent, font, neutral palette, radius, date style or e-paper mode. Rainbow accent mode cycles the primary accent and animates the Mealie Barcode Middleware brand gradient.

## Users and permissions

Admin is still a full-access role, but ordinary users also have granular write permissions. Printer/labels, Actions, Items, scanning controls, system configuration, scanner tokens, user management and database administration are separate permissions.

The browser may hide or disable controls the current account cannot use, but enforcement happens on the server. See [Users, Permissions & Appearance](permissions-appearance.md).

## Database and storage

Database administration shows more than the SQLite file. The storage overview includes total persistent system-data size, SQLite size, other persisted files and file count so growth can be tracked over time.

Destructive database operations require the Database administration permission. A permitted non-admin account can use the dedicated Database page without receiving unrelated administrator privileges.

## Real-time updates

The authenticated UI uses the `/events` SSE stream for scan, pause and notification updates. Scanner submission itself remains token-authenticated and independent of the browser session.

A normal scan therefore has two UI phases: immediate scanner-receipt feedback and a later routing result after Mealie/Home Assistant work has completed.

## Screenshots

The documentation is written so screenshots are optional rather than required to follow a workflow. Current screenshots can be added to the Gallery and individual guides later without restructuring the documentation.
