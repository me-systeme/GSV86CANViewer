# Changelog

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


