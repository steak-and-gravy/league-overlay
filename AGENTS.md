# AGENTS.md — iRacing League Overlay (Authoritative AI Rules)

## TL;DR (Read This First)

- iRacing SDK objects are NOT dicts → bracket access + try/except only
- DriverState is authoritative → attribute access, never dicts
- `position` locks on finish → never changes afterward
- Finish tracking is a state machine → no heuristics or simplification
- Gap calculations MUST normalize per-car lap times
- UI never owns race logic; telemetry never touches UI

---

⚠️ **MANDATORY**  
Before modifying **any `.py` file**, read this document fully and follow it exactly.

This file defines **binding rules and invariants**. If this document conflicts with any other documentation, **this file wins**.

---

## Project Summary

Real-time iRacing race position overlay supporting:
- division-based racing
- multi-class sessions
- per-driver finish tracking
- car-normalized gap calculations

The codebase contains **intentional complexity** required to match iRacing behavior. Simplification without full understanding is considered a bug.

---

## Absolute Rules (Do Not Violate)

### 1. IRSDK DATA ACCESS (CRITICAL)

`self.ir` / `live_data` are **irsdk.IRSDK objects**, not Python dicts.

**Required pattern**
```python
try:
    session_state = self.ir['SessionState']
except (KeyError, TypeError):
    session_state = 4
```

**Forbidden**
- ❌ `self.ir.get(...)`
- ❌ `'Field' in self.ir`
- ❌ assuming missing fields are safe

Reason: IRSDK only implements `__getitem__`; missing fields raise exceptions.

---

### 2. DriverState Access Rules

`DriverState` is a **dataclass**, not a dict.

**Correct**
```python
driver.position
driver.car_number
driver.driver_name
```

**Forbidden**
- ❌ `driver.get('position')`
- ❌ `driver['position']`

Rule:
- DriverState → attribute/property access only
- Plain dicts (`driver_info`) may use `.get()`, but prefer DriverState properties

---

## Positioning Model (Invariant)

### Unified `position`
- Racing drivers → live track position
- Finished drivers → locked official finishing position
- Practice/Qualifying → best-lap ordering
- Disconnected drivers → restored from snapshots

Positions **must not change** after a driver finishes.

**Sorting rule of thumb**
- `total_track_position` → internal ordering
- `position` → display and final standings

---

## Finish Tracking (State Machine — Sacred)

- Checkered flag does **not** mean all cars finished
- Each driver finishes individually

System behavior:
- Lock position + gap when each car crosses the line
- Use `ResultsPositions` for post-checkered correctness
- Freeze gaps to prevent slow-down distortion

Disconnected drivers:
- During race → marked disconnected
- After leader finishes → immediately marked finished
- Final order converges from official results

**Never replace this logic with heuristics, timers, or thresholds.**

---

## Gap Calculation (Highly Sensitive)

### Terminology

- **Interval** — time gap to the car immediately ahead (in your division if `show_division=True`)
- **Gap** — time gap to the division leader (if `show_division=True`) or overall race leader (if `show_division=False`)
- Both are calculated from normalized lap times

### Car-Specific Time Normalization (CRITICAL)

`CarIdxEstTime` is **car-model normalized** and cannot be directly compared.

**Normalization using `CarClassEstLapTime` is mandatory.**

Fallback only if lap times are zero or unavailable.

Removing or bypassing normalization is a correctness bug.

The `show_division` setting controls scope for both Interval and Gap:
- `True` (default) → division-scoped calculations
- `False` → overall race calculations

---

## Division Rules

- Divisions exist **within a class**
- Gaps are calculated **within division only**
- Division config comes from official remote leagues or local JSON

Managed exclusively by:
- `core/division_manager.py`
- `core/division_filter.py`

---

## Module Boundaries (Enforced)

- `core/` → race logic, telemetry, calculations
- `ui/` → rendering only, no race logic
- `config/` → settings, constants, logging

Do not move logic across these boundaries.

---

## Threading Rules

- Telemetry runs in background thread
- UI updates via Qt signals only
- **Never block the UI thread**

---

## Qt Lambda Rules (Strict)

Signals that pass parameters **must accept them**.

```python
widget.customContextMenuRequested.connect(
    lambda pos, d=driver: self.parent.show_context_menu(d)
)
```

Always capture values **by value**, never by reference.

---

## Logging Rules

- Use `get_logger(__name__)`
- Respect configured log level
- Logs are user-facing and relied upon for support

---

## Tests Are Authoritative

~470 tests define correct behavior.

If logic seems odd, assume it is intentional and tested.

---

## Never Simplify These

- Finish tracking state machine
- Snapshot-based disconnected driver handling
- Car-specific gap normalization
- Unified position semantics

---

## Pre‑Change Checklist

If any checkbox cannot be confidently checked, **re‑read this file before continuing**.

### Data Access
- [ ] No `.get()` or `'in'` used on `irsdk` objects
- [ ] All optional SDK fields wrapped in try/except
- [ ] DriverState accessed via attributes only

### Position & Finish Logic
- [ ] Finished drivers never change position or gap
- [ ] Finish handling still uses RaceStateTracker
- [ ] No timing thresholds or heuristics introduced

### Gap Calculations
- [ ] Car-specific time normalization preserved
- [ ] Division gaps remain division-scoped
- [ ] Fallback logic only triggers on missing lap times

### Architecture
- [ ] No race logic moved into UI modules
- [ ] Telemetry thread does not touch UI directly
- [ ] Existing module boundaries respected

### Tests
- [ ] Existing tests still pass
- [ ] Logic changes align with test intent

---

## Final Instruction

If a change touches:
- telemetry access
- positions
- gaps
- finish logic

Re-read this file **before coding**.
