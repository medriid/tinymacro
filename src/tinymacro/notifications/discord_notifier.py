from __future__ import annotations

from tinymacro.notifications.base import LoopEvent, Notifier
from tinymacro.notifications.discord import DiscordWebhookClient, WebhookSettings


class DiscordNotifier(Notifier):
    """Adapts the existing DiscordWebhookClient to the Notifier interface."""

    name = "discord"

    def __init__(self, settings: WebhookSettings, client: DiscordWebhookClient | None = None) -> None:
        self.settings = settings
        self.client = client or DiscordWebhookClient()

    def enabled_for(self, event: LoopEvent) -> bool:
        return self.settings.should_send(event.loop_index)

    def send(self, event: LoopEvent) -> None:
        screenshot = event.screenshot_png if self.settings.include_screenshot else None
        self.client.send_loop_update(
            self.settings,
            event.loop_index,
            event.total_loops,
            event.speed,
            event.macro,
            screenshot,
        )
