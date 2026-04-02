"""Shared test fixtures for League Overlay tests."""

import os
import pytest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='session')
def qapp():
    """Create QApplication for widget tests.

    This fixture is session-scoped to avoid creating multiple QApplication
    instances which would cause Qt to crash.

    Yields:
        QApplication: The Qt application instance for testing UI components
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def mock_irsdk():
    """Mock iRacing SDK connection.

    Returns:
        Mock: A configured mock object simulating iRacing SDK with:
            - Basic connection state (connected, initialized)
            - Player car index
            - Session information (session number, type)
            - Driver information
    """
    ir = Mock()
    ir.startup.return_value = True
    ir.is_connected = True
    ir.is_initialized = True
    ir['PlayerCarIdx'] = 5
    ir['SessionNum'] = 0
    ir['SessionInfo'] = {
        'Sessions': [
            {'SessionType': 'Practice', 'SessionNum': 0}
        ]
    }
    ir['DriverInfo'] = {
        'Drivers': [
            {
                'CarIdx': 5,
                'UserName': 'Test Driver',
                'CarNumber': '1',
                'CarClassID': 100
            }
        ]
    }
    ir['CarIdxClassPosition'] = [0] * 64  # 64 car positions
    ir['CarIdxClassPosition'][5] = 1
    ir['CarIdxLap'] = [0] * 64
    ir['CarIdxLap'][5] = 10
    ir['CarIdxLapDistPct'] = [0.0] * 64
    ir['CarIdxLapDistPct'][5] = 0.5
    ir['SessionState'] = 4  # Racing

    return ir


@pytest.fixture
def sample_race_data():
    """Sample race data for testing.

    Returns:
        list: A list of dictionaries representing race data for 2 drivers
    """
    return [
        {
            'car_idx': 5,
            'position': 1,
            'driver_info': {
                'UserName': 'Driver 1',
                'CarNumber': '1',
                'CarClassID': 100
            },
            'gap': None,
            'laps_completed': 10,
            'lap_distance_pct': 0.5,
            'est_time': 100.0,
            'division': 'Pro',
            'is_finished': False
        },
        {
            'car_idx': 6,
            'position': 2,
            'driver_info': {
                'UserName': 'Driver 2',
                'CarNumber': '2',
                'CarClassID': 100
            },
            'gap': '+2.5s',
            'laps_completed': 10,
            'lap_distance_pct': 0.3,
            'est_time': 102.5,
            'division': 'Pro',
            'is_finished': False
        }
    ]


@pytest.fixture
def temp_division_config(tmp_path):
    """Create temporary division config file.

    Args:
        tmp_path: pytest fixture providing temporary directory path

    Returns:
        str: Path to the temporary division config file
    """
    import json

    config_file = tmp_path / "test_divisions.json"
    config_data = {
        'drivers': [
            {
                'name': 'Test Driver',
                'car_number': '1',
                'division': 'Pro'
            },
            {
                'name': 'Driver 2',
                'car_number': '2',
                'division': 'ProAm'
            }
        ]
    }

    with open(config_file, 'w') as f:
        json.dump(config_data, f, indent=2)

    return str(config_file)


@pytest.fixture
def temp_settings_file(tmp_path):
    """Create temporary settings file.

    Args:
        tmp_path: pytest fixture providing temporary directory path

    Returns:
        str: Path to the temporary settings file
    """
    settings_file = tmp_path / "test_settings.config"
    return str(settings_file)


@pytest.fixture
def sample_driver_info():
    """Sample driver info structure from iRacing.

    Returns:
        dict: Driver information dictionary matching iRacing format
    """
    return {
        'CarIdx': 5,
        'UserName': 'John Doe',
        'CarNumber': '42',
        'CarNumberRaw': 42,
        'CarClassID': 100,
        'CarClassShortName': 'GT3',
        'TeamName': 'Test Team',
        'AbbrevName': 'JDoe',
        'IRating': 2500,
        'LicString': 'A 4.50'
    }
