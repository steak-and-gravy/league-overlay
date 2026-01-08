# Architecture Documentation

## Overview

The iRacing League Overlay is a real-time race position display application built with PySide6 (Qt for Python) and the iRacing SDK. The architecture follows a modular design with clear separation of concerns.

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    League Overlay (Qt UI)                │
│                                                          │
│  ┌────────────────────┐      ┌──────────────────────┐    │
│  │  Settings Dialog   │      │  Driver Row Renderer │    │
│  │   (UI Config)      │      │   (Display Logic)    │    │
│  └────────────────────┘      └──────────────────────┘    │
└──────────────────────────────────────────────────────────┘
                    │                       ▲
                    │                       │
                    ▼                       │
┌──────────────────────────────────────────────────────────┐
│              Telemetry Processor (Core)                  │
│                                                          │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐   │
│  │ Position     │  │ Race State  │  │ Division       │   │
│  │ Calculator   │  │ Tracker     │  │ Manager        │   │
│  └──────────────┘  └─────────────┘  └────────────────┘   │
│  ┌──────────────┐  ┌─────────────┐                       │
│  │ Gap          │  │ Division    │                       │
│  │ Calculator   │  │ Filter      │                       │
│  └──────────────┘  └─────────────┘                       │
└──────────────────────────────────────────────────────────┘
                    │                       ▲
                    │                       │
                    ▼                       │
