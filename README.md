# BB’s League Overlay

A lightweight desktop overlay for **iRacing** that gives you a clearer picture of your league division race within the race.  
BB’s League Overlay displays live standings and gaps with a focus on divisions. Gaps are to the next driver within your division, not just who is on track ahead of you.

![Alt text](https://leagueoverlay.com/assets/img/overall.png "Overlay image")

---

## ✨ Features
- **Live Standings** — Current race position (both overall and within division) with driver number and name.
- **Interval & Gap Tracking** — Real-time gaps with two columns:
  - **Interval** — Time to the car immediately ahead (in your division if division-scoped, otherwise overall)
  - **Gap** — Time to your division leader (if division-scoped) or overall race leader
- **Division Scope Toggle** — Toggle the "Show division scope" setting to switch both Interval and Gap between division-only or overall race calculations
- **Post-Race Gap Preservation** — Final gaps frozen at finish line, preventing changes as drivers slow down or continue circulating.
- **Positions Gained** — Optional column showing positions gained/lost from starting grid (green ↑ = gained, red ↓ = lost).
- **Best Lap Times** — Optional column displaying each driver's best lap time this session.
- **Lap Time Delta** — Optional column showing lap time comparison (green = you're faster, red = you're slower).
- **Last Lap Times** — Optional column displaying each driver's most recent lap time.
- **Division System** — Assign drivers to divisions (Pro, ProAm, Am, Rookie) with customizable colors.
- **Driver Rating** — Optional column showing iRating + Safety Rating combined (e.g., "A 2.5  6.0k") with license class background colors.
- **Pit Strategy** — Optional column showing last pit lap or "OUT" during out lap (orange when on out lap).
- **Division Filtering** — Toggle between viewing all divisions, your division only, or specific divisions (if spectating).
- **Multi-Class Support** — Automatically filters to your car class in multi-class races.
- **Auto-Centering** — Keeps you in view with intelligent timeout after manual scrolling.
- **Spectator Camera Highlight** — When spectating, the driver currently being viewed by the spectator camera is highlighted in the standings just like the active player's row. If the spectator is not using the Broadcast Header + Broadcast Rolling Standings, the overlay will also auto-center on the spectated driver.
- **Customizable Appearance** — Configure font sizes, row colors (Default/Dark/Alternate/Outline), opacity, and performance indicator colors.
- **Broadcast Header** — Optional professional-quality header displaying league logo, league name, session info, and track name—ideal for spectator streams and broadcast use. Supports custom logo images and accent colors with flag-aware styling (gold during caution, orange when disconnected).
- **Broadcast Rolling Standings** — Optional broadcast mode that locks the top standings rows and rolls the remaining drivers in the bottom 5 rows on a configurable timer (default 5 seconds), with automatic wrap-around and blank-row padding on the last page. When a specific driver is selected (or the spectator camera is viewing a driver) and that driver is not visible on the current broadcast rolling page, the rolling window will lock and center that driver. Automatic page advances are paused while the page is locked; they resume when the driver becomes visible or the selection changes. If the selection moves to another off-screen driver, the lock moves to that driver.
- **Right-Click Assignments** — Quickly assign drivers to divisions via context menu during a session.
- **Update Notifications** — Automatic checks for new versions from GitHub.

---

## 📥 Installation
Simply unzip and run — no complex setup required.  

---

## ⚙️ Configuration

### Settings
The overlay saves your preferences to `LeagueOverlay.config`. You can customize:
- Window position and size
- Opacity (transparency)
- Font size
- Row color style (Default, Dark, Alternate, Outline)
- Refresh rate
- Division colors
- License class colors (for Rating column background)
- Performance indicator colors (faster/gained and slower/lost)
- Column visibility (show/hide Positions Gained, Best Lap, Last Lap, Delta, Rating, and Pit Lap columns)
- Log level (DEBUG, INFO, WARNING, ERROR)
- Broadcast rolling standings (enable/disable)
- Broadcast rolling timer (1-60 seconds, default 5)

---

## 💡 Usage
1. Launch iRacing.
2. Start BB's League Overlay.
3. Position the overlay where you want it on screen.
4. Race with better awareness of your league battle.

**Tips:**
- **Filter divisions**: Click the division filter button to cycle through views
- **Assign on-the-fly**: Right-click any driver to change their division
- **Auto-centering**: The overlay keeps you in view; scroll manually to disable temporarily
- **Broadcast rolling mode**: When enabled (with Broadcast Header), the scrollbar is hidden and auto-centering is disabled while the bottom 5 rows (configurable) rotate through the remaining standings. When a driver is selected or the spectator camera is following a driver who is not visible on the current broadcast rolling page, the rolling page will lock and center that driver and pause automatic page advances until the selection changes or the driver becomes visible.
- **Positions Gained column**: Shows positions gained/lost from starting grid with color coding (green for gained, red for lost)
- **Best Lap column**: Shows each driver's best lap time this session
- **Delta column**: When driving, compares lap times to your last lap. When spectating, compares to overall leader's last lap
- **Last Lap column**: Shows formatted lap times (e.g., "1:24.56" or "58.34" for times under 60 seconds)
- **Rating column**: Shows combined iRating + Safety Rating (e.g., "A 2.5  6.0k") with license class background colors (R=dark red, D=orange, C=gold, B=green, A=blue, P=indigo)
- **Pit Lap column**: Shows last pit lap (e.g., "L12") or "OUT" in orange during out lap

---

## 🙏 Support
This project is freely given to help fellow racers.  
If you’d like to support development, you can:  

Buy me a coffee: [☕ Click here](https://www.buymeacoffee.com/brandonburns)

Share encouragement with someone in your life. A kind word can carry farther than you imagine.

---

## 📖 Inspiration
> *“Therefore encourage one another and build one another up, just as you are doing.”*  
> — 1 Thessalonians 5:11

---

## 🔧 Troubleshooting

### Logs
If you encounter issues, check `LeagueOverlay.log` in the same directory as the executable. This file contains:
- Startup information
- Session changes
- Error messages with full details

The log file is helpful when reporting bugs or seeking support.

### Reporting Issues
Found a bug or have a feature request? Visit the [GitHub Issues page](https://github.com/steak-and-gravy/league-overlay/issues).

---

## 🛠️ Development

### Local Setup
1. Create and activate a virtual environment:
   - Windows (PowerShell): `python -m venv .venv` then `.venv\Scripts\Activate.ps1`
   - macOS/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`
2. Install runtime dependencies: `pip install -r requirements.txt`
3. Install test dependencies (optional): `pip install -r requirements-dev.txt`
4. Run the app: `python league_overlay.py`
5. Run tests: `pytest`

### Architecture
This project uses a modular architecture with clear separation of concerns:

```
├── config/              # Settings and constants
│   ├── constants.py     # UI, file, and telemetry configuration
│   ├── settings.py      # Settings persistence and validation
│   └── logging_config.py # Logging setup
├── core/                # Business logic
│   ├── driver_state.py       # Unified driver data structure
│   ├── position_calculator.py # Real-time position tracking
│   ├── gap_calculator.py      # Gap calculations (time/laps)
│   ├── division_manager.py    # Division assignments
│   ├── division_filter.py     # Division filtering logic
│   ├── race_state_tracker.py  # Finish state machine
│   ├── telemetry_processor.py # Main telemetry orchestration
│   └── update_checker.py      # GitHub version checking
├── ui/                  # User interface
│   ├── driver_row_renderer.py    # Row rendering
│   ├── settings_dialog.py        # Settings UI
│   ├── styles.py                 # Color schemes
│   ├── widgets.py                # Custom Qt widgets
│   └── auto_center_controller.py # Auto-scroll logic
├── tests/               # Test suites (485 tests)
└── league_overlay.py    # Main application entry point
```

For detailed technical documentation, see [ARCHITECTURE.md](ARCHITECTURE.md).

For AI-Assisted development, see [CLAUDE.md](CLAUDE.md) for project context.

---

## ⚙️ Tech Stack
- **Python 3.9+** - Core language
- **PySide6** - Qt framework for UI
- **pyirsdk** - iRacing SDK Python wrapper for telemetry access
- **Nuitka** - Python-to-executable compilation
- **pytest** - Testing framework (485 comprehensive tests)

---

## Website
For more info visit https://leagueoverlay.com
