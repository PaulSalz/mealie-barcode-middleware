# Users, Permissions & Administration

B2M keeps the original **Admin** role as an unrestricted superuser and adds individual capabilities for normal users. Capabilities are enforced on the server; hiding a tab in the UI is not the security boundary.

## Personal Appearance

Every logged-in user has independent Appearance settings. Light/dark mode, accent color, font, neutral palette, corner radius, e-paper/contrast options, date style, and interface font size are stored for that user.

Existing installations inherit the previous global appearance until a user saves their own settings. This avoids a visual reset during upgrade. After the first personal save, changing another user's Appearance does not affect the account.

The **Rainbow** accent mode cycles the primary UI accent through the spectrum. On the Dashboard, the `Mealie Barcode Middleware` brand uses a slowly moving left-to-right rainbow gradient. E-paper mode remains monochrome and therefore suppresses the rainbow treatment.

## Capability Model

Open **Settings → Users → Access control** as an administrator. Normal users can receive these capabilities independently:

### Printer settings

Enabled by default for normal users. Allows configuration of the B21 connection, `niimblue-node` runtime values, roll profiles, RFID/profile bindings, and calibration.

Printing itself remains part of the normal label workflow; this capability is about changing shared printer configuration.

### Scan & Link control

Allows the user to start or stop Scan & Link mode from the navigation. Users without the capability can still see that the system is paused, but they cannot change the pause state.

### Database administration

Allows access to the Database settings page, storage metrics, backup downloads, selective purge, reset, and factory reset functions. Grant this only to users who are allowed to modify persistent application data.

Admin accounts always have all capabilities and cannot have individual capabilities removed.

## Database and System Data Size

The Database page shows both the SQLite database and the wider persistent data footprint. The system-data panel reports:

- **Total system data**: all regular files in the directory containing the configured SQLite database
- **SQLite database**: the main `.db` file
- **SQLite WAL + SHM**: SQLite's write-ahead log and shared-memory sidecar files
- **Other persistent files**: the remaining files in the data directory
- File count and data-directory path

Watching the total rather than only the main database file is useful because SQLite WAL can temporarily grow while the `.db` size appears unchanged.

## Backups and Destructive Operations

**Download Backup** copies the current SQLite database and returns the copy to the browser. It is not a complete container/host backup; preserve your deployment configuration and secrets separately.

**Selective Purge** deletes one application table/category while retaining the rest.

**Reset Data** clears operational barcode/item/activity/retry data while preserving scanner API tokens.

**Factory Reset** additionally clears API tokens. User accounts are intentionally not removed so the installation does not become inaccessible after the reset.

All database mutations require the Database administration capability or Admin status.

## Security Notes

- Capabilities are synchronized from the User record into the signed login session on requests.
- Direct API/URL access is checked server-side even when the matching Settings tab is hidden.
- Appearance is user-scoped and does not need an administrative capability.
- Admin remains a deliberate superuser shortcut for installations that do not need fine-grained delegation.
