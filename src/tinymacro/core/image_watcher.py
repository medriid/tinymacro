"""Background watcher that fires image-trigger schedules when their target
image appears on screen.

Design notes:

* **Edge-triggered.** A schedule fires when its image transitions from *absent*
  to *present* — i.e. once per distinct appearance — so "loop count" means
  "number of times it sees the image", not "frames the image was visible".
* **Busy suppression.** The moment a trigger fires it is marked busy and stops
  being scanned, so a still-visible image cannot relaunch the macro while it is
  already playing. The host calls :meth:`rearm` when playback finishes.
* **Testable.** :meth:`poll_once` performs exactly one scan pass with an injected
  locator, so the fire/busy/re-arm/stop-after-N logic can be unit-tested without
  threads or a real screen. The thread loop is a thin wrapper over it.
"""
from __future__ import annotations

import base64
from collections.abc import Callable
import threading
import time

from tinymacro.core.scheduler import Schedule

# Callback invoked (on the watcher thread) when a trigger fires.
MatchCallback = Callable[[Schedule], None]
ScheduleProvider = Callable[[], list[Schedule]]


class ImageWatcher:
    def __init__(
        self,
        provider: ScheduleProvider,
        locator_factory: Callable[[], object],
        on_match: MatchCallback,
        *,
        base_interval_s: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._provider = provider
        self._locator_factory = locator_factory
        self._on_match = on_match
        self._base_interval_s = base_interval_s
        self._clock = clock
        self._sleeper = sleeper

        self._busy: set[int] = set()          # schedule ids currently playing
        self._seen: dict[int, bool] = {}      # last-scan presence, for edge detection
        self._last_scan: dict[int, float] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- host-facing state transitions ----------------------------------------
    def mark_busy(self, schedule: Schedule) -> None:
        with self._lock:
            self._busy.add(id(schedule))

    def rearm(self, schedule: Schedule, *, seen: bool) -> None:
        """Clear the busy flag after playback.

        ``seen=True`` records that the image was present when it fired, so the
        trigger will not fire again until the image disappears and reappears.
        ``seen=False`` allows an immediate re-detection (used when a fire had to
        be skipped because something else was playing).
        """
        with self._lock:
            self._busy.discard(id(schedule))
            self._seen[id(schedule)] = seen

    def _is_busy(self, schedule: Schedule) -> bool:
        with self._lock:
            return id(schedule) in self._busy

    # -- scanning -------------------------------------------------------------
    def poll_once(self, locator) -> list[Schedule]:
        """One scan pass. Returns the schedules that fired this pass."""
        fired: list[Schedule] = []
        now = self._clock()
        for schedule in self._provider():
            if not schedule.is_image or not schedule.can_fire():
                continue
            key = id(schedule)
            if key in self._busy:
                continue
            last = self._last_scan.get(key, float("-inf"))
            if now - last < schedule.poll_seconds:
                continue
            self._last_scan[key] = now
            present = self._detect(locator, schedule)
            rising = present and not self._seen.get(key, False)
            self._seen[key] = present
            if rising:
                # Suppress re-fire until the host re-arms this schedule.
                self.mark_busy(schedule)
                fired.append(schedule)
                self._on_match(schedule)
        return fired

    def _detect(self, locator, schedule: Schedule) -> bool:
        try:
            png = base64.b64decode(schedule.image_b64) if schedule.image_b64 else b""
        except Exception:  # noqa: BLE001
            return False
        if not png:
            return False
        try:
            return locator.locate(png, schedule.confidence, schedule.region) is not None
        except Exception:  # noqa: BLE001 - a failed capture is just "not present"
            return False

    # -- thread lifecycle -----------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="tiny-macro-imagewatch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        self._thread = None

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        try:
            locator = self._locator_factory()
        except Exception:  # noqa: BLE001 - no vision deps → nothing to do
            return
        try:
            while not self._stop.is_set():
                try:
                    self.poll_once(locator)
                except Exception:  # noqa: BLE001 - never let a scan kill the thread
                    pass
                self._sleeper(self._base_interval_s)
        finally:
            close = getattr(locator, "close", None)
            if callable(close):
                close()
