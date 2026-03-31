#!/usr/bin/env python3
"""
Nuitka build script for BB's League Overlay

This script provides a convenient way to build the application with Nuitka.
Nuitka compiles Python to C and creates a standalone executable with better
performance than PyInstaller.

Usage:
    python nuitka-build.py

Requirements:
    pip install nuitka
    pip install ordered-set  # Nuitka dependency

Platform-specific requirements:
    - Windows: Visual Studio C++ compiler or MinGW64
    - macOS: Xcode Command Line Tools
    - Linux: gcc
"""

import subprocess
import sys
import os

# Import VERSION from the application
sys.path.insert(0, os.path.dirname(__file__))
from config.constants import VERSION

# Configuration
APP_NAME = "LeagueOverlay"
MAIN_SCRIPT = "league_overlay.py"
ICON_FILE = "app_icon.ico"  # Change to .icns for macOS

# Nuitka command-line arguments
nuitka_args = [
    sys.executable,
    "-m", "nuitka",

    # ===================================================================
    # COMPILATION MODE
    # ===================================================================
    "--standalone",              # Create standalone distribution
    #"--onefile",                 # Create single executable (alternative: use --standalone only for folder distribution)
    #"--onefile-no-compression",
    "--msvc=latest",
    #"--mingw64",

    # ===================================================================
    # OUTPUT CONFIGURATION
    # ===================================================================
    f"--output-filename={APP_NAME}",
    "--output-dir=build",

    # ===================================================================
    # OPTIMIZATION
    # ===================================================================
    "--enable-plugin=pyside6",   # Enable PySide6 plugin for better integration
    "--assume-yes-for-downloads", # Auto-download dependencies
    "--lto=yes",                 # Link-time optimization (slower build, faster runtime)
    "--python-flag=nosite,-O",   # Disable site.py and enable optimizations
    #"--python-flag=nosite",   # Disable site.py and enable optimizations
    "--remove-output",
    "--deployment",
    #"--disable-dll-dependency-cache",
    #"--force-dll-dependency-cache-update",

    # ===================================================================
    # WINDOWS-SPECIFIC (comment out on macOS/Linux)
    # ===================================================================
    #"--windows-disable-console", # No console window (GUI app)
    "--windows-console-mode=disable",
    f"--windows-icon-from-ico={ICON_FILE}",
    "--windows-company-name=Brandon G Burns",
    "--windows-product-name=BB's League Overlay",
    f"--windows-file-version={VERSION}",
    f"--windows-product-version={VERSION}",
    "--windows-file-description=BB's League Overlay",

    # ===================================================================
    # MACOS-SPECIFIC (uncomment for macOS builds)
    # ===================================================================
    # "--macos-create-app-bundle",
    # f"--macos-app-icon={ICON_FILE}",  # Use .icns file
    # "--macos-app-name=LeagueOverlay",
    # f"--macos-app-version={VERSION}",

    # ===================================================================
    # PACKAGE INCLUSION
    # ===================================================================
    # Nuitka usually auto-detects these, but explicit is better
    "--include-package=config",
    "--include-package=core",
    "--include-package=ui",

    # PySide6 modules (plugin should handle this, but being explicit)
    "--include-module=PySide6.QtCore",
    "--include-module=PySide6.QtGui",
    "--include-module=PySide6.QtWidgets",

    # External dependencies
    "--include-module=irsdk",
    "--include-module=packaging",
    "--include-module=packaging.version",

    # ===================================================================
    # DATA FILES
    # ===================================================================
    # Include JSON configuration files
    #"--include-data-files=*.json=.",

    # If you have specific config files:
    # "--include-data-files=league_divisions.json=.",
    # "--include-data-files=broken_wing_gt3.json=.",
    "--include-data-dir=assets=assets",

    # ===================================================================
    # EXCLUSIONS (reduce size)
    # ===================================================================
    "--nofollow-import-to=numpy",
    "--nofollow-import-to=scipy",
    "--nofollow-import-to=pandas",
    "--nofollow-import-to=matplotlib",
    "--nofollow-import-to=pytest",
    "--nofollow-import-to=unittest",
    "--nofollow-import-to=tkinter",
    "--nofollow-import-to=PyQt5",
    "--nofollow-import-to=PyQt6",

    # ===================================================================
    # DEBUGGING (uncomment for troubleshooting)
    # ===================================================================
    # "--show-modules",          # Show all included modules
    # "--show-progress",         # Show compilation progress
    # "--verbose",               # Verbose output
    # "--debug",                 # Include debug info (slower, larger)

    # ===================================================================
    # MAIN SCRIPT
    # ===================================================================
    MAIN_SCRIPT,
]

def check_nuitka_installed():
    """Check if Nuitka is installed."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "nuitka", "--version"],
            capture_output=True,
            text=True
        )
        print(f"✓ Nuitka version: {result.stdout.strip()}")
        return True
    except Exception as e:
        print(f"✗ Nuitka not found: {e}")
        print("\nInstall with: pip install nuitka ordered-set")
        return False

def check_dependencies():
    """Check required files exist."""
    issues = []

    if not os.path.exists(MAIN_SCRIPT):
        issues.append(f"Main script not found: {MAIN_SCRIPT}")

    if not os.path.exists(ICON_FILE):
        print(f"⚠ Warning: Icon file not found: {ICON_FILE}")
        print("  Build will continue without custom icon")

    for pkg in ['config', 'core', 'ui']:
        if not os.path.isdir(pkg):
            issues.append(f"Package directory not found: {pkg}/")

    if issues:
        print("✗ Missing dependencies:")
        for issue in issues:
            print(f"  - {issue}")
        return False

    print("✓ All dependencies found")
    return True

def build():
    """Run the Nuitka build."""
    print("="*70)
    print("BB's League Overlay - Nuitka Build")
    print("="*70)
    print(f"Version: {VERSION}")
    print()

    # Pre-flight checks
    if not check_nuitka_installed():
        return False

    if not check_dependencies():
        return False

    print()
    print(f"Starting Nuitka compilation for version {VERSION}...")
    print("This may take several minutes on first build.")
    print()

    # Run Nuitka
    try:
        result = subprocess.run(nuitka_args, check=True)
        print()
        print("="*70)
        print("✓ BUILD SUCCESSFUL!")
        print("="*70)
        print(f"\nVersion: {VERSION}")
        print(f"Output location: build/{APP_NAME}.dist/")
        print("\nDistribution instructions:")
        print(f"1. Zip the entire '{APP_NAME}.dist/' folder")
        print(f"2. Users extract and run {APP_NAME}.exe from inside the folder")
        print("3. All dependencies (DLLs, folders) must stay together with the exe")
        return True

    except subprocess.CalledProcessError as e:
        print()
        print("="*70)
        print("✗ BUILD FAILED")
        print("="*70)
        print(f"\nError code: {e.returncode}")
        print("\nTroubleshooting:")
        print("1. Ensure you have a C compiler installed")
        print("2. Try running with --show-modules flag to debug imports")
        print("3. Check Nuitka documentation: https://nuitka.net/")
        return False

if __name__ == "__main__":
    success = build()
    sys.exit(0 if success else 1)
