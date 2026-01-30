"""
recorder.py

Measurement data recorder for the GSV86CANViewer application. 

This module provides the DataRecorder class, which can write measurement rows
to either:
- CSV (streaming write during acquisition), or
- XLSX (buffered in memory and written once on stop())

Important design notes:
- Downsampling / logging rate control is intentionally handled outside of this
  class (e.g., in MainWindow.on_values()) to keep the recorder focused on
  file output only.
- The recorder writes *complete rows*: each output row contains all configured
  keys. Missing keys are filled using the last known value. 
- The recorder will not write any row until all keys have been seen at least
  once, to avoid partially empty log files at startup.
"""

import csv
import re
from datetime import datetime
from pathlib import Path

import openpyxl

from gsvgrid.config import PROJECT_ROOT


# -----------------------------------------------------------------------------
# Filename suffix helper for "base_001.ext" style file naming
# -----------------------------------------------------------------------------
_SUFFIX_RE = re.compile(r"^(?P<base>.*)_(?P<num>\d+)$")



class DataRecorder:
    """
    Write measurement data to disk as CSV or XLSX.

    What happens in this class:
    - The output format is determined by the file extension:
      - ".csv": rows are written directly as they arrive (streaming).
      - ".xlsx": rows are appended to a workbook in memory and saved at stop().
    - A "base path" is derived from the project root + configured path. This base
      path stays constant across runs.
    - The "output path" may change per recording session (e.g., when the GUI
      suggests a non-existing filename instead of overwriting an existing file).
    - Rows are only written once all keys have at least one known value.

    Parameters
    ----------
    file_path : str
        Path relative to the project root (e.g. "logs/data.xlsx").
        Must end in ".csv" or ".xlsx".
    keys : list[str]
        Ordered list of device/channel keys (e.g. ["1/2", "2/2", ...]) that define the
        columns written to the file.

    Attributes
    ----------
    is_recording : bool
        True while a recording session is active (start() called, stop() not yet
        called).
    base_path : pathlib.Path
        The original path derived from the config. Used as a reference for
        "suggest_nonexisting_path()" and to reset the output path.
    out_path : pathlib.Path
        The current output path for the next recording session.
    """

    def __init__(self, file_path: str, keys: list[str]):
        # ---------------------------------------------------------------------
        # Basic configuration and state
        # ---------------------------------------------------------------------
        self.file_path = str(file_path)
        self.keys = list(keys)
        self.is_recording = False

        # ---------------------------------------------------------------------
        # Runtime objects for CSV and XLSX modes
        # ---------------------------------------------------------------------
        self._csv_f = None
        self._csv_writer = None

        self._wb = None
        self._ws = None
        self._xlsx_rows = 0

        # ---------------------------------------------------------------------
        # Determine file type from extension
        # ---------------------------------------------------------------------
        self.ext = Path(self.file_path).suffix.lower()
        if self.ext not in (".csv", ".xlsx"):
            raise ValueError(f"Logging: unsupported file extension '{self.ext}'. Use .csv or .xlsx")
        
        # ---------------------------------------------------------------------
        # Resolve and prepare base output path (always relative to project root)
        # ---------------------------------------------------------------------
        self.base_path = (PROJECT_ROOT / file_path).resolve()
        self.base_path.parent.mkdir(parents=True, exist_ok=True)

        # Current output path (may be changed per recording session)
        self.out_path = self.base_path

        # ---------------------------------------------------------------------
        # Cache of last known values (used to build complete rows)
        # ---------------------------------------------------------------------
        self._last_values = {k: None for k in self.keys}

    # -----------------------------------------------------------------------------
    # Path helpers
    # -----------------------------------------------------------------------------
    def file_exists(self) -> bool:
        """
        Check if the current output file already exists.

        Returns
        -------
        bool
            True if out_path exists on disk.
        """
        return self.out_path.exists()
    
    def _next_index_for_base(self, width: int = 3) -> int:
        """
        Find the next free numeric suffix for the base output name.

        What happens:
        - Searches for existing files in the base folder matching:
            base.ext
            base_001.ext
            base_002.ext
            ...
        - Returns the next available integer index.

        Parameters
        ----------
        width : int
            Zero-padding width for the suffix (default: 3 -> 001, 002, ...).

        Returns
        -------
        int
            Next free numeric index (e.g. 1, 2, 3, ...).
        """
        parent = self.base_path.parent
        ext = self.base_path.suffix
        stem = self.base_path.stem

        max_idx = 0

        # If the base file already exists, the first alternative should be _001
        if self.base_path.exists():
            max_idx = 0  

        # Scan all matching files "stem_*.ext" and find the highest suffix
        for p in parent.glob(f"{stem}_*{ext}"):
            if p.suffix.lower() != ext.lower():
                continue

            m = _SUFFIX_RE.match(p.stem)
            if not m:
                continue
            if m.group("base") != stem:
                continue

            try:
                idx = int(m.group("num"))
                max_idx = max(max_idx, idx)
            except ValueError:
                # Ignore unexpected suffix formats
                pass

        return max_idx + 1

    def suggest_nonexisting_path(self, width: int = 3) -> Path:
        """
        Suggest a non-existing filename based on the base path.

        What happens:
        - If the base file does not exist yet, returns base_path.
        - Otherwise returns the next indexed variant:
            messdaten.xlsx -> messdaten_001.xlsx -> messdaten_002.xlsx -> ...

        Parameters
        ----------
        width : int
            Zero-padding width for the suffix (default: 3 -> 001, 002, ...).

        Returns
        -------
        pathlib.Path
            Suggested file path that does not collide with existing files.
        """
        if not self.base_path.exists():
            return self.base_path

        next_idx = self._next_index_for_base(width=width)
        return self.base_path.with_name(f"{self.base_path.stem}_{next_idx:0{width}d}{self.base_path.suffix}")

    def set_output_path(self, new_path: Path):
        """
        Override the output path for the next recording session.

        Parameters
        ----------
        new_path : pathlib.Path
            New output file path.

        Returns
        -------
        None
        """
        self.out_path = Path(new_path).resolve()

    def reset_output_to_base(self):
        """
        Reset the output path back to the configured base path.

        This is typically called after stop(), so the next "REC Start" begins
        with the original filename again.

        Returns
        -------
        None
        """
        self.out_path = self.base_path

    # -----------------------------------------------------------------------------
    # Recording lifecycle
    # -----------------------------------------------------------------------------
    def start(self):
        """
        Start a recording session.

        What happens:
        - If already recording, returns immediately.
        - For CSV:
          - Opens the output file in write mode (overwrites existing content).
          - Writes a header row ["timestamp"] + keys.
        - For XLSX:
          - Creates a new workbook in memory.
          - Creates a sheet and writes the header row.
        - Clears the last-value cache so startup logging begins "clean".

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        if self.is_recording:
            return

        if self.ext == ".csv":
            self._csv_f = open(self.out_path, "w", newline="", encoding="utf-8")
            self._csv_writer = csv.writer(self._csv_f)
            header = ["timestamp"] + self.keys
            self._csv_writer.writerow(header)
            self._csv_f.flush()

        else:  # .xlsx
            self._wb = openpyxl.Workbook()
            self._ws = self._wb.active
            self._ws.title = "Measurement Data"
            header = ["timestamp"] + self.keys
            self._ws.append(header)
            self._xlsx_rows = 1

        self._last_values = {k: None for k in self.keys}
        self.is_recording = True

    def stop(self):
        """
        Stop a recording session and flush data to disk.

        What happens:
        - If not recording, returns immediately.
        - For CSV:
          - Flushes and closes the file handle.
        - For XLSX:
          - Saves the in-memory workbook to the output file.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        if not self.is_recording:
            return

        if self.ext == ".csv":
            try:
                self._csv_f.flush()
            finally:
                self._csv_f.close()

            self._csv_f = None
            self._csv_writer = None
        else:
            self._wb.save(self.out_path)
            self._wb = None
            self._ws = None

        self.is_recording = False

    # -----------------------------------------------------------------------------
    # Data writing
    # -----------------------------------------------------------------------------
    def write(self, values: dict):
        """
        Append one measurement row to the log.

        What happens:
        - Updates the internal last-value cache for any keys present in `values`.
        - If any configured key has never been seen yet, no row is written.
          (This prevents incomplete rows right after startup.)
        - Creates a row consisting of:
          - ISO timestamp with millisecond precision
          - one column per configured key in `self.keys`
            (filled with the last known value)
        - Writes the row to CSV or appends it to the XLSX sheet.

        Parameters
        ----------
        values : dict
            Dictionary mapping device/channel keys (e.g. "3/4") to numeric values.

        Returns
        -------
        None
        """
        if not self.is_recording:
            return

        # ---------------------------------------------------------------------
        # Update the last-known-value cache (only for keys we track)
        # ---------------------------------------------------------------------
        for k, v in values.items():
            if k in self._last_values:
                try:
                    self._last_values[k] = float(v)
                except Exception:
                    # Ignore non-numeric values; keep the last valid value
                    pass
        
        # ---------------------------------------------------------------------
        # Do not write until all keys have at least one value
        # ---------------------------------------------------------------------
        if any(self._last_values[k] is None for k in self.keys):
            return
        
        # ---------------------------------------------------------------------
        # Build the output row (timestamp + values in stable key order)
        # ---------------------------------------------------------------------
        ts = datetime.now().isoformat(timespec="milliseconds")

        row = [ts]
        for k in self.keys:
            v = self._last_values.get(k, None)
            row.append("" if v is None else v)

        # ---------------------------------------------------------------------
        # Write to CSV (streaming) or append to XLSX (buffered)
        # ---------------------------------------------------------------------
        if self.ext == ".csv":
            self._csv_writer.writerow(row)
            # Intentionally not flushing on every write for performance
        else:
            self._ws.append(row)
            self._xlsx_rows += 1