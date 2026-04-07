import time
import threading
from typing import List, Optional
from .base import Powermeter


class PidPowermeter(Powermeter):
    """
    A wrapper around a powermeter that applies a PID (Proportional-Integral-
    Derivative) controller to steer the reported power toward a configurable
    setpoint.

    The PID controller uses the raw power-meter reading as its *process
    variable* and computes an adjustment that is either **added** to the raw
    reading (``mode="bias"``) or **used in place of** the raw reading
    (``mode="replace"``).

    Positive PID output motivates the B2500 to increase feed-in power;
    negative output motivates it to decrease feed-in power.

    **Gain sensitivity:** in ``mode="bias"`` the PID and the B2500's own
    closed-loop controller act *together*.  The effective closed-loop gain
    is ``(1 − Kp) × Kb``, where ``Kb`` is the B2500's internal gain.
    The system is stable for ``0 < Kp < 1``.  Use ``Kp = 0.5`` as the
    recommended starting value — at this gain P-only control reaches exactly
    the setpoint in steady state without requiring integral action.

    **Anti-windup** is built in: the integral term is clamped so that the
    total PID output never exceeds ``[−output_max, +output_max]``, and
    integration is paused while the output is saturated.

    Error convention:
        error = −setpoint − measurement
    This keeps the effective closed-loop gain at ``(1 − Kp) × Kb`` (where
    ``Kb`` is the B2500's internal gain), identical to the original stable
    formula, while converging to the *correct* direction.  For ``Kp = 0.5``
    P-only control the steady-state grid power equals the setpoint exactly;
    for other values of ``Kp`` it equals ``Kp × setpoint / (1 − Kp)``.

    **Important:** the integral term (``ki``) must remain at 0.  Because the
    error does not cross zero at ``actual == setpoint`` (it equals
    ``−2 × setpoint``), a non-zero ``ki`` causes the integral to accumulate
    indefinitely and will destabilise the loop.

    The controller runs on the **sum** of all phases (total grid power)
    and distributes its output equally across phases.

    Config parameters:
        PID_KP          Proportional gain (default 0 → PID disabled)
        PID_KI          Integral gain (default 0)
        PID_KD          Derivative gain (default 0)
        PID_SETPOINT    Target grid power in watts (default 0)
        PID_OUTPUT_MAX  Output clamp magnitude in watts (default 800)
        PID_MODE        "bias" or "replace" (default "bias")
    """

    VALID_MODES = ("bias", "replace")

    def __init__(
        self,
        wrapped_powermeter: Powermeter,
        kp: float = 0.0,
        ki: float = 0.0,
        kd: float = 0.0,
        setpoint: float = 0.0,
        output_max: float = 800.0,
        mode: str = "bias",
    ):
        """
        Initialise the PID powermeter wrapper.

        Args:
            wrapped_powermeter: The actual powermeter instance to wrap.
            kp:  Proportional gain.
            ki:  Integral gain.
            kd:  Derivative gain.
            setpoint:  Target grid power in watts (positive = import).
            output_max:  Maximum absolute PID output in watts.  Must be > 0.
            mode:  ``"bias"``  — add PID output to raw reading, or
                   ``"replace"`` — use PID output as the reported value.
        """
        if output_max <= 0:
            raise ValueError(f"PID output_max must be positive, got {output_max}")
        mode = mode.lower()
        if mode not in self.VALID_MODES:
            raise ValueError(
                f"PID mode must be one of {self.VALID_MODES}, got '{mode}'"
            )

        self.wrapped_powermeter = wrapped_powermeter
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.setpoint = setpoint
        self.output_max = output_max
        self.mode = mode

        # PID state
        self._integral: float = 0.0
        self._prev_error: Optional[float] = None
        self._prev_time: Optional[float] = None
        self._lock = threading.Lock()

    def wait_for_message(self, timeout=5):
        """Pass through to wrapped powermeter."""
        return self.wrapped_powermeter.wait_for_message(timeout)

    def get_powermeter_watts(self) -> List[float]:
        raw_values = self.wrapped_powermeter.get_powermeter_watts()
        current_time = time.monotonic()

        # Compute error on the total power across all phases
        total_power = sum(raw_values)
        error = -self.setpoint - total_power

        with self._lock:
            if self._prev_time is None:
                # First call — initialise state, no derivative yet
                self._prev_error = error
                self._prev_time = current_time
                dt = 0.0
            else:
                dt = current_time - self._prev_time
                if dt <= 0:
                    dt = 0.0

            # --- Proportional ---
            p_term = self.kp * error

            # --- Integral with anti-windup ---
            if dt > 0:
                # Tentatively accumulate
                tentative_integral = self._integral + error * dt
                tentative_output = p_term + self.ki * tentative_integral
                # Only accept the new integral if output is not saturated,
                # or if the integral is moving toward zero (unwinding).
                if abs(tentative_output) <= self.output_max or (
                    tentative_integral * error < 0
                ):
                    self._integral = tentative_integral
            i_term = self.ki * self._integral

            # --- Derivative ---
            if dt > 0 and self._prev_error is not None:
                d_term = self.kd * (error - self._prev_error) / dt
            else:
                d_term = 0.0

            self._prev_error = error
            self._prev_time = current_time

        # --- Total output with clamping ---
        pid_output = p_term + i_term + d_term
        pid_output = max(-self.output_max, min(self.output_max, pid_output))

        # --- Apply to readings ---
        num_phases = len(raw_values)
        per_phase = pid_output / num_phases if num_phases > 0 else 0.0

        if self.mode == "bias":
            return [value + per_phase for value in raw_values]
        else:
            # replace mode: distribute PID output equally across phases
            return [per_phase] * num_phases
