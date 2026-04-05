import threading
import time
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

    When ``ema_interval`` is set to a positive value, a background thread
    samples the underlying powermeter every ``ema_interval`` seconds to update
    the EMA state.  Calls to ``get_powermeter_watts()`` then return the cached
    EMA value without hitting the underlying source, so the EMA accumulation
    rate is decoupled from how often the B2500 device requests data.
    """

    def __init__(
        self,
        wrapped_powermeter: Powermeter,
        alpha: float = 0.1,
        ema_interval: float = 0.0,
    ):
        """
        Initialise the EMA powermeter wrapper.

        Args:
            wrapped_powermeter: The actual powermeter instance to wrap.
            alpha: Smoothing factor in the range (0, 1].
                   Lower values mean more smoothing; 1.0 disables smoothing.
            ema_interval: If > 0, a background thread samples the underlying
                          powermeter at this interval (in seconds) to update
                          the EMA, independent of how often
                          ``get_powermeter_watts()`` is called.
                          If 0 (default), the EMA is updated on every call to
                          ``get_powermeter_watts()``, preserving the original
                          behaviour.
        """
        if not (0 < alpha <= 1.0):
            raise ValueError(f"EMA alpha must be in the range (0, 1], got {alpha}")
        self.wrapped_powermeter = wrapped_powermeter
        self.alpha = alpha
        self.ema_values: Optional[List[float]] = None
        self._lock = threading.Lock()
        self._ema_interval = ema_interval

        if ema_interval > 0:
            self._first_reading_event = threading.Event()
            self._thread = threading.Thread(
                target=self._update_loop, daemon=True, name="ema-sampler"
            )
            self._thread.start()

    def _apply_ema(self, raw_values: List[float]) -> None:
        """Update ``self.ema_values`` in-place with one EMA step (caller holds lock)."""
        if self.ema_values is None:
            self.ema_values = list(raw_values)
        else:
            self.ema_values = [
                self.alpha * raw + (1.0 - self.alpha) * ema
                for raw, ema in zip(raw_values, self.ema_values)
            ]

    def _update_loop(self) -> None:
        """Background thread: sample the underlying powermeter every ema_interval seconds."""
        while True:
            start = time.monotonic()
            try:
                raw_values = self.wrapped_powermeter.get_powermeter_watts()
                with self._lock:
                    self._apply_ema(raw_values)
                self._first_reading_event.set()
            except Exception:
                pass
            elapsed = time.monotonic() - start
            sleep_time = max(0.0, self._ema_interval - elapsed)
            time.sleep(sleep_time)

    def wait_for_message(self, timeout=5):
        """Pass through to wrapped powermeter."""
        return self.wrapped_powermeter.wait_for_message(timeout)

    def get_powermeter_watts(self) -> List[float]:
        if self._ema_interval > 0:
            # Background-thread mode: wait for the first reading if needed,
            # then return the cached EMA without touching the underlying source.
            # Use a polling loop with a finite timeout so transient errors in
            # the background thread don't cause this method to block forever.
            while not self._first_reading_event.wait(timeout=1.0):
                pass
            with self._lock:
                return list(self.ema_values)  # type: ignore[arg-type]

        # Original synchronous mode: fetch and update EMA on every call.
        raw_values = self.wrapped_powermeter.get_powermeter_watts()
        with self._lock:
            self._apply_ema(raw_values)
        return list(self.ema_values)  # type: ignore[arg-type]
