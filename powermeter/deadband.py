from typing import List
from .base import Powermeter


class DeadBandPowermeter(Powermeter):
    """
    A wrapper around a powermeter that reports zero when values are small.

    When all phases are within a symmetric dead-band around zero
    (± ``deadband_watts``), zero is reported for every phase.  As soon as
    any phase exceeds the threshold the actual measured values are returned.

    This prevents the storage system from reacting to noise or minor load
    fluctuations near zero and is the most direct way to reduce hunting
    oscillation in Auto / Self-Adaptation mode.
    """

    def __init__(self, wrapped_powermeter: Powermeter, deadband_watts: float):
        """
        Initialise the dead-band powermeter wrapper.

        Args:
            wrapped_powermeter: The actual powermeter instance to wrap.
            deadband_watts: Half-width of the dead-band in watts (must be > 0).
                            If all phase values are within ±deadband_watts of
                            zero, zero is reported for every phase.
        """
        if deadband_watts <= 0:
            raise ValueError(
                f"deadband_watts must be positive, got {deadband_watts}"
            )
        self.wrapped_powermeter = wrapped_powermeter
        self.deadband_watts = deadband_watts

    def wait_for_message(self, timeout=5):
        """Pass through to wrapped powermeter."""
        return self.wrapped_powermeter.wait_for_message(timeout)

    def get_powermeter_watts(self) -> List[float]:
        values = self.wrapped_powermeter.get_powermeter_watts()

        # If all phases are within the dead-band around zero, report zero
        if all(abs(v) <= self.deadband_watts for v in values):
            return [0.0] * len(values)

        return list(values)
