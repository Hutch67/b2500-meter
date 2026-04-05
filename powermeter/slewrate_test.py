import time
import unittest
from unittest.mock import Mock
from .slewrate import SlewRatePowermeter


class TestSlewRatePowermeter(unittest.TestCase):
    def setUp(self):
        self.mock_powermeter = Mock()

    def test_first_reading_returned_unchanged(self):
        """First call should return the raw value with no slewing applied."""
        self.mock_powermeter.get_powermeter_watts.return_value = [500.0]
        pm = SlewRatePowermeter(self.mock_powermeter, slew_rate_watts_per_sec=100.0)

        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 500.0)

    def test_small_change_passes_through_immediately(self):
        """A change smaller than max_change for the elapsed time passes through."""
        pm = SlewRatePowermeter(self.mock_powermeter, slew_rate_watts_per_sec=100.0)
        self.mock_powermeter.get_powermeter_watts.return_value = [0.0]
        pm.get_powermeter_watts()  # initialise at 0 W

        # Simulate 1 second elapsed; max_change = 100 W; a 50 W jump should pass through
        pm.last_time -= 1.0
        self.mock_powermeter.get_powermeter_watts.return_value = [50.0]
        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 50.0)

    def test_large_jump_is_slew_limited(self):
        """A jump much larger than max_change should be clamped to max_change."""
        pm = SlewRatePowermeter(self.mock_powermeter, slew_rate_watts_per_sec=100.0)
        self.mock_powermeter.get_powermeter_watts.return_value = [0.0]
        pm.get_powermeter_watts()  # initialise at 0 W

        # Simulate 1 second elapsed; max_change = 100 W; raw jumps to 500 W
        pm.last_time -= 1.0
        self.mock_powermeter.get_powermeter_watts.return_value = [500.0]
        result = pm.get_powermeter_watts()

        # Reported value should advance by at most 100 W (with small real-time tolerance)
        self.assertAlmostEqual(result[0], 100.0, delta=1.0)

    def test_negative_jump_is_slew_limited(self):
        """A negative jump larger than max_change is also clamped."""
        pm = SlewRatePowermeter(self.mock_powermeter, slew_rate_watts_per_sec=100.0)
        self.mock_powermeter.get_powermeter_watts.return_value = [500.0]
        pm.get_powermeter_watts()  # initialise at 500 W

        # Simulate 1 second elapsed; raw drops to 0 W
        pm.last_time -= 1.0
        self.mock_powermeter.get_powermeter_watts.return_value = [0.0]
        result = pm.get_powermeter_watts()

        self.assertAlmostEqual(result[0], 400.0, delta=1.0)

    def test_slew_converges_to_target_over_time(self):
        """Given enough time the slewed value should reach the target."""
        pm = SlewRatePowermeter(self.mock_powermeter, slew_rate_watts_per_sec=100.0)
        self.mock_powermeter.get_powermeter_watts.return_value = [0.0]
        pm.get_powermeter_watts()  # initialise at 0 W

        # Simulate 10 polling cycles each 1 second apart
        target = 500.0
        self.mock_powermeter.get_powermeter_watts.return_value = [target]
        result = None
        for _ in range(10):
            pm.last_time -= 1.0
            result = pm.get_powermeter_watts()

        self.assertAlmostEqual(result[0], target, delta=1.0)

    def test_three_phase_each_phase_slewed_independently(self):
        """Each phase should be slewed independently."""
        pm = SlewRatePowermeter(self.mock_powermeter, slew_rate_watts_per_sec=100.0)
        self.mock_powermeter.get_powermeter_watts.return_value = [0.0, 0.0, 0.0]
        pm.get_powermeter_watts()  # initialise

        pm.last_time -= 1.0  # simulate 1 second elapsed
        self.mock_powermeter.get_powermeter_watts.return_value = [50.0, 500.0, -500.0]
        result = pm.get_powermeter_watts()

        # Phase 1: 50 W jump < 100 W/s × 1 s → passes through
        self.assertAlmostEqual(result[0], 50.0, delta=1.0)
        # Phase 2: 500 W jump > 100 W/s → clamped to ~+100 W
        self.assertAlmostEqual(result[1], 100.0, delta=1.0)
        # Phase 3: -500 W jump > 100 W/s → clamped to ~-100 W
        self.assertAlmostEqual(result[2], -100.0, delta=1.0)

    def test_invalid_slew_rate_raises_error(self):
        """Non-positive slew_rate_watts_per_sec should raise ValueError."""
        with self.assertRaises(ValueError):
            SlewRatePowermeter(self.mock_powermeter, slew_rate_watts_per_sec=0.0)
        with self.assertRaises(ValueError):
            SlewRatePowermeter(self.mock_powermeter, slew_rate_watts_per_sec=-50.0)

    def test_wait_for_message_passthrough(self):
        """wait_for_message should be delegated to the wrapped powermeter."""
        pm = SlewRatePowermeter(self.mock_powermeter, slew_rate_watts_per_sec=100.0)
        pm.wait_for_message(timeout=8)
        self.mock_powermeter.wait_for_message.assert_called_once()
        call_args = self.mock_powermeter.wait_for_message.call_args
        if call_args[1]:
            self.assertEqual(call_args[1]["timeout"], 8)
        else:
            self.assertEqual(call_args[0][0], 8)


if __name__ == "__main__":
    unittest.main()
