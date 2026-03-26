# Architecture


## Overview

GSV86CAN Viewer is a Windows desktop application for monitoring and logging measurement data from GSV CAN-based measurement amplifiers.

The application is intentionally designed as a **runtime viewer and logger**, not as a device configuration tool.

Its primary responsibilities are:

- activate already configured devices on the CAN bus
- display live values in the UI
- log measurement data to CSV or XLSX
- provide runtime actions such as zero/tare
- validate the local YAML configuration before startup

The application does **not** assign, repair, or rewrite CAN IDs on devices.

---

## Architectural Principle

A key design decision of this project is the strict separation between:

- **device configuration**
- **runtime data acquisition**

### Device configuration

CAN endpoint configuration must be completed **before** devices are connected together on a shared CAN bus.

This includes in particular:

- `cmd_id`
- `answer_id`
- `value_id`
- CAN baud rate

This task belongs to a dedicated configuration workflow/tool, for example:

- [StartupCAN](https://github.com/me-systeme/StartupCAN)

### Runtime acquisition

GSV86CAN Viewer assumes that devices are already configured correctly and can safely operate together on the bus.

At runtime, the Viewer only:

- reads the configuration from `config.yaml`
- activates devices using the configured IDs
- reads selected device metadata for diagnostics
- starts acquisition
- displays and records data

---

## Why the Viewer Does Not Reconfigure CAN Settings

This is an intentional design decision.

If multiple devices are connected to the same CAN bus and two devices share the same `value_id`, the collision already exists at bus level.

That collision can occur:

- immediately after power-up
- immediately after connecting devices to the bus
- before the Viewer is started

Because of that, runtime reconfiguration inside the Viewer would not be a reliable or conceptually clean solution.

Instead, the system requires that CAN settings are already valid **before shared bus operation begins**.

This keeps the Viewer:

- simpler
- more deterministic
- easier to reason about
- safer for measurement operation

---

## CAN Configuration Assumptions

The Viewer assumes the following about all connected devices:

- all devices are configured for the same bus baud rate
- all `cmd_id` values are unique
- all `answer_id` values are unique
- no CAN ID is reused across command and answer endpoints
- devices are already safe to operate together on the same CAN bus

Recommended device-side invariant:

- `value_id = answer_id`

The Viewer does not configure `value_id` from YAML.
Instead, it assumes that this has already been handled by the configuration workflow.

For diagnostics, the Viewer may read the device-side `value_id` via DLL calls and display it in the UI.
This is a read-only diagnostic feature and does not modify the device state.

---

## Configuration Layer

The configuration is loaded from `config.yaml` by `config.py`.

### Responsibilities of `config.py`

- read and normalize YAML values
- parse CAN IDs from hexadecimal or decimal form
- parse numeric sensor values from strings with units
- expose module-level constants for runtime use
- validate configuration consistency before the application starts

### Current validation rules

For `devices.config`, the loader validates that:

- `dev_no` values are unique
- `cmd_id != answer_id` for each device
- all configured CAN IDs are globally unique across all devices

This validation does **not** prove that the real hardware matches the YAML.
It only ensures that the local configuration file is internally consistent and plausible for multi-device runtime operation.

---

## Runtime Layer

The runtime path is split into UI code and acquisition code.

### `main_window.py`

Responsible for:

- building and updating the Qt UI
- showing device/channel values
- showing configured answer CAN IDs from YAML
- showing device-read value CAN IDs for diagnostics
- handling user actions such as recording and zeroing
- showing status and logging warnings

### `reader_thread.py`

Responsible for:

- activating configured devices
- reading selected device metadata during startup
  - serial number
  - value CAN ID
- reading buffered samples from the DLL
- computing latest channel values
- computing per-device update rates
- executing hardware-affecting runtime commands inside the acquisition thread

This separation ensures that:

- hardware access is isolated from the UI thread
- the UI remains responsive
- all periodic DLL communication is centralized

---

## Logging Layer

Logging is handled separately from live acquisition.

### Design goals

- logging rate should be independent of device sampling frequency
- logging should support both convenience and diagnostic use cases
- missing data should be visible when required

### Logging modes

#### `hold_last`

- missing values are filled with the last known value
- useful for complete tables and spreadsheet workflows
- may hide missing samples or device dropouts

#### `strict_samples`

- only values received within the current logging interval are written
- missing values remain empty
- useful for debugging CAN timing and data completeness

### Logging warnings

In `strict_samples` mode, the UI can display a temporary warning when fresh values are missing during a logging interval.

This warning is intentionally treated as:

- a data-quality/runtime indication
- not as a CAN configuration repair mechanism

---

## Device and Sensor Model

The YAML configuration separates:

- device communication settings
- sensor metadata
- sensor-to-channel mapping

### Devices

Each device entry defines:

- `dev_no`
- `cmd_id`
- `answer_id`
- optional frequency override

### Sensors

Sensor metadata provides:

- nominal load
- characteristic value

These values are used to compute scaling factors during startup.

### Mapping

`sensor_mapping` connects a sensor number to a specific device/channel pair.

This allows scaling logic to stay independent from the UI representation.

---

## Error Handling Philosophy

The project aims to be robust in partially failing environments.

Examples:

- one device may fail while others continue running
- optional metadata reads may fail without aborting the entire startup
- missing values may be logged without crashing the application
- invalid YAML configuration fails early at startup
- runtime acquisition and UI logic remain isolated

The design prefers:

- early validation for configuration errors
- clear runtime status reporting
- no hidden reconfiguration of hardware state inside the Viewer

---

## Summary

In short, the architecture follows this rule:

> Configure devices first, then monitor them.

This leads to a clean separation of concerns:

- **Startup/configuration tools** prepare CAN-capable devices for shared bus operation
- **GSV86CAN Viewer** performs runtime monitoring, visualization, and logging on top of that prepared system