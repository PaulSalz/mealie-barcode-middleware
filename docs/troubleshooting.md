# Troubleshooting

Start with the component that actually failed: scanner receipt, B2M routing, Mealie, an Action/webhook, the B21 printer, or the browser UI. A successful scanner receipt does not imply that every downstream target has finished.

## Scan received but result is slow

The notification bell flashes when B2M receives the physical scanner request. Food, recipe and webhook routing can finish later.

Check Activity and the application logs to separate the phases. For recipe targets, Mealie's shopping-list recipe endpoint can dominate the total runtime even when Home Assistant delivery is already complete.

If an Action is slow, inspect its recent execution duration and HTTP status. Increase **Read timeout** only when the remote endpoint really needs more time to return response data.

## Mealie routing problems

If Mealie is unreachable, verify the URL from the Docker host/container network rather than from your browser. `localhost` inside the B2M container refers to B2M itself, not another container or host service.

Check the configured API key and shopping-list IDs. A 404/422 from Mealie usually indicates an invalid destination or payload rather than a scanner problem.

For recipe scans, compare one destination list with multiple destination lists. Parallel requests can still contend inside Mealie or its database, so more concurrency is not automatically faster.

## Item filters do not react

The application uses a strict Content Security Policy and therefore must not depend on inline `onchange` JavaScript. Current versions bind Filter, Category, Sort and Order from `items-page.js`.

If the controls appear dead after an update, hard-refresh once to remove an old cached script. The URL should then change to include the selected GET parameters.

## Action does not run

Check, in order:

1. The account has the **Actions** permission for write/test operations.
2. The Action is enabled.
3. The webhook URL points at the intended endpoint.
4. Home Assistant `webhook_id` matches the ID in the URL.
5. Method and execution mode under Advanced are appropriate.
6. The scan is not inside the Action cooldown window.
7. The retry policy is safe for the action type.

The Action page's Test button bypasses normal scan cooldown/disabled handling where appropriate and reports HTTP status/duration.

### Home Assistant example payload

The Request Builder examples are data contracts between B2M and your Home Assistant webhook automation. If you change field names in the builder, adjust the Home Assistant automation to read the same `trigger.json` keys.

Do not expose Home Assistant webhook URLs in screenshots or public logs.

## B21 printer problems

### Connect button does nothing

Confirm the signed-in account has **Printer & labels** permission. Then check the niimblue-node service and Bluetooth adapter on the server.

Only one owner should control the printer at a time. Disconnect B2M/niimblue-node before opening a direct Web Bluetooth connection from niim.blue.

### Preview looks right but print is shifted

Use profile calibration offsets for whole-label physical alignment. Do not compensate for printer/media offset by moving every design element.

### Text formatting differs from preview

Current B21 printing rasterizes the selected typography settings before submitting the job. Hard-refresh after updating if the browser still has an old label script cached.

### Threshold appears to do nothing in the editor

That is expected. Threshold is a roll/profile raster setting and no longer alters the WYSIWYG layout preview. It is applied to the final B21 print job.

## Permission denied

Granular write permissions are enforced server-side. The browser also hides/disables common controls, but a stale page can still display a button that later receives HTTP 403.

Administrators can adjust permissions on the Users page. New ordinary users default to Printer & labels, Actions and Items; sensitive administration permissions are off.

Database administration is independent of general system configuration.

## Appearance looks different between users

That is intentional. Appearance settings are stored per account. The global theme is only the fallback.

If switching accounts in the same browser briefly shows the previous/global mode during load, the personal theme stylesheet and `/api/theme` response should correct it immediately. A hard refresh clears stale asset versions if necessary.

### Rainbow mode not animated

Check whether the operating system/browser has **Reduce motion** enabled. B2M respects `prefers-reduced-motion` and suppresses continuous rainbow animation in that case.

## Database/storage growth

Open the Database page with an account that has **Database administration** permission. Compare total System data with the SQLite database size. The difference represents other files persisted in the B2M data directory.

Use row counts to determine whether Activity, barcode cache or another table is growing. Purge operations are destructive and should be preceded by a database backup when the data matters.

## No live browser feedback

Open browser developer tools and verify there is a long-lived `/events` Server-Sent Events request. Reverse proxies must allow streaming responses and should not aggressively buffer or terminate idle SSE connections.

The early bell receipt and final `scan` result are separate events. Seeing one but not the other narrows the problem considerably.

## Mobile scanner returns 401

The scanner must send the raw API token, not its display name or token prefix. Tokens are shown in full only when created.

If uncertain, create a new scanner token and update the client. Removing a token revokes it immediately.

## Mobile scanner returns 422

Verify the endpoint and request format expected by the scanner integration. For JSON clients, ensure the decoded barcode/content field is present and the request uses the expected content type.

## Docker/container does not start

Check the current container logs first. Common causes are malformed environment configuration, an unwritable persistent data directory, a port conflict or an unavailable dependency.

The SQLite database and session data need a writable persistent directory. Avoid fixing permissions with broad world-writable access when normal UID/GID ownership can be used instead.

## After updating

For UI-heavy releases:

1. redeploy/restart the B2M container,
2. load the new version,
3. hard-refresh the browser once (`Ctrl+Shift+R`),
4. confirm the version shown/API version matches the deployed release,
5. reproduce the issue while watching Activity and container logs.

For feature-specific guidance see [Actions & Home Assistant](actions.md), [Labels & B21 Pro Printing](b21-printing.md) and [Users, Permissions & Appearance](permissions-appearance.md).
