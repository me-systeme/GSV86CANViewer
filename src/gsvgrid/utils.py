"""
utils.py

Small helper functions used across the GUI and acquisition code.

This module contains:
- Acquisition helpers (extract_latest_channels)

All functions are intentionally small and stateless so they can be reused
from different modules without creating circular dependencies.
"""


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