# TODO

## Priority A – Architecture & Maintainability

* [ ] Split `ReaderThread.run()` into smaller, clearly defined methods

  * [ ] `_emit_dll_version()`
  * [ ] `_initialize_devices()`
  * [ ] `_initialize_single_device()`
  * [ ] `_configure_channel_scaling()`
  * [ ] `_apply_frequency()`
  * [ ] `_process_pending_commands()`
  * [ ] `_read_active_devices()`
  * [ ] `_compute_rates()`
  * [ ] `_flatten_latest_values()`
* [ ] Separate device initialization from the acquisition loop conceptually
* [ ] Improve separation of concerns between UI, logging orchestration, and hardware access
* [ ] Evaluate introducing helper classes:

  * [ ] `DeviceInitializer`
  * [ ] `RecordingController`

---

## Priority A – Robustness & Error Handling

* [ ] Wrap acquisition loop in a top-level `try/except` to prevent thread crashes
* [ ] Normalize error state handling

  * [ ] Replace `saturation_error: False | str` with `None | str`
  * [ ] Remove other mixed-type state flags
* [ ] Improve shutdown behavior

  * [ ] Ensure safe exit if thread is blocked in DLL calls
  * [ ] Revisit `closeEvent()` + `wait(1000)`
* [ ] Improve zero behavior

  * [ ] Avoid showing stale buffer values after zero
  * [ ] Optionally reset buffer/rate state after zero

---

## Priority A – Logging Improvements

* [ ] Modify `strict_samples` to skip completely empty rows
* [ ] Separate logging warnings from main status display
* [ ] Document that `.xlsx` is not suitable for long sessions
* [ ] Recommend CSV for long-term recording
* [ ] Evaluate streaming/write-only XLSX approach
* [ ] Consider optional mode: only write rows when at least one fresh value exists

---

## Priority B – UI & Status Concept

* [ ] Separate status and warning display

  * [ ] Dedicated warning label or log panel
  * [ ] Prevent important errors from being overwritten
* [ ] Simplify `MainWindow`

  * [ ] Reduce logic inside `on_values()`
  * [ ] Decouple recording workflow from UI
* [ ] Consider extracting tree logic into a presenter/helper

---

## Priority B – Reduce Unnecessary Complexity

* [ ] Clean up unfinished serial/color concept

  * [ ] Remove `sn_colors` if unused
  * [ ] OR fully implement consistent color mapping
* [ ] Centralize or simplify stylesheet handling
* [ ] Break down deeply nested sensitivity logic

---

## Priority B – Domain Clarity

* [ ] Clarify meaning of displayed Hz values

  * [ ] actual device sampling rate?
  * [ ] or polling/update rate?
* [ ] Improve logging documentation

  * [ ] `hold_last`
  * [ ] `strict_samples`
  * [ ] implications for data analysis

---

## Priority C – Code Quality

* [ ] Align docstrings with actual behavior
* [ ] Add consistent type annotations
* [ ] Extract repeated status/error message patterns
* [ ] Centralize constants where useful

  * [ ] sleep timings
  * [ ] UI constants
  * [ ] colors

---

## Priority C – Production Readiness

* [ ] Define which parts are internal vs release-grade
* [ ] Test long-running recording sessions

  * [ ] memory usage
  * [ ] file size
  * [ ] crash behavior
* [ ] Test behavior with missing/misconfigured devices
* [ ] Test CAN disturbances and intermittent DLL errors

---

## Quick Wins

* [ ] Change `saturation_error` to `None | str`
* [ ] Skip empty rows in `strict_samples`
* [ ] Split `ReaderThread.run()` into smaller methods
* [ ] Remove unused `sn_colors`
* [ ] Separate status and warnings

---

## Optional (Future Improvements)

* [ ] Introduce `DeviceTreePresenter`
* [ ] Introduce `RecordingController`
* [ ] Introduce `DeviceInitializer`
* [ ] Replace single status line with structured event/log system
