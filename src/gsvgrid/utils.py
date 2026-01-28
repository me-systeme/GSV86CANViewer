"""
utils.py

Small helper functions used across the GUI and acquisition code.

This module contains:
- Layout helpers (clear_layout)
- Grid geometry helpers (mirror_col)
- Color helpers (make_blue_shades_stronger, best_text_color)
- Acquisition helpers (extract_latest_channels)

All functions are intentionally small and stateless so they can be reused
from different modules without creating circular dependencies.
"""

from PyQt5 import QtWidgets
from PyQt5.QtGui import QColor

from gsvgrid.config import TOTAL_COLS 


# ---------------------------------------------------------------------------
# Grid geometry helpers
# ---------------------------------------------------------------------------
def mirror_col(x: int) -> int:
    """
    Mirror a grid column index around the vertical center line.

    What happens:
    - The grid columns are indexed from 0..TOTAL_COLS-1.
    - Mirroring swaps left and right positions, keeping the center axis fixed.

    Parameters
    ----------
    x : int
        Original column index (0-based).

    Returns
    -------
    int
        Mirrored column index (0-based).
    """
    return (TOTAL_COLS - 1) - x

# ---------------------------------------------------------------------------
# Qt layout helpers
# ---------------------------------------------------------------------------
def clear_layout(layout: QtWidgets.QLayout):
    """
    Remove all items/widgets from a Qt layout.

    What happens:
    - Takes each item out of the layout.
    - If the item owns a widget, detaches it from its parent so Qt can delete it
      (or it can be re-parented later).

    Parameters
    ----------
    layout : QtWidgets.QLayout
        The layout instance to clear.

    Returns
    -------
    None
    """
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------
def make_blue_shades_stronger(n: int, base_hex="#00A3E0",
                              dark_min=70, light_max=170):
    """
    Generate `n` blue-ish shades with a stronger brightness spread.

    What happens:
    - Uses a base color (base_hex) and varies the perceived brightness.
    - Produces darker-to-lighter shades using QColor.darker()/lighter().
    - Applies a mild gamma curve so you get more resolution in the bright range
      (visually more distinct "light blues").

    Parameters
    ----------
    n : int
        Number of shades to generate.
    base_hex : str
        Base color in hex, e.g. "#0F8EBD".
    dark_min : int
        Lower brightness bound expressed as a percentage-like factor.
        Must be < 100 to generate darker colors.
    light_max : int
        Upper brightness bound expressed as a percentage-like factor.
        Must be > 100 to generate lighter colors.

    Returns
    -------
    list[QColor]
        List of QColor objects. Returns an empty list if n <= 0.
    """
    if n <= 0:
        return []

    base = QColor(base_hex)

    # Special case: a single shade is just the base color
    if n == 1:
        return [base]

    # Build a list of "brightness factors" in the range [dark_min .. light_max]
    # QColor.lighter(f): f=100 means unchanged, >100 makes it lighter
    # QColor.darker(f):  f=100 means unchanged, >100 makes it darker
    factors = []
    for i in range(n):
        t = i / (n - 1)  # 0..1
        gamma = 0.6      # <1 => more resolution in the bright region
        f = int(dark_min + (light_max - dark_min) * (t ** gamma))
        factors.append(f)

    shades = []
    for f in factors:
        if f == 100:
            c = QColor(base)
        elif f > 100:
            c = base.lighter(f)
        else:
            # Convert a "target brightness factor" (f<100) into a darker() percentage.
            # Example: f=70 means ~70% brightness => darker(100/0.70=143)
            dark_factor = int(round(10000 / f))  # equals round((100/f) * 100)
            c = base.darker(dark_factor)

        shades.append(c)

    return shades

def best_text_color(bg: QColor) -> str:
    """
    Pick a readable text color (black or white) based on background luminance.

    What happens:
    - Uses a simple luminance estimate with sRGB weights.
    - Returns black for bright backgrounds and white for dark backgrounds.

    Parameters
    ----------
    bg : QColor
        Background color.

    Returns
    -------
    str
        "#000" (black) or "#fff" (white).
    """
    r, g, b, _ = bg.getRgb()
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#000" if luminance > 150 else "#fff"

# ---------------------------------------------------------------------------
# Acquisition helpers
# ---------------------------------------------------------------------------
def extract_latest_channels(data, channels=3):
    """
    Extract the latest full channel block from a flat value list.

    What happens:
    - The DLL returns a flat list of values in "channel blocks".
    - This function takes the *last complete block* of `channels` values.
    - If there is no complete block (or too few values), it falls back to the
      last available values and pads missing entries with NaN.

    Parameters
    ----------
    data : list[float] | None
        Flat list of values as returned by the DLL wrapper.
    channels : int
        Number of channels per block that should be extracted (default: 3).

    Returns
    -------
    list[float] | None
        - list[float] with length == `channels` if data is available
        - None if `data` is empty/None
    """
    if not data:
        return None

    n = len(data)

    # Use the last complete block of size `channels`
    if n >= channels:
        full_blocks = n // channels
        start = (full_blocks - 1) * channels
        latest = data[start:start + channels]
        if len(latest) == channels:
            return latest

    # Fallback: not enough values or odd-sized buffer -> pad with NaN
    latest = data[-channels:]
    if len(latest) < channels:
        latest = [float("nan")] * (channels - len(latest)) + latest
    return latest