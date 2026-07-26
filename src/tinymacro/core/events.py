from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# ``wait`` is a synthetic step that pauses playback for ``duration_ns`` (plus an
# optional random ``jitter_ns``) without emitting real input. It lets a macro
# carry explicit, editable pauses instead of only implicit timestamp gaps.
#
# ``image`` is a synthetic step (format v3) that, at playback time, searches the
# screen for an embedded target image and clicks it once found. It emits no input
# directly; the player synthesizes the click, so ``is_input`` is False for it.
# Beyond raw input and waits, macros can carry synthetic control/automation
# steps handled entirely by the player:
#   run     - execute a shell command or Python snippet (opt-in, off by default)
#   pixel   - block until a screen pixel matches a colour
#   window  - block until the active window title matches
#   if/else/endif, loop/endloop - block-structured conditionals and loops
EventKind = Literal[
    "key", "mouse", "wheel", "wait", "image",
    "run", "pixel", "window", "if", "else", "endif", "loop", "endloop",
    "screenshot",
]
EventAction = Literal[
    "press", "release", "move", "scroll", "delay", "click",
    "wait", "shell", "python", "branch", "repeat", "noop", "capture",
]

# Only these kinds produce real input that is emitted to a backend; everything
# else is interpreted by the player.
INPUT_KINDS = ("key", "mouse", "wheel")

# Bumped alongside macro.FORMAT_VERSION when the on-disk shape grows. New
# optional fields are only written when they differ from their defaults so that
# version-1 readers keep working and version-1 files load unchanged.
DEFAULT_DURATION_NS = 0
DEFAULT_JITTER_NS = 0

# Defaults for the ``image`` (click-image) step.
DEFAULT_CONFIDENCE = 0.85
DEFAULT_TIMEOUT_MS = 5000
# What to do when the target image is not found before the timeout elapses.
OnMissing = Literal["fail", "skip", "continue"]


