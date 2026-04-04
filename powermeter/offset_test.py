import unittest
from unittest.mock import Mock
from .offset import OffsetPowermeter


class TestOffsetPowermeter(unittest.TestCase):
    def setUp(self):
        self.mock_powermeter = Mock()

    def test_positive_offset_single_phase(self):
        """A positive offset should be added to the raw reading."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm = OffsetPowermeter(self.mock_powermeter, offset=50.0)

        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 150.0)

    def test_negative_offset_single_phase(self):
        """A negative offset should be subtracted from the raw reading."""
        self.mock_powermeter.get_powermeter_watts.return_value = [200.0]
        pm = OffsetPowermeter(self.mock_powermeter, offset=-30.0)

        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 170.0)

    def test_zero_offset_returns_raw_value(self):
        """An offset of zero should return the raw value unchanged."""
        self.mock_powermeter.get_powermeter_watts.return_value = [123.4]
        pm = OffsetPowermeter(self.mock_powermeter, offset=0.0)

        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 123.4)

    def test_offset_applied_to_all_phases(self):
        """The offset should be applied independently to every phase."""
        self.mock_powermeter.get_powermeter_watts.return_value = [
            100.0,
            200.0,
            300.0,
        ]
        pm = OffsetPowermeter(self.mock_powermeter, offset=25.0)

        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 125.0)
        self.assertAlmostEqual(result[1], 225.0)
        self.assertAlmostEqual(result[2], 325.0)

    def test_wait_for_message_passthrough(self):
        """wait_for_message should be delegated to the wrapped powermeter."""
        pm = OffsetPowermeter(self.mock_powermeter, offset=10.0)
        pm.wait_for_message(timeout=7)
        self.mock_powermeter.wait_for_message.assert_called_once()
        call_args = self.mock_powermeter.wait_for_message.call_args
        if call_args[1]:
            self.assertEqual(call_args[1]["timeout"], 7)
        else:
            self.assertEqual(call_args[0][0], 7)

    def test_offset_does_not_mutate_original_list(self):
        """The wrapper must not mutate the list returned by the inner powermeter."""
        raw = [100.0, 200.0]
        self.mock_powermeter.get_powermeter_watts.return_value = raw
        pm = OffsetPowermeter(self.mock_powermeter, offset=10.0)

        pm.get_powermeter_watts()
        self.assertEqual(raw, [100.0, 200.0])


if __name__ == "__main__":
    unittest.main()
