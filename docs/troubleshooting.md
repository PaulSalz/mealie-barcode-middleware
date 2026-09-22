# Troubleshooting

Use the browser UI and container logs together. The **Activity** page is the best first check for scan routing, while Action detail pages contain request execution history and the Printer page shows B21/niimblue-node state.

## Quick Checks

```bash
docker compose ps
docker compose logs --tail=200 barcode-middleware
```

Then verify `GET /health` and hard-refresh the browser (`Ctrl+Shift+R`) after a deployment that changed UI assets.

## Items Filters Do Not React

Current B2M binds the Items filter dropdowns with normal JavaScript event listeners. Older builds used inline `onchange` handlers, which are blocked by B2M's strict Content Security Policy.

If selecting **With barcode**, **Category**, **Sort by**, or **Order** appears to do nothing:

1. Verify the footer/header shows the expected current B2M version.
2. Hard-refresh the page.
3. Open browser DevTools → Console and confirm there is no stale `items-page.js` syntax/load error.
4. Check the browser URL after selecting a filter. It should contain query parameters such as `?filter=linked&sort=name&order=asc`.

The text box below the server filters is separate: it filters only the rows already returned to the browser.

## Mealie Is Unreachable

If `/health` or the Dashboard reports Mealie as unreachable:

1. Verify `MEALIE_URL` is reachable **from the B2M container**, not only from your browser.
2. Verify the Mealie API token.
3. Test the Mealie endpoint from the Docker host/container network.
4. Check firewall/Docker network rules.

A URL containing `localhost` normally points back to the B2M container itself and is therefore wrong unless Mealie runs in that same container.

## Shopping-List Routing Is Wrong

B2M now discovers Mealie shopping lists and stores a runtime default. Individual targets can also select specific lists.

Check in this order:

1. **Settings → Mealie**: refresh the available shopping lists and confirm the default.
2. Open the barcode detail page and inspect each target's selected list(s).
3. For a Food target, check whether its route inherits the Food configuration or explicitly selects Mealie/Home Assistant/both/none.
4. For a recipe, check the selected list IDs and recipe scale.

Do not rely only on the legacy `MEALIE_SHOPPING_LIST_ID`; it is a fallback for older deployments.

## Scan Is Slow

Separate scanner receipt latency from downstream routing latency.

- The notification bell should react when B2M receives the physical scanner request.
- Food additions, recipe additions, Home Assistant requests, and Action webhooks can finish afterward.
- A slow recipe request often means the delay is inside Mealie's shopping-list recipe endpoint rather than the scanner path itself.

Check B2M logs for per-target duration and compare a one-target scan with a multi-target scan.

## Action Problems

### Home Assistant webhook does not run

On the Action page verify:

1. The Action ID and webhook URL match the intended Home Assistant `webhook_id`.
2. The generated Home Assistant YAML was copied after the latest ID/URL change.
3. The Home Assistant automation is enabled.
4. The Action is enabled in B2M.
5. **Test action** reports a successful HTTP response.

For a new Action, B2M normally derives the webhook URL from the `action_<name>` ID. If you manually override the ID or URL, that field stops following the automatic generator.

### Example payload does not do the expected thing

The request-builder examples and Home Assistant YAML are paired. If you switch from **Data** to **TTS**, **Timer**, **Light**, or **Automation**, copy the newly generated YAML or make the equivalent change in your existing Home Assistant automation.

Remember:

- Parameters are stored values referenced as `{{ params.key }}`.
- Payload is the actual request body/query data.
- Headers are HTTP metadata.

### Action times out

The most relevant setting for a remote service that accepts the connection but responds slowly is **Read timeout**. Connect timeout only covers establishing the connection.

Use retries carefully for non-idempotent actions. A remote service may have executed an action even when B2M received an ambiguous network error.

## B21 / niimblue-node

### Printer will not connect

Check:

1. Printer Settings URL, transport, and BLE address.
2. `niimblue-node` is reachable from B2M.
3. The B21 is not still connected to the official niim.blue Web Bluetooth page or another process.
4. Disconnect/reconnect from B2M and inspect `niimblue-node` logs.

B2M intentionally does not auto-acquire the printer when a print starts.

### Preview and physical print differ

Verify the selected roll profile:

- width/height
- DPI
- density
- label type
- threshold
- calibration offsets

Threshold is a print/raster property; it is intentionally not used to distort the element-layout preview.

Text font, bold/italic/underline, invert, alignment, and letter spacing are rasterized into the actual B21 print job. If an old print looks different after deploying an update, hard-refresh so the latest client-side renderer is loaded.

### X/Y values update only after releasing the mouse

That indicates stale label-editor JavaScript. In the current editor X/Y/Width/Height update live during drag/resize. Hard-refresh and verify the version.

## User Permissions

### A user cannot see Printer or Database settings

An Admin can change capabilities under **Settings → Users → Access control**.

Normal users have **Printer settings** enabled by default. **Database administration** and **Scan & Link control** are opt-in. Admin always has every capability.

Capabilities are checked server-side. Manually typing a hidden settings URL will not bypass the permission.

### Appearance changes affect the wrong user

Appearance is per-user in current versions. After upgrading from a global-theme version, each account initially inherits the old global appearance until that user saves Appearance once. This preserves the previous visual configuration during migration.

If two users still appear identical, confirm both accounts have saved their own Appearance settings and are not sharing the same browser login session.

## Rainbow Appearance

Rainbow mode is disabled by e-paper/monochrome mode because the two modes conflict by design. Turn off e-paper mode to see the changing accent and moving Dashboard brand gradient.

If the color swatch animates but the rest of the page does not, hard-refresh to reload `/theme.css` and the current UI CSS.

## Database / Storage

The Database page distinguishes:

- main SQLite database
- SQLite WAL and SHM files
- other persistent files
- total data-directory usage

A growing WAL file can make the persistent directory larger even when `barcode.db` has not changed much. This is why the total system-data metric is the useful long-term value.

Before purge/reset operations, download a DB backup. Deployment secrets and Compose/env configuration are outside the SQLite backup and must be backed up separately.

## Notifications / SSE

If the bell or live tables stop updating:

1. DevTools → Network → check the `/events` SSE connection.
2. Check whether a reverse proxy is buffering or timing out SSE.
3. Hard-refresh after an application update.
4. Check browser console errors.

The early physical scan receipt and the completed scan result are separate events, so a slow remote route should not delay the initial receipt feedback.

## Scanner Authentication

A `401` from `/scan` or `/scan/app` usually means the scanner is using a revoked/wrong token. Create a fresh token under **Settings → Tokens** and update that scanner only.

A `422` usually means the request body is malformed or missing the barcode field expected by that scanner endpoint.

## Docker / Startup

If the container fails after an update, inspect the first Python traceback in the logs. B2M performs idempotent SQLite migrations on startup; do not delete `barcode.db` to work around a migration error unless you intentionally want to lose data.

Common infrastructure causes are:

- `/data` not writable by the container
- invalid/missing required environment values
- port collision
- damaged SQLite file
- a stale image/container that was not rebuilt/redeployed after pulling code

For permissions or schema problems, include the B2M version and the startup migration traceback when reporting the issue.
