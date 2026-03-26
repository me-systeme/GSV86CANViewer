# Changelog

## [1.2.0] - 2026-03-26

### Added
- Configuration validation for `devices.config`
  - Ensures all `dev_no` values are unique
  - Ensures `cmd_id` and `answer_id` differ per device
  - Ensures all CAN IDs are globally unique across all devices
- Device-side CAN diagnostics in the UI
  - Reads the device `value_id` via `get_can_settings()`
  - Displays `value_id` as a separate column next to the configured answer CAN ID
- Explicit CAN bus safety documentation
  - Added detailed section in README explaining required preconditions for multi-device operation
  - Added safety note directly in `config.yaml`
- New `ARCHITECTURE.md`
  - Documents system design decisions and separation of concerns
  - Explains why CAN configuration is handled outside the Viewer
  - Describes runtime assumptions and logging design

### Improved
- Clear separation between:
  - device configuration (external tools, e.g. [StartupCAN](https://github.com/me-systeme/StartupCAN))
  - runtime monitoring (Viewer)
- Better visibility of configured vs. device-read CAN information
- Documentation clarity for CAN setup and failure scenarios
- Overall robustness of configuration handling (fail-fast on invalid setups)

### Notes
- The Viewer does **not** configure or modify CAN settings
- All devices must be fully configured before being connected to a shared CAN bus
- Misconfigured CAN IDs (especially duplicate `value_id`) may lead to bus collisions before the application starts

## [1.1.0] - 2026-03-20

### Added
- New logging mode: `strict_samples`
  - Writes only values received within each logging interval
  - Missing values are left empty instead of being filled
- Live logging warning system
  - Displays warning when channels have no fresh values
  - Automatically clears when data flow recovers
- Config option `logging.mode`
  - Supports `hold_last` and `strict_samples`
- Config option `logging.warn_on_missing`
  - Enables/disables logging warnings

### Improved
- Logging behavior is now more transparent for debugging CAN/data issues
- Status bar handling improved:
  - Separation between base status and temporary logging warnings
  - Warning no longer permanently overwrites system status

### Fixed
- Logging warning no longer persists after data recovers
- Improved internal state consistency for status messages

## [1.0.0] - 2026-03-19
### Added
- Initial release of GSV86CAN Viewer
- Tree-based live measurement view
- YAML configuration support
- Logging (CSV / XLSX)
- Zero / tare functionality


