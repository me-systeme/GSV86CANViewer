"""
reader_thread.py

Background acquisition thread for the GSV86CAN devices.

This module contains ReaderThread, a QThread that:
- Initializes and starts all configured devices (activate, set ranges/scales, set frequency, start TX).
- Continuously reads buffered samples from the centralized DLL buffer.
- Extracts the latest value per channel and maps them into the grid positions.
- Computes per-device update rates (Hz) over a sliding time window.
- Executes user-triggered commands (e.g., "Zero all") safely inside the acquisition thread.
"""

import time
from collections import deque

from PyQt5 import QtCore

from gsvgrid.config import (
    DEVICE_CONFIG,
    GRID_MAP,
    MYBUFFERSIZE,
    SENSORS_BY_NO,
    SENSOR_BY_DEVCH,
    LOAD_DEFAULT_SETTINGS,
    AUTO_SENSITIVITY_ADJUSTMENT,
)
from gsvgrid.utils import extract_latest_channels




class ReaderThread(QtCore.QThread):
    """
    QThread that manages device initialization and continuous acquisition.

    What happens in this thread:
    - During startup:
      - Query DLL version (informational).
      - For each configured device:
        - 1. Activate: Activate the device on CAN.
        - 2. Load default settings: Sets device settings to default settings (optional)
        - 3. Get serial number: Read the device serial number (optional).
        - For each active channel:
          - 4. Read sensitivity: Read input type and range.
          - 5. Auto-increase sensitivity: Auto-increase bridge range if the sensor characteristic value exceeds the configured range. (optional)
          - 6. Write user scale: Compute and write a user scale factor based on sensor data and input range.
        - 7. Set frequency: Set the device measurement frequency (if configured).
        - 8. Start streaming: Start TX streaming.
      - Emit a dev_info summary to the UI (serial/ok/error per dev_no).

    - During the acquisition loop:
      - Handle pending user commands from the GUI (e.g., zero request).
      - Read buffered data for each active device.
      - Extract the latest channel values and map them onto the grid positions.
      - Compute per-device update rates (Hz) in a sliding time window.
      - Emit the latest values + rates to the UI.

    Parameters
    ----------
    gsv:
        GSV DLL wrapper instance providing methods like activate(), read_multiple(), start_tx(), etc.
    parent:
        Optional Qt parent object.

    Returns
    -------
    None
    """

    valuesUpdated = QtCore.pyqtSignal(dict,dict) # (grid_values, rates_by_dev)
    statusUpdated = QtCore.pyqtSignal(str)       # status text for the UI
    deviceInfoUpdated = QtCore.pyqtSignal(dict)  # dev_no -> {"serial":..., "ok": bool, "error": str|None}


    def __init__(self, gsv, parent=None):
        super().__init__(parent)

        # ---------------------------------------------------------------------
        # External dependencies
        # ---------------------------------------------------------------------
        self.gsv = gsv

        # ---------------------------------------------------------------------
        # Thread control flags / state
        # ---------------------------------------------------------------------
        self._running = True
        self.active_devices = []  # list[int]: devices that were successfully started

        # ---------------------------------------------------------------------
        # Update-rate measurement (sliding window of timestamps per device)
        # ---------------------------------------------------------------------
        self.updates_by_dev = {}   # dev_no -> deque[float] (monotonic timestamps)
        self.rate_window_s = 1.0   # window length in seconds used to compute Hz
        
        # ---------------------------------------------------------------------
        # Command channel from GUI -> thread (thread-safe)
        # ---------------------------------------------------------------------
        self._zero_requested = False
        self._cmd_lock = QtCore.QMutex()

    def stop(self):
        """
        Request the thread to stop.

        What happens:
        - Sets the internal running flag to False.
        - The run() loop exits on the next iteration.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self._running = False

    @QtCore.pyqtSlot()
    def request_zero_all(self):
        """
        Request "zero all" from the GUI.

        What happens:
        - Sets a flag that will be processed inside the acquisition loop.
        - This ensures that all DLL calls (set_zero) happen in the ReaderThread.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self._cmd_lock.lock()
        try:
            self._zero_requested = True
        finally:
            self._cmd_lock.unlock()

    def run(self):
        """
        Thread entry point.

        What happens:
        - Initializes devices (activate, configure ranges/scales, set frequency, start TX).
        - Enters the acquisition loop and continuously reads and emits values.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        # ---------------------------------------------------------------------
        # Startup: initialize device list + device info structure for the UI
        # ---------------------------------------------------------------------
        self.active_devices = []
        dev_info = {}  # dev_no -> {"serial":..., "ok": bool, "error": str|None}

        # ---------------------------------------------------------------------
        # DLL version (informational)
        # ---------------------------------------------------------------------
        try:
            self.statusUpdated.emit(f"DLL Version: {self.gsv.dll_version()}")
        except Exception as e:
            self.statusUpdated.emit(f"Init Fehler (DLL): {e}")
            return

        # ---------------------------------------------------------------------
        # Initialize devices one-by-one (robust against partial failures)
        # ---------------------------------------------------------------------
        for d in DEVICE_CONFIG:
            dev_no = d["dev_no"]

            try:
                # Activate device and obtain number of active channels (chan)
                chan = self.gsv.activate(dev_no, d["cmd_id"], d["answer_id"])   
                
                if LOAD_DEFAULT_SETTINGS:
                    # -------------------------------------------------------------
                    # Load default settings (optional)
                    # -------------------------------------------------------------
                    try:
                        self.gsv.load_settings(dev_no, 1)
                        self.statusUpdated.emit(f"Dev {dev_no}: loadSettings(dataset={1}) OK")
                    except Exception as e:
                        # not fatal, but AoutScale/range might be inconsistent if settings not loaded
                        self.statusUpdated.emit(f"WARN: Dev {dev_no}: loadSettings(dataset={1}) failed: {e}")

                saturation_error = False
                freq_error = None

                # Serial number is optional; failure must not kill acquisition
                try:
                    sn = self.gsv.get_serial_no(dev_no)
                except Exception:
                    sn = None

                # -------------------------------------------------------------
                # Per-channel range + scaling setup (optional but recommended)
                # -------------------------------------------------------------
                try:
                    for ch in range(1, int(chan) + 1): 
                        # Read currently active input type and input range
                        try:
                            in_type, rng = self.gsv.get_in_type_range(dev_no, ch)

                            # Convert raw range to mV/V when bridge type is used
                            inputrange_mvv = (rng / 100.0) if (in_type in (0, 1, 2) and rng > 50) else (rng if in_type in (0, 1, 2) else None)

                            if inputrange_mvv is None:
                                self.statusUpdated.emit(
                                    f"WARN: Dev {dev_no} Ch{ch}: in_type={in_type} is not a bridge type."
                                )
                                continue

                            aout_scale = self.gsv.read_aout_scale(dev_no, ch)
                            if aout_scale <= 0:
                                self.statusUpdated.emit(
                                    f"WARN: Dev {dev_no} Ch{ch}: Aoutscale is 0."
                                )
                                continue

                            sensitivity = inputrange_mvv / aout_scale
                            
                            self.statusUpdated.emit(
                                f"Dev {dev_no} Ch{ch}: inputrange={inputrange_mvv:g} mV/V, "
                                f"AoutScale={aout_scale:g}, sensitivity={sensitivity:g}"
                            )

                        except Exception as e:
                            # Note: inputrange_mvv might not be set if the read fails; keep the message safe.
                            self.statusUpdated.emit(
                                f"WARN: Dev {dev_no} Ch{ch}: failed to read input type/range: {e}"
                            )
                            continue

                        # -----------------------------------------------------
                        # Map device/channel -> sensor configuration
                        # -----------------------------------------------------
                        ch_idx0 = ch - 1
                        sensor_no = SENSOR_BY_DEVCH.get((dev_no, ch_idx0))

                        if sensor_no is None:
                            # No sensor mapping for this channel -> skip scaling
                            continue  

                        sensor = SENSORS_BY_NO.get(sensor_no)
                        if not sensor:
                            self.statusUpdated.emit(
                                f"WARN: Dev {dev_no} Ch{ch}: sensor {sensor_no} not found in config."
                            )
                            continue

                        nominal_kn = float(sensor["nominal_load_kn"])
                        char_mvv = float(sensor["char_mvv"])
                    
                        # Sanity check for sensor characteristic value
                        if char_mvv <= 0:
                            self.statusUpdated.emit(
                                f"WARN: Sensor {sensor_no}: invalid characteristic value (<= 0). Skipping scaling."
                            )
                            continue

                        # -----------------------------------------------------
                        # Compute / adjust sensitivity via AoutScale, respecting:
                        # - AoutScale must be >= 1
                        # - if target sensitivity requires AoutScale < 1, increase inputrange_mvv first
                        # sensitivity = inputrange_mvv / AoutScale
                        # -----------------------------------------------------
                        try: 
                            SENS_STEPS = [1.0, 2.0, 3.0, 4.0, 5.0, 8.0]
                            BRIDGE_RANGES_MVV = [1.0, 2.0, 4.0, 8.0]
                            
                            def _next_step(char_mvv: float) -> float:

                                target = char_mvv * 1.02
                                for s in SENS_STEPS:
                                    if s + 1e-12 >= target:
                                        return s
                                return SENS_STEPS[-1]
                            
                            def _pick_next_range_mvv(curr_range: float) -> float:
                                """
                                Pick the smallest supported bridge range >= characteristic_mvv (with safety margin).

                                Parameters
                                ----------
                                characteristic_mvv : float
                                    Sensor characteristic value in mV/V.

                                Returns
                                -------
                                float
                                    Selected bridge range (mV/V) from BRIDGE_RANGES_MVV.
                                """
                                for r in BRIDGE_RANGES_MVV:
                                    if r > curr_range + 1e-12:
                                        return r
                                return BRIDGE_RANGES_MVV[-1] 
                            
                            if AUTO_SENSITIVITY_ADJUSTMENT:
                                try:
                                    # If we have a bridge range and it is too small, try to increase it
                                    if sensitivity + 1e-9 < char_mvv:
                                        target_sens = _next_step(char_mvv)

                                        # --- Ensure AoutScale can stay >= 1 ---
                                        # Need inputrange_mvv >= target_sens, otherwise AoutScale = inputrange/target < 1
                                        if inputrange_mvv + 1e-12 < target_sens:
                                            # increase input range until >= target_sens (or until max)
                                            old_range = inputrange_mvv
                                            new_range_mvv = inputrange_mvv
                                            while new_range_mvv + 1e-12 < target_sens:
                                                next_r = _pick_next_range_mvv(new_range_mvv)
                                                if next_r <= new_range_mvv + 1e-12:
                                                    break
                                                new_range_mvv = next_r

                                            if new_range_mvv <= inputrange_mvv + 1e-12 and inputrange_mvv + 1e-12 < target_sens:
                                                # can't increase further
                                                self.statusUpdated.emit(
                                                    f"WARN: Dev {dev_no} Ch{ch}: cannot reach target sensitivity {target_sens:g} "
                                                    f"because inputrange_mvv stuck at {inputrange_mvv:g}."
                                                )
                                            else:
                                                self.gsv.write_input_range(dev_no, chan=ch, in_type=in_type, mv_per_v=new_range_mvv)

                                                # re-read range and update inputrange_mvv
                                                in_type2, rng2 = self.gsv.get_in_type_range(dev_no, ch)
                                                inputrange_mvv2 = (rng2 / 100.0) if (in_type2 in (0, 1, 2) and rng2 > 50) else (rng2 if in_type2 in (0, 1, 2) else None)

                                                if inputrange_mvv2 is None:
                                                    self.statusUpdated.emit(
                                                        f"WARN: Dev {dev_no} Ch{ch}: sensor {sensor_no} mapped but in_type={in_type} is not a bridge type."
                                                    )
                                                    continue
                                                
                                                self.statusUpdated.emit(
                                                    f"Dev {dev_no} Ch{ch}: increased inputrange {inputrange_mvv:g} -> {inputrange_mvv2:g} mV/V "
                                                    f"to allow target sensitivity {target_sens:g} with AoutScale>=1"
                                                )

                                                if inputrange_mvv2 <= old_range + 1e-12:
                                                    self.statusUpdated.emit(
                                                        f"WARN: Dev {dev_no} Ch{ch}: inputrange write seems ineffective "
                                                        f"(still {inputrange_mvv2:g} mV/V). Check *100 encoding in write_input_range."
                                                    )

                                                inputrange_mvv = float(inputrange_mvv2)

                                        # Now compute new AoutScale (clamp to >= 1)
                                        # If inputrange_mvv still < target_sens, this would still go <1; clamp prevents invalid.
                                        new_aout_scale = inputrange_mvv / target_sens
                                        if new_aout_scale < 1.0:
                                            # clamp
                                            new_aout_scale = 1.0
                                            # NOTE: with clamp, achieved sensitivity will be inputrange_mvv/1 = inputrange_mvv (may be < target_sens)
                                            self.statusUpdated.emit(
                                                f"WARN: Dev {dev_no} Ch{ch}: computed AoutScale would be <1; clamped to 1. "
                                                f"Achievable sensitivity limited to {inputrange_mvv:g}."
                                            )
                                        
                                        self.gsv.write_aout_scale(dev_no, ch, new_aout_scale)

                                        # re-read to confirm
                                        aout_scale2 = self.gsv.read_aout_scale(dev_no, ch)
                                        if aout_scale2 <= 0:
                                            self.statusUpdated.emit(
                                                f"WARN: Dev {dev_no} Ch{ch}: sensor {sensor_no} mapped but Aoutscale is 0."
                                            )
                                            continue
                                        
                                        sensitivity2 = inputrange_mvv / aout_scale2

                                        self.statusUpdated.emit(
                                            f"Dev {dev_no} Ch{ch}: sensitivity adjust {sensitivity:.6g} -> {sensitivity2:.6g} "
                                            f"(target {target_sens:g}) using AoutScale {aout_scale:.6g} -> {aout_scale2:.6g}"
                                        )

                                        aout_scale = aout_scale2
                                        sensitivity = sensitivity2

                                except Exception as e:
                                    self.statusUpdated.emit(
                                        f"WARN: Dev {dev_no} Ch{ch}: sensitivity/AoutScale adjustment failed: {e}"
                                    )

                            # If still too small: warn and mark device as not ok (limited measuring range)
                            if sensitivity + 1e-9 < char_mvv:
                                limited_kn = (nominal_kn / char_mvv) * sensitivity
                                saturation_error = f"WARNING: measuring range limited to {limited_kn:g} kN (sensor {sensor_no})"
                                dev_info[dev_no] = {"serial": sn, "ok": False, "error": saturation_error}

                                self.statusUpdated.emit(
                                    f"WARN: Dev {dev_no} Ch{ch}: effective sensitivity {sensitivity:g} mV/V < "
                                    f"sensor char {char_mvv:g} mV/V -> saturation risk. "
                                    f"Effective max ≈ {limited_kn:g} kN."
                                )
                            
                            scale = (nominal_kn / char_mvv) * sensitivity
                            self.gsv.write_user_scale(dev_no, ch, scale)

                            self.statusUpdated.emit(
                                f"Scale OK: sensor {sensor_no} (Dev {dev_no} Ch{ch}) "
                                f"range={inputrange_mvv:.6g} mV/V, AoutScale={aout_scale:.6g}, "
                                f"sens={sensitivity:.6g} -> user_scale={scale:.6g}"
                            )

                        except Exception as e:
                            self.statusUpdated.emit(
                                f"WARN: Dev {dev_no} Ch{ch}: sensitivity/AoutScale scaling failed: {e}"
                            )
                            continue

                except Exception as e:
                    self.statusUpdated.emit(f"WARN: Dev {dev_no}: failed during input-range/scaling setup: {e}")

                # -------------------------------------------------------------
                # Frequency setup (optional)
                # -------------------------------------------------------------
                freq = d.get("frequency", None)
                if freq is not None:
                    try:
                        self.gsv.set_frequency(dev_no, float(freq))
                        self.statusUpdated.emit(f"Dev {dev_no}: setFrequency({freq} Hz) OK")
                    except RuntimeError as e:
                        freq_error = f"FAIL setFrequency({freq} Hz): {e}"
                        dev_info[dev_no] = {"serial": sn, "ok": False, "error": freq_error}
                        self.statusUpdated.emit(
                            f"FAIL: Dev {dev_no} setFrequency({freq} Hz) CMD=0x{d['cmd_id']:03X} ANS=0x{d['answer_id']:03X}: {e}"
                        )
                
                # -------------------------------------------------------------
                # Start TX streaming
                # -------------------------------------------------------------
                self.gsv.start_tx(dev_no)
                
                # If no hard error was recorded, mark as OK
                if freq_error == None and saturation_error == False:
                    dev_info[dev_no] = {"serial": sn, "ok": True, "error": None}
                    self.statusUpdated.emit(
                        f"OK: Dev {dev_no} CMD=0x{d['cmd_id']:03X} ANS=0x{d['answer_id']:03X} channels={chan}"
                    )
                
                # Add to active devices (even if dev_info says not-ok, device may still stream data)
                self.active_devices.append(dev_no)

            except Exception as e:
                # Device unreachable or misconfigured: skip it
                dev_info[dev_no] = {"serial": None, "ok": False, "error": str(e)}
                self.statusUpdated.emit(
                    f"FAIL Dev {dev_no} CMD=0x{d['cmd_id']:03X} ANS=0x{d['answer_id']:03X}: {e}"
                )
        
        # ---------------------------------------------------------------------
        # Emit startup summary
        # ---------------------------------------------------------------------
        failed_txt = [
            f"{dev_no} ({dev_info[dev_no].get('error','?')})"
            for dev_no in dev_info
            if not dev_info[dev_no].get("ok")
        ]
        if failed_txt:
            self.statusUpdated.emit(
                f"StartTX OK (active={len(self.active_devices)}/{len(DEVICE_CONFIG)}), "
                f"Failed devices: " + " | ".join(failed_txt)
            )
        else:
            self.statusUpdated.emit(
                f"StartTX OK (active={len(self.active_devices)}/{len(DEVICE_CONFIG)})"
            )

        # Send device info to UI (serial numbers, OK flags, errors)
        self.deviceInfoUpdated.emit(dev_info)

        if not self.active_devices:
            self.statusUpdated.emit(
                "No active devices. Check CAN IDs, wiring, CAN baudrate, and device streaming settings."
            )
            # Keep running to allow clean shutdown; UI will show 0 Hz / no values

        # ---------------------------------------------------------------------
        # Acquisition loop
        # ---------------------------------------------------------------------
        max_items = MYBUFFERSIZE * 6

        while self._running:
            # -------------------------------------------------------------
            # Process GUI commands (zero request)
            # -------------------------------------------------------------
            do_zero = False
            self._cmd_lock.lock()
            try:
                if self._zero_requested:
                    do_zero = True
                    self._zero_requested = False
            finally:
                self._cmd_lock.unlock()

            if do_zero:
                for dev_no in self.active_devices:
                    try:
                        # Chan=0 is assumed to mean "all channels" (per DLL header expectation)
                        self.gsv.set_zero(dev_no, 0)
                    except Exception as e:
                        self.statusUpdated.emit(f"FAIL: zero request for Dev {dev_no}: {e}")
                
                self.statusUpdated.emit("Zero OK: all active devices have been zeroed")

                # Optional: clear rate window so the displayed Hz restarts cleanly
                self.updates_by_dev = {}

            # -------------------------------------------------------------
            # Read devices and keep "latest value per channel"
            # -------------------------------------------------------------
            latest_by_dev = {}

            for dev_no in self.active_devices:
                data = self.gsv.read_multiple(dev_no, max_items)
                if data is None:
                    continue

                latest = extract_latest_channels(data, channels=3)
                if latest is None:
                    continue

                now = time.monotonic()
                dq = self.updates_by_dev.setdefault(dev_no, deque())
                dq.append(now)
                latest_by_dev[dev_no] = latest

            # -------------------------------------------------------------
            # Map latest device values into grid positions
            # -------------------------------------------------------------
            out = {}
            if latest_by_dev:
                for pos, (dev_no, ch_idx) in GRID_MAP.items():
                    latest = latest_by_dev.get(dev_no)
                    if latest is None:
                        continue
                    if 0 <= ch_idx < len(latest):
                        out[pos] = latest[ch_idx]
            
            # -------------------------------------------------------------
            # Compute per-device update rates (Hz) over a sliding window
            # -------------------------------------------------------------
            rates_by_dev = {}
            now = time.monotonic()

            for dev_no in self.active_devices:
                dq = self.updates_by_dev.get(dev_no)
                if not dq:
                    rates_by_dev[dev_no] = 0.0
                    continue

                while dq and (now - dq[0]) > self.rate_window_s:
                    dq.popleft()

                rates_by_dev[dev_no] = len(dq) / self.rate_window_s
            
            # -------------------------------------------------------------
            # Emit latest values + rates to the UI
            # -------------------------------------------------------------
            if out:
                self.valuesUpdated.emit(out, rates_by_dev)

            # NOTE: This sleep controls the UI update cadence, not the device sampling rate.
            self.msleep(5)