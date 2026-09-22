# Middleware Setup

B2M is a FastAPI service between scanner clients and Mealie. It owns local barcode identity/routing, product lookup/cache, Actions, retries, label generation, the web UI, and optional Home Assistant integration.

## Architecture

```text
Scanner / phone / label
        │  POST /scan
        ▼
      B2M
   ┌────┼───────────────┐
   │    │               │
SQLite  Mealie API   Home Assistant / Actions
   │                    │
Web UI + SSE         optional webhooks
```

Mealie is part of Food/recipe routing but Home Assistant is not required for normal scanning.

## Docker Deployment

Persist `/data`; it contains the SQLite database and application state used by the container.

Example Compose service:

```yaml
services:
  barcode-middleware:
    image: ghcr.io/paulsalz/mealie-barcode-middleware:latest
    restart: unless-stopped
    ports:
      - "9930:8000"
    volumes:
      - ./middleware-data:/data
    env_file:
      - .env
```

Use the image/build strategy appropriate to your deployment. After an update, redeploy the container so database migrations and the new static assets load from the same application version.

## Required Mealie Configuration

The core environment values are:

```bash
MEALIE_URL=http://mealie:9925
MEALIE_API_KEY=your-mealie-api-token
```

`MEALIE_SHOPPING_LIST_ID` still exists as a legacy fallback, but the normal runtime default shopping list is discovered from Mealie and selected in the B2M Settings UI. This lets targets select one or more shopping lists without rebuilding the container.

## Common Optional Configuration

```bash
MIDDLEWARE_BASE_URL=https://b2m.example.internal
TIMEZONE=Europe/Berlin
LOG_LEVEL=INFO

OFF_ENABLED=true
UPCDB_ENABLED=false
LOOKUP_STRATEGY=failover
LOOKUP_PRIMARY=off
LOOKUP_ENRICH_IN_BACKGROUND=true

HA_WEBHOOK_URL=http://homeassistant.local:8123/api/webhook/barcode-scanner
HA_NOTIFICATION_MODE=unresolved
```

Many non-secret runtime settings can be changed by an administrator in the web UI. Read-only infrastructure/secrets such as the Mealie API key remain deployment settings.

## Lookup Sources

B2M can use Open Food Facts and UPCDatabase. `failover` tries the secondary source only when the primary source has no product. `complement` can use the secondary source to fill missing metadata.

When background enrichment is enabled, the secondary complement lookup can happen after the scanner has already received its response. This keeps the scan path responsive while still enriching the cache.

UPCDatabase requires its API key. If the source is enabled without a usable key, B2M skips it.

## Matching and Sync

Important runtime controls include:

- Fuzzy match threshold
- Fuzzy ambiguity gap
- Item sync interval
- Lookup cache TTL
- Retry count
- Unknown-barcode behavior

Mealie Foods are synchronized into B2M for local matching/search. A manual sync is available from the Items page.

## Home Assistant

There are two distinct Home Assistant uses:

### Scan notifications

`HA_WEBHOOK_URL` can receive selected scan notifications/events. `HA_NOTIFICATION_MODE` controls whether B2M sends unresolved/actionable/all scans or disables the notification webhook.

### Actions

The Actions page can create dedicated Home Assistant webhook Actions. A new Action can derive a unique webhook URL from its generated `action_<name>` ID and generates example automation YAML for Light, TTS, Timer, Automation, or generic Data behavior.

These Action webhooks are independent from the general scan-notification webhook. See [Actions & Home Assistant](actions.md).

## B21 / niimblue-node

Direct B21 printing is optional. The runtime adapter reads these environment defaults and lets permitted users override them in the Printer Settings UI:

```bash
NIIMBLUE_URL=http://niimblue-node:5000
NIIMBLUE_TRANSPORT=ble
NIIMBLUE_ADDRESS=C3:18:28:04:16:99
NIIMBLUE_PRINT_TASK=D110M_V4
NIIMBLUE_PRINT_DIRECTION=top
NIIMBLUE_DENSITY=3
NIIMBLUE_LABEL_TYPE=1
NIIMBLUE_DPI=300
NIIMBLUE_MAX_LABEL_WIDTH_MM=50
NIIMBLUE_TIMEOUT=30
```

Runtime overrides are stored by B2M and take precedence over the environment defaults. Printer connection remains explicit; printing does not silently acquire BLE.

See [Labels & B21 Printing](label-printing.md).

## Users and Permissions

The first account is Admin. Admin is the unrestricted superuser.

Normal users can have granular capabilities for printer settings, Scan & Link control, and database administration. Appearance is always personal and stored per account. Printer settings are enabled by default for a normal user but can be disabled by Admin.

See [Users, Permissions & Administration](permissions.md).

## API Tokens

Scanner clients authenticate with B2M API tokens. Create tokens in **Settings → Tokens**. The raw token is only displayed when created; store it in the scanner configuration.

Create separate tokens for separate scanner clients so one device can be revoked without replacing every scanner credential.

## Database and Persistent Data

The default SQLite path is `/data/barcode.db`. Migrations run automatically at startup and are designed to preserve existing data.

The Database page shows both the main SQLite file and the total persistent directory size, including SQLite WAL/SHM sidecar files. This is more useful for long-term storage monitoring than the `.db` size alone.

Before destructive maintenance, download a database backup and retain your deployment configuration/secrets separately.

## Health and Diagnostics

`GET /health` reports application/Mealie/database health for the container health check.

For operational debugging, combine:

```bash
docker compose ps
docker compose logs --tail=200 barcode-middleware
```

with the B2M **Activity** page and, for Actions, the recent execution list on the Action detail page.

## Security

- The web UI requires a user session.
- Scanner submission uses API-token authentication.
- State-changing browser requests are protected by Origin/Referer CSRF checks.
- A strict Content Security Policy is used; UI behavior must not depend on inline JavaScript.
- Capability-sensitive settings are checked server-side even if a navigation item is hidden.
- Treat Mealie tokens and Home Assistant webhook URLs as secrets.
- Put B2M behind HTTPS when it is accessible across an untrusted network.