┌──────────────────────────────────────────────────────────┐
│                    iRacing SDK (irsdk)                   │
│                   (External Dependency)                  │
└──────────────────────────────────────────────────────────┘
```

## Module Structure

### Layer 1: Configuration (`config/`)

#### `constants.py`
Centralized configuration constants for the entire application.

**Classes:**
- `UIColors` - Color palette constants
- `LicenseColors` - License class background colors (R/D/C/B/A/P)
- `UIDimensions` - Window and UI element dimensions
- `ColumnLayout` - Column stretch factors for driver list
- `ColumnMinWidths` - Minimum pixel widths for columns to prevent misalignment at small window sizes
- `Timing` - Timing and refresh rate constants
- `UIConfig` - UI-related constants (colors, fonts, sizes, division colors)
- `FileConfig` - File paths and names
- `TelemetryConfig` - Telemetry update rates, iRacing SDK constants (MAX_CARS=63), session flags

**Purpose**: Single source of truth for configuration values, making it easy to adjust behavior without changing code.

**Dependencies**: None (no imports from other modules)

#### `settings.py`
Application settings persistence and validation.

**Classes:**
- `AppSettings` (dataclass) - Type-safe settings container
- `SettingsManager` - Load/save/validate settings

**Purpose**: Manage user preferences with validation to ensure values are always within valid ranges.

**Dependencies**: `config.constants`, `config.logging_config`, `config.settings_validator`

**Key Features:**
- Validates opacity (0.1-1.0), refresh rate (0.25-5.0), dimensions (200-2000)
- Validates font_size, row_color_style, log_level (enum values)
- Validates performance indicator colors (faster_color, slower_color) as hex colors
- Supports league_config (path or "official:{name}") and recent_local_configs list
- Gracefully handles missing/corrupt settings files
- Automatic defaults for missing fields
- Logs settings load/save operations and errors

#### `settings_validator.py`
Settings validation and type coercion.

**Class:**
- `SettingsValidator`

**Purpose**: Handle validation and type coercion of settings data loaded from JSON, ensuring values are of correct type and within valid ranges. Uses dataclass introspection to extract defaults from `AppSettings` as the single source of truth.

**Dependencies**: `config.constants`, `config.logging_config`, `config.settings` (imported dynamically to avoid circular dependency)

**Key Features:**
- **Single source of truth**: Extracts all default values from `AppSettings` dataclass via introspection at initialization
- Type coercion (e.g., "500" string → 500 int, "0.9" → 0.9 float)
- Range validation and clamping
- Enum validation for limited valid values
- List validation (recent_local_configs filters non-string items)
- Hex color validation for division colors and performance indicator colors
- Performance indicator colors: faster_color (default #00FF00 green), slower_color (default #FF0000 red)
- Graceful fallbacks to defaults on invalid data
- **No hardcoded defaults**: All defaults dynamically read from `AppSettings` dataclass fields using `dataclasses.fields()`

#### `official_leagues.py`
Official remotely-managed league configurations.

**Classes:**
- `OfficialLeague` (dataclass) - League configuration structure

**Functions:**
- `get_official_league(name)` - Retrieve league config by name

**Purpose**: Define official leagues hosted remotely with automatic updates.

**Dependencies**: None

**Key Features:**
- Dataclass defining league metadata (name, icon, URL, description, cache_file)
- OFFICIAL_LEAGUES list containing all available official leagues
- Used by DivisionManager to fetch remote configs
- Enables centralized league management without manual file distribution

#### `logging_config.py`
Logging configuration and setup.

**Functions:**
- `setup_logging(log_level)` - Initialize logging to LeagueOverlay.log with specified level
- `get_logger(name)` - Get a logger instance for a module

**Purpose**: Centralized logging configuration for the entire application.

**Dependencies**: None

**Key Features:**
- Logs to `LeagueOverlay.log` in same directory as executable
- Rotating file handler with 1MB max size, 1 backup (2MB total)
- Log level configurable via AppSettings (default: INFO)
- Works with both compiled exe (Nuitka) and script mode
- Simple format: `timestamp - module - level - message`
- Used by all modules for consistent logging

---

### Layer 2: Core Business Logic (`core/`)

#### `driver_state.py`
Unified data structure for driver information during a session.

**Class:**
- `DriverState` (dataclass)

**Purpose**: Single source of truth for all driver data during a race session. Replaces dict-based driver data with a type-safe dataclass.

**Dependencies**: None

**Key Features:**
- Dataclass with type hints for all fields
- Computed properties: `car_number`, `driver_name`, `car_class_id`, `total_track_position`
- Direct fields: `car_idx`, `driver_info`, `position`, `division_position`, `starting_position`, `division_name`, `division_color`, `gap`, `delta`, `last_lap`, `best_lap`, `positions_gained`, `is_player`, `is_disconnected`, `is_finished`, etc., `irating`, `safety_rating`, `combined_rating`, `lic_level`, `last_pit_lap`, `out_lap`, `pit_lap`
- Used throughout the codebase as the primary driver data container
- Eliminates the need for intermediate dicts and parallel data structures

**Design Benefits:**
- Type safety: IDE autocomplete and type checking
- Performance: No dict lookups, direct attribute access
- Clarity: Explicit fields vs. arbitrary dict keys
- Consistency: Single data structure used everywhere

#### `gap_calculator.py`
Pure functions for calculating and formatting time/lap gaps.

**Class:**
- `GapCalculator` (static methods only)

**Methods:**
- `calculate_time_gap()` - Calculate time difference in seconds
- `calculate_lap_gap()` - Calculate lap difference
- `format_gap_display()` - Format gap for UI display
- `format_delta_display()` - Format lap time delta comparison
- `format_lap_time()` - Format lap time for display (supports minutes:seconds)
- `format_positions_gained()` - Format positions gained/lost with arrow indicators (↑/↓)
- `format_irating()` - Format iRating rounded to hundreds with k suffix
- `format_safety_rating()` - Format license level + sublevel (e.g., "A2.5")
- `format_combined_rating()` - Combine safety rating + iRating (e.g., "A 2.5  6.0k")
- `format_last_pit_lap()` - Format last pit lap (e.g., "L12")
- `format_out_lap()` - Format out lap indicator ("OUT" or "")
- `format_pit_lap()` - Combined pit lap column (shows "OUT" or "L12")
- `get_license_background_color()` - Get license class background color

**Purpose**: Centralize gap calculation logic for consistency and testability.

**Dependencies**: None

**Design Pattern**: Pure static methods (no state, easy to test)

#### `division_manager.py`
Driver-to-division mapping and color management.

**Class:**
- `DivisionManager`

**Responsibilities:**
- Load driver-division mappings from JSON (local or remote)
- Support official remotely-hosted league configs with caching
- Assign/update driver divisions
- Provide division colors
- Persist configuration changes

**Purpose**: Manage the division system that allows league organizers to group drivers.

**Dependencies**: `config.constants`, `config.logging_config`, `config.official_leagues`, `requests`

**Key Features:**
- Supports two config modes: local files and official remote leagues
- Official leagues: Uses "official:{name}" prefix to load from remote URL
- Remote fetching: Downloads config from URL, caches locally for offline use
- Cache fallback: Automatically uses cached copy if remote fetch fails
- Matches drivers by ID (preferred) or name (fallback)
- "Default" division removes assignment
- JSON-based config shared across league members
- Logs driver assignment loads/saves and errors

#### `division_filter.py`
Division-based filtering of race data.

**Class:**
- `DivisionFilter`

**Responsibilities:**
- Apply division filters to race data (List[DriverState])
- Cycle through filter modes (All Divisions / My Division / specific division)
- Track filter state (player mode vs spectator mode)
- Provide button state for UI display
- Determine which divisions have active drivers

**Purpose**: Encapsulate division filtering logic for cleaner separation from UI orchestration.

**Dependencies**: `core.division_manager`, `core.driver_state`, `config.constants`

**Key Features:**
- Player mode: toggles between "My Division" and "All Divisions"
- Spectator mode: cycles through divisions with active drivers
- Returns filtered List[DriverState]
- Provides button text and color for UI rendering
- Resets filter state on session change
- Works directly with DriverState objects (no intermediate dicts)

#### `position_calculator.py`
Calculates driver positions from iRacing telemetry.

**Class:**
- `PositionCalculator`

**Responsibilities:**
- Calculate real-time positions based on track position (lap + lap_distance_pct)
- Get official positions from iRacing timing system
- Identify player car and class
- Find overall race leader (for multi-class finish tracking)
- Filter to player's class for multi-class support
- Create and return DriverState objects with position data

**Purpose**: Extract position calculation logic from TelemetryProcessor for better separation of concerns. Returns DriverState objects as the primary data structure.

**Dependencies**: `irsdk`, `core.driver_state`, `config.logging_config`

**Key Features:**
- Real-time positioning: continuous updates using lap + lap_distance_pct
- Official positioning: start/finish line updates (for practice/qualifying)
- Multi-class filtering: only show cars in player's class
- Player identification: tracks player's car index and class ID

#### `race_state_tracker.py`
State machine for tracking race finish status.

**Class:**
- `RaceStateTracker`

**Responsibilities:**
- Track checkered flag state
- Mark individual drivers as finished
- Store finish snapshots (DriverState objects)
- Capture and preserve final gaps from ResultsPositions data
- Recalculate division gaps after each finish
- Handle finish tracking for entire race
- Manage disconnected driver restoration

**Purpose**: Handle the complex finish tracking where cars finish individually after the checkered flag. Stores and manages DriverState snapshots.

**Dependencies**: `irsdk`, `core.driver_state`, `config.constants`, `config.logging_config`

**State Machine:**
```
Racing → Checkered Flag → Drivers Finishing Individually
  │
  └──> Each driver: Not Finished → Crossed Line → Finished (locked)
