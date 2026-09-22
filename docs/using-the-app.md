# Using the App

This guide covers normal B2M use after deployment: scanner authentication, routing, Actions, labels and the parts of the UI you will use regularly.

## First login and scanner token

On a new installation create the initial administrator account, then configure at least one scanner token. Tokens authenticate scan clients with a Bearer token and can be revoked independently of web users.

Administrators can create tokens under Settings. A token is shown in raw form once; store it in the scanner configuration rather than in a printed barcode.

## What happens when you scan

B2M first identifies the scanned code, then resolves its configured targets. A barcode can have one target or several enabled targets.

Typical targets are:

- **Food** — add a Mealie food/item to one or more shopping lists.
- **Recipe** — add the selected Mealie recipe to the configured shopping-list destination.
- **Action** — execute a reusable webhook Action such as a Home Assistant command.

The notification bell gives immediate scanner-receipt feedback before slow Mealie or webhook work has finished. Final routing results appear later as scan toasts/activity entries.

## Unknown and unlinked barcodes

If a product cannot be resolved automatically, open its barcode detail page from the notification or barcode list. From there you can inspect lookup data, search items and create or change targets.

Once a mapping/target is stored, future scans use the local identity first instead of repeating the full external lookup path.

## Items

The Items page represents the local view of the Mealie food catalog plus any manually created items. Use the server-side Filter, Category, Sort and Order controls to narrow the data set; the search box filters the returned table rows immediately in the browser.

Item detail pages show linked barcodes and scan history. Users need the **Items** permission for write/sync operations.

## Scan & Link mode

Scan & Link mode is useful when registering a large number of physical products without adding them to shopping lists at the same time. Lookup, target resolution and activity logging continue, while shopping-list delivery is suppressed where the route respects the pause state.

Access to pause/resume is controlled by the **Scanning controls** permission rather than being implicitly tied to every normal user.

## Generic and reusable labels

For products or workflows without a manufacturer barcode, use the Label Generator. Generic labels can represent text identities, while Food, Recipe and Action entries create stable codes tied to the selected target.

The queue can be printed through the browser or sent directly to a configured B21 Pro. See [Labels & B21 Pro Printing](b21-printing.md) for physical-label editing and printer settings.

## Actions

Actions are useful when a scan should do something other than, or in addition to, shopping-list routing. The printed code is stable while the remote request remains editable.

Common examples include a Home Assistant light command, TTS message, timer, automation trigger or generic structured data. See [Actions & Home Assistant](actions.md).

## Notifications and Activity

The bell contains recent attention items; Activity is the longer-term audit trail. Repeated equivalent browser toasts are grouped within the configured grouping window.

For troubleshooting, Activity is usually more useful than relying only on a phone notification because it records the middleware result and timing context.

## Personal appearance

Every signed-in account can open **Personal appearance** from the tools/settings menu. Appearance is stored per user, so changing dark mode, accent or font does not change another user's UI.

Rainbow accent mode cycles the primary accent and applies a slow moving rainbow gradient to the Mealie Barcode Middleware brand. See [Users, Permissions & Appearance](permissions-appearance.md).

## Permissions

Ordinary accounts can be granted individual write capabilities. Printer access is intentionally separate from database/system administration, so a household user can work with labels and the B21 without receiving destructive database controls.

The UI hides or disables unavailable controls, but the write routes also enforce permissions server-side.

## Recommended daily workflow

1. Scan a product or workflow label.
2. Check the immediate bell flash to confirm scanner delivery.
3. For a normal mapped scan, no browser action is required.
4. If a notification says the barcode needs mapping, open its detail page and assign the correct target.
5. Use Activity when you need to verify what happened after routing.
6. Use the Items, Actions and Labels pages for maintenance rather than changing printed codes unnecessarily.

## Next steps

- [Barcode & Routing Workflow](barcode-workflow.md)
- [Actions & Home Assistant](actions.md)
- [Labels & B21 Pro Printing](b21-printing.md)
- [Web Dashboard](web-dashboard.md)
- [Troubleshooting](troubleshooting.md)
