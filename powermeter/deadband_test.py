import unittest
from unittest.mock import Mock
from .deadband import DeadBandPowermeter


class TestDeadBandPowermeter(unittest.TestCase):
    def setUp(self):
        self.mock_powermeter = Mock()

    def test_first_reading_always_forwarded(self):
        """First call should return the raw value regardless of dead-band."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        result = pm.get_powermeter_watts()
        self.assertEqual(result, [100.0])

    def test_change_within_deadband_suppressed(self):
        """A change smaller than the dead-band should return the previous value."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        pm.get_powermeter_watts()  # initialise at 100 W

        # Change of 30 W is within the 50 W dead-band
        self.mock_powermeter.get_powermeter_watts.return_value = [130.0]
        result = pm.get_powermeter_watts()
        self.assertEqual(result, [100.0])

    def test_change_at_deadband_boundary_suppressed(self):
        """An exact dead-band-sized change should be suppressed (not strictly greater)."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        pm.get_powermeter_watts()  # initialise at 100 W

        # Change of exactly 50 W equals the dead-band – should still be suppressed
        self.mock_powermeter.get_powermeter_watts.return_value = [150.0]
        result = pm.get_powermeter_watts()
        self.assertEqual(result, [100.0])

    def test_change_outside_deadband_forwarded(self):
        """A change larger than the dead-band should return the new value."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        pm.get_powermeter_watts()  # initialise at 100 W

        # Change of 51 W exceeds the 50 W dead-band
        self.mock_powermeter.get_powermeter_watts.return_value = [151.0]
        result = pm.get_powermeter_watts()
        self.assertEqual(result, [151.0])

    def test_negative_change_outside_deadband_forwarded(self):
        """A negative change larger than the dead-band should be forwarded."""
        self.mock_powermeter.get_powermeter_watts.return_value = [200.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        pm.get_powermeter_watts()  # initialise at 200 W

        # Drop of 60 W exceeds the 50 W dead-band
        self.mock_powermeter.get_powermeter_watts.return_value = [140.0]
        result = pm.get_powermeter_watts()
        self.assertEqual(result, [140.0])

    def test_reference_updates_after_forward(self):
        """After forwarding a new value the reference updates to that value."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        pm.get_powermeter_watts()  # initialise at 100 W

        # Jump outside dead-band → reference moves to 200 W
        self.mock_powermeter.get_powermeter_watts.return_value = [200.0]
        pm.get_powermeter_watts()

        # Now a change of 30 W from the NEW reference (200 W) should be suppressed
        self.mock_powermeter.get_powermeter_watts.return_value = [230.0]
        result = pm.get_powermeter_watts()
        self.assertEqual(result, [200.0])

    def test_three_phase_any_phase_triggers_update(self):
        """If any single phase exceeds the dead-band, all phases are updated."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0, 100.0, 100.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        pm.get_powermeter_watts()  # initialise

        # Only phase 2 exceeds the dead-band
        self.mock_powermeter.get_powermeter_watts.return_value = [110.0, 200.0, 105.0]
        result = pm.get_powermeter_watts()
        self.assertEqual(result, [110.0, 200.0, 105.0])

    def test_three_phase_all_within_deadband_suppressed(self):
        """All phases within dead-band → return previous values for all phases."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0, 100.0, 100.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        pm.get_powermeter_watts()  # initialise

        self.mock_powermeter.get_powermeter_watts.return_value = [110.0, 120.0, 130.0]
        result = pm.get_powermeter_watts()
        self.assertEqual(result, [100.0, 100.0, 100.0])

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

    def test_return_value_does_not_mutate_internal_state(self):
        """Mutating the returned list must not corrupt the internal reference."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm = DeadBandPowermeter(self.mock_powermeter, deadband_watts=50.0)

        result = pm.get_powermeter_watts()
        result[0] = 9999.0  # mutate the returned list

        # Suppress a within-deadband change – should still get original reference
        self.mock_powermeter.get_powermeter_watts.return_value = [110.0]
        result2 = pm.get_powermeter_watts()
        self.assertEqual(result2, [100.0])


if __name__ == "__main__":
    unittest.main()
