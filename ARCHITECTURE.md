# Architecture Documentation

## Purpose

This document describes **system structure, module responsibilities, and data flow**.

Behavioral rules, invariants, and forbidden patterns are defined in **`AGENTS.md`** and are not duplicated here.

---

## Overview

The iRacing League Overlay is a real-time race position display application built with PySide6 (Qt for Python) and the iRacing SDK. The architecture follows a modular design with clear separation of concerns.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    League Overlay (Qt UI)                │
│                                                          │
│  ┌────────────────────┐      ┌──────────────────────┐   │
│  │  Settings Dialog   │      │  Driver Row Renderer │   │
│  │   (UI Config)      │      │   (Display Logic)    │   │
│  └────────────────────┘      └──────────────────────┘   │
└──────────────────────────────────────────────────────────┘
                    │                       ▲
                    │                       │
                    ▼                       │
┌──────────────────────────────────────────────────────────┐
│              Telemetry Processor (Core)                  │
│                                                          │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐ │
│  │ Position     │  │ Race State  │  │ Division       │ │
│  │ Calculator   │  │ Tracker     │  │ Manager        │ │
│  └──────────────┘  └─────────────┘  └────────────────┘ │
│  ┌──────────────┐  ┌─────────────┐                      │
│  │ Gap          │  │ Division    │                      │
│  │ Calculator   │  │ Filter      │                      │
│  └──────────────┘  └─────────────┘                      │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────┐
│                    iRacing SDK (irsdk)                   │
└──────────────────────────────────────────────────────────┘
```

---

## Module Structure

### Layer 1: Configuration (`config/`)

These modules provide configuration, persistence, validation, and logging. They do not contain race logic.

- `constants.py` — Centralized configuration constants
- `settings.py` — Settings persistence and defaults
- `settings_validator.py` — Validation and type coercion
- `official_leagues.py` — Official remote league definitions
- `logging_config.py` — Application-wide logging setup

---

### Layer 2: Core Business Logic (`core/`)

These modules implement race logic and telemetry processing. They are UI-agnostic and heavily tested.

- `driver_state.py` — Unified driver data structure
- `position_calculator.py` — Position derivation from telemetry
- `gap_calculator.py` — Gap and formatting utilities
- `division_manager.py` — Driver-to-division mapping
- `division_filter.py` — Division-based filtering
- `race_state_tracker.py` — Finish tracking state machine
- `telemetry_processor.py` — Orchestration and data pipeline
- `update_checker.py` — Application update detection

---

### Layer 3: UI Components (`ui/`)

UI modules render data from `DriverState` objects and handle user interaction. They do not contain race logic.

- `widgets.py` — Custom Qt widgets and signals
- `styles.py` — Row styling strategies
- `driver_row_renderer.py` — Driver row rendering
- `settings_dialog.py` — Settings UI
- `auto_center_controller.py` — Auto-centering logic

---

### Layer 4: Application (`league_overlay.py`)

Main entry point and orchestrator:
- Initializes modules
- Manages threads
- Receives telemetry updates
- Coordinates UI updates

---

## Data Flow

```
iRacing SDK
    ▼
TelemetryProcessor
    ▼
PositionCalculator → List[DriverState]
    ▼
Division assignment and filtering
    ▼
Gap calculation
    ▼
RaceStateTracker (finish handling)
    ▼
Sorted List[DriverState]
    ▼
Qt Signal → UI Rendering
```

### Example: Footer Data Flow

The optional footer demonstrates the signal-based communication pattern:

1. **TelemetryProcessor.get_footer_data()** reads iRSDK fields:
   - `TrackTemp` (track surface temperature)
   - `PlayerCarMyIncidentCount` (player incidents)
   - `WeekendInfo['WeekendOptions']['IncidentLimit']` (incident limit)
   - Calculates SoF from `DriverInfo['Drivers']` (filtered by player's class)

2. **league_overlay._handle_telemetry_update()** calls `get_footer_data()` and emits `update_footer` signal (telemetry thread)

3. **league_overlay.update_footer_display()** receives signal and updates QLabels (main thread)

This pattern ensures thread-safe UI updates and clean separation between telemetry logic and UI rendering.

---

## Threading Model

- **Main Thread**: Qt UI event loop
- **Telemetry Thread**: Reads SDK data and processes telemetry
- **Communication**: Qt signals only

This ensures UI responsiveness and clean separation.

---

## Testing Architecture

- Core logic is fully unit-tested
- External dependencies (irsdk, filesystem, time) are mocked
- Tests validate behavior, not implementation

---

## Design Patterns Used

- Separation of Concerns
- Dependency Injection
- Strategy Pattern
- State Machine
- Pure Functions
- Observer Pattern (Qt signals)

---

## Performance Notes

- Telemetry refresh rate configurable
- Player-class filtering reduces workload
- Cached lookups avoid linear scans
- Snapshot storage limited to finished drivers

---

## Related Documents

- **Behavioral rules and invariants**: `AGENTS.md`
- **Test coverage**: `tests/`

---

## Conclusion

This architecture emphasizes clarity, correctness, and testability. The modular structure allows complex race behavior to be modeled accurately while keeping UI concerns isolated.
