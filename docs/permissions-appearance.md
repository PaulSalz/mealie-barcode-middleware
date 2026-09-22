# Users, Permissions & Appearance

B2M separates authentication from write permissions. An administrator account still has full access, while ordinary users can be given only the parts of the application they should be allowed to change.

## Permission model

Permissions are stored per user and can be changed from the Users administration UI.

The current permission groups are:

| Permission | Allows |
| --- | --- |
| Printer & labels | B21 connection, roll settings and print jobs |
| Actions | Create, edit, test and delete Actions |
| Items | Create, edit and sync item data |
| Scanning controls | Pause/resume Scan & Link controls |
| System configuration | Integration, lookup, matching and system settings |
| Scanner tokens | Create and revoke scanner tokens |
| User management | Manage users and their permissions |
| Database administration | Backup and destructive database maintenance |

Administrators always have every permission. New ordinary users receive Printer & labels, Actions and Items by default; sensitive system and database permissions start disabled.

Permissions are checked server-side for write requests. Hiding a button in the browser is only a usability improvement and is not the security boundary.

## Database administration

Database administration is intentionally separate from general configuration. A user with this permission can open the database/system-data view and perform the exposed maintenance operations. Users without the permission receive no write access to those operations.

The storage overview reports:

- total persistent system-data size,
- SQLite database size,
- other persisted-data size,
- number of files in the application data directory,
- table row counts.

This makes long-term storage growth visible instead of showing only the SQLite file.

## Personal appearance

Appearance is per account and does not require an administrative permission. Open **Personal appearance** from the tools/settings menu.

Each account can choose its own:

- light or dark mode,
- accent color,
- font family,
- neutral palette,
- corner radius,
- date style,
- e-paper/monochrome mode and contrast.

The deployment/global theme remains a fallback for users without an override.

## Rainbow accent

Rainbow is available as an accent mode. In this mode the primary UI accent cycles through the color spectrum. The **Mealie Barcode Middleware** brand uses a slow left-to-right rainbow gradient. Reduced-motion browser preferences disable the continuous animation.

## Changing a user's permissions

Open **Settings → Users** as an administrator and choose **Configure** in the Permissions column. Changes take effect on subsequent requests; no database migration or container restart is required.

If an account is promoted to administrator, the granular toggles are superseded because administrators always receive full access.
