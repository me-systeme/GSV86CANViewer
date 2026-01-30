# 🔷 GSV86CAN Viewer – Tree View Measurement Monitor & Logger

## Overview

**GSV86CAN Viewer** is a lightweight Windows desktop application (Python / PyQt5) for monitoring and logging measurement data from GSV-6 / GSV-8 CAN-based measurement amplifiers.

The application:

* Communicates with one or more GSV devices over **CAN bus** using the vendor DLL
* Displays live measurement values in a **tree view** grouped by **Device → Channel**
* Supports **zeroing (tare)** of all devices
* Logs measurement data to **CSV or Excel (XLSX)** files
* Uses a **YAML configuration file** for CAN IDs and device options

The software is designed to be:

* Robust against missing or misconfigured devices
* Easily extensible (new devices, sensors, layouts)
* Clear and deterministic for experimental and test‑bench use

<p align="center">
  <img src="screenshots/main_window.png" alt="GSV Grid – Main Window" width="900">
</p>

---

## ✨ Application Features

### 🌳 Live Tree View (Device → Channel → Value)

The main view shows a **tree list**:
  * one top-level entry per device (from `config.yaml`)
  * one child entry per device channel (channel count detected at runtime)
Each channel row displays:
  * Channel number (1-based)
  * Current measurement value (e.g. kN)
The device rows show:
  * Device number
  * CAN Answer ID
  * Serial number (if readable)
Channel count is determined dynamically via `chan = gsv.activate(...)`.
You do **not** need to configure a channel mapping.

---

### 🎨 Device Color Coding

* Devices with configuration or communication errors are highlighted in **red**.

This makes it easy to visually identify:

* Which devices failed to initialize correctly

---

### ⚖️ Zero / Tare Function

* A **"Zero" button** is located in the bottom‑right corner of the grid.
* When pressed, a confirmation dialog is shown.
* If confirmed, **all active devices are zeroed** via the DLL.

Technical notes:

* Zeroing is executed safely inside the acquisition thread
* The UI immediately updates values to zero for visual feedback

---

### ⏺️ Recording / Logging

If logging is enabled in the YAML file:

* A **REC button** is shown
* Recording can be started/stopped at runtime

Supported formats:

* `.csv` (streaming write)
* `.xlsx` (written when recording stops)

Features:

* Automatic filename increment (`data.xlsx → data_001.xlsx → data_002.xlsx`)
* User confirmation if a file already exists
* Configurable logging rate (e.g. 1 sample per second)

Notes:

* Logging rate is **independent** of the device measurement frequency.
* Logging writes **complete rows** using last-known values.
* On startup, some channels may need a short time until they deliver their first value (depending on device streaming / CAN traffic).
---

### 📡 Status & Device Information

At the bottom of the window:

* **Status line** shows initialization messages, warnings, and errors
* **Devices line** shows live update rates per CAN ID (Hz)

This helps diagnose:

* CAN communication issues
* Incorrect baud rates or IDs
* Devices that stopped sending data

---

### 🧩 YAML Configuration File

All application behavior is controlled by `config.yaml`.
The configuration file controls:
* CAN baud rate and DLL buffer size
* Device CAN IDs (cmd/answer)
* Optional settings (frequency, scaling, sensor mapping)
* Logging

### ⚙️ 1. `dll`

```yaml
dll:
  mybuffersize: 300
  canbaud: 250000
```

| Key            | Description                             |
| -------------- | --------------------------------------- |
| `mybuffersize` | Internal DLL read buffer size           |
| `canbaud`      | CAN bus baud rate (must match hardware) |

---

### 💾 2. `logging`

```yaml
logging:
  file: "messdaten.xlsx"
  rate_hz: 1.0
```

| Key       | Description                                           |
| --------- | ----------------------------------------------------- |
| `file`    | Log file path (`.csv` or `.xlsx`). Empty = no logging |
| `rate_hz` | Logging rate in samples per second                    |

Notes:

* Logging is independent of device frequency
* Values are sampled from the latest available data

---

### 🔌 5. `devices`

```yaml
devices:
  frequency: 10
  load_default_settings: false
  auto_sensitivity_adjustment: false
  config:
    - dev_no: 1
      cmd_id: "0x0C8"
      answer_id: "0x0C9"
```

| Key                           | Description                                                  |
| ----------------------------- | ------------------------------------------------------------ |
| `frequency`                   | Global measurement frequency (Hz, ≤ 100 recommended)         |
| `load_default_settings`       | Loads factory defaults via DLL before reading ranges/scales. |   
| `auto_sensitivity_adjustment` | Automatically increases sensitivity of the devices           |
| `dev_no`                      | Logical device number                                        |
| `cmd_id`                      | CAN command ID                                               |
| `answer_id`                   | CAN answer ID                                                |

Per‑device frequency overrides are supported by setting `frequency` inside a device entry.

---

### 🧪 6. `sensors`

Defines physical sensor properties.

```yaml
sensors:
  - sensor_no: 1
    nominal_load: "250 kN"
    char_value: "3.15 mV/V"
```

Used to:

* Compute scaling factors
* Automatically adjust input ranges

---

### 7. `sensor_mapping`

Maps sensors to device channels.

```yaml
sensor_mapping:
  - sensor_no: 1
    channel: [1, 0]
```

Meaning:

* Sensor 1 is connected to device 1, channel 0

---

## 🚀 Getting Started

## 📦 Requirements

* **Windows** (DLL‑based)
* **Python 3.10+** 32 bit (recommended)
* Installed CAN hardware (PCAN)
* GSV CAN DLL (`GSV86CAN.dll`)

### Python Dependencies

Install required packages:

```bash
pip install PyQt5 pyyaml openpyxl
```

---

### Project Structure

```
project_root/
│
├─ config.yaml
├─ GSV86CAN.dll
├─ src/
│  └─ gsv86canviewer/
│     ├─ main.py
│     ├─ main_window.py
│     ├─ reader_thread.py
│     ├─ recorder.py
│     ├─ gsv86can.py
│     ├─ utils.py
│     └─ config.py
```

---

## ▶️ Running the Application

Start the application by running

```bash
python run.py
```

On startup:

1. Devices are activated (CAN IDs from config)
2. Channel count is detected automatically per device (`activate()` result)
3. Streaming starts and the tree view updates as values arrive

---

## 🧱 Building a Single-File Windows Executable (Onefile)

The application can be packaged into a single standalone `.exe` using PyInstaller.

### Characteristics

- The resulting executable is one single file
- The vendor DLL (`GSV86CAN.dll`) is embedded inside the executable
- At runtime, PyInstaller extracts the DLL to a temporary directory and loads it automatically
- The configuration file `config.yaml` remains external and must be located next to the `.exe`

### Build Command

Run the following command from the project root directory:

```
python -m PyInstaller --noconfirm --clean --windowed --onefile  --paths "src"  --add-binary "GSV86CAN.dll;."  run.py
```

### Resulting Files

After a successful build, the dist/ directory will contain:
```
dist/
└─ run.exe
```

To run the application, place config.yaml next to the executable:
```
run.exe
config.yaml
```

---

## Design Notes

* All DLL calls are isolated in `gsv86can.py`
* All hardware access runs in a **QThread** (no UI blocking)
* UI logic is strictly separated from acquisition logic
* YAML config is loaded once and treated as read‑only
* Channel structure is **not configured** manually:
  * devices from YAML
  * channels from `activate()`

---

## License / Usage

This application is intended for **engineering, laboratory, and test‑bench use**.

Ensure that:

* CAN IDs do not conflict with other devices
* Frequencies stay within device limits
* Zeroing is performed only under safe conditions
