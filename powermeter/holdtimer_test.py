import time
import unittest
from unittest.mock import Mock
from .holdtimer import HoldTimerPowermeter


class TestHoldTimerPowermeter(unittest.TestCase):
    def setUp(self):
        self.mock_powermeter = Mock()

    def test_first_reading_forwarded_immediately(self):
        """First call should fetch and return the underlying value."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm = HoldTimerPowermeter(self.mock_powermeter, hold_time=5.0)

        result = pm.get_powermeter_watts()
        self.assertEqual(result, [100.0])
        self.mock_powermeter.get_powermeter_watts.assert_called_once()

    def test_value_held_during_hold_window(self):
        """Polls within the hold window should return the held value."""
        pm = HoldTimerPowermeter(self.mock_powermeter, hold_time=5.0)

        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm.get_powermeter_watts()  # fetch and start hold window

        # Change underlying value; poll while hold window is still active
        self.mock_powermeter.get_powermeter_watts.return_value = [999.0]
        # hold_until is in the future, so we are inside the window
        result = pm.get_powermeter_watts()

        # Should still return the held value, not the new underlying value
        self.assertEqual(result, [100.0])
        # Underlying powermeter should only have been called once
        self.mock_powermeter.get_powermeter_watts.assert_called_once()

    def test_new_value_forwarded_after_hold_expires(self):
        """After the hold window expires a new value should be fetched."""
        pm = HoldTimerPowermeter(self.mock_powermeter, hold_time=5.0)

        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm.get_powermeter_watts()  # fetch and start hold window

        # Expire the hold window by setting hold_until to the past
        pm.hold_until = 0.0

        self.mock_powermeter.get_powermeter_watts.return_value = [200.0]
        result = pm.get_powermeter_watts()

        self.assertEqual(result, [200.0])

    def test_hold_window_resets_after_update(self):
        """Each new fetch should start a fresh hold window."""
        pm = HoldTimerPowermeter(self.mock_powermeter, hold_time=5.0)

        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm.get_powermeter_watts()  # first fetch

        # Expire first hold window
        pm.hold_until = 0.0
        self.mock_powermeter.get_powermeter_watts.return_value = [200.0]
        pm.get_powermeter_watts()  # second fetch, starts new hold window

        # Poll again while new hold window is still active
        self.mock_powermeter.get_powermeter_watts.return_value = [999.0]
        result = pm.get_powermeter_watts()

        self.assertEqual(result, [200.0])

    def test_three_phase_values_held(self):
        """Hold timer should hold all phases simultaneously."""
        pm = HoldTimerPowermeter(self.mock_powermeter, hold_time=5.0)

        self.mock_powermeter.get_powermeter_watts.return_value = [100.0, 200.0, 300.0]
        pm.get_powermeter_watts()

        self.mock_powermeter.get_powermeter_watts.return_value = [1.0, 2.0, 3.0]
        result = pm.get_powermeter_watts()

        self.assertEqual(result, [100.0, 200.0, 300.0])

    def test_real_time_hold(self):
        """Integration test using real time: value should be held for ~0.1 s."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm = HoldTimerPowermeter(self.mock_powermeter, hold_time=0.1)

        pm.get_powermeter_watts()  # fetch and start hold window

        # Immediately poll again – should get held value
        self.mock_powermeter.get_powermeter_watts.return_value = [999.0]
        result_held = pm.get_powermeter_watts()
        self.assertEqual(result_held, [100.0])

        # Wait for hold to expire, then poll again
        time.sleep(0.15)
        result_new = pm.get_powermeter_watts()
        self.assertEqual(result_new, [999.0])

    def test_invalid_hold_time_raises_error(self):
        """Non-positive hold_time should raise ValueError."""
        with self.assertRaises(ValueError):
            HoldTimerPowermeter(self.mock_powermeter, hold_time=0.0)
        with self.assertRaises(ValueError):
            HoldTimerPowermeter(self.mock_powermeter, hold_time=-1.0)

    def test_wait_for_message_passthrough(self):
        """wait_for_message should be delegated to the wrapped powermeter."""
        pm = HoldTimerPowermeter(self.mock_powermeter, hold_time=2.0)
        pm.wait_for_message(timeout=4)
        self.mock_powermeter.wait_for_message.assert_called_once()
        call_args = self.mock_powermeter.wait_for_message.call_args
        if call_args[1]:
            self.assertEqual(call_args[1]["timeout"], 4)
        else:
            self.assertEqual(call_args[0][0], 4)

    def test_return_value_does_not_mutate_internal_state(self):
        """Mutating the returned list must not corrupt the held value."""
        pm = HoldTimerPowermeter(self.mock_powermeter, hold_time=5.0)

        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        result = pm.get_powermeter_watts()
        result[0] = 9999.0  # mutate returned list

        # Poll within hold window – held value should still be the original
        result2 = pm.get_powermeter_watts()

        self.assertEqual(result2, [100.0])


if __name__ == "__main__":
    unittest.main()
