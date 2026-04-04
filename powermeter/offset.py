from typing import List
from .base import Powermeter


class OffsetPowermeter(Powermeter):
    """
    A wrapper around a powermeter that adds a constant offset (in watts) to
    every phase value returned by the underlying powermeter.

    A positive offset increases the reported power; a negative offset decreases
    it.  The offset is applied to each phase independently.

    This is useful when the physical meter has a known, systematic measurement
    error that should be compensated in software, or when a constant baseline
    load should be factored into the readings.
    """

    def __init__(self, wrapped_powermeter: Powermeter, offset: float):
        """
        Initialise the offset powermeter wrapper.

        Args:
            wrapped_powermeter: The actual powermeter instance to wrap.
            offset: Constant value in watts to add to every phase reading.
                    May be negative.
        """
        self.wrapped_powermeter = wrapped_powermeter
        self.offset = offset

    def wait_for_message(self, timeout=5):
        """Pass through to wrapped powermeter."""
        return self.wrapped_powermeter.wait_for_message(timeout)

    def get_powermeter_watts(self) -> List[float]:
        raw_values = self.wrapped_powermeter.get_powermeter_watts()
        return [value + self.offset for value in raw_values]
