# Labels & B21 Printing

The Labels page supports two output paths: normal browser printing and direct printing through a NIIMBOT B21 Pro using `niimblue-node`.

## Build the Label Queue

Open **Labels** and add one or more codes. The generator supports generic labels, Mealie Foods, recipes, Actions, and custom raw code values. Each queue entry keeps its own symbology and quantity.

Generic labels use a stable `GENERIC:` identity. Foods, recipes, and Actions keep their linked target IDs so scanning the printed label can route directly without another fuzzy lookup.

The queue is stored in the browser so layout work survives a normal page reload.

## Browser Print

Choose **Browser print** for normal sheet/page output. Configure label format, physical width, gap, padding, page margins, text visibility, and cut guides. The browser print dialog remains responsible for the final printer/page configuration.

## B21 Pro Output

Choose **B21 Pro** to switch to the physical label editor. B2M uses the configured `niimblue-node` service and keeps BLE connection state explicit rather than silently taking the printer from the official niim.blue web interface.

The printer must be connected before a print job starts. B2M queues an immutable raster snapshot of each label, so changing the editor while a job is running does not alter the pages already submitted.

## Roll Profiles

A roll profile describes the physical media and printer settings:

- Width and height in millimetres
- DPI
- Density
- NIIMBOT label type
- Print threshold

Profiles can be associated with the RFID information returned by the printer. Calibration offsets are stored per profile.

**Threshold** is a print/raster setting and therefore lives with the roll profile rather than the element inspector. It does not intentionally distort the design preview.

## Layout Editor

Select an element in the preview or in the inspector. The selected object receives the same accent outline as its resize handle.

While you drag or resize an object, **X, Y, Width, and Height update live** in the inspector. This makes the sliders useful as a precise readout instead of only updating after the pointer is released.

**Element alignment** controls the position of the entire object on the physical label: left, horizontal center, right, top, vertical center, bottom, or both centers. These controls are separate from text alignment.

The **Frame** switch is a primary label-level control because the border is often important for small die-cut rolls and calibration checks.

## Typography

Text elements have their own Typography section. Available controls include:

- Sans serif, serif, or monospace font family
- Bold
- Italic
- Underline
- Black/white invert
- Left, center, or right alignment inside the text box
- Top, middle, or bottom vertical alignment
- Letter spacing
- Font size from the element geometry controls

These properties are applied to both the on-screen preview and the client-side raster used for the actual B21 print job.

## Calibration

Calibration offsets move the complete rendered label relative to the physical media without changing every element's X/Y coordinate. Use **Calibration test** to print a center/reference pattern and adjust X/Y until the output lines up with the roll.

Keep calibration small. A large offset usually means the selected roll dimensions or label type are wrong rather than the layout itself being misplaced.

## Printer Permissions

Printer settings are controlled by the per-user **Printer settings** capability. It is enabled by default for normal users because roll/profile access is useful in day-to-day operation, but an administrator can disable it under **Settings → Users → Access control**.

The permission protects configuration and connection/profile mutations server-side. It is not only a hidden navigation item.

## Direct niim.blue Use

B2M and the official niim.blue Web Bluetooth page should not try to own the BLE printer at the same time. Disconnect the B21 from B2M before connecting it directly in a browser, and reconnect it in B2M afterward.

If a print fails, check the printer status first, then the selected roll profile, dimensions, density/label type, and the `niimblue-node` logs.
