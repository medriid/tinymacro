from __future__ import annotations

import pytest

from tinymacro.core.settings import Settings


def test_new_fields_round_trip():
    s = Settings()
    s.theme_preset = "amber"
    s.accent_color = "#3b82f6"
    s.compact_mode = False
    s.move_min_interval_ms = 8
    s.humanize_jitter_ms = 12
    s.notifications.generic.enabled = True
    s.notifications.generic.url = "https://example.com/hook"
    loaded = Settings.from_dict(s.to_dict())
    assert loaded.theme_preset == "amber"
    assert loaded.accent_color == "#3b82f6"
    assert loaded.compact_mode is False
    assert loaded.move_min_interval_ms == 8
    assert loaded.notifications.generic.url == "https://example.com/hook"


def test_webhook_alias_still_works():
    s = Settings()
    s.webhook.enabled = True
    s.webhook.url = "https://discord.com/api/webhooks/123/token"
    s.webhook.every_loops = 4
    loaded = Settings.from_dict(s.to_dict())
    assert loaded.webhook.enabled
    assert loaded.webhook.every_loops == 4


def test_migrates_legacy_bare_webhook():
    v1 = {"theme": "dark", "webhook": {"enabled": False, "url": "", "every_loops": 5}}
    migrated = Settings.from_dict(v1)
    assert migrated.notifications.discord.every_loops == 5
    assert migrated.webhook.every_loops == 5


def test_invalid_accent_rejected():
    s = Settings()
    s.accent_color = "not-a-color"
    with pytest.raises(ValueError):
        s.validate()


def test_invalid_preset_rejected():
    s = Settings()
    s.theme_preset = "rainbow"
    with pytest.raises(ValueError):
        s.validate()