```

**Key Features:**
- Locks position/gap when driver crosses line after checkered
- Preserves final gaps from ResultsPositions to prevent changes as drivers slow down
- Recalculates division-based gaps after each finish
- Stores DriverState snapshots for finished drivers
- Handles disconnected drivers (restores from DriverState snapshots)
- Manages finish tracking workflow (moved from TelemetryProcessor)
- Works directly with DriverState objects (no intermediate dicts)
- Captures starting grid positions (race sessions only) for positions gained tracking

#### `telemetry_processor.py`
Main telemetry processing pipeline.

**Class:**
- `TelemetryProcessor`

**Responsibilities:**
- Orchestrate telemetry processing pipeline
- Coordinate between PositionCalculator, RaceStateTracker, DivisionManager, GapCalculator
- Handle session changes (using SessionID from WeekendInfo + session_type)
- Separate finished and racing drivers to prevent position contamination
- Calculate division positions (sets DriverState.division_position directly)
- Calculate finishing gaps from ResultsPositions data for post-race accuracy
- Manage driver snapshots for racing drivers
- Calculate delta lap times (with mode detection for driving vs spectating)
- Return List[DriverState] for UI display

**Purpose**: Orchestrate all telemetry processing and coordinate between core modules. Acts as a coordinator rather than implementing low-level logic. Works exclusively with DriverState objects.

**Dependencies**:
- `irsdk` (external)
- `core.driver_state`
- `core.position_calculator`
- `core.gap_calculator`
- `core.race_state_tracker`
- `core.division_manager`
- `config.constants`
- `config.logging_config`

**Key Methods:**
- `_is_driving_mode()` - Detects if player is driving vs spectating (checks if player_car_idx < MAX_CARS)
- `_calculate_delta()` - Calculates delta lap times with mode-aware reference selection
- `_build_race_data_entry()` - Builds DriverState objects with all formatted display strings

**Logging:**
- Logs session changes (Practice → Qualifying → Race)
- Logs processing errors with full tracebacks
- Debug-level logs for non-critical telemetry issues

**Design Note - Delta Calculation:**
- DRIVING MODE: Compare each driver to player's lap (reference = player)
- SPECTATING MODE: Compare each driver to their division leader's lap (reference = division leader)
- Argument order is flipped between modes to maintain consistent color coding (green = faster, red = slower)

**Data Flow:**
```
iRacing SDK Data
    │
    ▼
