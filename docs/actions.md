# Actions & Home Assistant

Actions turn an `ACTION:<id>` barcode into a reusable HTTP request. The printed code only contains the stable Action ID; request details can be changed later without reprinting the label.

## Creating an Action

Open **Actions → New Action**. For new Actions, Home Assistant webhook is the normal starting point.

1. Enter a display name. B2M proposes a stable ID such as `action_kitchen_timer`.
2. The webhook URL is derived from the configured Home Assistant webhook URL when possible.
3. Choose an example in the Request Builder or build the request fields manually.
4. Save the Action and generate an `ACTION:<id>` label from the Action page or Label Generator.

The generated ID and webhook URL remain editable. Once you type an override manually, B2M stops replacing that value automatically.

## Parameters, Payload and Headers

**Parameters** are values stored with the Action for reuse. They are not transmitted automatically. Reference them from the payload with templates such as `{{ params.duration_seconds }}`. Parameters are useful for values you may want to change later without printing another barcode.

**Payload** is the actual request data. For POST, PUT and PATCH it becomes the JSON request body. For GET it is sent as query parameters. Templates are resolved when a scan happens. Useful templates include `{{ action.id }}`, `{{ action.name }}`, `{{ scan.barcode }}` and `{{ params.some_key }}`.

**Headers** are HTTP metadata. Most Home Assistant webhook Actions do not need custom headers. Use them only when an external endpoint requires values such as `Authorization` or a custom content type. Header secrets remain server-side and are never encoded into the printed barcode.

## Request Builder examples

The builder provides editable starting points for common workflows:

- **Light** — entity ID, command and optional brightness data.
- **TTS** — media player and message data for a Home Assistant automation.
- **Timer** — reusable `duration_seconds` parameter and timer target.
- **Automation** — target automation plus variables.
- **Data** — generic structured webhook data.

Selecting an example also aligns the Action name, generated ID, Home Assistant type, POST method, async execution and webhook identity. The Home Assistant YAML block then uses the resulting webhook ID.

## Advanced settings

Type, HTTP method, execution mode, retries and network timeouts live under **Advanced** because they normally do not need adjustment.

- **Async** returns control to the scanner immediately and executes the remote request in the background.
- **Sync** waits for the webhook result before the scan request completes.
- **Cooldown** prevents accidental repeated execution from rapid rescans.
- **Retries** should be used carefully for toggle-style actions because a repeated successful request can perform the action twice.
- **Read timeout** is how long B2M waits for response data after sending the request. Increase this first when a webhook itself is slow.

## Home Assistant

The Action page contains a ready-to-copy Home Assistant webhook automation. The webhook ID is derived from the configured URL. Keep webhook URLs private because possession of the URL may be sufficient to trigger the automation.

A good pattern is to keep B2M responsible for scan identity and request delivery while Home Assistant decides what the payload fields mean. This lets you change the automation later without changing the printed barcode.

## Testing

Saved Actions can be tested from the Action page. The result shows HTTP status and request duration. Recent executions distinguish success, failure and cooldown-ignored scans.
