"""
main_window.py

Main application window for the GSV grid UI.

This module contains the MainWindow class which:
- Builds and scales the grid-based live display.
- Shows device status and per-device update rates.
- Allows toggling "mirror view".
- Provides logging (REC) controls (CSV/XLSX via DataRecorder).
- Provides a "Zero" button to request zeroing all active devices (executed inside ReaderThread).
- Runs a startup prompt that optionally starts recording before the reader thread begins, so that the
  first incoming values are not missed by the logger.
"""

import time

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtGui import QFont

from gsvgrid.config import (
    ROW_COLS, 
    ACTIVE, 
    TOTAL_COLS, 
    GRID_MAP,
    DEVICE_BY_DEVNO, 
    DEVICE_CONFIG, 
    LOG_FILE, 
    LOG_RATE_HZ
)
from gsvgrid.utils import mirror_col, clear_layout, make_blue_shades_stronger
from gsvgrid.grid_cell import GridCell
from gsvgrid.reader_thread import ReaderThread
from gsvgrid.recorder import DataRecorder


class MainWindow(QtWidgets.QMainWindow):
    """
    Main Qt window that renders the measurement grid and all controls.

    What this class does:
    - Builds the grid layout (active/inactive cells) and keeps it responsive via apply_scale().
    - Subscribes to ReaderThread signals to update cell values, device rates, and device meta info.
    - Manages the recording UI and DataRecorder.
    - Provides a "Zero" action with confirmation, executed safely inside the ReaderThread.

    Parameters
    ----------
    gsv:
        Instance of the GSV wrapper object (DLL interface) used by ReaderThread.
        The window itself does not talk to the DLL directly (except release on close);
        all periodic DLL reads happen in ReaderThread.

    Returns
    -------
    None
    """

    def __init__(self, gsv):
        super().__init__()

        # ---------------------------------------------------------------------
        # Window basics
        # ---------------------------------------------------------------------
        self.setWindowTitle("GSV Grid (19 Values)")

        # ---------------------------------------------------------------------
        # View state (mirroring swaps the "diamond" columns)
        # ---------------------------------------------------------------------
        self.mirrored = False

        # ---------------------------------------------------------------------
        # Root layout (vertical)
        # ---------------------------------------------------------------------
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # ---------------------------------------------------------------------
        # Mirror control row (label + check-like button)
        # ---------------------------------------------------------------------
        row_mirror = QtWidgets.QHBoxLayout()
        row_mirror.setContentsMargins(0, 0, 0, 0)
        row_mirror.setSpacing(12)  

        self.lbl_mirror = QtWidgets.QLabel("Mirror view")

        # Base colors used for grid cells and buttons 
        self.base_blue = "#0F8EBD"  
        self.blue_hover = "#0D7FA9"

        self.chk_mirror = QtWidgets.QPushButton("✓")
        self.chk_mirror.setCheckable(True)
        self.chk_mirror.setCursor(QtCore.Qt.PointingHandCursor)
        self.chk_mirror.setFocusPolicy(QtCore.Qt.NoFocus)
        self.chk_mirror.setChecked(self.mirrored)

        # Map QPushButton(bool) click to the same state signature as a checkbox
        def _mirror_clicked(checked: bool):
            state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
            self.on_toggle_mirror(state)
        
        self.chk_mirror.clicked.connect(_mirror_clicked)

        row_mirror.addWidget(self.lbl_mirror)
        row_mirror.addWidget(self.chk_mirror)

        self.mirror_widget = QtWidgets.QWidget()
        self.mirror_widget.setLayout(row_mirror)
        self.mirror_widget.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        # ---------------------------------------------------------------------
        # Dynamic vertical gaps above/below the controls (scaled in apply_scale)
        # ---------------------------------------------------------------------
        self.controls_top_gap = QtWidgets.QWidget()
        self.controls_top_gap.setFixedHeight(0)

        self.controls_bottom_gap = QtWidgets.QWidget()
        self.controls_bottom_gap.setFixedHeight(0)

        layout.addWidget(self.controls_top_gap)

        # ---------------------------------------------------------------------
        # Recording UI (only if a log file is configured)
        # ---------------------------------------------------------------------
        self.recorder = None
        self.btn_record = None

        if LOG_FILE:
            # Stable column order for log files: ACTIVE keys sorted by row/col (e.g. "1/2", "2/2", ...)
            def key_sort(k: str):
                r, c = k.split("/")
                return (int(r), int(c))
            
            log_keys = sorted(list(ACTIVE), key=key_sort)
            self.recorder = DataRecorder(LOG_FILE, log_keys)

            # Logging rate limiting:
            # - LOG_RATE_HZ defines how many rows per second are written
            # - Default behavior is 1 Hz
            self._log_rate_hz = float(LOG_RATE_HZ) if LOG_RATE_HZ else 1.0
            self._log_min_dt = 1.0 / max(self._log_rate_hz, 1e-9)
            self._log_last_t = 0.0  # time.monotonic() timestamp of last write

            # Record toggle button
            self.btn_record = QtWidgets.QPushButton()
            self.btn_record.setCheckable(True)
            self.btn_record.clicked.connect(self.on_toggle_recording)

            self.btn_record.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Fixed
            )

            # Shared row: mirror on the left, REC centered, right dummy spacer to keep centering stable
            row_controls = QtWidgets.QHBoxLayout()
            row_controls.setContentsMargins(0, 0, 0, 0)
            row_controls.setSpacing(24)

            row_controls.addWidget(self.mirror_widget)

            row_controls.addStretch(1)
            row_controls.addWidget(self.btn_record, alignment=QtCore.Qt.AlignCenter)
            row_controls.addStretch(1)

            self.mirror_spacer = QtWidgets.QWidget()
            self.mirror_spacer.setFixedWidth(0)  # updated in apply_scale()
            row_controls.addWidget(self.mirror_spacer)

            layout.addLayout(row_controls)

            # Record button styles
            self.record_red = "#D64545"    
            self.record_green = "#2E9B6E"  

            self.btn_record_style_off = f"""
                QPushButton {{
                    background-color: {self.record_red};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 14px;
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    background-color: #C83B3B;
                }}
                QPushButton:pressed {{
                    background-color: #B73333;
                }}
            """

            self.btn_record_style_on = f"""
                QPushButton {{
                    background-color: {self.record_green};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 14px;
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    background-color: #268A62;
                }}
                QPushButton:pressed {{
                    background-color: #1F7352;
                }}
            """

            self.record_text_off = "● REC Start"
            self.record_text_on = "■ REC Stop"

            self._apply_record_button_style(is_recording=False)

        else:
            # Without LOG_FILE: keep mirror widget left-aligned in its own row
            row_controls = QtWidgets.QHBoxLayout()
            row_controls.setContentsMargins(0, 0, 0, 0)
            row_controls.setSpacing(24)

            row_controls.addWidget(self.mirror_widget)
            row_controls.addStretch(1)

            layout.addLayout(row_controls)

        layout.addWidget(self.controls_bottom_gap)

        # ---------------------------------------------------------------------
        # Grid layout (diamond layout of 19 active cells + inactive placeholders)
        # ---------------------------------------------------------------------
        self.grid = QtWidgets.QGridLayout()
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)

        self.grid_widget = QtWidgets.QWidget()
        self.grid_widget.setLayout(self.grid)
        self.grid_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # ---------------------------------------------------------------------
        # Overlay container: the grid + "Zero" button floating bottom-right
        # ---------------------------------------------------------------------
        self.grid_container = QtWidgets.QWidget()
        overlay = QtWidgets.QGridLayout(self.grid_container)
        overlay.setContentsMargins(0, 0, 0, 0)
        overlay.setSpacing(0)

        overlay.addWidget(self.grid_widget, 0, 0)

        base_blue = getattr(self, "base_blue", "#0F8EBD")
        hover = getattr(self, "blue_hover", "#0D7FA9")

        self.btn_zero = QtWidgets.QPushButton("Zero")
        self.btn_zero.setStyleSheet(f"""
            QPushButton {{
                background: {base_blue};
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 700;
                padding: 8px 14px;
            }}
            QPushButton:hover {{
                background: {hover};
            }}
            QPushButton:pressed {{
                background: {hover};
            }}
        """)
        self.btn_zero.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_zero.setFocusPolicy(QtCore.Qt.NoFocus)
        self.btn_zero.clicked.connect(self.on_zero_clicked)

        overlay.addWidget(self.btn_zero, 0, 0, alignment=QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom)

        layout.addWidget(self.grid_container, stretch=1, alignment=QtCore.Qt.AlignCenter)  

        # ---------------------------------------------------------------------
        # Bottom separator + status area
        # ---------------------------------------------------------------------
        self.sep_bottom = QtWidgets.QFrame()
        self.sep_bottom.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep_bottom.setFrameShadow(QtWidgets.QFrame.Plain)
        self.sep_bottom.setStyleSheet(f"color: {base_blue}; background-color: {base_blue};")
        self.sep_bottom.setFixedHeight(2)  
        layout.addWidget(self.sep_bottom)

        self.status = QtWidgets.QLabel("Status: -")
        self.dev_status = QtWidgets.QLabel("Devices: -")

        self.status_default_style = "color: #222; padding-top: 6px;"
        self.status_error_style = "color: #D64545; font-weight: 700;"
        self.status.setStyleSheet(self.status_default_style)
        self.dev_status.setStyleSheet("color: #222; padding-bottom: 4px;")

        layout.addWidget(self.status)
        layout.addWidget(self.dev_status)

        # ---------------------------------------------------------------------
        # Runtime caches for grid cells and device visual identity
        # ---------------------------------------------------------------------
        self.value_cells = {}       # ACTIVE: key -> GridCell
        self.sn_colors = {}         # serial(int) -> QColor
        self.last_dev_info = None   # cached meta info for repaint after rebuild

        # Build the initial grid and apply dynamic scaling once
        self.build_grid()
        self.apply_scale()

        # ---------------------------------------------------------------------
        # Reader thread wiring (signals only; thread starts after startup prompt)
        # ---------------------------------------------------------------------
        self.thread = ReaderThread(gsv=gsv)
        self.thread.valuesUpdated.connect(self.on_values)
        self.thread.statusUpdated.connect(self.on_status)
        self.thread.deviceInfoUpdated.connect(self.on_device_info)

        # ---------------------------------------------------------------------
        # Startup flow:
        # - show the window first
        # - then (optionally) start recording
        # - then start the reader thread so the very first values can be logged
        # ---------------------------------------------------------------------
        QtCore.QTimer.singleShot(0, self._startup_prompt_recording_then_start_thread)

    def _startup_prompt_recording_then_start_thread(self):
        """
        Run once right after the window has been shown.

        What happens here:
        - If logging is configured, ask the user whether recording should start immediately.
        - If the user chooses "Yes", start logging as if the REC button was clicked.
        - Only after that, start the ReaderThread. This ensures that the first incoming
          measurement values can be written to the log file.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """

        # Ensure this can only run once
        if getattr(self, "_startup_done", False):
            return
        self._startup_done = True

        # If logging is not configured, start acquisition immediately
        if not self.recorder or not self.btn_record:
            self.thread.start()
            return

        # Confirmation dialog
        msg = QtWidgets.QMessageBox(self)
        msg.setIcon(QtWidgets.QMessageBox.Question)
        msg.setWindowTitle("Start recording?")
        msg.setText(
            "Do you want to start REC recording immediately?\n\n"
            "If you choose 'Yes', the first incoming measurement values will be written to the log file."
        )
        btn_yes = msg.addButton("Yes, start REC", QtWidgets.QMessageBox.AcceptRole)
        btn_no  = msg.addButton("No", QtWidgets.QMessageBox.RejectRole)
        msg.setDefaultButton(btn_yes)

        msg.exec_()
        clicked = msg.clickedButton()

        if clicked == btn_yes:
            # Mirror a user click: set button checked without firing signals, then call the handler
            self.btn_record.blockSignals(True)
            self.btn_record.setChecked(True)
            self.btn_record.blockSignals(False)

            # Use existing logic (includes overwrite/name suggestion dialog)
            self.on_toggle_recording(True)

            # If the user cancels or an error occurs, on_toggle_recording() resets the button.
        else:
            # Explicitly ensure OFF state (red button)
            self._reset_record_button()

        # Start acquisition after recording decision
        self.thread.start()
    
    def on_status(self, msg: str):
        # ---------------------------------------------------------------------
        # Status line updates and basic severity coloring
        # ---------------------------------------------------------------------
        self.status.setText(f"Status: {msg}")

        if "Failed devices:" in msg or "FAIL" in msg:
            self.status.setStyleSheet(self.status_error_style)
        else:
            self.status.setStyleSheet(self.status_default_style)

    def on_values(self, values: dict, updates_by_dev: dict):
        # ---------------------------------------------------------------------
        # Grid cell updates (latest values)
        # ---------------------------------------------------------------------
        for key, val in values.items():
            cell = self.value_cells.get(key)
            if cell is not None:
                cell.set_value(val)

        # ---------------------------------------------------------------------
        # Per-device update rate line (Hz)
        # ---------------------------------------------------------------------
        parts = []
        for d in DEVICE_CONFIG:
            dev_no = d["dev_no"]
            ans = d["answer_id"]
            hz = updates_by_dev.get(dev_no, 0)
            parts.append(f"CAN 0x{ans:03X}: {hz:5.1f} Hz")
        self.dev_status.setText("Devices: " + " | ".join(parts))

        # ---------------------------------------------------------------------
        # Logging (rate-limited)
        # ---------------------------------------------------------------------
        if self.recorder and self.recorder.is_recording:
            t = time.monotonic()
            if (t - self._log_last_t) >= self._log_min_dt:
                self._log_last_t = t
                self.recorder.write(values)

    def on_device_info(self, dev_info: dict):
        # ---------------------------------------------------------------------
        # Cache latest device meta info and apply colors/labels in the grid
        # ---------------------------------------------------------------------
        self.last_dev_info = dev_info  # cache
        self.apply_device_info(dev_info)

    def on_zero_clicked(self):
        # ---------------------------------------------------------------------
        # "Zero all" action with confirmation. The actual DLL call runs in ReaderThread.
        # ---------------------------------------------------------------------
        reply = QtWidgets.QMessageBox.question(
            self,
            "Zero",
            "Do you really want to zero all values?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        # Optimistic UI update (instant feedback)
        for cell in self.value_cells.values():
            cell.set_value(0.0)

        # Thread request (ensures DLL access happens in the reader thread)
        try:
            self.thread.request_zero_all()
        except Exception as e:
            self.status.setText(f"Status: Zero request failed: {e}")

    def on_toggle_recording(self, checked: bool):
        """
        Toggle recording state.

        What happens here:
        - If recording is turned ON:
          - If the output file exists, show a dialog (overwrite / suggested new name / cancel).
          - Start the DataRecorder and switch the button to green.
        - If recording is turned OFF:
          - Stop the DataRecorder and restore the base output path.

        Parameters
        ----------
        checked : bool
            True to start recording, False to stop recording.

        Returns
        -------
        None
        """

        if not self.recorder or not self.btn_record:
            return

        if checked:
            try:
                # If the file exists, offer overwrite or an auto-incremented filename
                if self.recorder.file_exists():
                    suggested = self.recorder.suggest_nonexisting_path()

                    msg = QtWidgets.QMessageBox(self)
                    msg.setIcon(QtWidgets.QMessageBox.Warning)
                    msg.setWindowTitle("File already exists")
                    msg.setText(
                        "The log file already exists.\n\n"
                        f"Current:\n{self.recorder.out_path}\n\n"
                        f"Suggestion:\n{suggested}\n"
                    )

                    btn_overwrite = msg.addButton("Overwrite", QtWidgets.QMessageBox.DestructiveRole)
                    btn_use_suggested = msg.addButton("Use new name", QtWidgets.QMessageBox.AcceptRole)
                    btn_cancel = msg.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
                    msg.setDefaultButton(btn_use_suggested)

                    msg.exec_()
                    clicked = msg.clickedButton()

                    if clicked == btn_cancel:
                        self._reset_record_button()
                        return

                    if clicked == btn_use_suggested:
                        self.recorder.set_output_path(suggested)

                    # If overwrite was chosen, keep current out_path and let start() overwrite.

                self.recorder.start()

                # Ensure the first incoming values can be written immediately
                self._log_last_t = 0.0

                self._apply_record_button_style(is_recording=True)

            except Exception as e:
                self._reset_record_button()
                self.status.setText(f"Status: Logging error: {e}")

        else:
            try:
                self.recorder.stop()
                self.recorder.reset_output_to_base()
            finally:
                self._apply_record_button_style(is_recording=False)
    
    def _reset_record_button(self):
        # ---------------------------------------------------------------------
        # Reset REC button to OFF state without triggering on_toggle_recording()
        # ---------------------------------------------------------------------
        self.btn_record.blockSignals(True)
        self.btn_record.setChecked(False)
        self.btn_record.blockSignals(False)
        self._apply_record_button_style(is_recording=False)
    
    def _apply_record_button_style(self, is_recording: bool):
        # ---------------------------------------------------------------------
        # Apply REC button stylesheet and label based on current recording state
        # ---------------------------------------------------------------------
        if not self.btn_record:
            return
        
        if is_recording:
            self.btn_record.setStyleSheet(self.btn_record_style_on)
            self.btn_record.setText(self.record_text_on)
        else:
            self.btn_record.setStyleSheet(self.btn_record_style_off)
            self.btn_record.setText(self.record_text_off)

    def build_grid(self):
        """
        (Re)build the grid layout.

        What happens here:
        - Clears the existing grid layout.
        - Creates GridCell widgets for all positions defined in ROW_COLS.
        - Assigns CAN IDs for active cells from GRID_MAP / DEVICE_CONFIG.
        - Re-applies device serial/color information if available.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """

        # Clear current layout (used when toggling mirror mode)
        clear_layout(self.grid)
        self.value_cells = {}  

        # Create cells row by row (diamond layout)
        for r in range(1, 10):
            cols = ROW_COLS[r]
            for c, x in enumerate(cols, start=1):
                key = f"{r}/{c}"
                is_active = key in ACTIVE

                cell = GridCell(key, is_active)

                # Apply mirror transformation (only affects visual column index)
                col = mirror_col(x) if self.mirrored else x

                self.grid.addWidget(cell, r - 1, col)

                if is_active:
                    if key in GRID_MAP:
                        dev_no, _ch = GRID_MAP[key]
                        d = DEVICE_BY_DEVNO.get(dev_no)
                        if d:
                            cell.set_can(d["answer_id"])
                    self.value_cells[key] = cell

        # Re-apply cached device info after rebuild (colors/SN labels)
        if self.last_dev_info is not None:
            self.apply_device_info(self.last_dev_info)
            
        # Make all columns expand evenly
        for col in range(TOTAL_COLS):
            self.grid.setColumnStretch(col, 1)

    def on_toggle_mirror(self, state: int):
        # ---------------------------------------------------------------------
        # Toggle mirror mode and rebuild the grid
        # ---------------------------------------------------------------------
        self.mirrored = (state == QtCore.Qt.Checked)
        self.build_grid()
        self.apply_scale()

    def apply_device_info(self, dev_info: dict):
        """
        Apply device metadata to grid cells (serial numbers + consistent colors).

        What happens here:
        - Collect serial numbers from devices marked as ok.
        - Assign a stable blue shade per serial number (new ones get new shades).
        - Update each cell:
          - serial label (SN)
          - per-serial color if device ok, else neutral color
          - error highlight if device not ok

        Parameters
        ----------
        dev_info : dict
            Mapping dev_no -> {"serial": int|None, "ok": bool, "error": str|None}

        Returns
        -------
        None
        """

        # Collect serial numbers from OK devices only
        serials = []
        for dev_no, info in dev_info.items():
            if info.get("ok") and info.get("serial") is not None:
                serials.append(info["serial"])

        unique_serials = sorted(set(serials))

        # Assign new colors for serials we have not seen yet
        missing = [sn for sn in unique_serials if sn not in self.sn_colors]
        if missing:
            shades = make_blue_shades_stronger(
                len(missing),
                base_hex="#0F8EBD",
                dark_min=55,
                light_max=250
            )
            for sn, col in zip(missing, shades):
                self.sn_colors[sn] = col

        # Update all cells that are mapped to devices
        for pos, (dev_no, _ch) in GRID_MAP.items():
            cell = self.value_cells.get(pos)
            if cell is None:
                continue

            info = dev_info.get(dev_no, {})
            sn = info.get("serial", None)
            ok = info.get("ok", False)

            cell.set_sn(sn)
            if ok and sn is not None:
                cell.set_color(self.sn_colors.get(sn))  # per-serial blue shade
            else:
                cell.set_color(None)  # neutral

            # If the device is not ok, highlight cell as error
            if not ok:
                cell.set_error(True)

    def resizeEvent(self, event):
        # ---------------------------------------------------------------------
        # Recompute scaling on window resize
        # ---------------------------------------------------------------------
        super().resizeEvent(event)
        self.apply_scale()

    def apply_scale(self):
        """
        Compute responsive sizes (cells, fonts, spacings) based on current window size.

        What happens here:
        - Computes a target cell width that fits the full diamond into the available area.
        - Derives spacing and font sizes from cell width.
        - Applies those sizes to:
          - spacer gaps
          - mirror button (size/font/style)
          - status labels (font sizes)
          - all GridCells (fixed size + label fonts)
          - record button (size/font)
          - zero button (size/font)

        Parameters
        ----------
        None

        Returns
        -------
        None
        """

        # Available area inside the central widget
        w = self.centralWidget().width()
        h = self.centralWidget().height()

        top_space = self.chk_mirror.sizeHint().height() + 30  
        bottom_space = self.status.sizeHint().height() + self.dev_status.sizeHint().height() + 20

        # Include separator height in the bottom estimate
        if hasattr(self, "sep_bottom") and self.sep_bottom:
            bottom_space += self.sep_bottom.sizeHint().height()

        avail_w = max(200, w - 40)                 
        avail_h = max(200, h - top_space - bottom_space - 20)  

        # Geometry approximation of the full diamond (columns + spacings)
        denom_w = (TOTAL_COLS + 0.10 * (TOTAL_COLS - 1))
        denom_h = (9 * 1.10 + 8 * 0.10)

        cell_w_by_w = int(avail_w / denom_w)
        cell_w_by_h = int(avail_h / denom_h)
        cell_w = min(cell_w_by_w, cell_w_by_h)

        # Clamp cell size
        cell_w = max(70, min(cell_w, 140))

        # Dynamic gaps around top controls
        gap = max(6, min(24, int(cell_w * 0.15)))  
        self.controls_top_gap.setFixedHeight(gap)
        self.controls_bottom_gap.setFixedHeight(int(gap * 0.6))

        # Mirror toggle scaling
        if hasattr(self, "chk_mirror") and self.chk_mirror:
            ind = max(18, min(36, int(cell_w * 0.28)))
            radius = max(4, int(ind * 0.22))
            blue = getattr(self, "base_blue", "#0F8EBD")
            hover = getattr(self, "blue_hover", "#0D7FA9")

            self.chk_mirror.setFixedSize(ind, ind)

            f_tick = max(10, min(20, int(ind * 0.65)))
            self.chk_mirror.setFont(QFont(self.chk_mirror.font().family(), f_tick, QFont.Bold))

            self.chk_mirror.setStyleSheet(
                f"""
                QPushButton {{
                    border-radius: {radius}px;
                    border: 2px solid {blue};
                    background: transparent;
                    color: transparent;  
                    padding: 0px;
                }}
                QPushButton:hover {{
                    border: 2px solid {hover};
                }}
                QPushButton:checked {{
                    background: {blue};
                    border: 2px solid {blue};
                    color: white;         
                }}
                QPushButton:checked:hover {{
                    background: {hover};
                    border: 2px solid {hover};
                }}
                """
            )
        
        if hasattr(self, "lbl_mirror") and self.lbl_mirror:
            f_mirror = max(10, min(18, int(cell_w * 0.18)))
            self.lbl_mirror.setFont(QFont(self.lbl_mirror.font().family(), f_mirror))

        # Central layout margins/spacing
        m = max(12, int(cell_w * 0.15))
        self.centralWidget().layout().setContentsMargins(m, m, m, m)
        self.centralWidget().layout().setSpacing(max(8, int(cell_w * 0.10)))

        # Grid spacing + cell heights
        spacing = max(6, int(cell_w * 0.10))
        self.grid.setHorizontalSpacing(spacing)
        self.grid.setVerticalSpacing(spacing)

        cell_h_active = int(cell_w * 1.05)  
        cell_h_inactive = int(cell_w * 0.45)

        # Grid cell fonts
        f_key = max(6,  min(14, int(cell_w * 0.095)))
        f_sn  = max(5,  min(12, int(cell_w * 0.075)))
        f_can = max(5,  min(12, int(cell_w * 0.075)))
        f_val = max(6, min(18, int(cell_w * 0.080)))

        # Status fonts
        f_status = max(9, min(13, int(cell_w * 0.10)))  
        f_devices= max(9, min(12, int(cell_w * 0.075)))  

        self.status.setFont(QFont(self.status.font().family(), f_status))
        self.dev_status.setFont(QFont(self.dev_status.font().family(), f_devices))
        
        # Keep REC button perfectly centered by matching left widget width on the right
        if hasattr(self, "mirror_widget") and hasattr(self, "mirror_spacer"):
            self.mirror_spacer.setFixedWidth(self.mirror_widget.sizeHint().width())

        # Apply scaling to each cell
        for i in range(self.grid.count()):
            item = self.grid.itemAt(i)
            cell = item.widget()
            if cell is None or not isinstance(cell, GridCell):
                continue

            if cell.active:
                cell.setMinimumSize(cell_w, 1)
                cell.setMaximumSize(cell_w, cell_h_active)
                cell.lbl_key.setFont(QFont(cell.lbl_key.font().family(), f_key, QFont.DemiBold))
                cell.lbl_sn.setFont(QFont(cell.lbl_sn.font().family(), f_sn))
                cell.lbl_can.setFont(QFont(cell.lbl_can.font().family(), f_can))
                cell.lbl_val.setFont(QFont(cell.lbl_val.font().family(), f_val))
            else:
                cell.setFixedSize(cell_w, cell_h_inactive)
                cell.lbl_key.setFont(QFont(cell.lbl_key.font().family(), f_key))
        
        # Record button scaling
        if self.btn_record:
            btn_w = int(cell_w * 4.5) 
            btn_h = int(cell_w * 0.9)

            self.btn_record.setMinimumWidth(btn_w)
            self.btn_record.setMinimumHeight(btn_h)

            f_btn = max(10, min(16, int(cell_w * 0.18)))
            self.btn_record.setFont(QFont(self.btn_record.font().family(), f_btn, QFont.Bold))
        
        # Zero button scaling
        if hasattr(self, "btn_zero") and self.btn_zero:
            f_zero = max(9, min(14, int(cell_w * 0.10)))
            self.btn_zero.setFont(QFont(self.btn_zero.font().family(), f_zero, QFont.Bold))

            btn_h = max(28, int(cell_w * 0.55))
            self.btn_zero.setMinimumHeight(btn_h)

            btn_w = max(110, int(cell_w * 2.4))
            self.btn_zero.setMinimumWidth(btn_w)

    def closeEvent(self, event):
        # ---------------------------------------------------------------------
        # Graceful shutdown: stop the reader thread, release DLL, stop recording
        # ---------------------------------------------------------------------
        self.thread.stop()
        self.thread.wait(1000)

        try:
            self.thread.gsv.release()
        except Exception:
            pass

        try:
            if self.recorder and self.recorder.is_recording:
                self.recorder.stop()
        except Exception:
            pass

        event.accept()