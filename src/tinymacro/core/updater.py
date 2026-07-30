"""In-app auto-update: check GitHub Releases, download, swap the app, relaunch.

The app ships as a PyInstaller **onedir** folder (`<app>/` containing the
executable and `_internal/`). Updating means: fetch the latest release from the
GitHub API, compare its tag against :data:`tinymacro.__version__`, download this
platform's `.zip` asset with progress, extract it, then hand off to a tiny
detached helper that waits for us to quit, mirrors the new folder over the old
one **in place**, and relaunches the executable. Persisted settings/profiles live
in the user config dir (not the app folder), so the relaunched app comes back up
exactly as it was — just updated.

Only meaningful for frozen builds; :func:`updates_supported` is False when running
from source. All network I/O uses the standard library (no extra dependencies).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from tinymacro import __version__

GITHUB_REPO = "medriid/tinymacro"
API_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
_USER_AGENT = "TinyMacro-Updater"

# Per-platform release asset (the onedir folder, zipped) produced by release.yml.
_ASSET_BY_PLATFORM = {
    "win32": "tiny-macro-windows.zip",
    "darwin": "tiny-macro-macos.zip",
    "linux": "tiny-macro-linux.zip",
}

ProgressCallback = Callable[[int, int], None]  # (bytes_done, total_bytes)


class UpdaterError(RuntimeError):
    """A recoverable problem while checking for or applying an update."""


@dataclass(frozen=True)
class UpdateInfo:
    """A newer release than the running build."""

    version: str          # normalised, e.g. "0.1.7"
    tag: str              # raw tag, e.g. "v0.1.7"
    notes: str
    url: str              # asset download URL
    asset_name: str
    size: int             # bytes, 0 if the API didn't report it


# -- version handling ---------------------------------------------------------
def parse_version(text: str) -> tuple[int, ...]:
    """Turn a tag/version string into a comparable tuple of ints.

    ``"v0.1.7"`` -> ``(0, 1, 7)``. Non-numeric leading ``v`` and any trailing
    pre-release suffix (``-rc1``) are ignored; missing parts read as 0.
    """
    core = text.strip().lstrip("vV").split("-")[0].split("+")[0]
    parts: list[int] = []
    for chunk in core.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    """True if ``candidate`` is a strictly higher version than ``current``."""
    return parse_version(candidate) > parse_version(current)


# -- environment --------------------------------------------------------------
def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def current_asset_name() -> str | None:
    """The release asset filename for this OS, or None if unsupported."""
    return _ASSET_BY_PLATFORM.get(sys.platform)


def updates_supported() -> bool:
    """True only for a frozen build on a platform we publish binaries for."""
    return is_frozen() and current_asset_name() is not None


def app_dir() -> Path:
    """The onedir application folder (parent of the running executable)."""
    return Path(sys.executable).resolve().parent


# -- checking -----------------------------------------------------------------
def _open(url: str, timeout: float = 15.0):
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - fixed https host


def _asset_url(tag: str, asset_name: str) -> str:
    """The predictable public download URL for a release asset."""
    return f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{asset_name}"


def latest_tag_via_redirect() -> str | None:
    """Resolve the newest release tag from GitHub's *web* redirect.

    ``github.com/<repo>/releases/latest`` 302-redirects to the newest release's
    ``/releases/tag/<tag>`` page. Reading that redirect target costs nothing
    against the unauthenticated **api.github.com** limit of 60 requests/hour — the
    limit that was making update checks fail with HTTP 403. Returns the raw tag
    (e.g. ``"v0.1.8"``) or None if there's no published release.
    """
    request = urllib.request.Request(RELEASES_PAGE, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=15.0) as response:  # noqa: S310 - fixed https host
        final = response.geturl()  # after following the redirect; body left unread
    if "/tag/" not in final:
        return None
    tag = final.rstrip("/").rsplit("/", 1)[-1]
    return tag or None


def _release_notes(tag: str) -> str:
    """Best-effort release notes via the API; empty string if unavailable.

    This is the only call that touches the rate-limited API, and it's optional —
    a 403/timeout just means no notes, never a failed update check.
    """
    try:
        with _open(f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{tag}") as response:
            return str(json.loads(response.read()).get("body") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _friendly_check_error(exc: Exception) -> str:
    message = str(exc)
    if "403" in message or "rate limit" in message.lower():
        return "GitHub is rate-limiting update checks right now — please try again in a little while."
    return f"Could not check for updates: {message}"


def check_for_update(
    current_version: str = __version__,
    *,
    asset_name: str | None = None,
    fetch: Callable[[str], bytes] | None = None,
    resolve_tag: Callable[[], str | None] | None = None,
) -> UpdateInfo | None:
    """Return an :class:`UpdateInfo` if a newer release exists, else None.

    Production resolves the latest tag through :func:`latest_tag_via_redirect` (no
    API rate limit) and builds the asset URL from it. ``fetch`` (url -> GitHub API
    JSON bytes) selects the legacy API path, kept for tests; ``resolve_tag`` and
    ``asset_name`` are injectable too. Raises :class:`UpdaterError` on failure so
    callers can show a message; a successful check with nothing newer returns None.
    """
    wanted = asset_name or current_asset_name()
    if wanted is None:
        return None

    # Legacy/test path: caller hands us the GitHub API JSON directly.
    if fetch is not None:
        try:
            data = json.loads(fetch(API_LATEST_URL))
        except Exception as exc:  # noqa: BLE001
            raise UpdaterError(_friendly_check_error(exc)) from exc
        tag = str(data.get("tag_name") or "").strip()
        if not tag or not is_newer(tag, current_version):
            return None
        asset = next((a for a in data.get("assets", []) if a.get("name") == wanted), None)
        if asset is None or not asset.get("browser_download_url"):
            return None
        return UpdateInfo(
            version=".".join(str(p) for p in parse_version(tag)),
            tag=tag,
            notes=str(data.get("body") or "").strip(),
            url=str(asset["browser_download_url"]),
            asset_name=wanted,
            size=int(asset.get("size") or 0),
        )

    # Production path: resolve the tag via the web redirect (not API-rate-limited).
    try:
        tag = (resolve_tag or latest_tag_via_redirect)()
    except Exception as exc:  # noqa: BLE001
        raise UpdaterError(_friendly_check_error(exc)) from exc
    if not tag or not is_newer(tag, current_version):
        return None
    return UpdateInfo(
        version=".".join(str(p) for p in parse_version(tag)),
        tag=tag,
        # Skip the (rate-limited) notes fetch when a tag resolver is injected — the
        # tests use that path and must not touch the network.
        notes=_release_notes(tag) if resolve_tag is None else "",
        url=_asset_url(tag, wanted),
        asset_name=wanted,
        size=0,  # learned from Content-Length when the download starts
    )


# -- downloading --------------------------------------------------------------
def download(
    url: str,
    dest: Path,
    progress: ProgressCallback | None = None,
    *,
    chunk_size: int = 262144,
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    """Stream ``url`` to ``dest``, reporting progress. Returns ``dest``.

    ``should_cancel`` is polled between chunks; if it returns True the partial
    file is removed and :class:`UpdaterError` is raised.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _open(url, timeout=30.0) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(dest, "wb") as out:
                while True:
                    if should_cancel is not None and should_cancel():
                        raise UpdaterError("Download cancelled")
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total)
    except UpdaterError:
        dest.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise UpdaterError(f"Download failed: {exc}") from exc
    return dest


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    """Extract ``zip_path`` into ``dest_dir`` and return the extracted app folder.

    The release zips contain a single top-level folder (the onedir app); we return
    that folder. Falls back to ``dest_dir`` if the archive is flat.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        _validate_zip_members(archive, dest_dir)
        archive.extractall(dest_dir)
    tops = {n.split("/", 1)[0] for n in names if n.strip()}
    if len(tops) == 1:
        only = next(iter(tops))
        candidate = dest_dir / only
        if candidate.is_dir():
            return candidate
    return dest_dir


def _validate_zip_members(archive: zipfile.ZipFile, dest_dir: Path) -> None:
    root = dest_dir.resolve()
    for member in archive.infolist():
        target = (dest_dir / member.filename).resolve()
        if not (target == root or root in target.parents):
            raise UpdaterError(f"Unsafe update archive entry: {member.filename}")


# -- applying (swap folder + relaunch via a detached helper) ------------------
def apply_update_and_relaunch(new_app_dir: Path, target_dir: Path | None = None,
                              exe_path: Path | None = None) -> None:
    """Replace the running app folder with ``new_app_dir`` and relaunch it.

    Spawns a detached helper that waits for this process to exit (so the locked
    executable is released), mirrors the new folder over ``target_dir`` in place,
    relaunches the executable, and cleans up. This function then quits the app —
    it does not return normally.
    """
    target = Path(target_dir) if target_dir else app_dir()
    exe = Path(exe_path) if exe_path else Path(sys.executable)
    pid = os.getpid()
    if sys.platform == "win32":
        script = _write_windows_helper(pid, Path(new_app_dir), target, exe)
        subprocess.Popen(  # noqa: S603 - our own generated script
            ["cmd", "/c", str(script)],
            creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            close_fds=True,
        )
    else:
        script = _write_posix_helper(pid, Path(new_app_dir), target, exe)
        subprocess.Popen(["/bin/sh", str(script)], start_new_session=True, close_fds=True)  # noqa: S603
    # Leave promptly so the helper can take over the (now-unlocked) folder.
    os._exit(0)


def _write_windows_helper(pid: int, new_dir: Path, target: Path, exe: Path) -> Path:
    script = Path(tempfile.gettempdir()) / f"tinymacro_update_{pid}.cmd"
    stage_root = _stage_root_for(new_dir)
    # Wait for our PID to disappear, mirror the new build over the old folder,
    # relaunch, then delete the staged copy and this script.
    body = f"""@echo off
