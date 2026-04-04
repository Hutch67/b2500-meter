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


if __name__ == "__main__":
    unittest.main()
