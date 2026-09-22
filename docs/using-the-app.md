# Using the App

This guide covers the normal B2M workflow after deployment: login, scanner authentication, barcode routing, Actions, labels, and the user-specific interface.

## First Login

Open the B2M web address. The first account created is the Admin superuser. Additional users can be created later under **Settings → Users**.

The Dashboard shows Mealie status, scanner status, barcode counts, shopping lists, retry depth, frequently used targets, and recent scans.

## Personal Appearance

Every user can open **Settings → Appearance**. Appearance is stored per account, so light/dark mode, fonts, accent color, e-paper settings, date style, and other display preferences do not change another user's interface.

The **Rainbow** accent cycles the primary UI color and gives the Dashboard brand a moving rainbow gradient.

## Scanner Authentication

Physical/mobile scanners submit barcodes using an API token. Admin users create and revoke tokens under **Settings → Tokens**.

A token is shown only when it is created. Store it in the scanner client and send it as the configured Bearer/scanner credential. The token list shows known scanners and runtime scanner metadata where available.

## What Happens When You Scan

A scan is acknowledged quickly, then B2M resolves the barcode locally whenever possible. The physical scan receipt is reflected immediately in the notification bell; slower Mealie or Home Assistant routing continues afterward.

A barcode may route to one or more targets:

- **Food** — add a Food to one or more shopping destinations
- **Recipe** — add a recipe to selected Mealie shopping lists
- **Action** — execute the saved HTTP/Home Assistant Action

Targets can run in parallel where safe. The activity record stores target snapshots so historical scans remain understandable even if the routing is changed later.

## Unknown and Unlinked Barcodes

If a barcode is not mapped, B2M can query configured product databases and attempt a Food match. Depending on the result, you may see a linked/added result, a pending product that needs a target, or an unknown barcode.

Open the barcode detail page from the notification or barcode list. From there you can inspect product metadata, retry a lookup, search Foods, and edit the target list.

Once a barcode has a stable local target, later scans do not need to repeat the external product lookup before routing.

## Multi-Target Routing

A physical barcode is not limited to one destination. The target editor can attach multiple Foods, recipes, and Actions to the same code.

For Food targets you can configure quantity/unit and routing. Recipe targets support scale and selected shopping lists. Actions reference a stable Action ID and use the Action's current server-side request configuration.

Use this when one scan should perform several related operations, for example adding two staple Foods or adding an item and triggering Home Assistant feedback.

## Actions

Open **Actions** to create reusable automation codes. On a new Action, typing a name can generate an ID such as `action_kitchen_timer` and a matching Home Assistant webhook URL. The ID and URL are always overrideable.

The request builder has examples for Light, TTS, Timer, Automation, and generic Data. Parameters, payload, and headers can be edited as fields rather than by hand-writing JSON. The generated Home Assistant YAML follows the selected example.

See [Actions & Home Assistant](actions.md) for details.

## Scan & Link Mode

Scan & Link mode processes and maps barcodes without adding shopping-list entries. It is useful when labeling or onboarding many products at once.

Users need the **Scan & Link control** capability to start or stop the mode. Everyone can still see the global pause banner so it is clear why scans are not adding items.

The pause expires automatically after its selected duration unless a permitted user stops it early.

## Labels

The Labels page can generate generic codes, linked Foods, recipes, Actions, and custom codes.

Choose **Browser print** for normal sheet printing or **B21 Pro** for direct label printing. The B21 editor supports roll profiles, calibration, draggable/resizable elements, object alignment, typography, frame control, and print threshold.

See [Labels & B21 Printing](label-printing.md).

## Items

The Items page is the Food/catalog view. Server filters can select linked/unlinked, scanned/never-scanned, Mealie/custom, category, sort field, and order. A separate text search filters the visible table rows.

Item detail pages contain barcode mappings, scan history/statistics, Food metadata, and shopping-route configuration.

## Notifications and Activity

The bell focuses on current attention items and updates live. Activity is the longer chronological audit trail.

For debugging a scan, Activity is normally the best starting point because it records the barcode, result, target information, and timestamp even when the notification has already been read or archived.

## Users and Permissions

Admin remains the unrestricted superuser. Normal users can receive granular capabilities for printer settings, Scan & Link control, and database administration. Appearance is personal and available to every logged-in user.

See [Users, Permissions & Administration](permissions.md).

## Next Steps

- [How Barcode Scanning Works](barcode-workflow.md)
- [Web Dashboard](web-dashboard.md)
- [Actions & Home Assistant](actions.md)
- [Labels & B21 Printing](label-printing.md)
- [Troubleshooting](troubleshooting.md)
