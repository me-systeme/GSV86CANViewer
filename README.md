# 🔷 GSV Grid – Measurement Visualization & Logging Application

## Overview

**GSV Grid** is a desktop application written in Python (PyQt5) for visualizing, configuring, and logging measurement data from **GSV‑6 / GSV‑8 CAN‑based measurement amplifiers**.

The application:

* Communicates with multiple GSV devices over **CAN bus** using the vendor DLL
* Displays live measurement values in a **grid (diamond) layout**
* Assigns **colors by device serial number** for intuitive visual grouping
* Allows **mirroring** of the grid layout
* Supports **zeroing (tare)** of all devices
* Logs measurement data to **CSV or Excel (XLSX)** files
* Is fully configurable via a **YAML configuration file**

The software is designed to be:

* Robust against missing or misconfigured devices
* Easily extensible (new devices, sensors, layouts)
* Clear and deterministic for experimental and test‑bench use

<p align="center">
  <img src="screenshots/main_window.png" alt="GSV Grid – Main Window" width="900">
</p>

---

## ✨ Application Features

### 📊 Live Grid View

* The main view shows a **diamond‑shaped grid** of measurement cells.
* Each cell corresponds to a logical grid position like `3/4`.
* Only positions listed as *active* in the configuration display live values.

Each **active grid cell** shows:

* Grid position (row/column)
* Device serial number (SN)
* CAN answer ID
* Current measurement value (kN)

Inactive cells show only their grid position.

---

### 🎨 Device Color Coding

* Each **unique device serial number** is assigned a distinct blue shade.
* All channels belonging to the same device share the same color.python 
* Devices with configuration or communication errors are highlighted in **red**.

This makes it easy to visually identify:

* Which channels belong to the same amplifier
* Which devices failed to initialize correctly

---

### 🔄 Mirrored View

* A **Mirror View** toggle allows flipping the grid horizontally.
* This is useful when the physical setup is mirrored relative to the screen.

The mirror state:

* Only affects the visual layout
* Does **not** affect device mapping or logging

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

* A **REC button** appears above the grid
* Recording can be started/stopped at runtime
* On startup, the user is asked whether recording should begin immediately

Supported formats:

* `.csv` (streaming write)
* `.xlsx` (written when recording stops)

Features:

* Automatic filename increment (`data.xlsx → data_001.xlsx → data_002.xlsx`)
* User confirmation if a file already exists
* Configurable logging rate (e.g. 1 sample per second)

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

### 🧱 3. `grid`

Defines the visual layout.

```yaml
grid:
  total_cols: 15
  row_cols:
    "1": [3, 7, 11]
    "2": [2, 4, 6, 8, 10, 12]
  active:
    - "1/2"
```

| Key          | Description                   |
| ------------ | ----------------------------- |
| `total_cols` | Total number of grid columns  |
| `row_cols`   | Column indices per grid row   |
| `active`     | List of active grid positions |

---

### 4. `grid_map`

Maps grid positions to device channels.

```yaml
grid_map:
  "1/2": [1, 0]
```

Meaning:

* `1/2` → Device 1, channel index 0 (0‑based)

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
│  └─ gsvgrid/
│     ├─ main.py
│     ├─ main_window.py
│     ├─ reader_thread.py
│     ├─ recorder.py
│     ├─ grid_cell.py
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

1. Devices are initialized
2. The user is asked whether recording should start immediately
3. Live data appears once CAN traffic is detected

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

---

## Extending the Application

Typical extensions:

* Additional sensor types
* New grid layouts
* Alternative color schemes
* Export formats (e.g. HDF5)
* Remote control / scripting interface

The codebase is intentionally modular to support these extensions.

---

## License / Usage

This application is intended for **engineering, laboratory, and test‑bench use**.

Ensure that:

* CAN IDs do not conflict with other devices
* Frequencies stay within device limits
* Zeroing is performed only under safe conditions
