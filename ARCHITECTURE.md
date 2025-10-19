# league_overlay.py

## Overview

BB's League Overlay - Real-time iRacing race position overlay utilizing irsdk

KEY CONCEPTS:
1. REAL-TIME vs OFFICIAL POSITIONS
   - Official: Only updates when crossing start/finish line (iRacing default)
   - Real-time: Updates constantly based on track position (lap + lap%)
   - This overlay uses real-time during race, official after finish (and best lap time during practice or qualifying)

2. DIVISION SYSTEM
   - Drivers are assigned to divisions via league_divisions.json (or other loaded) config file
   - Each division has a color (customizable in settings)
   - Gaps are calculated within divisions (Pro only competes with Pro, etc.)
   - Right-click any driver to change their division

3. FINISH TRACKING
   - Checkered flag waves when leader approaches the finish line, but race isn't over
   - Tracks when each car completes their current lap after checkered
   - Locks positions and gaps at the moment each car finishes
   - Prevents position changes after individual cars finish

4. UI FEATURES
   - Frameless, always-on-top window
   - Auto-hide headers on mouse leave (optional)
   - Auto-center on player (allows manual scroll but auto-centers again after 5 seconds)
   - Three color styles: Default, Alternate, Outline
   - Adjustable opacity, refresh rate, and font sizes
   - Opacity setting affects background but text stays at full opacity

5. OTHER NOTES
   - Multi-class race support (always only show cars within same class)
   - Class refers to different types of cars (LMP2, GT3, GT4, etc), Divisions refers to groupings of drivers within the same class

CRITICAL iRACING SDK VARIABLES USED IN THIS APPLICATION

The irsdk library provides access to iRacing telemetry through a dict-like interface.
Access variables like: ir['VariableName']

KEY TELEMETRY VARIABLES USED:
─────────────────────────────────────────────────────────────────────────────

SESSION INFO (from ir['SessionInfo'] - YAML structure):
    SessionInfo['Sessions'][session_num]['SessionType']
        - Type: string - "Practice", "Qualify", "Race"
        - Purpose: Determine if we use real-time or official positions

    SessionInfo['Sessions'][session_num]['ResultsPositions']
        - Type: list[dict] with 'CarIdx', 'ClassPosition', 'FastestTime'
        - When: Only after session ends (checkered flag)
        - Purpose: Get final results and lap times

    DriverInfo['Drivers']
        - Type: list[dict] with 'CarIdx', 'UserID', 'UserName', 'CarClassID', 'CarNumber'
        - When: Always available
        - Purpose: Map car indices to driver info for display

LIVE TELEMETRY VARIABLES (from ir['VariableName'] - updated each tick):
    SessionNum: int
        - Current session number (0=practice, 1=qualify, 2=race typically)
        - Purpose: Detect session changes to reset state

    SessionState: int
        - 0=Invalid, 1=GetInCar, 2=Warmup, 3=ParadeLaps, 4=Racing, 5=Checkered, 6=CoolDown
        - CRITICAL: SessionState >= 5 means checkered flag has waved
        - Purpose: Trigger race finish tracking

    PlayerCarIdx: int
        - Index of player's car (0-63)
        - Purpose: Auto-centering and "My Division" filter

    CarIdxLap: list[int] - Array indexed by car_idx
        - Current lap number for each car
        - CRITICAL: Used to detect when cars complete finish lap
        - Edge case: Can be -1 if car not on track

    CarIdxLapDistPct: list[float] - Array indexed by car_idx
        - Percentage through current lap (0.0 to 1.0)
        - CRITICAL: Used for real-time position calculation
        - Edge case: Can be -1.0 if car not on track, >1.0 rarely (glitch)

    CarIdxClassPosition: list[int] - Array indexed by car_idx
        - Official class position (updated at start/finish line)
        - Value 0 = car not participating/active
        - Purpose: Get official positions, filter active cars

    CarIdxEstTime: list[float] - Array indexed by car_idx
        - iRacing's estimated time (for time-based gap calculation)
        - More accurate than distance when cars on same lap
        - Value 0 = no estimate available

EDGE CASES & ASSUMPTIONS:
─────────────────────────────────────────────────────────────────────────────
1. Car indices (car_idx) range from 0-63, even in small fields
2. Arrays are always length 64, even with fewer cars
3. Position 0 in CarIdxClassPosition means "not active" (DNF, spectator, etc.)
4. Lap numbers can be -1 (car in pits, not on track yet)
5. LapDistPct should be 0.0-1.0 but can exceed (treat as 0 if invalid)
6. SessionState transitions: Racing(4) -> Checkered(5) -> CoolDown(6)
7. ResultsPositions update each lap

RACE FINISH STATE MACHINE

PROBLEM: iRacing waves checkered flag when leader crosses line, but other cars
haven't finished yet. We need to track when EACH car finishes their current lap.

STATE MACHINE FLOW:
─────────────────────────────────────────────────────────────────────────────

STATE 0: RACING (SessionState < 5)
    Variables: All finish tracking vars are None/False/empty
    Exit condition: SessionState >= 5 (checkered flag)
    → Transition to STATE 1

STATE 1: CHECKERED WAVED, IDENTIFYING FINISH LAP
    leader_last_lap = None
    leader_finished = False

    Action: Find P1 car, record their current lap number
    Variables set:
        - leader_last_lap = current lap of P1
        - leader_car_idx = car_idx of P1

    Purpose: This lap number is the "finish lap" - when it increments,
             that car has crossed the finish line and completed the race

    Exit condition: leader_last_lap is set
    → Transition to STATE 2

STATE 2: WAITING FOR LEADER TO COMPLETE FINISH LAP
    leader_last_lap = <lap number>
    leader_finished = False

    Action: Every tick, check if current P1's lap > leader_last_lap
    Purpose: Leader might change due to last-lap pass

    Exit condition: Current P1's lap increments
    Variables set:
        - leader_finished = True
        - finished_drivers.add(leader_car_idx)
        - driver_snapshots[leader]['official_position'] = final position

    → Transition to STATE 3

STATE 3: LEADER DONE, TRACKING OTHER DRIVERS FINISHING
    leader_finished = True
    finished_drivers = {leader_car_idx, ...}

    Action: For each car NOT in finished_drivers:
        - Check if their lap incremented (compared to snapshot)
        - If yes: Add to finished_drivers, capture official_position
        - final_gaps[car_idx] preserved from last update before finish

    Purpose: Each car finishes when their lap counter increments
    Exit condition: All cars finish or session ends
    → Stay in STATE 3 until session change (resets to STATE 0)

KEY INVARIANTS:
─────────────────────────────────────────────────────────────────────────────
1. Once in finished_drivers, a car never leaves (until session reset)
2. Gaps are continuously updated for racing cars, frozen on finish
3. leader_last_lap never changes after initial set (even if P1 changes)
4. States only progress forward, reset only on session change

CRITICAL EDGE CASES:
─────────────────────────────────────────────────────────────────────────────
1. Last-lap pass: P1 at checkered might not be P1 at finish
   → Track "current P1" each update, not "P1 when checkered waved"

2. Disconnected cars: May finish based on ResultsPositions, not lap increment
   → Handle separately in disconnected driver logic

3. Multi-class: Only track cars in player's class
   → Filter by CarClassID before processing

## Contents

