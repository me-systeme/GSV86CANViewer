"""
config.py

YAML-based configuration loader for the GSV86CANViewer application.

This module provides:
- Helpers to parse common YAML value formats (hex CAN IDs, floats with units).
- A single load_config() function that reads and validates config.yaml.
- Module-level constants that are loaded once at import time and used throughout the app.

The returned configuration is normalized:
- Numeric strings are converted to int/float.
- CAN IDs can be specified as "0x..." or decimal strings.
- Mapping entries are converted into convenient Python structures.
"""
import sys
from pathlib import Path
import re

import yaml


# -----------------------------------------------------------------------------
# Parsing helpers
# -----------------------------------------------------------------------------
def _parse_hex(x):
    """
    Parse an integer that may be provided in different textual formats.

    What happens:
    - If value is an int: returned as-is.
    - If value is a string:
      - "0x..." is parsed as hexadecimal
      - otherwise parsed as decimal

    Parameters
    ----------
    value:
        int or str (e.g. 200, "0x0C8", "256")

    Returns
    -------
    int
        Parsed integer value.
    """
    if isinstance(x, int):
        return x
    if isinstance(x, str):
        s = x.strip().lower()
        return int(s, 16) if s.startswith("0x") else int(s)
    raise TypeError(f"Unsupported CAN ID value type: {type(x)}")

def _parse_float_with_unit(text: str) -> float:
    """
    Parse a float from a string that may contain units and comma/dot decimals.

    What happens:
    - Extracts the first numeric token, supporting:
      - optional sign
      - comma or dot decimal separator
      - optional decimal part
    - Ignores any units (e.g. "kN", "mV/V").

    Parameters
    ----------
    text : str
        Example inputs:
        - "3,15963 mV/V"
        - "250 kN"
        - "3.15"
        - "+1,0"

    Returns
    -------
    float
        Numeric value without units.

    Raises
    ------
    ValueError
        If text is None or no numeric token can be found.
    """
    if text is None:
        raise ValueError("Value is None")
    
    s = str(text).strip()

    # Keep digits, comma, dot, and sign; extract the first number-like substring
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", s)
    if not m:
        raise ValueError(f"Cannot parse numeric value from '{text}'")
    
    num = m.group(0).replace(",", ".")
    return float(num)


