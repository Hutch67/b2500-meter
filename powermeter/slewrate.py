import threading
import time
from typing import List, Optional
from .base import Powermeter


class SlewRatePowermeter(Powermeter):
    """
    A wrapper around a powermeter that limits the rate of change of power values.

    Even when the underlying reading jumps by a large amount in a single
    poll cycle, the reported value advances towards the target at most
    ``slew_rate_watts_per_sec`` watts per second.  This prevents sudden
    large steps from triggering an aggressive over-response in the storage
    system that would then reverse direction and cause oscillation.

    The slew limit is applied independently to each phase.

    The very first reading is always forwarded as-is (no previous reference
    exists, so there is nothing to slew from).
    """

    def __init__(
        self, wrapped_powermeter: Powermeter, slew_rate_watts_per_sec: float
    ):
        """
        Initialise the slew-rate powermeter wrapper.

        Args:
            wrapped_powermeter: The actual powermeter instance to wrap.
            slew_rate_watts_per_sec: Maximum allowed change in watts per second
                                     (must be > 0).
        """
        if slew_rate_watts_per_sec <= 0:
            raise ValueError(
                f"slew_rate_watts_per_sec must be positive, got {slew_rate_watts_per_sec}"
            )
        self.wrapped_powermeter = wrapped_powermeter
        self.slew_rate_watts_per_sec = slew_rate_watts_per_sec
        self.last_values: Optional[List[float]] = None
        self.last_time: Optional[float] = None
        self._lock = threading.Lock()

    def wait_for_message(self, timeout=5):
        """Pass through to wrapped powermeter."""
        return self.wrapped_powermeter.wait_for_message(timeout)

    def get_powermeter_watts(self) -> List[float]:
        with self._lock:
            raw_values = self.wrapped_powermeter.get_powermeter_watts()
            current_time = time.time()
    
            if self.last_values is None or self.last_time is None:
                # First reading – initialise without slewing
                self.last_values = list(raw_values)
                self.last_time = current_time
                return list(raw_values)
    
            elapsed = current_time - self.last_time
            max_change = self.slew_rate_watts_per_sec * elapsed
    
            slewed = []
            for raw, last in zip(raw_values, self.last_values):
                delta = raw - last
                if abs(delta) <= max_change:
                    slewed.append(raw)
                else:
                    slewed.append(last + max_change * (1.0 if delta > 0 else -1.0))
    
            self.last_values = slewed
            self.last_time = current_time
            return list(slewed)