setlocal
:waitloop
tasklist /FI "PID eq {pid}" 2>NUL | find "{pid}" >NUL
if not errorlevel 1 (
    ping -n 2 127.0.0.1 >NUL
    goto waitloop
)
robocopy "{new_dir}" "{target}" /MIR /NFL /NDL /NJH /NJS /NP >NUL
start "" "{exe}"
rmdir /S /Q "{stage_root}" >NUL 2>&1
del "%~f0" >NUL 2>&1
"""
    script.write_text(body, encoding="utf-8")
    return script


def _write_posix_helper(pid: int, new_dir: Path, target: Path, exe: Path) -> Path:
    script = Path(tempfile.gettempdir()) / f"tinymacro_update_{pid}.sh"
    stage_root = _stage_root_for(new_dir)
    body = f"""#!/bin/sh
while kill -0 {pid} 2>/dev/null; do sleep 0.3; done
# Mirror the new build over the old folder in place.
rm -rf "{target}.old" 2>/dev/null
cp -a "{target}" "{target}.old" 2>/dev/null
find "{target}" -mindepth 1 -maxdepth 1 -exec rm -rf {{}} + 2>/dev/null
cp -a "{new_dir}/." "{target}/" 2>/dev/null
chmod +x "{exe}" 2>/dev/null
rm -rf "{target}.old" "{stage_root}" 2>/dev/null
"{exe}" &
rm -f "$0" 2>/dev/null
"""
    script.write_text(body, encoding="utf-8")
    return script


def _stage_root_for(new_dir: Path) -> Path:
    # _DownloadWorker extracts to <stage>/extracted/<app-folder>; remove <stage>
    # after a successful relaunch so the downloaded zip does not linger in temp.
    if new_dir.parent.name == "extracted":
        return new_dir.parent.parent
    return new_dir