# -----------------------------------------------------------------------------
# Main configuration loader
# -----------------------------------------------------------------------------
def load_config(path: Path) -> dict:
    """
    Load and normalize the project configuration from a YAML file.

    What happens:
    - Reads YAML using yaml.safe_load().
    - Converts all required fields to expected Python types.
    - Normalizes nested configuration blocks into convenient structures:
      - DEVICE_CONFIG: list of dicts with numeric CAN IDs and float frequency
      - SENSORS_BY_NO: dict[int, sensor_info]
      - SENSOR_BY_DEVCH: dict[(dev_no, ch_idx0), sensor_no]
    - Applies defaults and validates values where appropriate:
      - logging.rate_hz defaults to 1.0 and must be > 0 if provided.

    Parameters
    ----------
    path : pathlib.Path
        Path to the YAML file (e.g. PROJECT_ROOT / "config.yaml").

    Returns
    -------
    dict
        Normalized configuration dictionary. Keys include:
        - MYBUFFERSIZE (int)
        - CANBAUD (int)
        - DEVICE_CONFIG (list[dict])
        - LOG_FILE (str|None)
        - LOG_RATE_HZ (float)
        - SENSORS_BY_NO (dict[int, dict])
        - SENSOR_BY_DEVCH (dict[tuple[int,int], int])

    Raises
    ------
    KeyError
        If required YAML keys are missing.
    ValueError
        If logging.rate_hz is provided but <= 0.
    """
    # -------------------------------------------------------------------------
    # Read YAML file
    # -------------------------------------------------------------------------
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # -------------------------------------------------------------------------
    # DLL block: required values
    # -------------------------------------------------------------------------
    mybuffersize = int(cfg["dll"]["mybuffersize"])
    canbaud = int(cfg["dll"]["canbaud"])

    # -------------------------------------------------------------------------
    # Devices block:
    # - Optional global frequency
    # - Optional startup flags (defaults = False)
    # - Per-device config entries
    # -------------------------------------------------------------------------
    devices_section = cfg.get("devices", {}) or {}

    global_freq = devices_section.get("frequency", None)
    global_freq = float(global_freq) if global_freq is not None else None
 
    load_default_settings = bool(devices_section.get("load_default_settings", False))
    auto_sensitivity_adjustment = bool(devices_section.get("auto_sensitivity_adjustment", False))

    device_config = []
    for d in devices_section["config"]:
        # Global frequency has priority; otherwise take per-device frequency
        if global_freq is not None:
            freq = global_freq
        else:
            freq = d.get("frequency", None)

        device_config.append({
            "dev_no": int(d["dev_no"]),
            "cmd_id": _parse_hex(d["cmd_id"]),
            "answer_id": _parse_hex(d["answer_id"]),
            "frequency": float(freq) if freq is not None else None,
        })

    # -------------------------------------------------------------------------
    # Logging block:
    # - file is optional (if missing/empty => logging UI disabled)
    # - rate_hz defaults to 1.0 and must be > 0
    # -------------------------------------------------------------------------
    log_file = None
    log_rate_hz = 1.0  # default: 1 sample per second
    log_mode = "strict_samples"
    log_warn_on_missing = True

    if isinstance(cfg.get("logging"), dict):
        lf = cfg["logging"].get("file")
        if isinstance(lf, str) and lf.strip():
            log_file = lf.strip()
        
            rhz = cfg["logging"].get("rate_hz", None)
            if rhz is not None:
                log_rate_hz = float(rhz)
                if log_rate_hz <= 0:
                    raise ValueError("logging.rate_hz must be > 0")
            
            mode = cfg["logging"].get("mode", "strict_samples")
            if mode not in ("hold_last", "strict_samples"):
                raise ValueError("logging.mode must be 'hold_last' or 'strict_samples'")
            log_mode = str(mode)

            log_warn_on_missing = bool(cfg["logging"].get("warn_on_missing", True))
    
    # -------------------------------------------------------------------------
    # Sensor metadata block: indexed by sensor_no
    # -------------------------------------------------------------------------
    sensors_by_no = {}
    for s in (cfg.get("sensors") or []):
        sensor_no = int(s["sensor_no"])
        nominal_load_kn = _parse_float_with_unit(s["nominal_load"])   # "250 kN" -> 250.0
        char_mvv = _parse_float_with_unit(s["char_value"])            # "3,15963 mV/V" -> 3.15963

        sensors_by_no[sensor_no] = {
            "sensor_no": sensor_no,
            "serial_number": int(s.get("serial_number")) if s.get("serial_number") is not None else None,
            "nominal_load_kn": float(nominal_load_kn),
            "char_mvv": float(char_mvv),
        }

    # -------------------------------------------------------------------------
    # Sensor mapping: (dev_no, ch_idx0) -> sensor_no
    # ch_idx0 is 0-based channel index (0..)
    # -------------------------------------------------------------------------
    sensor_by_devch = {}
    for m in (cfg.get("sensor_mapping") or []):
        sensor_no = int(m["sensor_no"])
        dev_no = int(m["channel"][0])
        ch_idx0 = int(m["channel"][1])
        sensor_by_devch[(dev_no, ch_idx0)] = sensor_no

    # -------------------------------------------------------------------------
    # Return normalized configuration
    # -------------------------------------------------------------------------
    return {
        "MYBUFFERSIZE": mybuffersize,
        "CANBAUD": canbaud,
        "DEVICE_CONFIG": device_config,
        "LOAD_DEFAULT_SETTINGS": load_default_settings,
        "AUTO_SENSITIVITY_ADJUSTMENT": auto_sensitivity_adjustment,
        "LOG_FILE": log_file,
        "LOG_RATE_HZ": log_rate_hz,
        "LOG_MODE": log_mode,
        "LOG_WARN_ON_MISSING": log_warn_on_missing,
        "SENSORS_BY_NO": sensors_by_no,
        "SENSOR_BY_DEVCH": sensor_by_devch,
    }

# -----------------------------------------------------------------------------
# Load global configuration once at import time
# -----------------------------------------------------------------------------

def _project_root() -> Path:
    """
    Determine the runtime root directory.

    - Dev run: project root (where config.yaml and GSV86CAN.dll live).
    - PyInstaller: directory next to the executable (dist/run).
    """
    if getattr(sys, "frozen", False):
        # When bundled, prefer the directory where the .exe resides.
        return Path(sys.executable).resolve().parent
    # Dev mode: this file is in .../src/gsv86canviewer/config.py -> parents[2] is project root.
    return Path(__file__).resolve().parents[2]

PROJECT_ROOT = _project_root()
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    # PyInstaller onefile extracts binaries here at runtime.
    DLL_PATH = Path(sys._MEIPASS) / "GSV86CAN.dll"
else:
    DLL_PATH = PROJECT_ROOT / "GSV86CAN.dll"

CONFIG = load_config(CONFIG_PATH)

MYBUFFERSIZE = CONFIG["MYBUFFERSIZE"]
CANBAUD = CONFIG["CANBAUD"]

DEVICE_CONFIG = CONFIG["DEVICE_CONFIG"]
LOAD_DEFAULT_SETTINGS = CONFIG.get("LOAD_DEFAULT_SETTINGS", False)
AUTO_SENSITIVITY_ADJUSTMENT = CONFIG.get("AUTO_SENSITIVITY_ADJUSTMENT", False)

LOG_FILE = CONFIG.get("LOG_FILE")
LOG_RATE_HZ = CONFIG.get("LOG_RATE_HZ", 1.0)
LOG_MODE = CONFIG.get("LOG_MODE", "strict_samples")
LOG_WARN_ON_MISSING = CONFIG.get("LOG_WARN_ON_MISSING", True)

# Convenience mapping: dev_no -> device config dict
DEVICE_BY_DEVNO = {d["dev_no"]: d for d in DEVICE_CONFIG}

SENSORS_BY_NO = CONFIG["SENSORS_BY_NO"]
SENSOR_BY_DEVCH = CONFIG["SENSOR_BY_DEVCH"]