### Classes
- [SessionType](#sessiontype)
- [SessionState](#sessionstate)
- [ColorStyle](#colorstyle)
- [UIConfig](#uiconfig)
- [FileConfig](#fileconfig)
- [TelemetryConfig](#telemetryconfig)
- [DriverData](#driverdata)
- [DivisionManager](#divisionmanager)
- [GapCalculator](#gapcalculator)
- [RaceStateTracker](#racestatetracker)
- [DataUpdateSignal](#dataupdatesignal)
- [CustomSizeGrip](#customsizegrip)
- [LeagueOverlay](#leagueoverlay)
- [SettingsDialog](#settingsdialog)

### Functions
- [main](#main)
- [__post_init__](#__post_init__)
- [__init__](#__init__)
- [load_driver_config](#load_driver_config)
- [load_division_config](#load_division_config)
- [save_config](#save_config)
- [get_driver_division](#get_driver_division)
- [set_driver_division](#set_driver_division)
- [get_division_color](#get_division_color)
- [set_division_color](#set_division_color)
- [calculate_time_gap](#calculate_time_gap)
- [calculate_lap_gap](#calculate_lap_gap)
- [format_gap_display](#format_gap_display)
- [__init__](#__init__)
- [reset](#reset)
- [is_racing](#is_racing)
- [set_checkered_flag](#set_checkered_flag)
- [mark_driver_finished](#mark_driver_finished)
- [is_driver_finished](#is_driver_finished)
- [get_final_gap](#get_final_gap)
- [update_snapshot](#update_snapshot)
- [get_snapshot](#get_snapshot)
- [__init__](#__init__)
- [set_parent_window](#set_parent_window)
- [paintEvent](#paintevent)
- [__init__](#__init__)
- [get_bg_color](#get_bg_color)
- [get_font_size](#get_font_size)
- [blend_color_with_black](#blend_color_with_black)
- [create_gradient_background](#create_gradient_background)
- [get_inverse_color](#get_inverse_color)
- [update_all_backgrounds](#update_all_backgrounds)
- [setup_ui](#setup_ui)
- [update_scroll_area_style](#update_scroll_area_style)
- [update_status_style](#update_status_style)
- [create_title_bar](#create_title_bar)
- [create_headers](#create_headers)
- [show_version_on_startup](#show_version_on_startup)
- [check_and_notify_updates](#check_and_notify_updates)
- [check_for_updates](#check_for_updates)
- [toggle_division_filter](#toggle_division_filter)
- [on_manual_scroll](#on_manual_scroll)
- [resizeEvent](#resizeevent)
- [load_color_config](#load_color_config)
- [load_settings](#load_settings)
- [load_division_colors](#load_division_colors)
- [save_settings](#save_settings)
- [save_color_config](#save_color_config)
- [get_driver_division](#get_driver_division)
- [set_driver_division](#set_driver_division)
- [update_driver_row_color](#update_driver_row_color)
- [get_driver_color](#get_driver_color)
- [refresh_driver_colors](#refresh_driver_colors)
- [open_settings](#open_settings)
- [hide_top_elements](#hide_top_elements)
- [show_top_elements](#show_top_elements)
- [enterEvent](#enterevent)
- [leaveEvent](#leaveevent)
- [focusInEvent](#focusinevent)
- [focusOutEvent](#focusoutevent)
- [timerEvent](#timerevent)
- [close_application](#close_application)
- [telemetry_loop](#telemetry_loop)
- [calculate_real_time_positions](#calculate_real_time_positions)
- [get_official_positions](#get_official_positions)
- [update_finish_status](#update_finish_status)
- [get_position_from_results](#get_position_from_results)
- [get_fastest_lap_time](#get_fastest_lap_time)
- [get_best_lap_from_session_info](#get_best_lap_from_session_info)
- [reset_fields](#reset_fields)
- [process_telemetry](#process_telemetry)
- [update_gui](#update_gui)
- [display_race_data](#display_race_data)
- [center_on_player](#center_on_player)
- [create_driver_row](#create_driver_row)
- [show_context_menu](#show_context_menu)
- [update_status_label](#update_status_label)
- [mousePressEvent](#mousepressevent)
- [mouseMoveEvent](#mousemoveevent)
- [mouseReleaseEvent](#mousereleaseevent)
- [__init__](#__init__)
- [setup_ui](#setup_ui)
- [on_opacity_change](#on_opacity_change)
- [choose_color](#choose_color)
- [create_new_config](#create_new_config)
- [load_config](#load_config)
- [reset_to_defaults](#reset_to_defaults)
- [apply_settings](#apply_settings)
- [on_cancel](#on_cancel)

## Classes

### SessionType

*Line 210*

iRacing session types.

### SessionState

*Line 217*

iRacing session states.

### ColorStyle

*Line 228*

Available color styles for driver rows.

### UIConfig

*Line 236*

UI configuration constants.

#### Methods

##### `__post_init__()`

*No documentation provided.*

### FileConfig

*Line 301*

File path configuration constants.

### TelemetryConfig

*Line 308*

Telemetry configuration constants.

### DriverData

*Line 328*

Data structure for a single driver's information.

### DivisionManager

*Line 353*

Manages driver-to-division assignments and color configuration.

Responsibilities:
- Load/save division configuration from/to JSON file
- Assign drivers to divisions (Pro, ProAm, Am, Rookie)
- Provide division colors for UI rendering
- Handle default division colors

#### Methods

##### `__init__()`

Initialize division manager.

Args:
    config_file: Path to JSON file containing driver-division mappings

##### `load_driver_config()`

Load driver-division mappings from config file.

##### `load_division_config()`

Load division colors

##### `save_config()`

Save driver-division mappings to config file.

##### `get_driver_division()`

Get the division assigned to a driver.

Args:
    driver_info: Dictionary with 'UserID' and 'UserName' keys

Returns:
    Division name (e.g., "Pro", "ProAm") or None if not assigned

##### `set_driver_division()`

Assign a driver to a division or remove assignment.

Args:
    driver_info: Dictionary with 'UserID' and 'UserName' keys
    division: Division name to assign (e.g., "Pro", "ProAm", "Am", "Rookie")
             or "Default" to remove the driver from config

Note:
    Setting division to "Default" removes the driver from the config,
    causing them to display with the default white color.

##### `get_division_color()`

Get the color hex code for a division.

Args:
    division: Division name (e.g., "Pro", "ProAm")

Returns:
    Hex color code (e.g., "#FF8C00")

##### `set_division_color()`

Set the color for a division.

Args:
    division: Division name
    color: Hex color code

### GapCalculator

*Line 511*

Calculates and formats time/distance gaps between cars.

Responsibilities:
- Calculate time-based gaps using iRacing telemetry
- Calculate lap-based gaps for cars on different laps
- Format gap strings for display (e.g., "5.3", "2L", "Leader")
- Handle edge cases (disconnected cars, invalid data)

#### Methods

##### `calculate_time_gap()`

Calculate time gap in seconds between two cars.

Args:
    est_time_ahead: Estimated time for car ahead (from CarIdxEstTime)
    est_time_behind: Estimated time for car behind (from CarIdxEstTime)

Returns:
    Time gap in seconds, or None if data invalid

##### `calculate_lap_gap()`

Calculate lap difference between two cars based on lap + possibly distance.

Args:
    lap_ahead: Lap number + optionally current lap distance of car ahead
    lap_behind: Lap number + optionally current lap distance of car behind

Returns:
    Number of laps behind (always >= 0)

##### `format_gap_display()`

Format gap for display in UI.

Args:
    time_gap: Time gap in seconds (None if not on same lap)
    lap_gap: Number of laps behind
    is_leader: Whether this is the race leader
    is_disconnected: Whether driver is disconnected

Returns:
    Formatted gap string (e.g., "Leader", "5.3", "2L", "(DC)")

### RaceStateTracker

*Line 587*

Tracks race finish state machine and completed laps after checkered flag.

State Machine:
- RACING: Normal racing, no checkered flag yet
- CHECKERED_WAVED: Checkered flag shown, waiting for leader to finish
- LEADER_FINISHED: Leader completed, tracking other cars finishing

Responsibilities:
- Track when checkered flag waves
- Detect when each car completes their finish lap
- Freeze positions and gaps when cars finish
- Handle disconnected drivers in final results

#### Methods

##### `__init__()`

Initialize race state tracker.

##### `reset()`

Reset all finish tracking state (called on session change).

##### `is_racing()`

Check if race is still in progress (not finished).

Returns:
    True if race is ongoing, False if checkered flag waved

##### `set_checkered_flag()`

Mark checkered flag as waved and record leader state.

Args:
    leader_car_idx: Car index of current leader
    leader_lap: Current lap number of leader

##### `mark_driver_finished()`

Mark a driver as having completed their finish lap.

Args:
    car_idx: Car index of finished driver
    gap: Final gap string to freeze
    official_position: Final official position

##### `is_driver_finished()`

Check if a driver has finished their race.

Args:
    car_idx: Car index to check

Returns:
    True if driver has completed their finish lap

##### `get_final_gap()`

Get the frozen gap for a finished driver.

Args:
    car_idx: Car index

Returns:
    Frozen gap string, or None if not finished

##### `update_snapshot()`

Update or create driver snapshot with current state.

Args:
    car_idx: Car index
    snapshot_data: Dictionary with driver state (lap, position, etc.)

##### `get_snapshot()`

Get stored snapshot for a driver.

Args:
    car_idx: Car index

Returns:
    Snapshot dictionary or None if not found

### DataUpdateSignal

*Line 708*

Signal emitter for thread-safe GUI updates.

Emits signals from telemetry thread to UI thread for safe updates.

### CustomSizeGrip

*Line 717*

Custom size grip widget with transparent background and conditional visibility.

Shows diagonal arrow pattern when parent window has focus, allows window resizing.

#### Methods

##### `__init__()`

Initialize custom size grip.

Args:
    parent: Parent widget

##### `set_parent_window()`

Set reference to parent window for focus checking.

Args:
    window: Parent main window reference

##### `paintEvent()`

Custom paint to show diagonal arrows when focused with transparent background.

Args:
    event: Paint event

### LeagueOverlay

*Line 787*

Main application window for iRacing race position overlay.

KEY INSTANCE VARIABLES - DATA STRUCTURES & THEIR LIFECYCLE
============================================================

IRSDK CONNECTION:
    self.ir: irsdk.IRSDK instance - Connection to iRacing simulator
        - Provides telemetry data via self.ir['VariableName']
        - Must call startup() before use, shutdown() on disconnect
        - Access like dict: self.ir['SessionState'], self.ir['CarIdxLap']

    self.is_connected: bool - Whether currently connected to iRacing
        - Set True when ir.startup() succeeds
        - Set False when ir.is_connected fails (iRacing closed)

    self.running: bool - Main loop control flag
        - Set False to stop telemetry thread (on app close)

SESSION STATE TRACKING (cleared on session change):
    self.driver_snapshots: dict[int, dict] - Last known state of each car
        - Key: car_idx (iRacing's car index, 0-63)
        - Value: Full driver data with position, lap, lap_pct, etc.
        - Used to track disconnected drivers and finish status
        - CLEARED: On session number or type change

    self.current_session_num: int | None - iRacing's session number
        - 0 = practice, 1 = qualify, 2 = race (typically)
        - Used to detect session changes and reset state

    self.current_session_type: str | None - "Race", "Practice", "Qualify"
        - Used with session_num to detect transitions

RACE FINISH STATE MACHINE (see detailed diagram below):
    self.leader_finished: bool - Has the race leader completed their finish lap?
        - False: Still racing or waiting for leader
        - True: Leader done, now tracking other drivers finishing

    self.finished_drivers: set[int] - Car indices that have finished
        - Added when car's lap increments after checkered flag
        - Prevents re-processing the same finish

    self.leader_car_idx: int | None - Car index of the race leader
        - Set when checkered flag waves (SessionState >= 5)

    self.leader_last_lap: int | None - Lap number leader was on at checkered
        - When this lap increments, leader has truly finished
        - CRITICAL: Used to determine "finish lap" for all drivers

    self.final_gaps: dict[int, str] - Frozen gap strings for finished drivers
        - Key: car_idx
        - Value: Gap string like "5.3", "2L", "Leader"
        - Continuously updated during race, frozen on finish

PLAYER IDENTIFICATION:
    self.player_car_idx: int | None - iRacing index of player's car
        - From self.ir['PlayerCarIdx']
        - Used for auto-centering and "My Division" filter
        - CLEARED: On session change (re-detected)

    self.player_car_class_id: int | None - Player's car class (multi-class)
        - Used to filter overlay to only player's class
        - CLEARED: On session change

UI DATA:
    self.race_data: list[dict] - All drivers from telemetry (unfiltered)
        - Updated by telemetry thread, filtered in update_gui()

    self.displayed_data: list[dict] - Filtered data currently shown in UI
        - Copy of race_data after division filtering applied
        - Used to preserve context for UI updates

#### Methods

##### `__init__()`

*No documentation provided.*

##### `get_bg_color()`

Convert a hex color to RGBA format with current window opacity.

Purpose: All background colors must respect the user's opacity setting for
the semi-transparent overlay effect. This centralizes that conversion.

Args:
    base_color: Hex color string like "#FF8C00" or "rgba(...)" already

Returns:
    RGBA string like "rgba(255, 140, 0, 0.5)" for use in stylesheets

Assumptions:
    - self.opacity is a float between 0.0 and 1.0
    - Input is either hex format or already rgba (passed through unchanged)

##### `get_font_size()`

Get the appropriate font size or spacing for a UI element.

Purpose: Centralizes font sizing to make the entire UI scale together
when user changes font size setting (Small/Medium/Large/Extra Large).

Args:
    element_type: One of "title", "button", "status", "header", "data", "spacing"

Returns:
    For font elements: String like "9pt", "10pt", etc.
    For "spacing": Integer pixel value (2, 3, 4, 5)

Why this exists: Different UI elements need different sizes, but they
should all scale proportionally when user adjusts the font size setting.

##### `blend_color_with_black()`

Blend a division color with black to create a subtle tinted background.

Purpose: Used for gradient backgrounds on player rows. We want a hint of
the division color without being too bright or distracting. This creates
a "glow" effect that's visible but doesn't overpower the text.

Args:
    color_hex: Division color like "#FF8C00" (orange for Pro)
    amount: How much of the color to keep (0.0 = pure black, 1.0 = full color)
           Default 0.15 gives a subtle tint, 0.25 is more visible

Returns:
    Hex color string like "#261500" (very dark orange)

Why this exists: Pure division colors are too bright for backgrounds.
We need darkened versions that still convey the division color.

##### `create_gradient_background()`

Create a horizontal gradient that creates a subtle "glow" effect for player row.

Purpose: Makes the player's row stand out without being overpowering.
The gradient goes from tinted color on edges to dark gray in the middle.

Args:
    color_hex: Division color like "#FF8C00"

Returns:
    Qt gradient string for stylesheet backgrounds

Why this exists: A solid colored background would be too bright and
distracting. A gradient gives a nice subtle highlight that draws the eye
to the player without overwhelming the data.

Visual effect: [dark orange] -> [dark gray] -> [dark orange]

##### `get_inverse_color()`

Calculate the inverse/complementary color for maximum contrast.

Purpose: Currently unused, but intended for future features that might
need high contrast text on colored backgrounds (like Alternate color style).

Args:
    color_hex: Hex color like "#FF8C00"

Returns:
    Inverted hex color like "#0073FF"

How it works: Inverts each RGB channel (255 - value)
Example: Orange #FF8C00 -> Blue #0073FF

Assumptions: Input is a valid 6-character hex color

##### `update_all_backgrounds()`

Refresh all UI backgrounds, fonts, and styling after settings change.

Purpose: When user changes opacity, font size, or color style in settings,
we need to update all existing UI elements to reflect the new values.

Why this exists: Qt doesn't automatically update stylesheets when variables
change. We must manually reapply styles to all widgets that depend on
opacity or font settings.

Called by:
    - Settings dialog when user changes opacity slider
    - Settings dialog when applying changes
    - On startup after loading saved settings

Assumptions:
    - All UI widgets have been created (checks with hasattr)
    - self.opacity and self.font_size are already updated with new values

##### `setup_ui()`

Setup the main user interface

##### `update_scroll_area_style()`

Update scroll area style with current opacity

##### `update_status_style()`

Update status label style with current opacity

##### `create_title_bar()`

Create custom title bar

##### `create_headers()`

Create column headers

##### `show_version_on_startup()`

Show version on startup

##### `check_and_notify_updates()`

Check for updates

##### `check_for_updates()`

Check GitHub for updates

##### `toggle_division_filter()`

Toggle division filter - cycles through different division views.

Two modes:
1. Player is on track: Toggle between "All Divisions" and "My Division"
2. Player spectating: Cycle through each division (Pro -> ProAm -> Am -> Rookie -> All)

This allows spectators to focus on specific divisions, while active racers
can quickly filter to just their competition.

##### `on_manual_scroll()`

Record when user manually scrolls, to temporarily disable auto-centering.

Purpose: When user manually scrolls to look at other drivers, we don't
want auto-center immediately yanking the view back to the player.

Why this exists: Auto-centering is helpful but shouldn't fight user input.
By recording scroll time, center_on_player() can check if enough time has
passed (manual_scroll_timeout, default 5 seconds) before re-enabling.

How it works:
    1. User scrolls -> this sets last_manual_scroll = now
    2. Auto-center checks: if (now - last_manual_scroll < 5s), skip centering
    3. After 5s of no scrolling, auto-center resumes

Assumptions:
    - Connected to scroll_area.verticalScrollBar().valueChanged signal

##### `resizeEvent()`

Qt event handler: Window was resized by user or programmatically.

Purpose: Keep the resize grip (bottom-right corner handle) positioned
correctly as window size changes.

Why this exists: The size grip is a widget that must be manually positioned.
Qt doesn't auto-anchor it, so we must move it on every resize.

Args:
    event: QResizeEvent from Qt (unused, but required by Qt signature)

Assumptions:
    - size_grip widget exists (checked with hasattr)
    - Called automatically by Qt framework

##### `load_color_config()`

Load the driver-to-division mapping from JSON config file.

Purpose: Each league maintains a JSON file that maps drivers to divisions
(Pro, ProAm, Am, Rookie). This file is shared among league members so
everyone sees consistent division colors.

Returns:
    Dict with 'drivers' key containing list of driver entries:
    {'drivers': [
        {'id': '12345', 'name': 'John Doe', 'division': 'Pro'},
        ...
    ]}

Why this exists: Different leagues have different division structures.
Using a config file allows customization per league without code changes.

File migration: Automatically converts old format (dict of drivers) to
new format (drivers list) if needed.

Assumptions:
    - File is valid JSON or doesn't exist (returns empty structure)
    - File path is set in self.color_config_file

##### `load_settings()`

Load user preferences from LeagueOverlay.config JSON file.

Purpose: Persists window position, size, opacity, colors, and all user
preferences between application sessions.

Why this exists: Users want the overlay to remember their settings,
especially window position and opacity, so they don't have to reconfigure
every time they start the app.

Settings loaded:
    - Window position (x, y) and size (width, height)
    - Opacity and refresh rate
    - Font size and color style
    - UI preferences (hide_headers, center_drivers, bold_drivers)
    - Division color customizations
    - Path to league-specific driver config file

Assumptions:
    - File may not exist on first run (silently ignored)
    - Invalid JSON or missing keys are handled gracefully
    - Settings are validated elsewhere (e.g., opacity clamped to 0-1)

##### `load_division_colors()`

Load division colors

##### `save_settings()`

Persist current settings to LeagueOverlay.config JSON file.

Purpose: Automatically called when user moves/resizes window, closes app,
or applies settings changes. Ensures preferences survive between sessions.

Why this exists: Paired with load_settings() to provide persistent config.
Called frequently (on window move, resize, close) to minimize data loss.

Saves:
    - Current window geometry (position and size)
    - All user preferences (opacity, fonts, colors, etc.)
    - Path to active league config file

Assumptions:
    - Write permissions exist in current directory
    - Failures are non-fatal (prints error, continues)

##### `save_color_config()`

Save color configuration - delegates to DivisionManager.

Purpose: Called when user changes driver division assignments via
right-click context menu. Ensures changes are persisted.

Note: This method delegates to DivisionManager.save_config() to maintain
single source of truth for division persistence logic.

##### `get_driver_division()`

Get the assigned division for a driver - delegates to DivisionManager.

Lookup priority:
1. Match by UserID (most reliable, survives name changes)
2. Match by UserName (fallback)
3. Return None if not found (will use "Default" color)

Args:
    driver_info: Dictionary with 'UserID' and 'UserName' keys

Returns:
    Division name ("Pro", "ProAm", "Am", "Rookie") or None

Note:
    This method now delegates to DivisionManager to avoid duplicate logic.
    The division name maps to a color in available_colors.

##### `set_driver_division()`

Assign a driver to a division - delegates to DivisionManager.

This is called from the right-click context menu on driver rows.
Changes are immediately saved to the config file and UI refreshes.

Args:
    driver_info: Dict with 'UserID' and 'UserName'
    division_name: "Pro", "ProAm", "Am", "Rookie", or "Default"
                  "Default" removes the driver from the config

Note:
    This method now delegates to DivisionManager for the actual assignment,
    then triggers UI refresh. Single source of truth for division logic.

##### `update_driver_row_color()`

Update driver row color

##### `get_driver_color()`

Get color for driver

##### `refresh_driver_colors()`

Refresh all driver colors

##### `open_settings()`

Open settings dialog

##### `hide_top_elements()`

Hide title bar and status label

##### `show_top_elements()`

Show title bar and status label

##### `enterEvent()`

Mouse entered window

##### `leaveEvent()`

Mouse left window

##### `focusInEvent()`

Window gained focus - update size grip

##### `focusOutEvent()`

Window lost focus - update size grip

##### `timerEvent()`

Handle timer events for auto-hide

##### `close_application()`

Close application

##### `telemetry_loop()`

Background thread that continuously reads data from iRacing SDK.

Purpose: Runs in a separate thread to avoid blocking the UI. Continuously
polls iRacing for telemetry data at the configured refresh rate.

Why this exists: The iRacing SDK requires continuous polling. Running in
a thread keeps the UI responsive while we wait for data.

Flow:
    1. Try to connect to iRacing if not connected
    2. If connected, process telemetry data
    3. Sleep for refresh_rate seconds
    4. Repeat until self.running = False

Thread safety: Uses self.signals (Qt signals) to communicate updates
back to the main UI thread safely.

Assumptions:
    - irsdk library is properly installed
    - Runs as daemon thread (dies when main thread exits)
    - self.refresh_rate is a positive float (seconds)

##### `calculate_real_time_positions()`

Calculate real-time positions based on actual track position.

This provides more accurate positioning than iRacing's official positions,
which only update at the start/finish line. Real-time positions update
constantly based on where each car is on track.

Formula: total_track_position = current_lap + lap_distance_percentage
Example: Car on lap 5, 30% through = 5.30
         Car on lap 5, 90% through = 5.90 (ahead of the 30% car)

##### `get_official_positions()`

Get positions from iRacing's official timing system (updates at start/finish line).

Purpose: Used during practice/qualifying sessions where real-time position
tracking isn't needed. Simpler than calculate_real_time_positions() since
we just use iRacing's official positions directly.

Why this exists: Practice/qualifying don't need the complexity of real-time
tracking. Official positions are sufficient and more stable.

Returns:
    List of driver dicts with 'official_position' sorted by that position

Differences from calculate_real_time_positions():
    - No track position calculation (lap + lap%)
    - Uses official positions directly from iRacing
    - Faster, simpler, less CPU intensive

Assumptions:
    - CarIdxClassPosition is available in live_data
    - Position 0 means not active/participating

##### `update_finish_status()`

Track which drivers have finished the race after the checkered flag.

IMPORTANT: iRacing shows the checkered flag when the leader crosses the line,
but other drivers haven't finished yet. We need to track when each driver
completes their current lap after the checkered to know their final position.

This method:
1. Identifies what lap the leader is on when checkered waves
2. Waits for the leader to complete that lap (true finish)
3. Tracks each subsequent driver as they finish their current lap
4. Stores their official position at the moment they finish

##### `get_position_from_results()`

Look up a car's final position from session results.

Purpose: After race ends, iRacing provides complete results in SessionInfo.
This extracts the final class position for a specific car.

Why this exists: Used for:
    - Finished drivers (to lock in their final position)
    - Disconnected drivers after checkered (to show where they finished)

Args:
    current_session: Session dict from SessionInfo['Sessions'][session_num]
    car_idx: The car index to look up

Returns:
    1-based position (int) or -1 if not found

Assumptions:
    - Session has ResultsPositions array (only after session ends)
    - ClassPosition is 0-based, so we add 1

##### `get_fastest_lap_time()`

Find the fastest lap time in the session for gap estimation.

Purpose: When cars are on different laps, we estimate time gaps by
multiplying lap difference by average lap time. This finds the fastest
lap as a reasonable estimate.

Why this exists: Estimating gaps between cars on different laps requires
knowing typical lap time. Fastest lap is used as a baseline (assumes
cars lap at similar pace to the fastest).

Returns:
    Fastest lap time in seconds (float), or 90 if none found

Why 90 seconds: Fallback for when no laps recorded yet (session start).
90s is a reasonable default that won't cause divide-by-zero or absurd gaps.

Assumptions:
    - ResultsPositions exists and has FastestTime field
    - FastestTime of 0 means no lap recorded (skipped)

##### `get_best_lap_from_session_info()`

Look up a specific car's fastest lap time from session results.

Purpose: In practice/qualifying, gaps are shown as delta to best lap
times, not real-time gaps. This retrieves a car's personal best.

Why this exists: Practice/qualifying use different gap logic than racing.
Instead of "5.3s behind," it shows "+0.234" (delta to car ahead's best lap).

Args:
    current_session: Session dict from SessionInfo
    car_idx: Which car to look up

Returns:
    Best lap time in seconds (float), or 90 if not found/no laps

Why 90 seconds: Same reason as get_fastest_lap_time() - safe fallback.

Assumptions:
    - ResultsPositions exists (practice/qualifying sessions)
    - FastestTime field is present

##### `reset_fields()`

Clear all session-specific tracking data.

Purpose: Called when switching sessions (practice->qualify->race) or when
session number changes. Ensures we start fresh with no stale data.

Why this exists: Data from one session (like finish tracking) should not
carry over to the next session. Each session needs clean state.

Clears:
    - Race state tracker (finish tracking, snapshots, gaps)
    - Player identification (car_idx and class_id)
    - Legacy state variables for backward compatibility

Called by:
    - Session number change detection in process_telemetry()
    - Session type change (practice -> qualifying -> race)

Assumptions: None - safe to call at any time

##### `process_telemetry()`

Process telemetry data

##### `update_gui()`

Update GUI (called by timer)

##### `display_race_data()`

Display race data (thread-safe slot)

##### `center_on_player()`

Auto-center the scroll view on the player's position.

This only activates if the user hasn't manually scrolled recently
(see manual_scroll_timeout). Helps keep player visible during races
without fighting manual scrolling.

##### `create_driver_row()`

Create a driver row widget with styling based on color style.

Three color styles supported:
1. Default: Black background, colored text, player gets gradient glow
2. Alternate: Colored background, black text, player gets white border
3. Outline: Black background, colored border and text, player gets gradient glow

##### `show_context_menu()`

Display right-click menu to assign driver to a division.

Purpose: Provides quick UI to change a driver's division without opening
settings or editing JSON files manually.

Why this exists: During a race, league admins can quickly assign new
drivers to divisions by right-clicking their name.

Flow:
    1. User right-clicks any part of a driver row
    2. Menu shows: Pro, ProAm, Am, Rookie, Default
    3. User clicks division -> set_driver_division() -> saves to JSON
    4. UI refreshes with new color

Args:
    driver_data: Dict with 'driver_info' containing UserID and UserName

Assumptions:
    - available_colors dict has all division names
    - Called from driver row widgets' customContextMenuRequested signal

##### `update_status_label()`

Update the status message and color (thread-safe Qt slot).

Purpose: Display connection status and session type at top of overlay.
Examples: "Connecting...", "Connected - Live Data (Race)", "Update available"

Why this exists: Telemetry thread needs to communicate status to UI thread.
Qt requires slots to be called from signals for thread safety.

Args:
    text: Status message to display
    color: "green" (connected), "orange" (connecting), or hex like "#00FF00"

Thread safety: This is a Qt slot connected to self.signals.update_status,
so it's safe to call from the telemetry background thread.

Assumptions:
    - status_label widget exists
    - update_status_style() handles color setting

##### `mousePressEvent()`

Qt event handler: Mouse button pressed in window.

Purpose: Enable dragging the frameless window by its title bar.

Why this exists: With Qt.FramelessWindowHint, we lose the default OS
window dragging. This reimplements it for the title bar area.

How it works: Stores the click position offset, used in mouseMoveEvent()
to calculate new window position while dragging.

Assumptions:
    - Title bar height is 30 pixels
    - Only left-click drags

##### `mouseMoveEvent()`

Qt event handler: Mouse moved while button held.

Purpose: Update window position during drag operation.

Why this exists: Completes the drag functionality started in mousePressEvent().

Assumptions:
    - drag_position was set in mousePressEvent()
    - Left button is still held

##### `mouseReleaseEvent()`

Qt event handler: Mouse button released.

Purpose: End drag operation and save new window position to config.

Why this exists: Ensures window position is persisted immediately after
user moves the window, not just on app close (in case of crash).

Assumptions: Left button release ends drag

### SettingsDialog

*Line 3041*

Modal settings dialog for configuring overlay appearance and behavior.

Purpose: Provides a user-friendly GUI for all configurable options without
editing JSON files or using command-line arguments.

Settings provided:
    - Driver color config file (create new or load existing)
    - Window opacity (0.10 to 1.00 in 0.05 increments)
    - Refresh rate (0.25 to 5.0 seconds in 0.25 increments)
    - Font size (Small/Medium/Large/Extra Large)
    - Row color style (Default/Alternate/Outline)
    - UI preferences (auto-hide headers, center names, bold rows)
    - Division colors (customize Pro/ProAm/Am/Rookie colors)

Why this exists: Users shouldn't need to manually edit config files.
This provides safe, validated, live-preview access to all settings.

Features:
    - Live opacity preview (changes as you drag slider)
    - Cancel reverts opacity changes
    - Reset to defaults button
    - Shows update notification if new version available

#### Methods

##### `__init__()`

*No documentation provided.*

##### `setup_ui()`

Setup settings UI

##### `on_opacity_change()`

Live preview of opacity changes as user drags slider.

Purpose: Lets user see exactly how transparent/opaque the overlay will be
before committing the change with "Apply Settings."

Why this exists: Opacity is hard to judge from a number. Live preview
lets users find the perfect transparency for their setup.

Args:
    value: Slider value (2-20), divided by 20 to get 0.10-1.00 opacity

Note: Changes are temporary until "Apply Settings" clicked. "Cancel"
reverts to original_opacity stored in __init__.

##### `choose_color()`

Open color picker to customize a division's color.

Purpose: Allows leagues to customize division colors to match their
branding or preferences.

Why this exists: Default colors might not work for all leagues. Some
might want different colors for better visibility or aesthetics.

Args:
    division: "Pro", "ProAm", "Am", or "Rookie"

Flow:
    1. Opens Qt color picker dialog with current division color
    2. If user selects new color, updates:
       - available_colors dict
       - Color button preview
       - Hex code label
    3. Changes saved when "Apply Settings" clicked

Note: Changes affect ALL drivers in that division immediately after apply.

##### `create_new_config()`

Create new config file

##### `load_config()`

Load different config file

##### `reset_to_defaults()`

Reset to default settings

##### `apply_settings()`

Apply all settings

##### `on_cancel()`

Cancel settings

## Functions

### `main()`

*Line 3659*

*No documentation provided.*

### `__post_init__()`

*Line 253*

*No documentation provided.*

### `__init__()`

*Line 363*

Initialize division manager.

Args:
    config_file: Path to JSON file containing driver-division mappings

### `load_driver_config()`

*Line 376*

Load driver-division mappings from config file.

### `load_division_config()`

*Line 392*

Load division colors

### `save_config()`

*Line 406*

Save driver-division mappings to config file.

### `get_driver_division()`

*Line 414*

Get the division assigned to a driver.

Args:
    driver_info: Dictionary with 'UserID' and 'UserName' keys

Returns:
    Division name (e.g., "Pro", "ProAm") or None if not assigned

### `set_driver_division()`

*Line 435*

Assign a driver to a division or remove assignment.

Args:
    driver_info: Dictionary with 'UserID' and 'UserName' keys
    division: Division name to assign (e.g., "Pro", "ProAm", "Am", "Rookie")
             or "Default" to remove the driver from config

Note:
    Setting division to "Default" removes the driver from the config,
    causing them to display with the default white color.

### `get_division_color()`

*Line 487*

Get the color hex code for a division.

Args:
    division: Division name (e.g., "Pro", "ProAm")

Returns:
    Hex color code (e.g., "#FF8C00")

### `set_division_color()`

*Line 500*

Set the color for a division.

Args:
    division: Division name
    color: Hex color code

### `calculate_time_gap()`

*Line 522*

Calculate time gap in seconds between two cars.

Args:
    est_time_ahead: Estimated time for car ahead (from CarIdxEstTime)
    est_time_behind: Estimated time for car behind (from CarIdxEstTime)

Returns:
    Time gap in seconds, or None if data invalid

### `calculate_lap_gap()`

*Line 538*

Calculate lap difference between two cars based on lap + possibly distance.

Args:
    lap_ahead: Lap number + optionally current lap distance of car ahead
    lap_behind: Lap number + optionally current lap distance of car behind

Returns:
    Number of laps behind (always >= 0)

### `format_gap_display()`

*Line 552*

Format gap for display in UI.

Args:
    time_gap: Time gap in seconds (None if not on same lap)
    lap_gap: Number of laps behind
    is_leader: Whether this is the race leader
    is_disconnected: Whether driver is disconnected

Returns:
    Formatted gap string (e.g., "Leader", "5.3", "2L", "(DC)")

### `__init__()`

*Line 602*

Initialize race state tracker.

### `reset()`

*Line 606*

Reset all finish tracking state (called on session change).

### `is_racing()`

*Line 615*

Check if race is still in progress (not finished).

Returns:
    True if race is ongoing, False if checkered flag waved

### `set_checkered_flag()`

*Line 623*

Mark checkered flag as waved and record leader state.

Args:
    leader_car_idx: Car index of current leader
    leader_lap: Current lap number of leader

### `mark_driver_finished()`

*Line 634*

Mark a driver as having completed their finish lap.

Args:
    car_idx: Car index of finished driver
    gap: Final gap string to freeze
    official_position: Final official position

### `is_driver_finished()`

*Line 653*

Check if a driver has finished their race.

Args:
    car_idx: Car index to check

Returns:
    True if driver has completed their finish lap

### `get_final_gap()`

*Line 664*

Get the frozen gap for a finished driver.

Args:
    car_idx: Car index

Returns:
    Frozen gap string, or None if not finished

### `update_snapshot()`

*Line 675*

Update or create driver snapshot with current state.

Args:
    car_idx: Car index
    snapshot_data: Dictionary with driver state (lap, position, etc.)

### `get_snapshot()`

*Line 684*

Get stored snapshot for a driver.

Args:
    car_idx: Car index

Returns:
    Snapshot dictionary or None if not found

### `__init__()`

*Line 723*

Initialize custom size grip.

Args:
    parent: Parent widget

### `set_parent_window()`

*Line 734*

Set reference to parent window for focus checking.

Args:
    window: Parent main window reference

### `paintEvent()`

*Line 742*

Custom paint to show diagonal arrows when focused with transparent background.

Args:
    event: Paint event

### `__init__()`

*Line 861*

*No documentation provided.*

### `get_bg_color()`

*Line 992*

Convert a hex color to RGBA format with current window opacity.

Purpose: All background colors must respect the user's opacity setting for
the semi-transparent overlay effect. This centralizes that conversion.

Args:
    base_color: Hex color string like "#FF8C00" or "rgba(...)" already

Returns:
    RGBA string like "rgba(255, 140, 0, 0.5)" for use in stylesheets

Assumptions:
    - self.opacity is a float between 0.0 and 1.0
    - Input is either hex format or already rgba (passed through unchanged)

### `get_font_size()`

*Line 1016*

Get the appropriate font size or spacing for a UI element.

Purpose: Centralizes font sizing to make the entire UI scale together
when user changes font size setting (Small/Medium/Large/Extra Large).

Args:
    element_type: One of "title", "button", "status", "header", "data", "spacing"

Returns:
    For font elements: String like "9pt", "10pt", etc.
    For "spacing": Integer pixel value (2, 3, 4, 5)

Why this exists: Different UI elements need different sizes, but they
should all scale proportionally when user adjusts the font size setting.

### `blend_color_with_black()`

*Line 1036*

Blend a division color with black to create a subtle tinted background.

Purpose: Used for gradient backgrounds on player rows. We want a hint of
the division color without being too bright or distracting. This creates
a "glow" effect that's visible but doesn't overpower the text.

Args:
    color_hex: Division color like "#FF8C00" (orange for Pro)
    amount: How much of the color to keep (0.0 = pure black, 1.0 = full color)
           Default 0.15 gives a subtle tint, 0.25 is more visible

Returns:
    Hex color string like "#261500" (very dark orange)

Why this exists: Pure division colors are too bright for backgrounds.
We need darkened versions that still convey the division color.

### `create_gradient_background()`

*Line 1069*

Create a horizontal gradient that creates a subtle "glow" effect for player row.

Purpose: Makes the player's row stand out without being overpowering.
The gradient goes from tinted color on edges to dark gray in the middle.

Args:
    color_hex: Division color like "#FF8C00"

Returns:
    Qt gradient string for stylesheet backgrounds

Why this exists: A solid colored background would be too bright and
distracting. A gradient gives a nice subtle highlight that draws the eye
to the player without overwhelming the data.

Visual effect: [dark orange] -> [dark gray] -> [dark orange]

### `get_inverse_color()`

*Line 1090*

Calculate the inverse/complementary color for maximum contrast.

Purpose: Currently unused, but intended for future features that might
need high contrast text on colored backgrounds (like Alternate color style).

Args:
    color_hex: Hex color like "#FF8C00"

Returns:
    Inverted hex color like "#0073FF"

How it works: Inverts each RGB channel (255 - value)
Example: Orange #FF8C00 -> Blue #0073FF

Assumptions: Input is a valid 6-character hex color

### `update_all_backgrounds()`

*Line 1122*

Refresh all UI backgrounds, fonts, and styling after settings change.

Purpose: When user changes opacity, font size, or color style in settings,
we need to update all existing UI elements to reflect the new values.

Why this exists: Qt doesn't automatically update stylesheets when variables
change. We must manually reapply styles to all widgets that depend on
opacity or font settings.

Called by:
    - Settings dialog when user changes opacity slider
    - Settings dialog when applying changes
    - On startup after loading saved settings

Assumptions:
    - All UI widgets have been created (checks with hasattr)
    - self.opacity and self.font_size are already updated with new values

### `setup_ui()`

*Line 1222*

Setup the main user interface

### `update_scroll_area_style()`

*Line 1298*

Update scroll area style with current opacity

### `update_status_style()`

*Line 1322*

Update status label style with current opacity

### `create_title_bar()`

*Line 1333*

Create custom title bar

### `create_headers()`

*Line 1410*

Create column headers

### `show_version_on_startup()`

*Line 1444*

Show version on startup

### `check_and_notify_updates()`

*Line 1450*

Check for updates

### `check_for_updates()`

*Line 1463*

Check GitHub for updates

### `toggle_division_filter()`

*Line 1481*

Toggle division filter - cycles through different division views.

Two modes:
1. Player is on track: Toggle between "All Divisions" and "My Division"
2. Player spectating: Cycle through each division (Pro -> ProAm -> Am -> Rookie -> All)

This allows spectators to focus on specific divisions, while active racers
can quickly filter to just their competition.

### `on_manual_scroll()`

*Line 1553*

Record when user manually scrolls, to temporarily disable auto-centering.

Purpose: When user manually scrolls to look at other drivers, we don't
want auto-center immediately yanking the view back to the player.

Why this exists: Auto-centering is helpful but shouldn't fight user input.
By recording scroll time, center_on_player() can check if enough time has
passed (manual_scroll_timeout, default 5 seconds) before re-enabling.

How it works:
    1. User scrolls -> this sets last_manual_scroll = now
    2. Auto-center checks: if (now - last_manual_scroll < 5s), skip centering
    3. After 5s of no scrolling, auto-center resumes

Assumptions:
    - Connected to scroll_area.verticalScrollBar().valueChanged signal

### `resizeEvent()`

*Line 1573*

Qt event handler: Window was resized by user or programmatically.

Purpose: Keep the resize grip (bottom-right corner handle) positioned
correctly as window size changes.

Why this exists: The size grip is a widget that must be manually positioned.
Qt doesn't auto-anchor it, so we must move it on every resize.

Args:
    event: QResizeEvent from Qt (unused, but required by Qt signature)

Assumptions:
    - size_grip widget exists (checked with hasattr)
    - Called automatically by Qt framework

### `load_color_config()`

*Line 1598*

Load the driver-to-division mapping from JSON config file.

Purpose: Each league maintains a JSON file that maps drivers to divisions
(Pro, ProAm, Am, Rookie). This file is shared among league members so
everyone sees consistent division colors.

Returns:
    Dict with 'drivers' key containing list of driver entries:
    {'drivers': [
        {'id': '12345', 'name': 'John Doe', 'division': 'Pro'},
        ...
    ]}

Why this exists: Different leagues have different division structures.
Using a config file allows customization per league without code changes.

File migration: Automatically converts old format (dict of drivers) to
new format (drivers list) if needed.

Assumptions:
    - File is valid JSON or doesn't exist (returns empty structure)
    - File path is set in self.color_config_file

### `load_settings()`

*Line 1651*

Load user preferences from LeagueOverlay.config JSON file.

Purpose: Persists window position, size, opacity, colors, and all user
preferences between application sessions.

Why this exists: Users want the overlay to remember their settings,
especially window position and opacity, so they don't have to reconfigure
every time they start the app.

Settings loaded:
    - Window position (x, y) and size (width, height)
    - Opacity and refresh rate
    - Font size and color style
    - UI preferences (hide_headers, center_drivers, bold_drivers)
    - Division color customizations
    - Path to league-specific driver config file

Assumptions:
    - File may not exist on first run (silently ignored)
    - Invalid JSON or missing keys are handled gracefully
    - Settings are validated elsewhere (e.g., opacity clamped to 0-1)

### `load_division_colors()`

*Line 1711*

Load division colors

### `save_settings()`

*Line 1725*

Persist current settings to LeagueOverlay.config JSON file.

Purpose: Automatically called when user moves/resizes window, closes app,
or applies settings changes. Ensures preferences survive between sessions.

Why this exists: Paired with load_settings() to provide persistent config.
Called frequently (on window move, resize, close) to minimize data loss.

Saves:
    - Current window geometry (position and size)
    - All user preferences (opacity, fonts, colors, etc.)
    - Path to active league config file

Assumptions:
    - Write permissions exist in current directory
    - Failures are non-fatal (prints error, continues)

### `save_color_config()`

*Line 1764*

Save color configuration - delegates to DivisionManager.

Purpose: Called when user changes driver division assignments via
right-click context menu. Ensures changes are persisted.

Note: This method delegates to DivisionManager.save_config() to maintain
single source of truth for division persistence logic.

### `get_driver_division()`

*Line 1778*

Get the assigned division for a driver - delegates to DivisionManager.

Lookup priority:
1. Match by UserID (most reliable, survives name changes)
2. Match by UserName (fallback)
3. Return None if not found (will use "Default" color)

Args:
    driver_info: Dictionary with 'UserID' and 'UserName' keys

Returns:
    Division name ("Pro", "ProAm", "Am", "Rookie") or None

Note:
    This method now delegates to DivisionManager to avoid duplicate logic.
    The division name maps to a color in available_colors.

### `set_driver_division()`

*Line 1798*

Assign a driver to a division - delegates to DivisionManager.

This is called from the right-click context menu on driver rows.
Changes are immediately saved to the config file and UI refreshes.

Args:
    driver_info: Dict with 'UserID' and 'UserName'
    division_name: "Pro", "ProAm", "Am", "Rookie", or "Default"
                  "Default" removes the driver from the config

Note:
    This method now delegates to DivisionManager for the actual assignment,
    then triggers UI refresh. Single source of truth for division logic.

### `update_driver_row_color()`

*Line 1825*

Update driver row color

### `get_driver_color()`

*Line 1840*

Get color for driver

### `refresh_driver_colors()`

*Line 1847*

Refresh all driver colors

### `open_settings()`

*Line 1853*

Open settings dialog

### `hide_top_elements()`

*Line 1865*

Hide title bar and status label

### `show_top_elements()`

*Line 1872*

Show title bar and status label

### `enterEvent()`

*Line 1879*

Mouse entered window

### `leaveEvent()`

*Line 1889*

Mouse left window

### `focusInEvent()`

*Line 1898*

Window gained focus - update size grip

### `focusOutEvent()`

*Line 1904*

Window lost focus - update size grip

### `timerEvent()`

*Line 1910*

Handle timer events for auto-hide

### `close_application()`

*Line 1918*

Close application

### `telemetry_loop()`

*Line 1924*

Background thread that continuously reads data from iRacing SDK.

Purpose: Runs in a separate thread to avoid blocking the UI. Continuously
polls iRacing for telemetry data at the configured refresh rate.

Why this exists: The iRacing SDK requires continuous polling. Running in
a thread keeps the UI responsive while we wait for data.

Flow:
    1. Try to connect to iRacing if not connected
    2. If connected, process telemetry data
    3. Sleep for refresh_rate seconds
    4. Repeat until self.running = False

Thread safety: Uses self.signals (Qt signals) to communicate updates
back to the main UI thread safely.

Assumptions:
    - irsdk library is properly installed
    - Runs as daemon thread (dies when main thread exits)
    - self.refresh_rate is a positive float (seconds)

### `calculate_real_time_positions()`

*Line 1966*

Calculate real-time positions based on actual track position.

This provides more accurate positioning than iRacing's official positions,
which only update at the start/finish line. Real-time positions update
constantly based on where each car is on track.

Formula: total_track_position = current_lap + lap_distance_percentage
Example: Car on lap 5, 30% through = 5.30
         Car on lap 5, 90% through = 5.90 (ahead of the 30% car)

### `get_official_positions()`

*Line 2036*

Get positions from iRacing's official timing system (updates at start/finish line).

Purpose: Used during practice/qualifying sessions where real-time position
tracking isn't needed. Simpler than calculate_real_time_positions() since
we just use iRacing's official positions directly.

Why this exists: Practice/qualifying don't need the complexity of real-time
tracking. Official positions are sufficient and more stable.

Returns:
    List of driver dicts with 'official_position' sorted by that position

Differences from calculate_real_time_positions():
    - No track position calculation (lap + lap%)
    - Uses official positions directly from iRacing
    - Faster, simpler, less CPU intensive

Assumptions:
    - CarIdxClassPosition is available in live_data
    - Position 0 means not active/participating

### `update_finish_status()`

*Line 2092*

Track which drivers have finished the race after the checkered flag.

IMPORTANT: iRacing shows the checkered flag when the leader crosses the line,
but other drivers haven't finished yet. We need to track when each driver
completes their current lap after the checkered to know their final position.

This method:
1. Identifies what lap the leader is on when checkered waves
2. Waits for the leader to complete that lap (true finish)
3. Tracks each subsequent driver as they finish their current lap
4. Stores their official position at the moment they finish

### `get_position_from_results()`

*Line 2204*

Look up a car's final position from session results.

Purpose: After race ends, iRacing provides complete results in SessionInfo.
This extracts the final class position for a specific car.

Why this exists: Used for:
    - Finished drivers (to lock in their final position)
    - Disconnected drivers after checkered (to show where they finished)

Args:
    current_session: Session dict from SessionInfo['Sessions'][session_num]
    car_idx: The car index to look up

Returns:
    1-based position (int) or -1 if not found

Assumptions:
    - Session has ResultsPositions array (only after session ends)
    - ClassPosition is 0-based, so we add 1

### `get_fastest_lap_time()`

*Line 2234*

Find the fastest lap time in the session for gap estimation.

Purpose: When cars are on different laps, we estimate time gaps by
multiplying lap difference by average lap time. This finds the fastest
lap as a reasonable estimate.

Why this exists: Estimating gaps between cars on different laps requires
knowing typical lap time. Fastest lap is used as a baseline (assumes
cars lap at similar pace to the fastest).

Returns:
    Fastest lap time in seconds (float), or 90 if none found

Why 90 seconds: Fallback for when no laps recorded yet (session start).
90s is a reasonable default that won't cause divide-by-zero or absurd gaps.

Assumptions:
    - ResultsPositions exists and has FastestTime field
    - FastestTime of 0 means no lap recorded (skipped)

### `get_best_lap_from_session_info()`

*Line 2262*

Look up a specific car's fastest lap time from session results.

Purpose: In practice/qualifying, gaps are shown as delta to best lap
times, not real-time gaps. This retrieves a car's personal best.

Why this exists: Practice/qualifying use different gap logic than racing.
Instead of "5.3s behind," it shows "+0.234" (delta to car ahead's best lap).

Args:
    current_session: Session dict from SessionInfo
    car_idx: Which car to look up

Returns:
    Best lap time in seconds (float), or 90 if not found/no laps

Why 90 seconds: Same reason as get_fastest_lap_time() - safe fallback.

Assumptions:
    - ResultsPositions exists (practice/qualifying sessions)
    - FastestTime field is present

### `reset_fields()`

*Line 2293*

Clear all session-specific tracking data.

Purpose: Called when switching sessions (practice->qualify->race) or when
session number changes. Ensures we start fresh with no stale data.

Why this exists: Data from one session (like finish tracking) should not
carry over to the next session. Each session needs clean state.

Clears:
    - Race state tracker (finish tracking, snapshots, gaps)
    - Player identification (car_idx and class_id)
    - Legacy state variables for backward compatibility

Called by:
    - Session number change detection in process_telemetry()
    - Session type change (practice -> qualifying -> race)

Assumptions: None - safe to call at any time

### `process_telemetry()`

*Line 2328*

Process telemetry data

### `update_gui()`

*Line 2563*

Update GUI (called by timer)

### `display_race_data()`

*Line 2609*

Display race data (thread-safe slot)

### `center_on_player()`

*Line 2632*

Auto-center the scroll view on the player's position.

This only activates if the user hasn't manually scrolled recently
(see manual_scroll_timeout). Helps keep player visible during races
without fighting manual scrolling.

### `create_driver_row()`

*Line 2684*

Create a driver row widget with styling based on color style.

Three color styles supported:
1. Default: Black background, colored text, player gets gradient glow
2. Alternate: Colored background, black text, player gets white border
3. Outline: Black background, colored border and text, player gets gradient glow

### `show_context_menu()`

*Line 2905*

Display right-click menu to assign driver to a division.

Purpose: Provides quick UI to change a driver's division without opening
settings or editing JSON files manually.

Why this exists: During a race, league admins can quickly assign new
drivers to divisions by right-clicking their name.

Flow:
    1. User right-clicks any part of a driver row
    2. Menu shows: Pro, ProAm, Am, Rookie, Default
    3. User clicks division -> set_driver_division() -> saves to JSON
    4. UI refreshes with new color

Args:
    driver_data: Dict with 'driver_info' containing UserID and UserName

Assumptions:
    - available_colors dict has all division names
    - Called from driver row widgets' customContextMenuRequested signal

### `update_status_label()`

*Line 2954*

Update the status message and color (thread-safe Qt slot).

Purpose: Display connection status and session type at top of overlay.
Examples: "Connecting...", "Connected - Live Data (Race)", "Update available"

Why this exists: Telemetry thread needs to communicate status to UI thread.
Qt requires slots to be called from signals for thread safety.

Args:
    text: Status message to display
    color: "green" (connected), "orange" (connecting), or hex like "#00FF00"

Thread safety: This is a Qt slot connected to self.signals.update_status,
so it's safe to call from the telemetry background thread.

Assumptions:
    - status_label widget exists
    - update_status_style() handles color setting

### `mousePressEvent()`

*Line 2978*

Qt event handler: Mouse button pressed in window.

Purpose: Enable dragging the frameless window by its title bar.

Why this exists: With Qt.FramelessWindowHint, we lose the default OS
window dragging. This reimplements it for the title bar area.

How it works: Stores the click position offset, used in mouseMoveEvent()
to calculate new window position while dragging.

Assumptions:
    - Title bar height is 30 pixels
    - Only left-click drags

### `mouseMoveEvent()`

*Line 2999*

Qt event handler: Mouse moved while button held.

Purpose: Update window position during drag operation.

Why this exists: Completes the drag functionality started in mousePressEvent().

Assumptions:
    - drag_position was set in mousePressEvent()
    - Left button is still held

### `mouseReleaseEvent()`

*Line 3015*

Qt event handler: Mouse button released.

Purpose: End drag operation and save new window position to config.

Why this exists: Ensures window position is persisted immediately after
user moves the window, not just on app close (in case of crash).

Assumptions: Left button release ends drag

### `__init__()`

*Line 3065*

*No documentation provided.*

### `setup_ui()`

*Line 3076*

Setup settings UI

### `on_opacity_change()`

*Line 3465*

Live preview of opacity changes as user drags slider.

Purpose: Lets user see exactly how transparent/opaque the overlay will be
before committing the change with "Apply Settings."

Why this exists: Opacity is hard to judge from a number. Live preview
lets users find the perfect transparency for their setup.

Args:
    value: Slider value (2-20), divided by 20 to get 0.10-1.00 opacity

Note: Changes are temporary until "Apply Settings" clicked. "Cancel"
reverts to original_opacity stored in __init__.

### `choose_color()`

*Line 3484*

Open color picker to customize a division's color.

Purpose: Allows leagues to customize division colors to match their
branding or preferences.

Why this exists: Default colors might not work for all leagues. Some
might want different colors for better visibility or aesthetics.

Args:
    division: "Pro", "ProAm", "Am", or "Rookie"

Flow:
    1. Opens Qt color picker dialog with current division color
    2. If user selects new color, updates:
       - available_colors dict
       - Color button preview
       - Hex code label
    3. Changes saved when "Apply Settings" clicked

Note: Changes affect ALL drivers in that division immediately after apply.

### `create_new_config()`

*Line 3523*

Create new config file

### `load_config()`

*Line 3551*

Load different config file

### `reset_to_defaults()`

*Line 3578*

Reset to default settings

### `apply_settings()`

*Line 3620*

Apply all settings

### `on_cancel()`

*Line 3641*

Cancel settings

