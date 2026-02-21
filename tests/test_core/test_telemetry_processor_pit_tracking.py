"""Unit tests for TelemetryProcessor pit tracking transitions."""

from unittest.mock import MagicMock

from core.telemetry_processor import TelemetryProcessor


def _build_processor(ir_data):
    """Create a telemetry processor with minimal mocked dependencies."""
    return TelemetryProcessor(
        ir=ir_data,
        division_manager=MagicMock(),
        race_state_tracker=MagicMock(),
        gap_calculator=MagicMock(),
        position_calculator=MagicMock()
    )


def test_valid_stop_uses_pit_entry_lap_and_corrects_out_lap():
    """Pit entry lap is authoritative; out-lap uses corrected pit-exit lap."""
    car_idx = 1
    ir_data = {
        'CarIdxOnPitRoad': [False, False],
        'CarIdxTrackSurface': [3, 3],
        'CarIdxLap': [0, 10],
        'CarIdxLapDistPct': [0.0, 0.30]
    }
    processor = _build_processor(ir_data)

    # Enter pit road on lap 10.
    ir_data['CarIdxOnPitRoad'][car_idx] = True
    processor._update_pit_tracking()

    # Reach pit stall after crossing into next lap.
    ir_data['CarIdxTrackSurface'][car_idx] = 1
    ir_data['CarIdxLap'][car_idx] = 11
    ir_data['CarIdxLapDistPct'][car_idx] = 0.40
    processor._update_pit_tracking()

    # Exit pit road after halfway point: corrected out-lap should increment.
    ir_data['CarIdxOnPitRoad'][car_idx] = False
    ir_data['CarIdxTrackSurface'][car_idx] = 3
    ir_data['CarIdxLap'][car_idx] = 11
    ir_data['CarIdxLapDistPct'][car_idx] = 0.60
    processor._update_pit_tracking()

    assert processor.pit_tracking[car_idx] == 10
    assert processor.pit_exit_out_lap[car_idx] == 12
    assert processor.pit_on_road[car_idx] is False


def test_drive_through_does_not_update_last_pit_lap():
    """Pit-road pass without stall visit should not count as a pit stop."""
    car_idx = 1
    ir_data = {
        'CarIdxOnPitRoad': [False, False],
        'CarIdxTrackSurface': [3, 3],
        'CarIdxLap': [0, 20],
        'CarIdxLapDistPct': [0.0, 0.20]
    }
    processor = _build_processor(ir_data)
    processor.pit_tracking[car_idx] = 7

    # Enter and exit pit road without ever reaching stall.
    ir_data['CarIdxOnPitRoad'][car_idx] = True
    processor._update_pit_tracking()
    ir_data['CarIdxOnPitRoad'][car_idx] = False
    ir_data['CarIdxLap'][car_idx] = 21
    ir_data['CarIdxLapDistPct'][car_idx] = 0.10
    processor._update_pit_tracking()

    assert processor.pit_tracking[car_idx] == 7
    assert car_idx not in processor.pit_exit_out_lap