@dataclass(frozen=True, slots=True)
class MacroEvent:
    """A normalized input event stored at a monotonic offset in nanoseconds.

    Fields added in format v2 (all optional, default to their v1 behaviour):

    * ``duration_ns`` -- for ``wait`` steps this is the base pause; for ``key``
      press events it may record how long the key was physically held.
    * ``jitter_ns`` -- an upper bound of extra random time added at playback so
      QA/testing playback is not perfectly metronomic.
    * ``note`` -- a free-form human label shown in the editor.
    """

    timestamp_ns: int
    kind: EventKind
    action: EventAction
    key: str | None = None
    button: str | None = None
    x: int | None = None
    y: int | None = None
    dx: int = 0
    dy: int = 0
    duration_ns: int = DEFAULT_DURATION_NS
    jitter_ns: int = DEFAULT_JITTER_NS
    note: str = ""
    # -- image (click-image) step fields, format v3 ---------------------------
    image_b64: str = ""
    confidence: float = 0.0
    timeout_ms: int = 0
    on_missing: OnMissing = "fail"
    click_button: str = "left"  # "none" waits for the image without clicking
    offset_x: int = 0
    offset_y: int = 0
    grayscale: bool = True
    region: tuple[int, int, int, int] | None = None
    # Generic string payload for run/pixel/window/loop steps: a command or Python
    # snippet, a target colour hex, a window-title substring, etc.
    command: str = ""
    # Repeat count for ``loop`` steps (0 = infinite until stopped).
    count: int = 0
    # Normalised (0..1) pointer coordinates relative to the docked window, used by
    # the Studio UI so macros replay at any resolution. Absent on classic macros.
    fx: float | None = None
    fy: float | None = None

    # -- construction helpers -------------------------------------------------
    @classmethod
    def wait(cls, timestamp_ns: int, duration_ns: int, jitter_ns: int = 0, note: str = "") -> "MacroEvent":
        return cls(
            timestamp_ns=timestamp_ns,
            kind="wait",
            action="delay",
            duration_ns=max(0, int(duration_ns)),
            jitter_ns=max(0, int(jitter_ns)),
            note=note,
        )

    @classmethod
    def image_click(
        cls,
        timestamp_ns: int,
        image_b64: str,
        *,
        confidence: float = DEFAULT_CONFIDENCE,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        on_missing: OnMissing = "fail",
        click_button: str = "left",
        offset_x: int = 0,
        offset_y: int = 0,
        grayscale: bool = True,
        region: tuple[int, int, int, int] | None = None,
        note: str = "",
    ) -> "MacroEvent":
        return cls(
            timestamp_ns=timestamp_ns,
            kind="image",
            action="click",
            image_b64=image_b64,
            confidence=float(confidence),
            timeout_ms=max(0, int(timeout_ms)),
            on_missing=on_missing,
            click_button=click_button,
            offset_x=int(offset_x),
            offset_y=int(offset_y),
            grayscale=bool(grayscale),
            region=tuple(region) if region else None,  # type: ignore[arg-type]
            note=note,
        )

    @classmethod
    def run_step(
        cls,
        timestamp_ns: int,
        command: str,
        *,
        mode: str = "shell",
        timeout_ms: int = 10_000,
        on_missing: OnMissing = "fail",
        note: str = "",
    ) -> "MacroEvent":
        return cls(
            timestamp_ns=timestamp_ns,
            kind="run",
            action="python" if mode == "python" else "shell",
            command=command,
            timeout_ms=max(0, int(timeout_ms)),
            on_missing=on_missing,
            note=note,
        )

    @classmethod
    def wait_pixel(
        cls,
        timestamp_ns: int,
        x: int,
        y: int,
        color: str,
        *,
        tolerance: float = 0.05,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        on_missing: OnMissing = "fail",
        note: str = "",
    ) -> "MacroEvent":
        return cls(
            timestamp_ns=timestamp_ns,
            kind="pixel",
            action="wait",
            x=int(x),
            y=int(y),
            command=color,
            confidence=float(tolerance),
            timeout_ms=max(0, int(timeout_ms)),
            on_missing=on_missing,
            note=note,
        )

    @classmethod
    def wait_window(
        cls,
        timestamp_ns: int,
        title: str,
        *,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        on_missing: OnMissing = "fail",
        note: str = "",
    ) -> "MacroEvent":
        return cls(
            timestamp_ns=timestamp_ns,
            kind="window",
            action="wait",
            command=title,
            timeout_ms=max(0, int(timeout_ms)),
            on_missing=on_missing,
            note=note,
        )

    @classmethod
    def if_image(
        cls,
        timestamp_ns: int,
        image_b64: str,
        *,
        confidence: float = DEFAULT_CONFIDENCE,
        timeout_ms: int = 1500,
        region: tuple[int, int, int, int] | None = None,
        grayscale: bool = True,
        note: str = "",
    ) -> "MacroEvent":
        """An ``if`` whose condition is 'the image is visible' (short timeout)."""
        return cls(
            timestamp_ns=timestamp_ns,
            kind="if",
            action="branch",
            image_b64=image_b64,
            confidence=float(confidence),
            timeout_ms=max(0, int(timeout_ms)),
            region=tuple(region) if region else None,  # type: ignore[arg-type]
            grayscale=bool(grayscale),
            note=note,
        )

    @classmethod
    def loop_start(cls, timestamp_ns: int, count: int, note: str = "") -> "MacroEvent":
        return cls(timestamp_ns=timestamp_ns, kind="loop", action="repeat", count=max(0, int(count)), note=note)

    @classmethod
    def control(cls, timestamp_ns: int, kind: str, note: str = "") -> "MacroEvent":
        """Build a bare control marker (else/endif/endloop)."""
        return cls(timestamp_ns=timestamp_ns, kind=kind, action="noop", note=note)  # type: ignore[arg-type]

    @classmethod
    def screenshot(cls, timestamp_ns: int, note: str = "") -> "MacroEvent":
        """A marker that captures the screen during playback (for the webhook)."""
        return cls(timestamp_ns=timestamp_ns, kind="screenshot", action="capture", note=note)

    @property
    def is_input(self) -> bool:
        """True when the event produces real input (i.e. should be emitted).

        Synthetic/control steps return False: the player interprets them rather
        than sending them straight to a backend.
        """
        return self.kind in INPUT_KINDS

    @property
    def is_control(self) -> bool:
        """True for block-structured control-flow markers."""
        return self.kind in ("if", "else", "endif", "loop", "endloop")

    def replace(self, **changes: Any) -> "MacroEvent":
        data = self.to_dict()
        data.update(changes)
        return MacroEvent.from_dict(data)

    def shifted(self, delta_ns: int) -> "MacroEvent":
        return self._with(timestamp_ns=max(0, self.timestamp_ns + delta_ns))

    def scaled(self, factor: float) -> "MacroEvent":
        return self._with(
            timestamp_ns=max(0, int(self.timestamp_ns * factor)),
            duration_ns=max(0, int(self.duration_ns * factor)),
            jitter_ns=max(0, int(self.jitter_ns * factor)),
        )

    def _with(self, **changes: Any) -> "MacroEvent":
        base = dict(
            timestamp_ns=self.timestamp_ns,
            kind=self.kind,
            action=self.action,
            key=self.key,
            button=self.button,
            x=self.x,
            y=self.y,
            dx=self.dx,
            dy=self.dy,
            duration_ns=self.duration_ns,
            jitter_ns=self.jitter_ns,
            note=self.note,
            image_b64=self.image_b64,
            confidence=self.confidence,
            timeout_ms=self.timeout_ms,
            on_missing=self.on_missing,
            click_button=self.click_button,
            offset_x=self.offset_x,
            offset_y=self.offset_y,
            grayscale=self.grayscale,
            region=self.region,
            command=self.command,
            count=self.count,
            fx=self.fx,
            fy=self.fy,
        )
        base.update(changes)
        return MacroEvent(**base)

    def describe(self) -> str:
        """Short, human-friendly one-line description used in the UI/log."""
        if self.kind == "wait":
            base = self.duration_ns / 1_000_000
            if self.jitter_ns:
                return f"wait {base:.0f}–{base + self.jitter_ns / 1_000_000:.0f} ms"
            return f"wait {base:.0f} ms"
        if self.kind == "image":
            verb = "find" if self.click_button == "none" else "click"
            return f"image {verb} · conf {self.confidence:.2f}"
        if self.kind == "run":
            snippet = self.command.splitlines()[0] if self.command else ""
            return f"run {self.action}: {snippet[:40]}"
        if self.kind == "pixel":
            return f"wait pixel {self.command} @ {self.x},{self.y}"
        if self.kind == "window":
            return f"wait window ~ {self.command!r}"
        if self.kind == "if":
            return "if image found"
        if self.kind == "else":
            return "else"
        if self.kind == "endif":
            return "end if"
        if self.kind == "loop":
            return f"loop ×{self.count}" if self.count else "loop (forever)"
        if self.kind == "endloop":
            return "end loop"
        if self.kind == "screenshot":
            return "screenshot point"
        if self.kind == "key":
            return f"key {self.action} {self.key}"
        if self.kind == "wheel":
            return f"wheel scroll {self.dx},{self.dy}"
        pos = "" if self.x is None else f" @ {self.x},{self.y}"
        if self.action == "move":
            return f"mouse move{pos}"
        return f"mouse {self.action} {self.button or ''}{pos}".rstrip()

    # -- serialization --------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "timestamp_ns": self.timestamp_ns,
            "kind": self.kind,
            "action": self.action,
            "key": self.key,
            "button": self.button,
            "x": self.x,
            "y": self.y,
            "dx": self.dx,
            "dy": self.dy,
        }
        # Only emit v2 fields when they carry information; keeps files that never
        # use the new features byte-for-byte v1-shaped.
        if self.duration_ns:
            data["duration_ns"] = self.duration_ns
        if self.jitter_ns:
            data["jitter_ns"] = self.jitter_ns
        if self.note:
            data["note"] = self.note
        # v3 image-step fields, likewise only emitted for image/if events so
        # other events stay byte-for-byte v1/v2-shaped.
        if self.kind in ("image", "if"):
            data["image_b64"] = self.image_b64
            data["confidence"] = self.confidence
            data["timeout_ms"] = self.timeout_ms
            data["on_missing"] = self.on_missing
            data["click_button"] = self.click_button
            if self.offset_x:
                data["offset_x"] = self.offset_x
            if self.offset_y:
                data["offset_y"] = self.offset_y
            if not self.grayscale:
                data["grayscale"] = self.grayscale
            if self.region:
                data["region"] = list(self.region)
        # v4 automation/control fields.
        if self.kind in ("run", "pixel", "window"):
            data["command"] = self.command
            data["timeout_ms"] = self.timeout_ms
            data["on_missing"] = self.on_missing
            if self.kind == "pixel":
                data["confidence"] = self.confidence
        if self.kind == "loop":
            data["count"] = self.count
        # Relative Studio coordinates, emitted only when captured.
        if self.fx is not None and self.fy is not None:
            data["fx"] = self.fx
            data["fy"] = self.fy
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MacroEvent":
        kind = data["kind"]
        action = data["action"]
        key = data.get("key")
        button = data.get("button")
        legacy_button = _legacy_mouse_button_from_key(key)
        if kind == "key" and legacy_button:
            kind = "mouse"
            button = legacy_button
            key = None
        raw_region = data.get("region")
        region = tuple(int(v) for v in raw_region) if raw_region else None
        return cls(
            timestamp_ns=int(data["timestamp_ns"]),
            kind=kind,
            action=action,
            key=key,
            button=button,
            x=data.get("x"),
            y=data.get("y"),
            dx=int(data.get("dx", 0)),
            dy=int(data.get("dy", 0)),
            duration_ns=int(data.get("duration_ns", DEFAULT_DURATION_NS)),
            jitter_ns=int(data.get("jitter_ns", DEFAULT_JITTER_NS)),
            note=str(data.get("note", "")),
            image_b64=str(data.get("image_b64", "")),
            confidence=float(data.get("confidence", 0.0)),
            timeout_ms=int(data.get("timeout_ms", 0)),
            on_missing=str(data.get("on_missing", "fail")),  # type: ignore[arg-type]
            click_button=str(data.get("click_button", "left")),
            offset_x=int(data.get("offset_x", 0)),
            offset_y=int(data.get("offset_y", 0)),
            grayscale=bool(data.get("grayscale", True)),
            region=region,  # type: ignore[arg-type]
            command=str(data.get("command", "")),
            count=int(data.get("count", 0)),
            fx=_opt_float(data.get("fx")),
            fy=_opt_float(data.get("fy")),
        )


def _opt_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _legacy_mouse_button_from_key(key: object) -> str | None:
    if not isinstance(key, str):
        return None
    compact = key.replace(" ", "").lower()
    mapping = {
        "('left','mouse')": "left",
        "('right','mouse')": "right",
        "('middle','mouse')": "middle",
        "['left','mouse']": "left",
        "['right','mouse']": "right",
        "['middle','mouse']": "middle",
        "btn_left": "left",
        "btn_right": "right",
        "btn_middle": "middle",
    }
    return mapping.get(compact)
