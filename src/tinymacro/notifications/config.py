from __future__ import annotations

from dataclasses import dataclass, field
import re

from tinymacro.notifications.discord import WebhookSettings, parse_color


@dataclass(slots=True)
class GenericWebhookSettings:
    """POSTs a small JSON payload to any URL on loop completion.

    The body is ``{"text": <rendered template>, "loop": .., "total": ..}`` which
    fits Slack/Mattermost-style incoming webhooks and generic endpoints alike.
    """

    enabled: bool = False
    url: str = ""
    every_loops: int = 1
    template: str = "Tiny Macro finished loop {iteration}/{total_loops} of {macro_name}"

    def validate(self) -> None:
        if self.every_loops < 1:
            raise ValueError("Generic webhook loop interval must be at least 1")
        if self.enabled and not re.match(r"^https?://", self.url.strip()):
            raise ValueError("Generic webhook URL must start with http:// or https://")

    def should_send(self, loop_index: int) -> bool:
        return self.enabled and bool(self.url) and loop_index > 0 and loop_index % self.every_loops == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "url": self.url,
            "every_loops": self.every_loops,
            "template": self.template,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "GenericWebhookSettings":
        defaults = cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            url=str(data.get("url", "")),
            every_loops=int(data.get("every_loops", 1)),
            template=str(data.get("template", defaults.template)),
        )


@dataclass(slots=True)
class TraySettings:
    """OS-native tray/toast notifications shown by the GUI."""

    enabled: bool = True
    notify_on_finish: bool = True
    every_loops: int = 0  # 0 = only on the final loop / playback end

    def should_send(self, loop_index: int, is_final: bool) -> bool:
        if not self.enabled or not self.notify_on_finish:
            return False
        if self.every_loops <= 0:
            return is_final
        return loop_index > 0 and loop_index % self.every_loops == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "notify_on_finish": self.notify_on_finish,
            "every_loops": self.every_loops,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "TraySettings":
        return cls(
            enabled=bool(data.get("enabled", True)),
            notify_on_finish=bool(data.get("notify_on_finish", True)),
            every_loops=int(data.get("every_loops", 0)),
        )


@dataclass(slots=True)
class NotificationSettings:
    """Aggregate of every notification channel Tiny Macro supports."""

    discord: WebhookSettings = field(default_factory=WebhookSettings)
    generic: GenericWebhookSettings = field(default_factory=GenericWebhookSettings)
    tray: TraySettings = field(default_factory=TraySettings)

    def validate(self) -> None:
        self.discord.validate()
        self.generic.validate()
        parse_color(self.discord.embed.color)

    def any_remote_enabled(self) -> bool:
        return self.discord.enabled or self.generic.enabled

    def to_dict(self) -> dict[str, object]:
        return {
            "discord": self.discord.to_dict(),
            "generic": self.generic.to_dict(),
            "tray": self.tray.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "NotificationSettings":
        discord_data = data.get("discord", {})
        generic_data = data.get("generic", {})
        tray_data = data.get("tray", {})
        settings = cls(
            discord=WebhookSettings.from_dict(discord_data if isinstance(discord_data, dict) else {}),
            generic=GenericWebhookSettings.from_dict(generic_data if isinstance(generic_data, dict) else {}),
            tray=TraySettings.from_dict(tray_data if isinstance(tray_data, dict) else {}),
        )
        settings.validate()
        return settings

    @classmethod
    def from_legacy_webhook(cls, webhook_data: dict[str, object]) -> "NotificationSettings":
        return cls(discord=WebhookSettings.from_dict(webhook_data))
