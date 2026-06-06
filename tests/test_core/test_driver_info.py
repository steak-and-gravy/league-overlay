"""Tests for DriverInfo helper functions."""

from core.driver_info import build_driver_lookup, get_pace_car_indices, is_pace_car


def test_get_pace_car_indices_accepts_scalar_and_list_fields():
    driver_info = {
        'PaceCarIdx': '63',
        'PaceCarXIdx': [64, '65', -1, None, 'bad'],
    }

    assert get_pace_car_indices(driver_info) == {63, 64, 65}


def test_is_pace_car_prefers_authoritative_pace_car_indices():
    pace_car_indices = {70}
    driver = {'CarIdx': 70, 'UserName': 'Official Vehicle', 'CarNumber': 'PC2'}

    assert is_pace_car(driver, pace_car_indices) is True


def test_build_driver_lookup_uses_car_idx_values_not_list_positions():
    drivers = [
        {'CarIdx': 90, 'UserName': 'High Index'},
        {'CarIdx': 4, 'UserName': 'Low Index'},
    ]

    lookup = build_driver_lookup(drivers)

    assert lookup[90]['UserName'] == 'High Index'
    assert lookup[4]['UserName'] == 'Low Index'
