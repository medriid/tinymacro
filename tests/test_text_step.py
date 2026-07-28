from __future__ import annotations

from tinymacro.backends.fake import FakeBackend
from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player


class _Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(0, int(seconds * 1_000_000_000))


def test_text_step_round_trip():
    ev = MacroEvent.text_step(0, "Hello, world!", cps=15)
    assert ev.kind == "text" and ev.action == "type"
    assert ev.command == "Hello, world!" and ev.count == 15
    restored = MacroEvent.from_dict(ev.to_dict())
    assert restored.command == "Hello, world!" and restored.count == 15
    assert 'type "Hello, world!"' in restored.describe()


def test_player_types_instant():
    backend = FakeBackend()
    macro = Macro(events=[MacroEvent.text_step(0, "hi there")])
    player = Player(backend, sleeper=lambda s: None)
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    player.start(macro, loop_count=1, blocking=True)
    assert backend.typed == ["hi there"]  # cps 0 → one shot


def test_player_types_paced_per_char():
    backend = FakeBackend()
    clock = _Clock()
    macro = Macro(events=[MacroEvent.text_step(0, "abc", cps=10)])
    player = Player(backend, clock_ns=clock, sleeper=clock.sleep)
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    player.start(macro, loop_count=1, blocking=True)
    assert backend.typed == ["a", "b", "c"]  # paced → char by char
    # 3 chars at 10/s = ~0.2s of inter-char waits after the first two.
    assert clock.now >= 200_000_000


def test_player_skips_text_when_backend_cannot_type():
    class _NoType(FakeBackend):
        def type_text(self, text):
            raise NotImplementedError

    backend = _NoType()
    macro = Macro(events=[MacroEvent.text_step(0, "x"), MacroEvent(1_000_000, "key", "press", key="a")])
    player = Player(backend, sleeper=lambda s: None)
    player.on_error = lambda exc: (_ for _ in ()).throw(exc)
    player.start(macro, loop_count=1, blocking=True)
    # Text step skipped gracefully; the following key still emitted.
    assert [e.key for e in backend.emitted] == ["a"]
