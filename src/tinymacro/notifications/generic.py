from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tinymacro.notifications.base import LoopEvent, Notifier
from tinymacro.notifications.config import GenericWebhookSettings
from tinymacro.notifications.discord import build_context, render_template


class GenericWebhookNotifier(Notifier):
    """Posts a compact JSON body to any HTTP(S) endpoint."""

    name = "generic-webhook"

    def __init__(self, settings: GenericWebhookSettings, timeout: float = 15.0) -> None:
        self.settings = settings
        self.timeout = timeout

    def enabled_for(self, event: LoopEvent) -> bool:
        return self.settings.should_send(event.loop_index)

    def send(self, event: LoopEvent) -> None:
        self.settings.validate()
        context = build_context(event.loop_index, event.total_loops, event.speed, event.macro)
        text = render_template(self.settings.template, context)
        payload = {
            "text": text,
            "loop": event.loop_index,
            "total": context["total_loops"],
            "macro": event.macro.name,
            "speed": event.speed,
        }
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self.settings.url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "tiny-macro/0.2"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status >= 400:
                    raise RuntimeError(f"Webhook failed with HTTP {response.status}")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Webhook failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Webhook failed: {exc.reason}") from exc
