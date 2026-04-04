from typing import List, Optional
from .base import Powermeter


class ExponentialMovingAveragePowermeter(Powermeter):
    """
    A wrapper around a powermeter that applies an exponential moving average
    (EMA) to the raw values before returning them to the client.

    The EMA smooths out short-term fluctuations in power readings, which can
    be useful for noisy data sources or to reduce oscillation in the storage
    system's charge/discharge decisions.

    The smoothing factor ``alpha`` controls the degree of smoothing:
      - Values close to 0 produce heavy smoothing (slow to react to changes).
      - Values close to 1 produce little smoothing (close to the raw reading).

    Formula:
        EMA_t = alpha * raw_t + (1 - alpha) * EMA_{t-1}

    The first reading initialises the EMA (no averaging on the very first call).
    """

    def __init__(self, wrapped_powermeter: Powermeter, alpha: float = 0.1):
        """
        Initialise the EMA powermeter wrapper.

        Args:
            wrapped_powermeter: The actual powermeter instance to wrap.
            alpha: Smoothing factor in the range (0, 1].
                   Lower values mean more smoothing; 1.0 disables smoothing.
        """
        if not (0 < alpha <= 1.0):
            raise ValueError(f"EMA alpha must be in the range (0, 1], got {alpha}")
        self.wrapped_powermeter = wrapped_powermeter
        self.alpha = alpha
        self.ema_values: Optional[List[float]] = None

    def wait_for_message(self, timeout=5):
        """Pass through to wrapped powermeter."""
        return self.wrapped_powermeter.wait_for_message(timeout)

    def get_powermeter_watts(self) -> List[float]:
        raw_values = self.wrapped_powermeter.get_powermeter_watts()

        if self.ema_values is None:
            # Initialise EMA with the first reading
            self.ema_values = list(raw_values)
        else:
            self.ema_values = [
                self.alpha * raw + (1.0 - self.alpha) * ema
                for raw, ema in zip(raw_values, self.ema_values)
            ]

        return list(self.ema_values)
