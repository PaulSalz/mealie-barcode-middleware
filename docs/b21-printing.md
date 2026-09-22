# Labels & B21 Pro Printing

The Label Generator supports normal browser printing and direct B21 Pro printing through the configured niimblue-node service.

## Label queue

Add Generic, Food, Recipe, Action or Custom codes to the queue. Each queue entry keeps its own code type, quantity and B21 layout state. The browser-print layout and B21 physical-label layout are independent.

## B21 connection and roll profiles

Choose **B21 Pro** as the output. Printer connection is manual and remains a server-side connection intent rather than a browser Bluetooth connection.

A roll profile defines physical printing properties such as:

- label width and height,
- DPI,
- print density,
- label/stock type,
- raster threshold.

Threshold belongs to the roll/profile because it affects the final black/white raster sent to the printer. It is intentionally not a normal element-layout control.

RFID data can be read from compatible rolls and associated with a profile. Calibration offsets are stored per profile.

## Label editor

Click an element in the preview to select it. The selected object receives the same accent outline used by the resize handle.

You can drag an element directly on the label and resize it from the handle. X, Y, width and height values update live while dragging, so the visual editor and precise controls stay in sync.

### Element alignment

Element alignment positions the selected object box on the physical label. It is separate from alignment of text inside a text box.

Available object alignment includes left, horizontal center, right, top, vertical center, bottom and center-both.

### Typography

For text elements the Typography section provides:

- Sans serif, Serif and Monospace fonts,
- bold,
- italic,
- underline,
- black/white inversion,
- left, center or right text alignment,
- top, middle or bottom vertical alignment,
- letter spacing.

These settings are used by both the on-screen preview and the actual client-side print raster. They are not preview-only styling.

## Frame

**Frame** remains a primary label-level switch because it is useful for physical alignment and bordered labels. It is independent of individual elements.

## Calibration

Print offsets shift the complete label image in millimetres. Use the calibration test to verify the physical center before fine-tuning individual elements. Keep layout coordinates for design and calibration offsets for printer/media alignment.

## Printing

Before a print job is queued, B2M snapshots the current queue entry, layout, typography, roll profile and calibration. Later UI changes therefore do not modify a print job already submitted.

The job status reports queued/running/completed state, pages and printed label count. Printer mutation operations require the **Printer & labels** user permission; ordinary users receive this permission by default unless an administrator removes it.

## Direct niim.blue use

Do not let direct Web Bluetooth and niimblue-node own the printer connection at the same time. Disconnect B2M/niimblue-node first if you want to use the browser-based niim.blue application directly.
