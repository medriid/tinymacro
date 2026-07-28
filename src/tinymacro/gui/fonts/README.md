# Bundled UI fonts

Any `.ttf` / `.otf` dropped in this folder is registered with Qt at startup
(`theme.load_bundled_fonts`) and becomes available to the UI font stack.

Tiny Macro's stack (`theme.UI_FONT_STACK`) asks for **Inter** first, so shipping
Inter here makes every machine render the UI identically instead of falling back
to the OS default (Segoe UI on Windows, SF on macOS, Cantarell/Ubuntu on Linux).

To bundle Inter:

1. Download the desktop release from <https://rsms.me/inter/> (SIL Open Font
   License 1.1 — redistribution is allowed; keep the license file alongside).
2. Copy `Inter-Regular.ttf`, `Inter-Medium.ttf`, `Inter-SemiBold.ttf` and
   `Inter-Bold.ttf` (or `InterVariable.ttf`) into this folder.
3. Restart Tiny Macro — the UI picks it up automatically.

No font files are committed to the repo, so the app degrades gracefully to the
system stack when this folder is empty.
