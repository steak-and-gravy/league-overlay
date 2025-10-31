# BB’s League Overlay

A lightweight desktop overlay for **iRacing** that gives you a clearer picture of your league division race within the race.  
BB’s League Overlay displays live standings and gaps with a focus on divisions. Gaps are to the next driver within your division, not just who is on track ahead of you.

---

## ✨ Features
- **Live Standings** — Current race position (both overall and within division) with driver number and name.
- **Gap Tracking** — See the real-time gap to the car ahead in your division.
- **Division System** — Assign drivers to divisions (Pro, ProAm, Am, Rookie) with customizable colors.
- **Division Filtering** — Toggle between viewing all divisions, your division only, or specific divisions (if spectating).
- **Multi-Class Support** — Automatically filters to your car class in multi-class races.
- **Auto-Centering** — Keeps you in view with intelligent timeout after manual scrolling.
- **Customizable Appearance** — Configure font sizes, row colors (Default/Dark/Alternate/Outline), and opacity.
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
- Row color style (Default, Alternate, Outline, Dark)
- Refresh rate
- Division colors
- Log level (DEBUG, INFO, WARNING, ERROR)

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
Found a bug or have a feature request? Visit the [GitHub Issues page](https://github.com/BrandonBurns/league-overlay/issues) (update with actual URL).

---

## 🛠️ Development

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
├── tests/               # Test suites (349 tests: 317 passing, 32 skipped)
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
- **pytest** - Testing framework (349 comprehensive tests)

---

## Website
For more info visit https://leagueoverlay.com
