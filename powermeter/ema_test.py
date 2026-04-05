import threading
import time
import unittest
from unittest.mock import Mock
from .ema import ExponentialMovingAveragePowermeter


class TestExponentialMovingAveragePowermeter(unittest.TestCase):
    def setUp(self):
        self.mock_powermeter = Mock()

    def test_first_reading_initialises_ema(self):
        """First call should return the raw value (EMA is initialised to it)."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        ema = ExponentialMovingAveragePowermeter(self.mock_powermeter, alpha=0.5)

        result = ema.get_powermeter_watts()
        self.assertEqual(result, [100.0])

    def test_ema_smoothing_single_phase(self):
        """EMA should smooth values across consecutive readings (single phase)."""
        self.mock_powermeter.get_powermeter_watts.return_value = [0.0]
        ema = ExponentialMovingAveragePowermeter(self.mock_powermeter, alpha=0.5)

        # Initialise: EMA = 0
        ema.get_powermeter_watts()

        # Feed a spike of 100 W
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        result = ema.get_powermeter_watts()
        # EMA = 0.5 * 100 + 0.5 * 0 = 50
        self.assertAlmostEqual(result[0], 50.0)

        # Another reading at 100 W
        result = ema.get_powermeter_watts()
        # EMA = 0.5 * 100 + 0.5 * 50 = 75
        self.assertAlmostEqual(result[0], 75.0)

    def test_ema_smoothing_three_phase(self):
        """EMA should smooth all phases independently."""
        self.mock_powermeter.get_powermeter_watts.return_value = [0.0, 0.0, 0.0]
        ema = ExponentialMovingAveragePowermeter(self.mock_powermeter, alpha=0.5)

        ema.get_powermeter_watts()  # initialise

        self.mock_powermeter.get_powermeter_watts.return_value = [100.0, 200.0, 300.0]
        result = ema.get_powermeter_watts()

        self.assertAlmostEqual(result[0], 50.0)
        self.assertAlmostEqual(result[1], 100.0)
        self.assertAlmostEqual(result[2], 150.0)

    def test_alpha_one_returns_raw_value(self):
        """alpha=1 means no smoothing – each reading is the raw value."""
        self.mock_powermeter.get_powermeter_watts.return_value = [50.0]
        ema = ExponentialMovingAveragePowermeter(self.mock_powermeter, alpha=1.0)

        ema.get_powermeter_watts()  # initialise

        self.mock_powermeter.get_powermeter_watts.return_value = [200.0]
        result = ema.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 200.0)

    def test_invalid_alpha_raises_error(self):
        """alpha outside (0, 1] should raise ValueError."""
        with self.assertRaises(ValueError):
            ExponentialMovingAveragePowermeter(self.mock_powermeter, alpha=0.0)
        with self.assertRaises(ValueError):
            ExponentialMovingAveragePowermeter(self.mock_powermeter, alpha=1.5)
        with self.assertRaises(ValueError):
            ExponentialMovingAveragePowermeter(self.mock_powermeter, alpha=-0.1)

    def test_wait_for_message_passthrough(self):
        """wait_for_message should be delegated to the wrapped powermeter."""
        ema = ExponentialMovingAveragePowermeter(self.mock_powermeter, alpha=0.3)
        ema.wait_for_message(timeout=10)
        self.mock_powermeter.wait_for_message.assert_called_once()
        call_args = self.mock_powermeter.wait_for_message.call_args
        if call_args[1]:
            self.assertEqual(call_args[1]["timeout"], 10)
        else:
            self.assertEqual(call_args[0][0], 10)

    def test_ema_converges_towards_stable_value(self):
        """EMA should converge to a stable input after enough readings."""
        self.mock_powermeter.get_powermeter_watts.return_value = [0.0]
        ema = ExponentialMovingAveragePowermeter(self.mock_powermeter, alpha=0.1)

        ema.get_powermeter_watts()  # initialise at 0

        self.mock_powermeter.get_powermeter_watts.return_value = [1000.0]
        result = None
        for _ in range(100):
            result = ema.get_powermeter_watts()

        # After 100 iterations with alpha=0.1, EMA should be very close to 1000
        self.assertAlmostEqual(result[0], 1000.0, delta=1.0)

    # --- Background-thread (ema_interval) mode tests ---

    def test_ema_interval_returns_value_from_background_thread(self):
        """With ema_interval set, get_powermeter_watts returns the cached EMA value."""
        self.mock_powermeter.get_powermeter_watts.return_value = [42.0]
        ema = ExponentialMovingAveragePowermeter(
            self.mock_powermeter, alpha=1.0, ema_interval=0.05
        )

        # Wait for background thread to produce at least one reading
        result = ema.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 42.0)

    def test_ema_interval_does_not_call_underlying_on_get(self):
        """With ema_interval set, get_powermeter_watts must not call the underlying source."""
        self.mock_powermeter.get_powermeter_watts.return_value = [10.0]
        ema = ExponentialMovingAveragePowermeter(
            self.mock_powermeter, alpha=1.0, ema_interval=0.05
        )

        # Wait for first background reading
        ema._first_reading_event.wait(timeout=2)

        call_count_before = self.mock_powermeter.get_powermeter_watts.call_count
        # Multiple get calls must not increase the underlying call count
        ema.get_powermeter_watts()
        ema.get_powermeter_watts()
        ema.get_powermeter_watts()
        call_count_after = self.mock_powermeter.get_powermeter_watts.call_count
        self.assertEqual(call_count_before, call_count_after)

    def test_ema_interval_background_thread_updates_ema(self):
        """Background thread should keep updating the EMA over time."""
        # Start with 0, then switch to 100 after first reading
        call_count = [0]

        def side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return [0.0]
            return [100.0]

        self.mock_powermeter.get_powermeter_watts.side_effect = side_effect
        ema = ExponentialMovingAveragePowermeter(
            self.mock_powermeter, alpha=0.5, ema_interval=0.05
        )

        # Wait long enough for several background updates
        time.sleep(0.4)

        result = ema.get_powermeter_watts()
        # After several iterations converging from 0 to 100, value should be high
        self.assertGreater(result[0], 80.0)

    def test_ema_interval_zero_uses_synchronous_mode(self):
        """ema_interval=0 (default) must use the original synchronous behaviour."""
        self.mock_powermeter.get_powermeter_watts.return_value = [0.0]
        ema = ExponentialMovingAveragePowermeter(
            self.mock_powermeter, alpha=0.5, ema_interval=0.0
        )

        ema.get_powermeter_watts()  # initialise at 0

        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        result = ema.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 50.0)

        result = ema.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 75.0)

    def test_ema_interval_background_thread_is_daemon(self):
        """Background thread must be a daemon so it does not prevent process exit."""
        self.mock_powermeter.get_powermeter_watts.return_value = [1.0]
        ema = ExponentialMovingAveragePowermeter(
            self.mock_powermeter, alpha=0.5, ema_interval=1.0
        )
        self.assertTrue(ema._thread.daemon)


if __name__ == "__main__":
    unittest.main()
