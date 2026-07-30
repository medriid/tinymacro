"""Auto-updater logic: version comparison, release parsing, download, extract.

Network and the swap/relaunch handoff are not exercised here (they need a real
frozen build); everything testable off a live process is covered with fakes.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from tinymacro.core import updater
from tinymacro.core.updater import UpdateInfo, UpdaterError


# -- version handling ---------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [("v0.1.7", (0, 1, 7)), ("0.1.10", (0, 1, 10)), ("v1.2.3-rc1", (1, 2, 3)), ("v2", (2,))],
)
def test_parse_version(text, expected):
    assert updater.parse_version(text) == expected


def test_is_newer():
    assert updater.is_newer("v0.1.7", "0.1.6")
    assert updater.is_newer("0.1.10", "0.1.9")   # numeric, not lexicographic
    assert updater.is_newer("v1.0.0", "0.9.9")
    assert not updater.is_newer("v0.1.6", "0.1.6")
    assert not updater.is_newer("v0.1.5", "0.1.6")


# -- asset selection ----------------------------------------------------------
def test_asset_by_platform(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "win32")
    assert updater.current_asset_name() == "tiny-macro-windows.zip"
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    assert updater.current_asset_name() == "tiny-macro-macos.zip"
    monkeypatch.setattr(updater.sys, "platform", "linux")
    assert updater.current_asset_name() == "tiny-macro-linux.zip"
    monkeypatch.setattr(updater.sys, "platform", "sunos")
    assert updater.current_asset_name() is None


# -- check_for_update ---------------------------------------------------------
def _release_json(tag: str, asset: str = "tiny-macro-windows.zip", size: int = 123):
    return json.dumps({
        "tag_name": tag,
        "body": "Release notes here.",
        "assets": [
            {"name": "other.txt", "browser_download_url": "https://x/other.txt", "size": 1},
            {"name": asset, "browser_download_url": f"https://x/{asset}", "size": size},
        ],
    }).encode()


def test_check_returns_update_when_newer():
    info = updater.check_for_update(
        "0.1.6", asset_name="tiny-macro-windows.zip",
        fetch=lambda url: _release_json("v0.1.7"),
    )
    assert isinstance(info, UpdateInfo)
    assert info.version == "0.1.7" and info.tag == "v0.1.7"
    assert info.url == "https://x/tiny-macro-windows.zip"
    assert info.size == 123 and info.notes == "Release notes here."


def test_check_none_when_not_newer():
    info = updater.check_for_update(
        "0.1.7", asset_name="tiny-macro-windows.zip",
        fetch=lambda url: _release_json("v0.1.7"),
    )
    assert info is None


def test_check_none_when_asset_missing():
    info = updater.check_for_update(
        "0.1.6", asset_name="tiny-macro-linux.zip",
        fetch=lambda url: _release_json("v0.1.7", asset="tiny-macro-windows.zip"),
    )
    assert info is None


def test_check_raises_on_bad_json():
    with pytest.raises(UpdaterError):
        updater.check_for_update(
            "0.1.6", asset_name="tiny-macro-windows.zip",
            fetch=lambda url: b"not json",
        )


# -- redirect path (no API rate limit) ----------------------------------------
def test_check_via_redirect_builds_asset_url():
    info = updater.check_for_update(
        "0.1.6", asset_name="tiny-macro-linux.zip", resolve_tag=lambda: "v0.1.8",
    )
    assert isinstance(info, UpdateInfo)
    assert info.tag == "v0.1.8" and info.version == "0.1.8"
    assert info.url == "https://github.com/medriid/tinymacro/releases/download/v0.1.8/tiny-macro-linux.zip"
    assert info.notes == ""  # notes fetch is skipped on the injected path


def test_check_via_redirect_none_when_not_newer():
    assert updater.check_for_update(
        "0.1.8", asset_name="tiny-macro-linux.zip", resolve_tag=lambda: "v0.1.8",
    ) is None


def test_check_via_redirect_none_when_no_release():
    assert updater.check_for_update(
        "0.1.6", asset_name="tiny-macro-linux.zip", resolve_tag=lambda: None,
    ) is None


def test_latest_tag_parsed_from_redirect_url(monkeypatch):
    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def geturl(self): return "https://github.com/medriid/tinymacro/releases/tag/v0.1.9"
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: _Resp())
    assert updater.latest_tag_via_redirect() == "v0.1.9"


def test_rate_limit_error_is_friendly():
    def _boom(url):
        raise Exception("HTTP Error 403: rate limit exceeded")
    with pytest.raises(UpdaterError, match="rate-limiting"):
        updater.check_for_update("0.1.6", asset_name="tiny-macro-windows.zip", fetch=_boom)


# -- swap-and-relaunch helper -------------------------------------------------
def test_windows_helper_caps_robocopy_retries_and_keeps_macros(tmp_path):
    """The Windows helper must not use robocopy's default /R:1000000 (which retries
    a locked exe for ~347 days and looks like a hang), and must preserve macros/."""
    new_dir = tmp_path / "stage" / "extracted" / "tiny-macro-windows"
    new_dir.mkdir(parents=True)
    target = tmp_path / "app"
    exe = target / "tiny-macro-windows.exe"
    script = updater._write_windows_helper(4242, new_dir, target, exe)
    body = script.read_text()
    assert "/R:2" in body and "/W:2" in body        # bounded retries, not the default
    assert "/R:1000000" not in body
    assert "/XD" in body and "macros" in body        # user macros survive the mirror
    assert "robocopy" in body and str(target) in body


def test_posix_helper_waits_and_relaunches(tmp_path):
    new_dir = tmp_path / "stage" / "extracted" / "tiny-macro-linux"
    new_dir.mkdir(parents=True)
    target = tmp_path / "app"
    exe = target / "tiny-macro-linux"
    body = updater._write_posix_helper(4242, new_dir, target, exe).read_text()
    assert "kill -0 4242" in body      # waits for the app to exit
    assert str(exe) in body            # relaunches


# -- download -----------------------------------------------------------------
class _FakeResponse:
    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))}

    def read(self, n): return self._buf.read(n)
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_download_streams_with_progress(monkeypatch, tmp_path):
    payload = b"x" * 1000
    monkeypatch.setattr(updater, "_open", lambda url, timeout=30.0: _FakeResponse(payload))
    seen: list[tuple[int, int]] = []
    dest = updater.download("https://x/file.zip", tmp_path / "f.zip",
                            progress=lambda d, t: seen.append((d, t)), chunk_size=256)
    assert dest.read_bytes() == payload
    assert seen[-1] == (1000, 1000)  # finishes at 100%


def test_download_cancel_removes_partial(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "_open", lambda url, timeout=30.0: _FakeResponse(b"y" * 1000))
    dest = tmp_path / "f.zip"
    with pytest.raises(UpdaterError):
        updater.download("https://x/f.zip", dest, should_cancel=lambda: True, chunk_size=128)
    assert not dest.exists()


# -- extract ------------------------------------------------------------------
def test_extract_returns_top_folder(tmp_path):
    zip_path = tmp_path / "app.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("tiny-macro-windows/tiny-macro-windows.exe", b"MZ...")
        z.writestr("tiny-macro-windows/_internal/base_library.zip", b"data")
    out = updater.extract_zip(zip_path, tmp_path / "out")
    assert out.name == "tiny-macro-windows"
    assert (out / "tiny-macro-windows.exe").exists()
    assert (out / "_internal" / "base_library.zip").exists()


def test_extract_rejects_zip_slip(tmp_path):
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("../outside.txt", b"nope")
    with pytest.raises(UpdaterError):
        updater.extract_zip(zip_path, tmp_path / "out")
