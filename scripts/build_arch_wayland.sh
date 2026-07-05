#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PACMAN_PACKAGES=(
  base-devel
  binutils
  python
  python-pip
  python-virtualenv
  libxkbcommon
  libxkbcommon-x11
  libxcb
  xcb-util-cursor
  wayland
)

say() {
  printf '\n==> %s\n' "$*"
}

fail() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 2
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing command '$1'. $2"
}

run_step() {
  local name="$1"
  shift
  say "$name"
  "$@"
}

say "Tiny Macro Arch/Wayland build preflight"
printf 'Project: %s\n' "$ROOT"

[[ "$(uname -s)" == "Linux" ]] || fail "This build must run on Linux. Run it on your friend's Arch machine."

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  printf 'Detected distro: %s\n' "${PRETTY_NAME:-unknown}"
  if [[ "${ID:-}" != "arch" && "${ID_LIKE:-}" != *"arch"* ]]; then
    printf 'WARNING: This does not look like Arch. Continuing only because pacman may still be available.\n' >&2
  fi
else
  printf 'WARNING: /etc/os-release not found; cannot identify distro.\n' >&2
fi

need_command pacman "Install Arch Linux or run this on an Arch-based distro."
need_command sudo "Install sudo or run package installation manually as root."

if [[ "${EUID}" -eq 0 ]]; then
  fail "Do not run this whole script as root. Run as a normal user with sudo access."
fi

say "Checking sudo access"
sudo -v || fail "This user needs sudo access to install/check packages."

say "Checking pacman database"
sudo pacman -Sy --needed --noconfirm archlinux-keyring >/dev/null || fail "Could not refresh Arch keyring. Check internet/pacman mirrors."

say "Checking required pacman packages"
missing_packages=()
for pkg in "${PACMAN_PACKAGES[@]}"; do
  if pacman -Qi "$pkg" >/dev/null 2>&1; then
    printf '  ok: %s\n' "$pkg"
  else
    printf '  missing: %s\n' "$pkg"
    missing_packages+=("$pkg")
  fi
done

if (( ${#missing_packages[@]} > 0 )); then
  say "Installing missing pacman packages"
  sudo pacman -S --needed --noconfirm "${missing_packages[@]}" || fail "pacman package install failed."
else
  say "All pacman packages are already installed"
fi

need_command python "Install the 'python' package with pacman."
python - <<'PY' || fail "Python 3.12+ is required for this project."
import sys
if sys.version_info < (3, 12):
    raise SystemExit(f"found Python {sys.version.split()[0]}")
print(f"Python {sys.version.split()[0]} ok")
PY

python -m ensurepip --version >/dev/null 2>&1 || printf 'WARNING: ensurepip is unavailable; pacman python-pip should still provide pip in the venv.\n' >&2
python -m venv --help >/dev/null 2>&1 || fail "python venv support is missing even after installing python."

say "Recreating build virtualenv"
rm -rf .venv-build
python -m venv .venv-build || fail "Could not create .venv-build."
source .venv-build/bin/activate

python -m pip --version >/dev/null 2>&1 || fail "pip is unavailable inside the virtualenv."
run_step "Upgrading Python build tools" python -m pip install --upgrade pip wheel setuptools
run_step "Installing Tiny Macro and PyInstaller into the virtualenv" python -m pip install -e ".[build]"

need_command pyinstaller "PyInstaller should have been installed in .venv-build/bin; activation may have failed."

say "Cleaning old build output"
rm -rf build dist/tiny-macro-wayland dist/README-WAYLAND.txt
mkdir -p dist

run_step "Building one-file Wayland executable" pyinstaller --clean --noconfirm packaging/tiny-macro-wayland.spec

[[ -f dist/tiny-macro-wayland ]] || fail "PyInstaller finished but dist/tiny-macro-wayland was not created."
chmod +x dist/tiny-macro-wayland

say "Checking produced binary"
file dist/tiny-macro-wayland || true
ldd dist/tiny-macro-wayland >/dev/null 2>&1 || printf 'WARNING: ldd could not inspect the binary; it may still run as a PyInstaller executable.\n' >&2

cat > dist/README-WAYLAND.txt <<'EOF'
Tiny Macro Wayland build

Run:
  ./tiny-macro-wayland --backend wayland

If the GUI opens but recording/playback does not work, Wayland permissions are
probably not configured yet.

Wayland input capture/playback uses:
  /dev/input/event*
  /dev/uinput

Recommended permission setup:
  sudo groupadd -f input
  sudo usermod -aG input "$USER"
  printf 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"\n' | sudo tee /etc/udev/rules.d/99-tiny-macro-uinput.rules
  sudo udevadm control --reload-rules
  sudo modprobe uinput

Then log out and back in so the group change applies.

Quick permission checks after logging back in:
  groups
  ls -l /dev/uinput
  ls -l /dev/input/event* | head

Avoid running the full GUI as root unless you are only doing a temporary test.
EOF

say "Build complete"
printf 'Binary: %s/dist/tiny-macro-wayland\n' "$ROOT"
printf 'Notes:  %s/dist/README-WAYLAND.txt\n' "$ROOT"
printf '\nSend both files to your friend if they only need to run it:\n'
printf '  dist/tiny-macro-wayland\n'
printf '  dist/README-WAYLAND.txt\n'
