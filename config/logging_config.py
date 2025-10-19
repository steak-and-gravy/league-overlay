"""
Logging configuration for the League Overlay application.

This module sets up logging to a file in the same directory as the executable,
overwriting the log file on each application launch.
"""

import logging
import sys
from pathlib import Path


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

    # Create file handler (mode='w' overwrites on each launch)
    file_handler = logging.FileHandler(
        log_file,
        mode='w',
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
