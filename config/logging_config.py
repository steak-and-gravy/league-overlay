"""
Logging configuration for the League Overlay application.

This module sets up logging to a file in the same directory as the executable,
overwriting the log file on each application launch.
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logging(log_level=logging.INFO):
    """
    Setup logging to LeagueOverlay.log in the same directory as the executable.

    Args:
        log_level: The logging level (default: logging.INFO)

    Returns:
        Path: The path to the log file
    """
    # Determine the application directory
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        app_dir = Path(sys.executable).parent
    else:
        # Running as script
        app_dir = Path(__file__).parent.parent

    log_file = app_dir / "LeagueOverlay.log"

    # Create rotating file handler with 25MB limit (safety against runaway logging)
    # backupCount=1 keeps 1 backup, rotates continuously (max 50MB total: 25MB * 2 files)
    file_handler = RotatingFileHandler(
        log_file,
        mode='a',  # RotatingFileHandler uses append mode
        maxBytes=25 * 1024 * 1024,  # 25MB
        backupCount=1,
        encoding='utf-8'
    )

    # Console handler for development (won't show in compiled exe without console)
    console_handler = logging.StreamHandler()

    # Format: timestamp - module - level - message
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return log_file


def get_logger(name):
    """
    Get a logger instance for a specific module.

    Args:
        name: Usually __name__ of the calling module

    Returns:
        logging.Logger: Configured logger instance
    """
    return logging.getLogger(name)


def set_log_level(level_name):
    """
    Dynamically change the log level for the entire application.

    Args:
        level_name: Log level as string ("DEBUG", "INFO", "WARNING", "ERROR")
    """
    # Convert string to logging level constant
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR
    }

    level = level_map.get(level_name.upper(), logging.INFO)

    # Get root logger
    root_logger = logging.getLogger()
    old_level = root_logger.level
    old_level_name = logging.getLevelName(old_level)

    # Log the change at WARNING level BEFORE changing (so it's visible with old level)
    # and temporarily force the log by setting level to DEBUG if needed
    min_level = min(old_level, logging.WARNING)
    root_logger.setLevel(min_level)
    root_logger.warning(f"Log level changed from {old_level_name} to {level_name}")

    # Now set the new level
    root_logger.setLevel(level)
