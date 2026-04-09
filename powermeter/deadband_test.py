import unittest
from unittest.mock import Mock
from .deadband import DeadBandPowermeter


class TestDeadBandPowermeter(unittest.TestCase):
    def setUp(self):
        self.mock_powermeter = Mock()

    def test_value_within_deadband_returns_zero(self):
        """A value within ±deadband of zero should return zero."""
        self.mock_powermeter.get_powermeter_watts.return_value = [30.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        result = pm.get_powermeter_watts()
        self.assertEqual(result, [0.0])

    def test_value_at_deadband_boundary_returns_zero(self):
        """A value exactly at ±deadband_watts should return zero (inclusive)."""
        self.mock_powermeter.get_powermeter_watts.return_value = [50.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        result = pm.get_powermeter_watts()
        self.assertEqual(result, [0.0])

    def test_negative_value_at_deadband_boundary_returns_zero(self):
        """A value exactly at -deadband_watts should return zero (inclusive)."""
        self.mock_powermeter.get_powermeter_watts.return_value = [-50.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        result = pm.get_powermeter_watts()
        self.assertEqual(result, [0.0])

    def test_value_outside_deadband_forwarded(self):
        """A value larger than the dead-band should return the actual value."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        result = pm.get_powermeter_watts()
        self.assertEqual(result, [100.0])

    def test_negative_value_outside_deadband_forwarded(self):
        """A negative value larger than the dead-band should be forwarded."""
        self.mock_powermeter.get_powermeter_watts.return_value = [-60.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        result = pm.get_powermeter_watts()
        self.assertEqual(result, [-60.0])

    def test_zero_value_returns_zero(self):
        """Zero value is within the dead-band and should return zero."""
        self.mock_powermeter.get_powermeter_watts.return_value = [0.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        result = pm.get_powermeter_watts()
        self.assertEqual(result, [0.0])

    def test_three_phase_all_within_deadband_returns_zeros(self):
        """All phases within dead-band → return zeros for all phases."""
        self.mock_powermeter.get_powermeter_watts.return_value = [10.0, -20.0, 30.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        result = pm.get_powermeter_watts()
        self.assertEqual(result, [0.0, 0.0, 0.0])

    def test_three_phase_one_outside_deadband_returns_actuals(self):
        """If any single phase exceeds the dead-band, all actual values are returned."""
        self.mock_powermeter.get_powermeter_watts.return_value = [10.0, 200.0, 30.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        result = pm.get_powermeter_watts()
        self.assertEqual(result, [10.0, 200.0, 30.0])

    def test_repeated_within_deadband_always_returns_zero(self):
        """Consecutive within-deadband readings should always return zero."""
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        for value in [10.0, 20.0, -15.0, 0.0, 49.0]:
            self.mock_powermeter.get_powermeter_watts.return_value = [value]
            result = pm.get_powermeter_watts()
            self.assertEqual(result, [0.0])

    def test_invalid_deadband_raises_error(self):
        """Non-positive deadband_watts should raise ValueError."""
        with self.assertRaises(ValueError):
            DeadBandPowermeter(self.mock_powermeter, deadband_watts=0.0)
        with self.assertRaises(ValueError):
            DeadBandPowermeter(self.mock_powermeter, deadband_watts=-10.0)

    def test_wait_for_message_passthrough(self):
        """wait_for_message should be delegated to the wrapped powermeter."""
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)
        pm.wait_for_message(timeout=5)
        self.mock_powermeter.wait_for_message.assert_called_once()
        call_args = self.mock_powermeter.wait_for_message.call_args
        if call_args[1]:
            self.assertEqual(call_args[1]["timeout"], 5)
        else:
            self.assertEqual(call_args[0][0], 5)


if __name__ == "__main__":
    unittest.main()
