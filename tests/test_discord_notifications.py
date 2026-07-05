from __future__ import annotations

import json

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.core.settings import Settings
from tinymacro.notifications.discord import (
    WebhookSettings,
    build_context,
    build_embed,
    encode_multipart,
    parse_color,
)


def test_webhook_settings_roundtrip():
    settings = Settings()
    settings.webhook.enabled = True
    settings.webhook.url = "https://discord.com/api/webhooks/123/token"
    settings.webhook.every_loops = 3
    settings.webhook.embed.color = "#abcdef"

    loaded = Settings.from_dict(settings.to_dict())

    assert loaded.webhook.enabled
    assert loaded.webhook.every_loops == 3
    assert loaded.webhook.embed.color == "#abcdef"


def test_embed_uses_loop_keywords_and_screenshot_attachment():
    macro = Macro(events=[MacroEvent(0, "key", "press", key="a")], backend="fake", name="Demo")
    settings = WebhookSettings(
        enabled=True,
        url="https://discord.com/api/webhooks/123/token",
        every_loops=2,
    )
    context = build_context(4, 10, 2.0, macro)

    embed = build_embed(settings, context, attach_screenshot=True)

    assert embed["title"] == "Iteration: 4"
    assert embed["image"]["url"] == "attachment://loop-screenshot.png"
    assert embed["color"] == parse_color("#2f3136")
    assert any(field["name"] == "Backend" and field["value"] == "fake" for field in embed["fields"])


def test_multipart_payload_contains_payload_json_and_file():
    body, content_type = encode_multipart(
        fields={"payload_json": json.dumps({"embeds": [{"title": "ok"}]})},
        files={"files[0]": ("loop-screenshot.png", b"png", "image/png")},
    )

    assert content_type.startswith("multipart/form-data; boundary=")
    assert b'name="payload_json"' in body
    assert b'name="files[0]"; filename="loop-screenshot.png"' in body
    assert b"png" in body
