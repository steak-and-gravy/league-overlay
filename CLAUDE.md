# iRacing League Overlay - Context for AI Assistance

Real-time iRacing race position overlay with division-based racing.

## ⚠️ PRE-CODE CHECKLIST - READ THIS FIRST!

**Before writing ANY code, check the relevant sections below:**

- [ ] **Accessing `self.ir` or `live_data`?** → Read ["IRSDK DATA ACCESS"](#0-irsdk-data-access-important) section
  - NEVER use `.get()` on iRSDK objects
  - NEVER use `in` operator on iRSDK objects
  - ALWAYS use bracket notation with try/except

- [ ] **Working with driver positions?** → Read ["POSITIONING"](#1-positioning) section
  - Understand the unified `position` field
  - Know the difference between real-time vs official positions

- [ ] **Calculating or displaying gaps?** → Read ["GAP CALCULATION"](#2-gap-calculation) section
  - Check time gap vs lap gap logic
  - Understand division gap vs overall gap

- [ ] **Working with DriverState objects?** → Read ["DRIVER STATE"](#3-driver-state-unified-data-structure) section
  - Use attribute access, not `.get()`
  - Understand finish tracking and disconnection flags

- [ ] **Handling disconnected/finished drivers?** → Read ["RACE STATE TRACKING"](#4-race-state-tracking-finish-detection) section
  - Understand the finish state machine
  - Know how snapshots work

**Common Mistakes to Avoid:**
1. ❌ `self.ir.get('SessionState', 4)` → ✅ Use try/except with bracket notation
2. ❌ `if 'SessionState' in self.ir:` → ✅ Use try/except
3. ❌ `driver.get('position')` on DriverState → ✅ Use `driver.position`
4. ❌ Modifying position after finish → ✅ Positions lock when drivers finish

## Project Structure
```
league-overlay/
├── config/              # Settings and constants
│   ├── constants.py          # UIConfig, FileConfig, TelemetryConfig
│   ├── settings.py           # AppSettings, SettingsManager
│   ├── settings_validator.py # Settings validation and coercion
│   ├── official_leagues.py   # Official league configurations (remote URLs)
│   └── logging_config.py     # Logging setup and configuration
├── core/                # Business logic
│   ├── driver_state.py         # Unified driver data structure (DriverState dataclass)
│   ├── position_calculator.py  # Position calculation
│   ├── gap_calculator.py       # Time/lap gap calculations
│   ├── division_manager.py     # Driver-to-division mapping
│   ├── division_filter.py      # Division filtering logic
│   ├── race_state_tracker.py   # Finish state machine
│   ├── telemetry_processor.py  # Main telemetry orchestration
│   └── update_checker.py       # GitHub update checking
├── ui/                  # UI components
│   ├── driver_row_renderer.py    # Row widget creation
│   ├── settings_dialog.py        # Settings UI
│   ├── styles.py                 # Color strategies (Default/Alternate/Outline/Dark)
│   ├── widgets.py                # Custom Qt widgets
│   └── auto_center_controller.py # Auto-scrolling controller
├── league_overlay.py    # Main application and orchestration
└── LeagueOverlay.log    # Application log (rotating, 1MB max per file)
```

## Key Concepts

### 0. IRSDK DATA ACCESS (IMPORTANT!)

**CRITICAL: Different objects have different access patterns!**

#### `live_data` / `self.ir` (irsdk.IRSDK object)
- This is the iRacing SDK connection object - NOT a regular Python dict
- irsdk.IRSDK implements `__getitem__` but NOT `__contains__` or `.get()`
- **ALWAYS use try/except for optional fields**: Use try/except to handle missing fields
- **NEVER use .get()**: `self.ir.get('SessionState', default)` ✗ (AttributeError: 'IRSDK' object has no attribute 'get')
- **NEVER use 'in' operator**: `'SessionState' in self.ir` may not work reliably
- This is a wrapper around iRacing's memory-mapped data
- Common fields: `'CarIdxLap'`, `'CarIdxLapDistPct'`, `'CarIdxClassPosition'`, `'SessionState'`, `'SessionNum'`, `'SessionTime'`, `'RaceLaps'`, `'SessionTimeRemain'`
- Session info is nested: `self.ir['SessionInfo']['Sessions'][session_num]`
- Weekend info: `self.ir['WeekendInfo']['SessionID']`

**Common Pattern for Optional Fields with Defaults:**
```python
# CORRECT - Use try/except for optional fields
try:
    session_state = self.ir['SessionState']
except (KeyError, TypeError):
    session_state = 4

try:
    race_laps = self.ir['RaceLaps']
except (KeyError, TypeError):
    race_laps = 0

# WRONG - .get() does not exist on IRSDK objects
session_state = self.ir.get('SessionState', 4)  # ❌ AttributeError!

# WRONG - 'in' operator may not work reliably
session_state = self.ir['SessionState'] if 'SessionState' in self.ir else 4  # ❌ May fail!
```

#### `DriverState` (dataclass from core/driver_state.py)
- This is a **dataclass** created by TelemetryProcessor for each driver
- Unified data structure replacing redundant dictionary objects
- **Performance**: 45x improvement in driver searches compared to previous implementation
- **Use attribute access**: `driver.position`, `driver.car_number`, `driver.gap` ✓
- **Never use dict access**: `driver['position']` ✗ (TypeError: DriverState is not subscriptable)
- Key attributes:
  - Direct fields: `car_idx`, `driver_info`, `position`, `division_position`, `division_name`, `division_color`, `gap`, `is_player`, `is_disconnected`, `is_finished`, etc.
  - Computed properties: `car_number`, `driver_name`, `car_class_id`, `total_track_position`
- See `core/driver_state.py` for complete list of fields and properties

#### `driver_info` (dict from iRacing API)
- This is a regular Python dict from iRacing's DriverInfo (stored inside DriverState)
- **CAN use .get() safely**: `driver_info.get('UserName', '')` ✓
- Contains: `UserID`, `UserName`, `CarNumber`, `CarClassID`, etc.
- **Prefer using DriverState properties** instead of accessing driver_info directly:
  - Use `driver.car_number` instead of `driver.driver_info.get('CarNumber')`
  - Use `driver.driver_name` instead of `driver.driver_info.get('UserName')`
  - Use `driver.car_class_id` instead of `driver.driver_info.get('CarClassID')`

**Summary**: Only `irsdk.IRSDK` objects (like `self.ir` and `live_data`) require bracket notation with try/except. DriverState uses attribute/property access. Regular dicts use `.get()` safely.

### 1. POSITIONING
- **Single unified position field**: The `position` field adapts to context
- **During race (racing drivers)**: Continuously updated using `lap + lap_distance_pct` for real-time tracking
- **During race (finished drivers)**: Locked to official finishing position when driver crosses finish line
- **Practice/Qualifying**: Based on best lap times
- **After disconnection**: Preserved from snapshot (doesn't change when other drivers disconnect)

### 2. DIVISION SYSTEM
- Drivers assigned to divisions via JSON config (Pro, ProAm, Am, Rookie)
- **Two config modes**: Official remote leagues (recommended) or local files (legacy/custom)
- **Official leagues**: Fetched from remote URL, cached locally, auto-updates on demand
  - Identifier format: "official:{league_name}" (e.g., "official:BWRL GT3 Sprint")
  - Defined in `config/official_leagues.py`
  - Cached as `cache_{league_name}.json` for offline use
  - Managed via dropdown in Settings dialog
- **Local files**: User-specified paths with MRU list (max 5 recent files)
- Each division has customizable color
- Gaps calculated within divisions only
- Right-click driver to change division
- Managed by `core/division_manager.py`

### 3. FINISH TRACKING (State Machine)
- Checkered flag waves when leader approaches line, but race continues
- Tracks each car completing their finish lap individually
- Locks position + gap when each car crosses line after checkered
- **Gap Preservation**: Final gaps captured from ResultsPositions and frozen to prevent changes as drivers slow down
- Implemented in `core/race_state_tracker.py` and `core/telemetry_processor.py`
- **NEW**: Finish tracking methods moved from TelemetryProcessor to RaceStateTracker for better cohesion
- **NEW**: Finishing gaps calculated from ResultsPositions data for accurate post-race display

**Snapshots and Disconnected Drivers:**
- Active drivers come from `PositionCalculator.calculate_real_time_positions()` as DriverState objects with full data including `total_track_position`
- Disconnected drivers are restored from snapshots via `RaceStateTracker.handle_disconnected_drivers()`
- Snapshots store DriverState objects - use attribute access with fallbacks for safety
- Example: `racing_drivers.sort(key=lambda x: x.total_track_position or 0, reverse=True)`

**Disconnected Driver Position Handling:**
- **During race**: Disconnected drivers marked as DC, position unknown
- **After leader finishes**: ALL disconnected drivers immediately marked as finished
- **Finished drivers**: Continuously updated from `ResultsPositions` (iRacing's official results) after checkered flag
- **Why this works**: No arbitrary thresholds - simple logic that always converges to correct final positions
- **Network blips**: Self-correcting via continuous `ResultsPositions` updates
- Implemented in `race_state_tracker.py` `handle_disconnected_drivers()` and `telemetry_processor.py` lines 611-619

### 4. MULTI-CLASS SUPPORT
- **Class** = Car types (LMP2, GT3, GT4, etc.)
- **Division** = Driver groupings within same class
- Overlay filters to player's class automatically

### 5. CAR-SPECIFIC TIME NORMALIZATION FOR GAP CALCULATIONS
**The Problem:**
- iRacing's `CarIdxEstTime` is scaled to each **car's** expected pace (not class or driver skill)
- Each car model has unique `CarClassEstLapTime` set by iRacing based on car performance
  - Example: Corvette C8.R GT3: 90.5s, Ferrari 296 GT3: 90.2s, Mustang GT3: 90.8s
  - Example: GT3 class: ~90s, GT4 class: ~95s
- `CarIdxEstTime` values are in "car-specific time" and cannot be directly compared
- Even same-class cars (Corvette vs Ferrari) need normalization for accurate gaps

**The Solution:**
Normalize using each car's `CarClassEstLapTime` to convert to a common time scale:
```python
# Get estimated lap times for each car (iRacing's expected pace for that car model)
ahead_lap_time = ir['DriverInfo']['Drivers'][car_ahead_idx]['CarClassEstLapTime']
current_lap_time = ir['DriverInfo']['Drivers'][car_idx]['CarClassEstLapTime']

# Calculate normalization ratio
normalize_lap_time_pct = ahead_lap_time / current_lap_time

# Normalize car ahead's EstTime to current car's time reference
normalized_ahead_est_time = ahead_est_time / normalize_lap_time_pct
```

**Examples:**
- Multi-class: GT3 (90s) vs GT4 (95s) → normalize by 90/95 = 0.947
- Same class: Ferrari (90.2s) vs Corvette (90.5s) → normalize by 90.2/90.5 = 0.997

**Edge Cases:**
- Falls back to non-normalized gaps if lap times unavailable (division by zero protection)
- Check: `if (ahead_lap_time > 0 and current_lap_time > 0)`

**Implementation:**
- Location: `telemetry_processor.py` `_calculate_live_race_gap()` lines 465-470
- Applied before all gap calculations (same lap, different laps, etc.)

## Common Tasks

### Adding New Feature
1. Identify which module (config/core/ui)
2. Make changes in appropriate module
3. Update league_overlay.py orchestration if needed

### Modifying Telemetry Logic
- **Position calculation**: `core/position_calculator.py`
- **Finish tracking**: `core/race_state_tracker.py`
- **Gap calculation**: `core/gap_calculator.py`
- **Division filtering**: `core/division_filter.py`
- **Orchestration**: `core/telemetry_processor.py` (coordinates the above)

### UI Changes
- Driver rows: `ui/driver_row_renderer.py`
- Settings: `ui/settings_dialog.py`
- Colors/styles: `ui/styles.py`

### Configuration Changes
- Constants: `config/constants.py`
- Settings persistence: `config/settings.py`

### Debugging with Logs
- Log file: `LeagueOverlay.log` (same directory as executable)
- Appends with rotation (1MB max per file, 1 backup)
- Contains startup info, exceptions with full tracebacks, state changes
- Useful for troubleshooting user issues - ask for this file
- **Tip**: Enable DEBUG log level in Settings for detailed troubleshooting

## Important Notes for AI

### Critical Coding Patterns

#### Data Access Patterns by Object Type
See "IRSDK DATA ACCESS" section above for complete details. Quick reference:

- **irsdk objects** (`self.ir`, `live_data`): Use bracket notation ONLY with try/except
  ```python
  car_idx_lap = live_data['CarIdxLap']  # ✓
  ```

- **DriverState objects** (`driver`, items in `race_data`/`active_drivers`): Use attribute/property access
  ```python
  position = driver.position  # ✓
  car_number = driver.car_number  # ✓ (computed property)
  driver_name = driver.driver_name  # ✓ (computed property)
  ```

- **Regular dicts** (`driver_info`): Use `.get()` safely (but prefer DriverState properties when available)
  ```python
  driver_name = driver_info.get('UserName', '')  # ✓ but prefer driver.driver_name
  ```

#### Qt Signal Lambda Functions
When connecting Qt signals that pass arguments (like `customContextMenuRequested`), always explicitly include the signal's parameter in the lambda signature, even if you don't use it:

**Correct:**
```python
widget.customContextMenuRequested.connect(
    lambda pos, d=driver: self.parent.show_context_menu(d)
)
```

**Incorrect:**
```python
widget.customContextMenuRequested.connect(
    lambda d=driver: self.parent.show_context_menu(d)  # ❌ Missing 'pos' parameter
)
```

**Reason**: Qt signals like `customContextMenuRequested` pass a `QPoint` as their first argument. If you don't explicitly accept it in your lambda signature, the QPoint gets passed to your function instead of your intended data, causing `TypeError`.

#### Lambda Closure Best Practices
Always capture data **by value** in lambda closures to avoid stale reference issues:

**Correct:**
```python
lambda pos, d=driver: self.parent.show_context_menu(d)  # d captured by value
```

**Incorrect:**
```python
lambda pos: self.parent.show_context_menu(driver)  # driver captured by reference
```

**Reason**: When widgets are recreated frequently, capturing by reference can lead to the lambda referencing deleted or wrong data.

### Code Organization
- Code is modularized - avoid suggesting changes that revert to monolithic structure
- Always check if functionality exists in a module before suggesting new code
- Single responsibility: each module has one clear purpose

### Key Design Patterns
- Dependency injection (AutoCenterController accepts time_func)
- Static methods for pure functions (GapCalculator)
- Clear separation: UI doesn't know about Core internals

### Threading
- Telemetry runs in background thread
- Uses Qt signals for thread-safe UI updates
- Never block UI thread with telemetry operations

### Configuration
- Division config is JSON-based and shared across league members
- Settings saved to LeagueOverlay.config
- Division colors customizable per league

### Logging
- Logging is implemented using Python's `logging` module
- All modules use `get_logger(__name__)` from `config.logging_config`
- Logs include: startup info, version, errors with tracebacks, state changes
- **Log Rotation**: Uses `RotatingFileHandler` with 1MB max size, keeps 1 backup (2MB total max)
- **Log Level**: User-configurable via Settings dialog (DEBUG, INFO, WARNING, ERROR)
  - Default: INFO (balanced verbosity)
  - DEBUG: Detailed telemetry/gap calculation debugging
  - WARNING/ERROR: Quieter logs for production use
  - Takes effect on next app restart
- Logs persist across app launches (appends until rotation)

### Session Tracking
- Uses `SessionID` from `WeekendInfo` (not `SessionNum`) combined with `session_type`
- `SessionNum` is just an array index and resets for each session type
- `SessionID` is unique per event and persists across reconnects
- Change detection: `telemetry_processor.py` `_detect_session_change()`

## Quick Reference Docs

- **Architecture details**: `ARCHITECTURE.md`

## Testing

The project includes comprehensive test coverage with **466 tests** across multiple test suites:

### Test Organization
```
tests/
├── test_core/                       # Core business logic tests
│   ├── test_race_state_tracker.py       # Finish tracking, multi-class, snapshots
│   ├── test_telemetry_processor.py      # Driver separation, session tracking
│   ├── test_gap_calculator.py           # Gap calculations
│   ├── test_position_calculator.py      # Position logic
│   ├── test_division_manager.py         # Division management
│   └── test_division_filter.py          # Division filtering logic
├── test_ui/                         # UI component tests
│   ├── test_auto_center_controller.py   # Auto-centering behavior
│   └── test_session_status.py           # Session status formatting
├── test_integration/                # Integration tests
│   └── test_telemetry_flow.py           # Full telemetry processing flow
├── test_config/                     # Configuration tests
│   ├── test_settings_manager.py         # Settings persistence
│   └── test_settings_validator.py       # Settings validation
└── conftest.py                      # Shared fixtures
```

### Running Tests
```bash
# Run all tests
pytest

# Run specific test suite
pytest tests/test_core/test_race_state_tracker.py

# Run with coverage
pytest --cov=core --cov=ui --cov-report=html

# Run specific test class
pytest tests/test_core/test_race_state_tracker.py::TestFinishGapWithPositionSwaps
```