Parse Session Info
    │
    ▼
PositionCalculator: Calculate positions → List[DriverState]
    │
    ▼
Filter to Player's Class
    │
    ▼
Set Division Info (DivisionManager) on each DriverState
    │
    ▼
Calculate Division Positions (sets DriverState.division_position)
    │
    ▼
Calculate Gaps (GapCalculator) → sets DriverState.gap
    │
    ▼
Handle Finish State (RaceStateTracker) → manages DriverState snapshots
    │
    ▼
Return Sorted List[DriverState]
```

**Session Change Detection:**
- Uses `SessionID` from `WeekendInfo` (not `SessionNum`)
- Combines `SessionID` + `session_type` for reliable change detection
- `SessionNum` is just an array index (0 for Practice, 0 for Quali, 0 for Race)
- `SessionID` is unique per event and persists across reconnects

**Finished Driver Position Fix (Gap-Filling Algorithm):**

*Problem:* When drivers finish and disconnect, positions could show gaps (e.g., 8, 9, 12, 13 - skipping 10, 11) especially when lapped drivers finished.

*Root Cause:*
1. Finished drivers with frozen track position data mixed with active racing data
2. Lapped drivers who finished (e.g., P13, P14) were counted in offset for racing positions
3. Created gaps: if 7 drivers finished (P1-P5, P13-P14), racing drivers started at P8 instead of P6

*Solution (implemented 10/17/25):*
1. Separate finished and racing drivers into distinct lists
2. Finished drivers: sorted by official results position (e.g., {1,2,3,4,5,13,14})
3. Identify which positions are taken by finished drivers
4. Racing drivers: sorted by track position, assigned to *available* positions
   - Example: if finished have {1,2,3,5,13,14}, racing get {4,6,7,8,9,10,11,12,15,16...}
5. Result: No gaps, no duplicates, correct order maintained

*Code Location:* `telemetry_processor.py` lines 851-876

#### `update_checker.py`
Checks for application updates from GitHub.

**Class:**
- `UpdateChecker`

**Responsibilities:**
- Fetch latest version from GitHub API
- Compare versions using semantic versioning
- Provide download URLs

**Purpose**: Notify users of new versions.

**Dependencies**: `packaging` (for version comparison), `urllib` (for API calls), `config.logging_config`

**Design Features:**
- Clean API: `check_for_update()` returns dict with update info
- Configurable timeout for API requests
- Error handling with graceful degradation
- Logs update check results (available/not available/failed)

---

### Layer 3: UI Components (`ui/`)

#### `widgets.py`
Custom Qt widgets and signals.

**Classes:**
- `DataUpdateSignal` - Qt signal for thread-safe UI updates
- `CustomSizeGrip` - Custom window resize grip

**Purpose**: Reusable UI components.

**Dependencies**: `PySide6`

#### `styles.py`
Row styling strategies.

**Classes:**
- `ColorStyleStrategy` (base class)
- `DefaultColorStyle` - Solid background
- `AlternateColorStyle` - Alternating row colors
- `OutlineColorStyle` - Outlined rows

**Purpose**: Strategy pattern for different row appearance modes.

**Dependencies**: `PySide6`

**Design Pattern**: Strategy Pattern - easy to add new styles

**Key Features:**
- Delta colors (faster/slower) and positions gained/lost colors now use customizable settings
- Each style pulls `faster_color` and `slower_color` from parent.settings
- Default green (#00FF00) for faster/gained, red (#FF0000) for slower/lost

#### `driver_row_renderer.py`
Renders driver rows in the UI.

**Class:**
- `DriverRowRenderer`

**Responsibilities:**
- Create QLabel widgets for each DriverState field
- Apply color styles
- Handle layout and spacing
- Support different font sizes
- Extract data from DriverState objects using attribute access

**Purpose**: Separate UI rendering logic from main application. Works with DriverState objects.

**Dependencies**:
- `PySide6`
- `core.driver_state`
- `ui.styles`
- `config.constants`

#### `settings_dialog.py`
Settings UI dialog.

**Class:**
- `SettingsDialog`

**Responsibilities:**
- Display settings UI
- Validate user input
- Emit signals on changes
- Manage division color pickers and performance indicator color pickers
- **Reset to defaults**: Creates fresh `AppSettings()` instance to get default values (single source of truth)

**Purpose**: Provide user interface for configuration.

**Dependencies**:
- `PySide6`
- `config.constants`
- `config.settings`

**Key Features:**
- Reset button uses `AppSettings()` introspection to get all default values dynamically
- No hardcoded defaults in UI layer

#### `auto_center_controller.py`
Manages auto-centering behavior with manual override.

**Class:**
- `AutoCenterController`

**Responsibilities:**
- Track manual user interactions
- Implement timeout-based re-enabling
- Provide enable/disable controls

**Purpose**: Provide intelligent auto-scrolling that respects user actions.

**Dependencies**: None (standalone)

**Design Features:**
- Dependency injection for time function (testable)
- Clear API: `on_manual_interaction()`, `should_auto_center()`

---

### Layer 4: Application (`/`)

#### `league_overlay.py`
Main application entry point and orchestration.

**Class:**
- `LeagueOverlay` (QMainWindow)

**Responsibilities:**
- Initialize all modules
- Manage Qt main window
- Run telemetry loop in background thread
- Handle UI updates via signals (receives List[DriverState])
- Dynamically adjust header margins based on scrollbar visibility for column alignment
- Coordinate auto-centering
- Manage context menus (DriverState context menus)
- Handle session changes
- Apply division filters to race data (List[DriverState])

**Purpose**: Orchestrate all components and manage application lifecycle. Works with DriverState objects from telemetry processor.

**Dependencies**: All other modules

**Threading Model:**
- **Main Thread**: Qt UI event loop
- **Telemetry Thread**: Background thread reading iRacing data
- **Communication**: Qt signals for thread-safe updates

**Key Methods:**
- `_telemetry_loop()` - Background telemetry reading
- `_handle_telemetry_update()` - Session change detection and state sync
- `_update_ui()` - Render race data to UI
- `_center_on_player()` - Auto-scrolling logic
- `adjust_header_margins()` - Dynamic header margin adjustment for scrollbar alignment

---

## Design Patterns Used

### 1. **Separation of Concerns**
- **Config** layer: Configuration only
- **Core** layer: Business logic only (no UI)
- **UI** layer: Presentation only (no business logic)
- **Application** layer: Orchestration

### 2. **Dependency Injection**
- `AutoCenterController` accepts `time_func` parameter
- Enables testing with fake time
- Makes code testable without mocking global state

### 3. **Strategy Pattern**
- `ColorStyleStrategy` and subclasses
- Easy to add new row color styles
- Open/Closed Principle

### 4. **State Machine**
- `RaceStateTracker` implements finish state machine
- Clear state transitions
- Easy to reason about race finish logic

### 5. **Pure Functions**
- `GapCalculator` uses static methods only
- No side effects
- Easy to test

### 6. **Observer Pattern (Qt Signals)**
- `DataUpdateSignal` for telemetry updates
- Thread-safe communication
- Decouples telemetry thread from UI thread

---

## Data Flow

### Session Start
```
User starts iRacing session
    │
    ▼
