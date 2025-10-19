"""Configuration module for League Overlay."""

from .constants import UIConfig, FileConfig, TelemetryConfig, UI_CONFIG, FILE_CONFIG, TELEMETRY_CONFIG, VERSION
from .settings import AppSettings, SettingsManager

__all__ = [
    'UIConfig',
    'FileConfig',
    'TelemetryConfig',
    'UI_CONFIG',
    'FILE_CONFIG',
    'TELEMETRY_CONFIG',
    'VERSION',
    'AppSettings',
    'SettingsManager',
]
