import time
from typing import List, Optional
from .base import Powermeter


class HoldTimerPowermeter(Powermeter):
    """
    A wrapper around a powermeter that holds each reported value for a
    minimum duration before allowing an update.

    Once a value is forwarded to the caller a hold window of ``hold_time``
    seconds starts.  Any poll that arrives during this window receives the
    held value unchanged, preventing the storage system from acting on
    rapid successive changes before it has had a chance to respond
    physically.  After the window expires the next underlying value is
    forwarded and a new hold window begins.

    This complements throttling (which rate-limits *fetching* from the
    source) by rate-limiting *reporting* to the storage system regardless
    of how frequently it polls.
    """

    def __init__(self, wrapped_powermeter: Powermeter, hold_time: float):
        """
        Initialise the hold-timer powermeter wrapper.

        Args:
            wrapped_powermeter: The actual powermeter instance to wrap.
            hold_time: Minimum seconds to hold a reported value before
                       forwarding the next update (must be > 0).
        """
        if hold_time <= 0:
            raise ValueError(f"hold_time must be positive, got {hold_time}")
        self.wrapped_powermeter = wrapped_powermeter
        self.hold_time = hold_time
        self.held_values: Optional[List[float]] = None
        self.hold_until: float = 0.0

    def wait_for_message(self, timeout=5):
        """Pass through to wrapped powermeter."""
        return self.wrapped_powermeter.wait_for_message(timeout)

    def get_powermeter_watts(self) -> List[float]:
        current_time = time.time()

        if self.held_values is not None and current_time < self.hold_until:
            # Still within the hold window – return the held value
            return list(self.held_values)

        # Hold window has expired (or first call) – fetch and hold new value
        values = self.wrapped_powermeter.get_powermeter_watts()
        self.held_values = list(values)
        self.hold_until = current_time + self.hold_time
        return list(values)
