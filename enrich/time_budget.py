"""Wall-clock budget helper used by every phase's main loop, so a slow
upstream (a hung registry, a stalled Postgres connection) can only ever
delay a phase, never make it run indefinitely into the next day's cycle."""
import time


class TimeBudget:
    def __init__(self, seconds):
        self._deadline = time.monotonic() + seconds

    @property
    def expired(self):
        return time.monotonic() >= self._deadline

    @property
    def remaining(self):
        return max(0.0, self._deadline - time.monotonic())
