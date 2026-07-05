from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import mimetypes
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from tinymacro.core.macro import Macro


DISCORD_WEBHOOK_RE = re.compile(r"^https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w.-]+")


@dataclass(slots=True)
class WebhookEmbedSettings:
    title: str = "Iteration: {iteration}"
    description: str = "Macro: {macro_name}\nEvents: {event_count}\nSpeed: {speed}x"
    footer: str = "Finished at {time} | Loop {iteration}/{total_loops}"
    color: str = "#2f3136"
    image: str = "{screenshot}"
    fields: str = "Backend={backend}\nDuration={duration}s"
    username: str = "Tiny Macro"

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "description": self.description,
            "footer": self.footer,
            "color": self.color,
            "image": self.image,
            "fields": self.fields,
            "username": self.username,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "WebhookEmbedSettings":
        defaults = cls()
        return cls(
            title=str(data.get("title", defaults.title)),
            description=str(data.get("description", defaults.description)),
            footer=str(data.get("footer", defaults.footer)),
            color=str(data.get("color", defaults.color)),
            image=str(data.get("image", defaults.image)),
            fields=str(data.get("fields", defaults.fields)),
            username=str(data.get("username", defaults.username)),
        )


@dataclass(slots=True)
class WebhookSettings:
    enabled: bool = False
    url: str = ""
    every_loops: int = 1
    include_screenshot: bool = True
    embed: WebhookEmbedSettings = field(default_factory=WebhookEmbedSettings)

    def validate(self) -> None:
        if self.every_loops < 1:
            raise ValueError("Webhook loop interval must be at least 1")
        if self.enabled and not DISCORD_WEBHOOK_RE.match(self.url):
            raise ValueError("Discord webhook URL is invalid")
        parse_color(self.embed.color)

    def should_send(self, loop_index: int) -> bool:
        return self.enabled and bool(self.url) and loop_index > 0 and loop_index % self.every_loops == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "url": self.url,
            "every_loops": self.every_loops,
            "include_screenshot": self.include_screenshot,
            "embed": self.embed.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "WebhookSettings":
        embed_data = data.get("embed", {})
        settings = cls(
            enabled=bool(data.get("enabled", False)),
            url=str(data.get("url", "")),
            every_loops=int(data.get("every_loops", 1)),
            include_screenshot=bool(data.get("include_screenshot", True)),
            embed=WebhookEmbedSettings.from_dict(embed_data if isinstance(embed_data, dict) else {}),
        )
        settings.validate()
        return settings


def parse_color(value: str) -> int:
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    if not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        raise ValueError("Embed color must be a 6-digit hex value, like #2f3136")
    return int(text, 16)


def render_template(template: str, context: dict[str, object]) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def build_context(loop_index: int, total_loops: int, speed: float, macro: Macro, now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now().astimezone()
    return {
        "iteration": loop_index,
        "loop": loop_index,
        "loop_count": total_loops if total_loops else "infinite",
        "total_loops": total_loops if total_loops else "infinite",
        "time": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "date": now.strftime("%Y-%m-%d"),
        "macro_name": macro.name,
        "duration": f"{macro.duration_s:.3f}",
        "event_count": len(macro.events),
        "speed": f"{speed:g}",
        "backend": macro.backend,
        "screenshot": "screenshot",
    }


def build_embed(settings: WebhookSettings, context: dict[str, object], attach_screenshot: bool) -> dict[str, Any]:
    embed_settings = settings.embed
    embed: dict[str, Any] = {
        "title": render_template(embed_settings.title, context),
        "description": render_template(embed_settings.description, context),
        "color": parse_color(embed_settings.color),
        "footer": {"text": render_template(embed_settings.footer, context)},
    }
    fields = parse_fields(embed_settings.fields, context)
    if fields:
        embed["fields"] = fields
    if attach_screenshot and "{screenshot}" in embed_settings.image:
        embed["image"] = {"url": "attachment://loop-screenshot.png"}
    elif embed_settings.image.strip():
        image = render_template(embed_settings.image, context).strip()
        if image and image != "screenshot":
            embed["image"] = {"url": image}
    return {key: value for key, value in embed.items() if value not in ("", None)}


def parse_fields(fields_text: str, context: dict[str, object]) -> list[dict[str, object]]:
    fields: list[dict[str, object]] = []
    for line in fields_text.splitlines():
        if not line.strip() or "=" not in line:
            continue
        name, value = line.split("=", 1)
        fields.append(
            {
                "name": render_template(name.strip(), context)[:256],
                "value": render_template(value.strip(), context)[:1024] or "-",
                "inline": True,
            }
        )
    return fields[:25]


class DiscordWebhookClient:
    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def send_loop_update(
        self,
        settings: WebhookSettings,
        loop_index: int,
        total_loops: int,
        speed: float,
        macro: Macro,
        screenshot_png: bytes | None = None,
    ) -> None:
        settings.validate()
        context = build_context(loop_index, total_loops, speed, macro)
        attach_screenshot = bool(settings.include_screenshot and screenshot_png)
        payload: dict[str, Any] = {
            "username": settings.embed.username or "Tiny Macro",
            "embeds": [build_embed(settings, context, attach_screenshot)],
            "allowed_mentions": {"parse": []},
        }
        if attach_screenshot:
            payload["attachments"] = [{"id": 0, "filename": "loop-screenshot.png"}]
            body, content_type = encode_multipart(
                fields={"payload_json": json.dumps(payload)},
                files={"files[0]": ("loop-screenshot.png", screenshot_png or b"", "image/png")},
            )
        else:
            body = json.dumps(payload).encode("utf-8")
            content_type = "application/json"
        request = Request(settings.url, data=body, method="POST", headers={"Content-Type": content_type, "User-Agent": "tiny-macro/0.1"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status >= 400:
                    raise RuntimeError(f"Discord webhook failed with HTTP {response.status}")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Discord webhook failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Discord webhook failed: {exc.reason}") from exc


def encode_multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str | None]]) -> tuple[bytes, str]:
    boundary = f"----tiny-macro-{uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n'.encode())
        chunks.append(b"Content-Type: application/json\r\n\r\n" if name == "payload_json" else b"\r\n")
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")
    for name, (filename, data, content_type) in files.items():
        content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode())
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
