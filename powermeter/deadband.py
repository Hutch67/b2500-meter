from typing import List, Optional
from .base import Powermeter


class DeadBandPowermeter(Powermeter):
    """
    A wrapper around a powermeter that suppresses small power changes.

    A new set of values is forwarded to the caller only when at least one
    phase has moved outside a symmetric dead-band (± ``deadband_watts``)
    around the last reported value.  While all phases remain inside the
    dead-band the previously reported values are returned unchanged.

    This prevents the storage system from reacting to noise or minor load
    fluctuations near the current operating point and is the most direct
    way to reduce hunting oscillation in Auto / Self-Adaptation mode.

    The dead-band is evaluated independently per phase; a change on any
    single phase is enough to trigger an update for all phases.

    The very first reading is always forwarded (no previous reference
    exists).
    """

    def __init__(self, wrapped_powermeter: Powermeter, deadband_watts: float):
        """
        Initialise the dead-band powermeter wrapper.

        Args:
            wrapped_powermeter: The actual powermeter instance to wrap.
            deadband_watts: Half-width of the dead-band in watts (must be > 0).
                            A change smaller than or equal to this threshold is
                            suppressed; a change larger than this threshold
                            triggers an update.
        """
        if deadband_watts <= 0:
            raise ValueError(
                f"deadband_watts must be positive, got {deadband_watts}"
            )
        self.wrapped_powermeter = wrapped_powermeter
        self.deadband_watts = deadband_watts
        self.last_reported: Optional[List[float]] = None

    def wait_for_message(self, timeout=5):
        """Pass through to wrapped powermeter."""
        return self.wrapped_powermeter.wait_for_message(timeout)

    def get_powermeter_watts(self) -> List[float]:
        values = self.wrapped_powermeter.get_powermeter_watts()

        if self.last_reported is None:
            # First reading – always forward and initialise the reference
            self.last_reported = list(values)
            return list(values)

        # Update if any phase exceeds the dead-band threshold
        outside = any(
            abs(new - last) > self.deadband_watts
            for new, last in zip(values, self.last_reported)
        )

        if outside:
            self.last_reported = list(values)
            return list(values)

        # All phases within dead-band – return last reported value
        return list(self.last_reported)
