import unittest
import time
from unittest.mock import Mock, patch
from .pid import PidPowermeter


class TestPidPowermeter(unittest.TestCase):
    def setUp(self):
        self.mock_powermeter = Mock()

    # ------------------------------------------------------------------
    # Construction / validation
    # ------------------------------------------------------------------

    def test_invalid_output_max_raises(self):
        """output_max must be positive."""
        with self.assertRaises(ValueError):
            PidPowermeter(self.mock_powermeter, output_max=0.0)
        with self.assertRaises(ValueError):
            PidPowermeter(self.mock_powermeter, output_max=-100.0)

    def test_invalid_mode_raises(self):
        """Only 'bias' and 'replace' are accepted."""
        with self.assertRaises(ValueError):
            PidPowermeter(self.mock_powermeter, mode="invalid")

    def test_mode_case_insensitive(self):
        """Mode string should be case-insensitive."""
        pm = PidPowermeter(self.mock_powermeter, mode="BIAS")
        self.assertEqual(pm.mode, "bias")
        pm2 = PidPowermeter(self.mock_powermeter, mode="Replace")
        self.assertEqual(pm2.mode, "replace")

    # ------------------------------------------------------------------
    # Proportional-only behaviour
    # ------------------------------------------------------------------

    def test_p_only_positive_error(self):
        """With P-only control, a large import (actual=200W, setpoint=0) produces
        a negative adjustment to tell the B2500 to cover that import."""
        self.mock_powermeter.get_powermeter_watts.return_value = [200.0]
        pm = PidPowermeter(self.mock_powermeter, kp=1.0, setpoint=0.0, output_max=800.0)
        # error = -0 - 200 = -200  →  P output = -200
        result = pm.get_powermeter_watts()
        # bias mode: 200 + (-200) = 0  (reported as balanced, B2500 stops)
        self.assertAlmostEqual(result[0], 0.0)

    def test_p_only_negative_error(self):
        """Export reading (actual=-100W, setpoint=0) produces a positive adjustment,
        telling the B2500 to reduce feed-in and let imports rise."""
        self.mock_powermeter.get_powermeter_watts.return_value = [-100.0]
        pm = PidPowermeter(self.mock_powermeter, kp=1.0, setpoint=0.0, output_max=800.0)
        # error = -0 - (-100) = 100  →  P output = 100
        result = pm.get_powermeter_watts()
        # bias: -100 + 100 = 0
        self.assertAlmostEqual(result[0], 0.0)

    def test_p_only_with_setpoint(self):
        """With a non-zero setpoint the controller drives toward it.
        For Kp=0.5 the P-only steady-state equals exactly the setpoint."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm = PidPowermeter(
            self.mock_powermeter, kp=0.5, setpoint=20.0, output_max=800.0
        )
        # error = -20 - 100 = -120  →  P output = 0.5 * (-120) = -60
        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 40.0)  # 100 + (-60)

    # ------------------------------------------------------------------
    # Output clamping
    # ------------------------------------------------------------------

    def test_output_clamped_positive(self):
        """PID output should not exceed +output_max."""
        self.mock_powermeter.get_powermeter_watts.return_value = [-1000.0]
        pm = PidPowermeter(self.mock_powermeter, kp=1.0, setpoint=0.0, output_max=500.0)
        # error = -0 - (-1000) = 1000  →  clamped to 500
        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], -500.0)  # -1000 + 500

    def test_output_clamped_negative(self):
        """PID output should not go below -output_max."""
        self.mock_powermeter.get_powermeter_watts.return_value = [2000.0]
        pm = PidPowermeter(self.mock_powermeter, kp=1.0, setpoint=0.0, output_max=500.0)
        # error = -0 - 2000 = -2000  →  clamped to -500
        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 1500.0)  # 2000 + (-500)

    # ------------------------------------------------------------------
    # Integral behaviour
    # ------------------------------------------------------------------

    def test_integral_accumulates_over_time(self):
        """The integral term should grow over successive calls."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        pm = PidPowermeter(
            self.mock_powermeter, kp=0.0, ki=1.0, setpoint=0.0, output_max=800.0
        )

        # First call initialises state (dt = 0, no integral contribution)
        t0 = 1000.0
        with patch("powermeter.pid.time") as mock_time:
            mock_time.monotonic.return_value = t0
            r1 = pm.get_powermeter_watts()

        # Second call after 1 second
        with patch("powermeter.pid.time") as mock_time:
            mock_time.monotonic.return_value = t0 + 1.0
            r2 = pm.get_powermeter_watts()

        # error = -0 - 100 = -100, integral = -100 * 1s = -100
        # I output = 1.0 * -100 = -100
        self.assertAlmostEqual(r2[0], 0.0)  # 100 + (-100) in bias mode

    def test_anti_windup_stops_integration(self):
        """The integral should not grow beyond what output_max allows."""
        self.mock_powermeter.get_powermeter_watts.return_value = [500.0]
        pm = PidPowermeter(
            self.mock_powermeter, kp=0.0, ki=1.0, setpoint=0.0, output_max=200.0
        )

        t0 = 1000.0
        with patch("powermeter.pid.time") as mock_time:
            mock_time.monotonic.return_value = t0
            pm.get_powermeter_watts()  # init

        # Accumulate a large integral over 10 seconds
        with patch("powermeter.pid.time") as mock_time:
            mock_time.monotonic.return_value = t0 + 10.0
            result = pm.get_powermeter_watts()

        # Without anti-windup the integral would be -500*10 = -5000
        # But output is clamped to -200, so bias result >= 500 - 200 = 300
        self.assertGreaterEqual(result[0], 300.0)

    # ------------------------------------------------------------------
    # Derivative behaviour
    # ------------------------------------------------------------------

    def test_derivative_reacts_to_change(self):
        """The D term should respond to changes in error."""
        pm = PidPowermeter(
            self.mock_powermeter, kp=0.0, kd=1.0, setpoint=0.0, output_max=800.0
        )

        t0 = 1000.0
        # First reading: 100 W
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0]
        with patch("powermeter.pid.time") as mock_time:
            mock_time.monotonic.return_value = t0
            pm.get_powermeter_watts()

        # Second reading: 200 W (1 second later)
        self.mock_powermeter.get_powermeter_watts.return_value = [200.0]
        with patch("powermeter.pid.time") as mock_time:
            mock_time.monotonic.return_value = t0 + 1.0
            result = pm.get_powermeter_watts()

        # error1 = -0-100 = -100, error2 = -0-200 = -200
        # d_term = 1.0 * (-200 - (-100)) / 1.0 = -100
        # bias: 200 + (-100) = 100
        self.assertAlmostEqual(result[0], 100.0)

    # ------------------------------------------------------------------
    # Multi-phase
    # ------------------------------------------------------------------

    def test_multiphase_bias(self):
        """PID output should be distributed equally across phases in bias mode."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0, 200.0, 300.0]
        pm = PidPowermeter(self.mock_powermeter, kp=1.0, setpoint=0.0, output_max=800.0)
        # total = 600, error = -0 - 600 = -600, P = -600
        # per_phase = -600 / 3 = -200
        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], -100.0)  # 100 + (-200)
        self.assertAlmostEqual(result[1], 0.0)   # 200 + (-200)
        self.assertAlmostEqual(result[2], 100.0)  # 300 + (-200)

    def test_multiphase_replace(self):
        """In replace mode, all phases should get equal share of PID output."""
        self.mock_powermeter.get_powermeter_watts.return_value = [100.0, 200.0, 300.0]
        pm = PidPowermeter(
            self.mock_powermeter,
            kp=1.0,
            setpoint=0.0,
            output_max=800.0,
            mode="replace",
        )
        # total = 600, error = -0 - 600 = -600, P = -600
        # per_phase = -600 / 3 = -200
        result = pm.get_powermeter_watts()
        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(result[0], -200.0)
        self.assertAlmostEqual(result[1], -200.0)
        self.assertAlmostEqual(result[2], -200.0)

    # ------------------------------------------------------------------
    # Replace mode basics
    # ------------------------------------------------------------------

    def test_replace_mode(self):
        """In replace mode the raw value should be discarded."""
        self.mock_powermeter.get_powermeter_watts.return_value = [500.0]
        pm = PidPowermeter(
            self.mock_powermeter,
            kp=1.0,
            setpoint=0.0,
            output_max=800.0,
            mode="replace",
        )
        # error = -0 - 500 = -500, P = -500
        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], -500.0)

    # ------------------------------------------------------------------
    # Zero gains (disabled)
    # ------------------------------------------------------------------

    def test_all_gains_zero_passthrough(self):
        """With all gains at zero, the PID should have no effect."""
        self.mock_powermeter.get_powermeter_watts.return_value = [123.4]
        pm = PidPowermeter(self.mock_powermeter, kp=0.0, ki=0.0, kd=0.0)
        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 123.4)

    # ------------------------------------------------------------------
    # wait_for_message pass-through
    # ------------------------------------------------------------------

    def test_wait_for_message_passthrough(self):
        """wait_for_message should be delegated to the wrapped powermeter."""
        pm = PidPowermeter(self.mock_powermeter, kp=1.0)
        pm.wait_for_message(timeout=7)
        self.mock_powermeter.wait_for_message.assert_called_once()
        call_args = self.mock_powermeter.wait_for_message.call_args
        if call_args[1]:
            self.assertEqual(call_args[1]["timeout"], 7)
        else:
            self.assertEqual(call_args[0][0], 7)

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------

    def test_does_not_mutate_wrapped_list(self):
        """The wrapper must not mutate the list from the inner powermeter."""
        raw = [100.0, 200.0]
        self.mock_powermeter.get_powermeter_watts.return_value = raw
        pm = PidPowermeter(self.mock_powermeter, kp=0.5, setpoint=0.0)

        pm.get_powermeter_watts()
        self.assertEqual(raw, [100.0, 200.0])

    # ------------------------------------------------------------------
    # First call — no derivative spike
    # ------------------------------------------------------------------

    def test_first_call_no_derivative_spike(self):
        """The first call should not produce a derivative spike."""
        self.mock_powermeter.get_powermeter_watts.return_value = [500.0]
        pm = PidPowermeter(
            self.mock_powermeter, kp=0.0, kd=100.0, setpoint=0.0, output_max=800.0
        )
        # First call: dt=0, so D term should be 0
        result = pm.get_powermeter_watts()
        self.assertAlmostEqual(result[0], 500.0)


if __name__ == "__main__":
    unittest.main()