TelemetryProcessor connects to irsdk
    │
    ▼
Parse SessionInfo (drivers, classes, etc.)
    │
    ▼
DivisionManager loads division config
    │
    ▼
UI displays initial grid
```

### During Race (Real-time Updates)
```
TelemetryProcessor reads live data every 0.5-2.0s
    │
    ▼
PositionCalculator: Calculate positions → List[DriverState]
    │
    ▼
Filter to player's class (multi-class support)
    │
    ▼
Sort by position
    │
    ▼
For each DriverState:
    ├─> Set division_name and division_color (DivisionManager)
    ├─> Calculate and set division_position
    ├─> Calculate and set gap (GapCalculator)
    └─> Set is_player flag
    │
    ▼
Emit signal with List[DriverState]
    │
    ▼
UI thread receives signal
    │
    ▼
DriverRowRenderer creates/updates widgets (reads DriverState attributes)
    │
    ▼
AutoCenterController determines if should scroll
    │
    ▼
Display updated grid
```

### Race Finish
```
Leader approaches finish line
    │
    ▼
RaceStateTracker.set_checkered_flag()
    │
    ▼
Leader crosses line
    │
    ▼
RaceStateTracker.set_leader_finished()
    │
    ▼
For each following car crossing line:
    ├─> RaceStateTracker.mark_driver_finished()
    ├─> Store finish snapshot (DriverState with locked position, gap, lap)
    ├─> Recalculate division gaps (updates DriverState.finish_gap)
    └─> Lock display for that driver
    │
    ▼
