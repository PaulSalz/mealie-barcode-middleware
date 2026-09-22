# Web Dashboard

B2M's web UI is server-rendered with Jinja2 and enhanced with JavaScript for live scan updates, interactive tables, label design, and settings. Static assets are bundled locally.

## Dashboard (`/`)

The Dashboard combines operational status and scan history:

- Mealie connectivity and last catalog sync
- Scanner online/known counts
- Retry queue depth
- Barcode totals: all, linked, pending, and unknown
- Current Mealie shopping-list item counts
- Frequently used Foods, recipes, and Actions when enough history exists
- Recent scan events including multi-target scans

The notification bell reacts as soon as a physical scanner request is received, before slower Mealie routing finishes. Scan results and other live UI changes are delivered with Server-Sent Events.

When a user selects the **Rainbow** appearance mode, the Dashboard's `Mealie Barcode Middleware` brand uses a slow moving rainbow gradient and the primary accent cycles through the spectrum.

## Barcodes (`/barcodes`)

The barcode list is the identity/routing view for physical codes. Filters separate mapped, pending, unknown, and other states.

A barcode detail page can contain more than one target. Targets may be:

- Food / Mealie item
- Recipe
- Action

Each target can have its own route, shopping-list destinations, quantity/unit information, recipe scale, ordering, and enabled state. Legacy single mappings are mirrored for compatibility, but the target list is the current routing model.

The detail page also exposes cached product metadata, lookup/retry controls, manual linking, and target editing.

## Items (`/items`)

Items are synchronized Mealie Foods or local/manual entries. The table includes category, source, barcode count, scan count, last scan, and update time.

The server filters support:

- All items
- With / without barcode
- Scanned / never scanned
- Mealie / custom source
- Category
- Sort field and ascending/descending order

The search field then filters the currently returned rows in the browser. Filter dropdowns use CSP-safe JavaScript listeners; no inline JavaScript is required.

Item detail pages show barcode mappings, scan statistics, Food metadata, category/unit information, and shopping routing. Routing can use Mealie, Home Assistant, both, none, or the global/default behavior.

## Actions (`/actions`)

Actions turn `ACTION:<id>` codes into configurable HTTP requests. The detail page contains execution statistics, a guided request builder, generated Home Assistant automation YAML, testing, cooldown/retry controls, and request history.

New Actions default to Home Assistant webhook behavior. A display name can automatically produce an ID such as `action_kitchen_timer` and a matching webhook URL, while both fields remain manually overrideable.

See [Actions & Home Assistant](actions.md) for the request-builder model and examples.

## Labels (`/labels`)

The generator supports generic codes, Foods, recipes, Actions, and raw custom codes. Output can be sent to the browser print layout or to a configured B21 Pro.

The B21 editor provides:

- Physical roll profiles and RFID/profile association
- Drag/resize with live X/Y/Width/Height readout
- Element alignment independent from text alignment
- Font family, bold, italic, underline, invert, text alignment, vertical alignment, and letter spacing
- Label frame control
- Per-profile print threshold and calibration offsets
- Snapshot-based queued print jobs

See [Labels & B21 Printing](label-printing.md).

## Activity and Notifications

**Activity** is the chronological audit trail. It includes scan events, result status, barcode, target snapshots, and timestamps.

The **notification bell** focuses on events that need attention. Notifications can be marked read or archived, while the Activity page retains the historical event stream until data is purged.

## Settings (`/settings`)

Settings are capability-aware rather than globally admin-only.

### Appearance

Every user can manage personal Appearance settings. They are stored per user and include mode, accent, font, neutral palette, radius, accessibility/contrast settings, date presentation, and UI font size.

### Printer

The Printer tab is visible when the account has the **Printer settings** capability. Normal users receive this capability by default; an administrator can disable it per user.

The page combines connection status, printer/model information, RFID data, and `niimblue-node` runtime configuration.

### Configuration

Global integration/system configuration remains an administrative function. It contains Mealie, Home Assistant, lookup, matching, scanning, and system settings. Editable runtime values override environment defaults without rewriting the deployment file.

### Users

Administrators create users, change passwords, and edit normal-user capabilities in the **Access control** panel. Admin remains the unrestricted superuser.

### Database

Accounts with **Database administration** can view the Database tab. It now shows total persistent system-data usage in addition to the main SQLite file, including WAL/SHM and other files beside the database. Backup, selective purge, reset, and factory reset are protected by the same server-side capability.

See [Users, Permissions & Administration](permissions.md).

## Real-Time Updates

The browser subscribes to B2M's SSE event stream. Live events power the scan receipt flash, toast/notification updates, pause-state changes, and selected table/dashboard refreshes.

The UI should not be treated as the authorization boundary: destructive or capability-sensitive endpoints perform their own server-side checks.

## Screenshots

Screenshots in the documentation are illustrative and may lag a UI release. They can be replaced independently without changing the workflow documentation; current field names and behavior in the text are the reference when a screenshot differs.
