"""
main_window.py

Main application window for the GSV UI (tree view).

This module contains the MainWindow class which:
- Shows live values grouped by device -> channel in a QTreeWidget.
- Shows device status and per-device update rates.
- Provides logging (REC) controls (CSV/XLSX via DataRecorder).
- Provides a "Zero" button to request zeroing all active devices (executed inside ReaderThread).
"""

import time

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtGui import QFont, QColor, QBrush

from gsv86canviewer.config import ( 
    DEVICE_CONFIG, 
    LOG_FILE, 
    LOG_RATE_HZ
)
from gsv86canviewer.reader_thread import ReaderThread
from gsv86canviewer.recorder import DataRecorder


class MainWindow(QtWidgets.QMainWindow):
    """
    Main Qt window that renders a device/channel tree and all controls.

    What this class does:
    - Subscribes to ReaderThread signals to update values, device rates, and device meta info.
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
        self.setWindowTitle("GSV Measurements")

        # Base colors used for buttons
        self.base_blue = "#0F8EBD"
        self.blue_hover = "#0D7FA9"
        
        # ---------------------------------------------------------------------
        # Root layout (vertical)
        # ---------------------------------------------------------------------
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # ---------------------------------------------------------------------
        # Optional small top gap (kept simple)
        # ---------------------------------------------------------------------
        self.controls_top_gap = QtWidgets.QWidget()
        self.controls_top_gap.setFixedHeight(8)
        layout.addWidget(self.controls_top_gap)

        # ---------------------------------------------------------------------
        # Recording UI (only if a log file is configured)
        # ---------------------------------------------------------------------
        self.recorder = None
        self.btn_record = None

        if LOG_FILE:
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
            self.btn_record.setEnabled(False)  # will be activated after deviceInfoUpdated

            self.btn_record.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Fixed
            )

            # Shared row: REC centered, right dummy spacer to keep centering stable
            row_controls = QtWidgets.QHBoxLayout()
            row_controls.addStretch(1)
            row_controls.addWidget(self.btn_record, alignment=QtCore.Qt.AlignCenter)
            row_controls.addStretch(1)
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
            # Without LOG_FILE
            row_controls = QtWidgets.QHBoxLayout()
            row_controls.addStretch(1)
            layout.addLayout(row_controls)


        # ---------------------------------------------------------------------
        # Tree
        # ---------------------------------------------------------------------
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["Device", "CAN", "Serial", "Channel", "Value"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        layout.addWidget(self.tree, stretch=1)

        # ---------------------------------------------------------------------
        # Zero
        # ---------------------------------------------------------------------
        row_bottom = QtWidgets.QHBoxLayout()
        row_bottom.addStretch(1)

        self.btn_zero = QtWidgets.QPushButton("Zero")
        self.btn_zero.setStyleSheet(f"""
            QPushButton {{
                background: {self.base_blue};
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 700;
                padding: 8px 14px;
            }}
            QPushButton:hover {{ background: {self.blue_hover}; }}
            QPushButton:pressed {{ background: {self.blue_hover}; }}
        """)
        self.btn_zero.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_zero.setFocusPolicy(QtCore.Qt.NoFocus)
        self.btn_zero.clicked.connect(self.on_zero_clicked)
        row_bottom.addWidget(self.btn_zero, alignment=QtCore.Qt.AlignRight)
        layout.addLayout(row_bottom)

        # ---------------------------------------------------------------------
        # Bottom separator + status area
        # ---------------------------------------------------------------------
        self.sep_bottom = QtWidgets.QFrame()
        self.sep_bottom.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep_bottom.setFrameShadow(QtWidgets.QFrame.Plain)
        self.sep_bottom.setStyleSheet(f"color: {self.base_blue}; background-color: {self.base_blue};")
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
        # Runtime caches 
        # ---------------------------------------------------------------------
        self.dev_items = {}    # dev_no -> QTreeWidgetItem
        self.chan_items = {}   # (dev_no, ch) -> QTreeWidgetItem
        self.sn_colors = {}         # serial(int) -> QColor
        self.last_dev_info = None   # cached meta info for repaint after rebuild

        self._build_devices_only()

        # ---------------------------------------------------------------------
        # Reader thread wiring (signals only; thread starts after startup prompt)
        # ---------------------------------------------------------------------
        self.thread = ReaderThread(gsv=gsv)
        self.thread.valuesUpdated.connect(self.on_values)
        self.thread.statusUpdated.connect(self.on_status)
        self.thread.deviceInfoUpdated.connect(self.on_device_info)
        self.thread.start()

        self.apply_scale()
    
    # -------------------------------------------------------------------------
    # Build tree structure
    # -------------------------------------------------------------------------
    def _build_devices_only(self):
        """Create top-level device rows (no channels yet)."""
        self.tree.clear()
        self.dev_items.clear()
        self.chan_items.clear()

        for d in DEVICE_CONFIG:
            dev_no = d["dev_no"]
            ans = d["answer_id"]
            dev_item = QtWidgets.QTreeWidgetItem([f"DEV {dev_no}", f"0x{ans:03X}", "SN ?", "", ""])
            self.tree.addTopLevelItem(dev_item)
            self.dev_items[dev_no] = dev_item

        self.tree.expandAll()

        hdr = self.tree.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)

    def _ensure_channels(self, dev_no: int, nchan: int):
        # ---------------------------------------------------------------------
        # Ensure channel child items exist for dev_no: CH 1..nchan.
        # ---------------------------------------------------------------------
        dev_item = self.dev_items.get(dev_no)
        if dev_item is None:
            return

        # Create missing channel items
        for ch in range(1, int(nchan) + 1):
            key = (dev_no, ch)
            if key in self.chan_items:
                continue
            ch_item = QtWidgets.QTreeWidgetItem(["", "", "", f"CH {ch}", "-"])
            dev_item.addChild(ch_item)
            self.chan_items[key] = ch_item

        dev_item.setExpanded(True)

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
        # Value updates 
        # Values keys are expected to be "dev_no/ch" (1-based channel).
        # Example: {"2/1": 12.3, "2/2": 12.4, "5/3": ...})
        # ---------------------------------------------------------------------
        for k, val in values.items():
            try:
                dev_s, ch_s = k.split("/")
                dev_no = int(dev_s)
                ch = int(ch_s)
            except Exception:
                continue

            item = self.chan_items.get((dev_no, ch))
            if item is None:
                # If values arrive before deviceInfoUpdated, create on-the-fly (safe)
                self._ensure_channels(dev_no, ch)
                item = self.chan_items.get((dev_no, ch))
                if item is None:
                    continue
            
            try:
                item.setText(4, f"{val:.2f} kN")
            except Exception:
                item.setText(4, "NaN")

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
        # Cache latest device meta info and apply colors/labels 
        # ---------------------------------------------------------------------
        self.last_dev_info = dev_info

        # Build channels once we know them
        for dev_no, info in dev_info.items():
            nchan = int(info.get("channels", 0) or 0)
            if nchan > 0:
                self._ensure_channels(dev_no, nchan)

        # Init recorder now that we know channel counts
        if LOG_FILE and self.recorder is None:
            self._init_recorder_from_devinfo(dev_info)
            if self.btn_record:
                self.btn_record.setEnabled(True)

        self.apply_device_info(dev_info)
    
    # -------------------------------------------------------------------------
    # Recorder init 
    # -------------------------------------------------------------------------
    def _init_recorder_from_devinfo(self, dev_info: dict):
        # Stable key order: by dev_no then ch
        keys = []
        for d in DEVICE_CONFIG:
            dev_no = d["dev_no"]
            nchan = int(dev_info.get(dev_no, {}).get("channels", 0) or 0)
            for ch in range(1, nchan + 1):
                keys.append(f"{dev_no}/{ch}")
        self.recorder = DataRecorder(LOG_FILE, keys)

        self._log_last_t = 0.0

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
        for item in self.chan_items.values():
            item.setText(4, "0.00 kN")

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


    def apply_device_info(self, dev_info: dict):
        """
        Apply device metadata to tree viewer UI (serial numbers + consistent colors).

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

        # Update all values that are mapped to devices
        for dev_no, dev_item in self.dev_items.items():
            info = dev_info.get(dev_no, {})
            sn = info.get("serial", None)
            ok = info.get("ok", False)

            dev_item.setText(2, "SN ?" if sn is None else f"SN {sn}")

            if ok:
                self._set_item_row_color(dev_item, None, is_error=False)
                for i in range(dev_item.childCount()):
                    self._set_item_row_color(dev_item.child(i), None, is_error=False)
            else:
                self._set_item_row_color(dev_item, None, is_error=True)
                for i in range(dev_item.childCount()):
                    self._set_item_row_color(dev_item.child(i), None, is_error=True)
    
    def _set_item_row_color(self, item: QtWidgets.QTreeWidgetItem, color: QColor | None, is_error: bool):
        cols = self.tree.columnCount()

        if is_error:
            bg = QBrush(QColor("#FDECEC"))
            fg = QBrush(QColor("#8A1F1F"))
            for c in range(cols):
                item.setBackground(c, bg)
                item.setForeground(c, fg)
            return

        if color is None:
            for c in range(cols):
                item.setBackground(c, QBrush())
                item.setForeground(c, QBrush())
            return

        bg = QBrush(color)
        r, g, b, _ = color.getRgb()
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        fg = QBrush(QColor("#111" if lum > 150 else "#FFF"))
        for c in range(cols):
            item.setBackground(c, bg)
            item.setForeground(c, fg)

    def resizeEvent(self, event):
        # ---------------------------------------------------------------------
        # Recompute scaling on window resize
        # ---------------------------------------------------------------------
        super().resizeEvent(event)
        self.apply_scale()

    def apply_scale(self):
        w = max(400, self.centralWidget().width())
        base = max(9, min(13, int(w / 85)))

        self.tree.setFont(QFont(self.tree.font().family(), base))
        self.status.setFont(QFont(self.status.font().family(), max(9, base)))
        self.dev_status.setFont(QFont(self.dev_status.font().family(), max(9, base - 1)))

        if self.btn_record:
            self.btn_record.setFont(QFont(self.btn_record.font().family(), max(10, base), QFont.Bold))
            self.btn_record.setMinimumHeight(max(34, base * 3))

        self.btn_zero.setFont(QFont(self.btn_zero.font().family(), max(10, base), QFont.Bold))
        self.btn_zero.setMinimumHeight(max(32, base * 3))
        self.btn_zero.setMinimumWidth(max(110, base * 8))

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