All cars finished → Race complete
```

### Session Change
```
User joins new session or restarts
    │
    ▼
TelemetryProcessor detects session change
    │
    ▼
Signal sent to UI: session changed
    │
    ▼
LeagueOverlay._handle_telemetry_update():
    ├─> Clear race_data
    ├─> Reset player_car_idx
    └─> Update session tracking
    │
    ▼
RaceStateTracker.reset()
    │
    ▼
Fresh state for new session
```

---

## Threading Model

### Main Thread (Qt Event Loop)
- Handles all UI interactions
- Processes signals from telemetry thread
- Renders driver rows
- Handles user input (scrolling, context menus, settings)

### Telemetry Thread (Background)
- Runs `_telemetry_loop()` continuously
- Reads iRacing SDK data
- Processes telemetry via `TelemetryProcessor`
- Emits `DataUpdateSignal` with race data
- **Never touches UI directly**

### Thread Communication
```
Telemetry Thread                Main Thread
      │                              │
      ├─── Read irsdk data
      ├─── Process with              │
      │    TelemetryProcessor        │
      │                              │
      ├─── Emit DataUpdateSignal ───>│
      │                              │
      │                         Receive signal
      │                              │
      │                         Update UI widgets
      │                              │
      ├<──────────────────────────── Continue
      │
      └─── Sleep refresh_rate seconds
      │
      └─── Repeat
```

**Benefits:**
- UI stays responsive (never blocked by telemetry processing)
- Telemetry can run at different rate than UI refresh
- Clean separation via Qt signals

---

## File I/O

### Configuration Files

#### `LeagueOverlay.config` (Settings)
- **Format**: JSON
- **Location**: Same directory as executable
- **Managed by**: `SettingsManager`
- **Contents**: Window position, opacity, fonts, division colors, league_config, recent_local_configs, etc.

#### `LeagueOverlay.log` (Application Log)
- **Format**: Plain text
- **Location**: Same directory as executable
- **Managed by**: `logging_config.setup_logging()`
- **Contents**: Startup info, errors, state changes, version info
- **Behavior**: Rotating file handler (1MB max per file, 1 backup, 2MB total)
- **Usage**: Debugging, user support, troubleshooting

#### League Configuration Files (Driver Assignments)

**Two modes:**

1. **Official Remote Leagues** (Recommended)
   - **Format**: Remote JSON fetched from URL
   - **Identifier**: "official:{league_name}" in settings
   - **Managed by**: `DivisionManager` with `official_leagues.py`
   - **Caching**: Automatically cached locally (e.g., `cache_broken_wing_gt3.json`)
   - **Offline support**: Falls back to cache if remote fetch fails
   - **Updates**: Refreshed on demand via Settings dialog
   - **Sharing**: Centrally managed, no manual file distribution needed

2. **Local Files** (Legacy/Custom)
   - **Format**: JSON
   - **Location**: User-specified path (absolute)
   - **Managed by**: `DivisionManager`
   - **Recent files**: MRU list maintained (max 5) in settings
   - **Sharing**: Manual file distribution required

**Division Config Structure:**
```json
{
  "drivers": [
    {
      "id": "123456",           // iRacing user ID (preferred)
      "name": "Driver Name",    // Fallback if ID not available
      "division": "Pro"         // Division assignment
    }
  ]
}
```

---

## Testing Architecture

### Unit Tests (485 tests)

**Test Organization:**
```
tests/
├── conftest.py                         # Shared fixtures
├── test_auto_center_controller.py      # 27 tests
├── test_config/
│   ├── test_settings_manager.py        # 36 tests
│   └── test_settings_validator.py      # 58 tests
└── test_core/
    ├── test_gap_calculator.py          # 36 tests
