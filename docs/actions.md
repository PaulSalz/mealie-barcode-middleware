# Actions & Home Assistant

Actions turn a printed `ACTION:<id>` code into an HTTP request. The physical code only stores the stable Action ID; the URL, payload, parameters, headers, retry policy and Home Assistant behavior remain editable in B2M.

## Create an Action

Open **Actions → New Action** and enter a display name. For a new Action, B2M proposes an ID such as `action_kitchen_light` and derives a Home Assistant webhook URL from that ID. Both fields remain editable: once you manually override the ID or URL, the automatic generator stops changing that field.

New Actions default to a **Home Assistant webhook**, `POST`, and asynchronous execution. Type, HTTP method and execution mode are available under **Advanced** because the normal Home Assistant workflow rarely needs them changed.

The printed code remains `ACTION:<id>`. Renaming the display name does not require a new label. If an old Action ID must continue working, add it under **Aliases**.

## Request Builder

The request builder avoids hand-writing JSON for normal use. Choose an example and then edit the generated fields.

- **Light** creates a Home Assistant light payload with an entity, command and brightness.
- **TTS** creates a speech payload with a TTS entity, media player, message and language.
- **Timer** stores a reusable duration and sends it to a Home Assistant timer.
- **Automation** targets a Home Assistant automation and can pass variables.
- **Data** is a generic structured webhook example for custom automations or another HTTP service.

Each example updates the generated Home Assistant automation YAML below the request settings. The alias, automation ID and `webhook_id` follow the current Action name/ID/URL.

## Parameters vs Payload vs Headers

These three areas have different jobs:

**Parameters** are values stored with the Action. They are not sent automatically. Reference a parameter from the payload with `{{ params.key }}`. Parameters are useful for values you want to change later without reprinting the Action code. A timer duration is the common example.

**Payload** is the actual request data. At scan time B2M resolves templates such as `{{ scan.barcode }}` or `{{ params.duration_seconds }}` and sends the resulting object as JSON for `POST`, `PUT`, or `PATCH`. For `GET`, the object becomes query parameters.

**Headers** are HTTP metadata. They are separate from the payload and are suitable for API/version hints or authorization expected by the destination. Headers stay on the B2M server and are never encoded in the printed barcode.

The builder supports text, numbers, booleans, templates and nested JSON objects. Use **Preview JSON** to inspect the generated structure. Raw JSON remains available under **Advanced / raw JSON**.

## Home Assistant Automation

The generated YAML is designed as a starting point that matches the selected example:

- Light → `light.turn_on`
- TTS → `tts.speak`
- Timer → `timer.start`
- Automation → `automation.trigger`
- Data → emits a `b2m_action` event

Copy the YAML into Home Assistant, then replace the example entity IDs with your real entities. The webhook ID is derived from the Action webhook URL, so an Action with ID `action_kitchen_timer` can use a dedicated Home Assistant webhook with the same identifier.

Keep webhook URLs private. Anyone who can reach a Home Assistant webhook URL may be able to trigger that automation depending on your network exposure and Home Assistant configuration.

## Execution Controls

The normal defaults are intentionally conservative. Advanced settings include:

- **Cooldown**: minimum gap before the same Action is accepted again. Scans inside the window are recorded as `ignored_cooldown`.
- **Retries**: additional attempts after a failure.
- **Retry policy**: controls whether network failures, HTTP 5xx, or other HTTP failures are retryable.
- **Retry delay / backoff**: controls the delay between attempts.
- **Connect timeout**: time allowed to establish the network connection.
- **Read timeout**: time allowed to wait for response data after the request was sent.
- **Write timeout**: time allowed to upload the request body.
- **Pool timeout**: time allowed to wait for an available HTTP connection.

For toggle-like side effects, avoid aggressive retries unless the destination is idempotent; an ambiguous network failure can otherwise result in the remote action being executed twice.

## Testing

Saved Actions have a **Test action** button. The test uses the current server-side configuration and reports HTTP status and duration. It does not change the printed code.

For Home Assistant debugging, first verify that the generated `webhook_id` matches the automation trigger, then check Home Assistant automation traces and B2M's recent Action executions.
