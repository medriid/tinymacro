from __future__ import annotations

from tinymacro.core.macro import Macro
from tinymacro.core.events import MacroEvent
from tinymacro.notifications.base import LoopEvent, NotificationDispatcher, Notifier
from tinymacro.notifications.config import GenericWebhookSettings, NotificationSettings, TraySettings


class RecordingNotifier(Notifier):
    name = "recorder"

    def __init__(self, accept: bool) -> None:
        self.accept = accept
        self.sent = 0

    def enabled_for(self, event: LoopEvent) -> bool:
        return self.accept

    def send(self, event: LoopEvent) -> None:
        self.sent += 1


class ExplodingNotifier(Notifier):
    name = "boom"

    def enabled_for(self, event: LoopEvent) -> bool:
        return True

    def send(self, event: LoopEvent) -> None:
        raise RuntimeError("kaboom")


def _event():
    macro = Macro(events=[MacroEvent(0, "key", "press", key="a")], name="m")
    return LoopEvent(1, 1, 1.0, macro, is_final=True)


def test_dispatcher_only_calls_enabled():
    yes = RecordingNotifier(True)
    no = RecordingNotifier(False)
    disp = NotificationDispatcher()
    disp.register(yes)
    disp.register(no)
    fired = disp.dispatch(_event())
    assert fired == ["recorder"]
    assert yes.sent == 1
    assert no.sent == 0


def test_dispatcher_isolates_failures():
    errors = []
    disp = NotificationDispatcher(on_error=lambda name, exc: errors.append(name))
    disp.register(ExplodingNotifier())
    ok = RecordingNotifier(True)
    disp.register(ok)
    disp.dispatch(_event())
    assert errors == ["boom"]
    assert ok.sent == 1


def test_generic_should_send_interval():
    g = GenericWebhookSettings(enabled=True, url="https://x.test/hook", every_loops=2)
    assert not g.should_send(1)
    assert g.should_send(2)


def test_tray_should_send_on_final_only_by_default():
    tray = TraySettings()
    assert tray.should_send(1, is_final=True)
    assert not tray.should_send(1, is_final=False)


def test_notifications_round_trip():
    n = NotificationSettings()
    n.generic.enabled = True
    n.generic.url = "https://x.test/hook"
    restored = NotificationSettings.from_dict(n.to_dict())
    assert restored.generic.url == "https://x.test/hook"