│   ├── test_gap_calculator_combined_columns.py  # 40 tests (combined rating, pit lap, license colors)
    ├── test_division_manager.py        # 27 tests
    ├── test_division_filter.py         # 29 tests
    ├── test_position_calculator.py     # 26 tests
    ├── test_race_state_tracker.py      # 32 tests
    └── test_telemetry_processor.py     # 37 tests
```

**Testing Principles:**
1. **Mock external dependencies** (irsdk mocked, no iRacing required)
2. **Use tmp_path** for file I/O tests
3. **Inject dependencies** for time-based tests
4. **Test behavior, not implementation**
5. **Cover edge cases** (None, empty, invalid data)


---

## Performance Considerations

### Telemetry Processing
- Configurable refresh rate (0.25-5.0 seconds)
- Only process data for player's class (skip other classes)
- **O(1) division lookups** - Hash-based caching via `_division_cache_by_id` and `_division_cache_by_name` (95%+ faster than O(n) linear search)
- **O(1) session results lookups** - Cached dictionary instead of repeated linear searches
- **Lap time persistence** - Driver lap times cached and preserved when drivers go inactive, preventing data loss during session transitions

### UI Rendering
- Only update changed rows (Qt handles this automatically)
- Use QLabel caching where possible
- Scroll view only when needed (auto-center logic)

### Memory
- Limited to 64 cars maximum (iRacing limit)
- Snapshots stored only for finished drivers
- Old session data cleared on session change

---

## Future Improvements

### Potential Enhancements
- Consider async/await for telemetry (currently uses threads)
- Extract more methods from `league_overlay.py` for testability
- Add integration tests for full data flow
- Consider migrating to PySide6's asyncio support

---

## Key Design Decisions

### Why Modular Architecture?
- **Testability**: Core logic testable without UI
- **Maintainability**: Easy to find and fix bugs
- **Extensibility**: Add features without touching unrelated code
- **Reusability**: Modules can be used in other projects

### Why Static Methods in GapCalculator?
- No state needed
- Pure functions (same input → same output)
- Easy to test
- Clear intent (calculator doesn't maintain state)

### Why Separate DivisionManager?
- Division logic is complex (ID vs name matching, file I/O)
- Reusable in other contexts
- Easy to test in isolation
- Clear ownership of division configuration

### Why RaceStateTracker State Machine?
- Finish tracking is complex (checkered ≠ finished)
- State machine makes logic explicit
- Easy to debug (know exact state at any time)
- Testable state transitions

### Why Background Thread for Telemetry?
- UI must stay responsive
- iRacing SDK read can be slow
- Allows independent update rates (telemetry vs UI)
- Qt signals provide clean thread communication

### Why DriverState Dataclass Instead of Dicts?
- **Type Safety**: IDE autocomplete and type checking catch bugs at development time
- **Performance**: Direct attribute access is faster than dict lookups
- **Clarity**: Explicit fields (`driver.car_number`) vs. arbitrary keys (`driver['car_number']`)
- **Consistency**: Single data structure used everywhere eliminates parallel data structures
- **Maintainability**: Changes to driver data structure are compile-time checked
- **Properties**: Computed properties (like `total_track_position`) encapsulate logic
- **Eliminated ~120 lines**: Removed redundant intermediate dicts and parameter passing

**Migration Benefits:**
- Eliminated `get_driver_color_fn` parameter (9 method signatures simplified)
- Removed `all_drivers_with_colors` parallel list (~40 lines)
- Removed temporary dicts in gap calculations (~30 lines)
- Methods now modify DriverState directly instead of returning intermediate dicts
- All 319 tests still passing after migration

---

## Dependencies

### Core
- **Python 3.9+** - Language
- **PySide6** - Qt bindings for UI
- **irsdk** - iRacing SDK Python wrapper
- **requests** - HTTP library for remote league config fetching

### Testing
- **pytest** - Test framework
- **pytest-cov** - Coverage reporting
- **pytest-qt** - Qt testing support
- **pytest-mock** - Mocking utilities

### Utilities
- **packaging** - Version comparison (update checker)

---

## Conclusion

The iRacing League Overlay follows a clean, modular architecture with clear separation between configuration, business logic, and UI. This design makes the codebase testable, maintainable, and extensible.
