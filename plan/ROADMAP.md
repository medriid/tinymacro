# Tiny Macro — Roadmap & Working Notes

Living plan for picking the project back up on a fresh machine: what exists, what
to build next, what to improve, and how to develop/build/release.

---

## Unreleased (on `master` since v0.1.5)

- **macOS backend** — `backends/macos.py` (`MacBackend`) drives capture/playback
  through Quartz via `pynput`. Shared pynput logic now lives in
  `backends/_pynput.py` (`PynputBackend`); X11 is a thin subclass. Factory
  auto-selects it on `darwin`; needs Accessibility + Input Monitoring grants.
- **Studio taskbar icon fix** — an explicit Windows AppUserModelID plus a
  re-assert of the window icon on the native handle in `showEvent` (covers
  Studio's maximized-first show, which previously dropped the taskbar icon).
- **CI/CD** — `.github/workflows/ci.yml` runs the suite on Win/macOS/Linux;
  `release.yml` builds all three binaries on a `v*` tag and attaches them to a
  GitHub Release. Added `packaging/tiny-macro-macos.spec`; brought the Linux spec
  up to parity (sounds/fonts/QtMultimedia). Added `LICENSE`; pro README rewrite.

## Current state (shipped in v0.1.5)

- **Two UI variants** (both frameless, custom title bar/icons, animations):
  - **Classic** — compact toolbar UI, absolute-coordinate macros (`.tmacc`).
  - **Studio** — 16:9 frame that position-attaches a selected window into a
    **see-through dock aperture**; records **window-relative** coordinates so
    macros are resolution-independent and shareable (`.tmacd`). Single
    **Dock/Undock** button, overview + logs (left), options (right),
    Preferences, and the same global hotkeys as Classic.
- **Playback engine**: deterministic, absolute-time-anchored scheduling;
  captures leading/trailing idle as wait steps so loop time includes idle and
  loops don't speed up. **Sub-millisecond precise timing** — each event's
  deadline is anchored to a per-loop start and the final slice is busy-spun on a
  high-res clock (with the Windows 1ms timer via `timeBeginPeriod`), so every
  loop replays identically (measured stdev ~0.005 ms across loops) and small
  inter-event pauses are honored. The control-flow interpreter advances a running
  target clock so `if/else/endif` + `loop` timing doesn't drift either.
  **Fresh loops**: an optional (default-on) settling gap between iterations and a
  release of any keys/buttons left held, so each loop starts clean.
- **Playlists**: chain several macros to play back-to-back (`core/playlist.py` +
  `PlaylistDialog`, `.tmplist` files) with per-item repeat and an inter-macro gap;
  variant-scoped (classic/Studio). Surfaced in both UIs; the stitched macro runs
  through the normal player, so loop/speed/notifications apply to the whole set.
- **Visual flow builder + image-gated playlists** (`gui/flow_builder.py`): a node
  canvas that wires macros into a Start→…→end flow, each with a repeat and an
  optional **image gate** (snip a load-screen; the macro waits for it before it
  plays). Exports **portable `.tmbundle` bundles** (`core/bundle.py`) that embed
  the playlist + every macro + gate image, so they run on any machine/OS —
  **optionally encrypted** (password or "open") via the build-only `securepack`
  (Argon2id + AES-256-GCM).
- **Text-type step**: `MacroEvent.text_step` types a string at a set chars/sec
  (Windows unicode injection); inserted from the editor's "Type Text…".
- **Live debugging editor**: the Macro Editor is non-modal and can stay open while
  a macro plays. It highlights the executing step in the event tree and the
  timeline (a green playhead), and supports **breakpoints** (right-click → Toggle
  Breakpoint) that auto-pause playback at a step (amber highlight) with Resume.
  Edits apply to the host live; the timeline gained a `set_playing` marker.
- **DPI-correct docking**: the Studio aperture is reported in physical pixels
  (`dock.scale_to_physical`), so on a scaled display (e.g. 125%) the docked window
  fills and centres correctly and recorded clicks land right — Studio macros are
  truly resolution-independent. Studio now opens **maximized**; undock restores the
  target window to where it was (Preferences toggle).
- **Window chrome**: the title-bar maximize button swaps between a full-window and
  a restore (two-window) glyph to mirror the window state, in both UIs.
- **Cinematic onboarding**: a first-run guided tour (`gui/onboarding.py`) blurs the
  window and spotlights each feature one at a time with a **crisp white, pixel-style
  card** (monospace, square reticle with corner brackets), Back / Next / Skip (arrow
  keys / Esc). It tracks the window wherever it is/resizes, runs once
  (`onboarding_seen`) in whichever UI launches first, and is replayable from
  **Preferences → Show Introduction** in both UIs.
- **Studio dock aperture**: aspect lock (Free / 16:9 / Match-window) that
  letterboxes the aperture; the choice persists.
- **Themed colour picker** (`gui/color_picker.py`): a custom SV-field + hue-bar +
  hex/RGB + preset/recent picker that inherits the app theme, used everywhere
  (theme editor, accent) in place of the native dialog.
- **UI polish**: onboarding fills the whole screen (app window drawn blurred in
  place) and adopts the app theme (rounded card, UI font, accent ring); transport
  is Record / Play (Play·Stop toggle) / Pause in both UIs; per-button icon colours
  are themeable; the always-on-top pin keeps the normal button look with a
  fill-when-pinned icon; Studio keeps its taskbar icon; the redundant Classic
  title label is gone. **Docs**: Preferences → Docs opens a categorised in-app
  help window (`gui/docs_dialog.py`; sections scaffolded, content TBD).
- **Interaction feedback**: transport buttons carry built-in colours (record
  orange, play green, stop red, pause blue) via `theme_pack.DEFAULT_BUTTON_COLORS`
  — custom themes' `button_colors` still override. Buttons glow/ring on hover and
  press (`anim.AnimatedToolButton`, `anim.InteractionFx`) and play subtle
  hover/click sounds (`gui/sounds.py`, throttled, Preferences → Interface sounds).
  Studio's Record/Play/Pause share one icon-only row. Fonts: the stack prefers
  crafted faces over OS defaults and `theme.load_bundled_fonts()` registers any
  typeface dropped in `gui/fonts/` so the UI can look identical on every machine.
- **Recording fidelity**: only the *full* global-hotkey chord is swallowed, so
  plain letters used in a chord (c/r/s/p/m) and lone modifiers (Ctrl for
  Ctrl+C in the target app) record correctly.
- **Screenshot event**: a while-recording hotkey drops a "screenshot point"; at
  playback the screen is captured at that exact instant and that image is what
  the Discord webhook sends (works in both UIs).
- **Step types**: key/mouse/wheel, wait (fixed/jitter), **click-image**,
  **wait-pixel**, **wait-window**, **run shell/Python** (opt-in, off by default).
- **Windows backend**: low-level hooks; **scan-code injection** (works in games
  like Roblox); focus-restore before keyboard playback; window enumerate/move for
  docking. Wayland (evdev/uinput) + X11 (pynput) backends also present.
- **Vision** (optional `[vision]` extra: OpenCV + mss): template match + pixel read.
- **Extras**: macro library, scheduler (interval/daily/once/**image-trigger**),
  notifications (Discord + generic webhook + tray), settings profiles, autosave/
  crash recovery, logging + log viewer, graphical timeline, editor power-ups.
- **Formats**: `.tmacc` (classic), `.tmacd` (Studio/docked). Legacy `.tmacro`
  still loads. On-disk `format` field is the source of truth, not the extension.

---

## Features to add next

0. **Install manager + auto-update** (big; see "Distribution" below) — ship an
   installer and a self-updater so users download once and always get the latest
   app, and their macros sync/update whenever they connect.
1. ~~**Studio parity with Classic tools**~~ — **done**: Library, Scheduler, Log
   Viewer, Validate, Export (and now Playlist) are in the Studio side panel.
2. ~~**Region-capture tool**~~ — **done**: `gui/region_capture.py` drag-to-snip
   feeds click-image and wait-pixel steps.
3. ~~**Live current-step highlight** during playback + non-modal editor~~ —
   **done**: the editor is non-modal (live two-way sync, `show()` not `exec()`),
   the executing step is highlighted in the tree and timeline (green playhead), and
   **breakpoints** (right-click → Toggle Breakpoint) auto-pause playback (amber
   highlight) with Resume in both UIs. Player hooks: `on_step` / `on_breakpoint` /
   `breakpoints`.
4. ~~**Undock leaves the target where it is**~~ — **done**: the target window's
   client rect is captured at dock time and restored on undock (toggle in
   Preferences, default on).
5. ~~**Studio: aspect-ratio lock options**~~ — **done**: a Studio selector locks
   the dock aperture to Free / 16:9 / Match-window (the docked target's ratio);
   `DockArea` letterboxes its inner frame and the choice persists.
6. ~~**Macro chaining / playlists in the UI**~~ — **done**: `core/playlist.py` +
   `PlaylistDialog` (`.tmplist`), surfaced in both UIs.
7. **GIF/preview export** of a macro (was deferred; needs Pillow/imageio).
8. **First-run onboarding** — **done** (the guided tour); bundled sample macros
   still TODO. `gui/onboarding.py` is a cinematic blurred-spotlight walk-through
   (animated spotlight + card, Back/Next/Skip, arrow keys/Esc) that runs once on
   first launch (`onboarding_seen`) and can be replayed from Guided Tour in both
   UIs.

## Improvements / tech debt

- **Shared controller refactor**: Classic and Studio each drive their own
  Recorder/Player glue. Extract a `MacroController` so both are thin views (was
  deferred to limit risk). Would de-duplicate record/play/save wiring.
- **Timeline in Studio**: reuse `gui/timeline.py` in the Studio overview.
- **Dock tracker**: currently a 150 ms `QTimer`; consider WinEvent hooks for
  smoother/instant tracking and less idle CPU.
- **Wayland docking**: enumerate/move windows isn't supported on Wayland; Studio
  degrades to a message. Investigate portal-based approaches if needed.
- **Test the frameless chrome interactions** (drag/resize/min/max) — currently
  only construction is smoke-tested.
- **Packaging size**: binaries are ~90–130 MB (PyQt6 + OpenCV). Consider trimming
  unused Qt plugins / opencv modules if size matters.

## Known limitations

- Window docking + enumeration is **Windows-only**.
- Kernel-level anti-cheat games can block all synthetic input (by design; not a bug).
- Elevated target apps require running Tiny Macro **as administrator**.

---

## Backlog: features & improvements

A living wishlist, grouped by area. Rough size/impact tags: (S)mall, (M)edium,
(L)arge; ★ = high user value.

### Recording & playback engine
- ~~★ **Text-type step (M)**~~ — **done**: `MacroEvent.text_step` types a whole
  string at a configurable chars/sec (Windows `KEYEVENTF_UNICODE`, layout-safe;
  backends without unicode injection skip it). Insert via the editor's "Type Text…".
- ★ **Window-relative recording for Classic (M)** — optionally anchor coordinates
  to the *active/target window* (not just the Studio dock), so classic macros
  survive the target window moving. Reuse the `dock.py` relative-coords engine.
- **Macro variables / parameters (L)** — named values prompted at run time (or
  passed via CLI/URL), referenced in text-type, `run`, wait, and image steps.
  Enables templated, reusable macros.
- **Sub-macros / "call macro" step (M)** — invoke another `.tmacc/.tmacd` as a
  step; compose large flows from small pieces (builds on `Macro.chain`).
- **Clipboard steps (S)** — set/get the clipboard as a step (paste dynamic text,
  capture a value into a variable).
- **Humanized mouse paths (M)** — optional Bézier/‑jitter interpolation between
  click points on playback for natural motion (QA realism, not evasion).
- **Per-step / ramped speed (M)** — a speed multiplier per step or a ramp over the
  macro, beyond the single global speed.
- **Manual pause/step hotkeys during playback (S)** — global keys to pause, resume
  and single-step a running macro (pairs with breakpoints).
- **Conditional loops UI (M)** — surface "repeat while image/pixel/window" in the
  editor (interpreter already supports blocks).
- **Mouse-move thinning presets (S)** — one-click "smooth / balanced / tiny file"
  capture profiles over the existing `move_min_interval_ms`.

### Editor & debugging
- ★ **Find & replace across events (M)** — remap a key/button everywhere, shift all
  timings, bulk-edit a selection.
- **Run-to-cursor / step-over (M)** — richer debugging on top of breakpoints.
- **Drag-to-retime on the timeline (M)** — move an event in time by dragging its
  mark; snap to neighbours.
- **Record-append (M)** — resume recording *into* an existing macro at a chosen
  point instead of only replacing.
- **Command palette (S)** — fuzzy action launcher (Ctrl-K) for editor + app.
- **Macro diff (M)** — compare two macros (added/removed/retimed steps).

### Vision & automation
- ★ **OCR step (L)** — wait for / read on-screen text (Tesseract, optional extra);
  feed a variable or gate a branch.
- **Multi-image match (S)** — "any of these N images" for one step.
- **Region capture reuse + preview (S)** — live confidence preview when tuning a
  click-image step; cache the search region.
- **Colour-condition builder (S)** — pick a pixel and tolerance visually for
  wait-pixel / `if colour`.

### Themes & UI
- **Theme gallery / workshop (L)** — browse, preview and one-click install themes
  (phase 5 of the theming plan; ties into the website).
- **Auto light/dark (S)** — follow the OS, or switch by time of day.
- **Mini-player mode (M)** — a tiny always-on-top floating transport (record/play/
  stop) for when the main window is in the way.
- **Tray quick-launch (S)** — run favourite macros straight from the tray menu.
- **In-app docs content (M)** — fill the `DocsDialog` categories with real
  write-ups + screenshots (scaffold already shipped).
- **Localization / i18n (L)** — externalise strings; community translations.
- **Accessibility pass (M)** — high-contrast preset, focus order, screen-reader
  labels, full keyboard operability audit.
- **Optional sound cues (S)** — subtle audio on record start/stop, loop complete.

### Integrations & extensibility
- ★ **Local HTTP trigger API (M)** — a tiny opt-in local server to start/stop
  macros from other tools (Stream Deck, scripts, hotkey apps).
- **Plugin system for step types (L)** — register custom steps (Python entry
  points) so the community can extend the engine.
- **Incoming webhook triggers (M)** — fire a macro when an endpoint is hit (mirror
  of the outgoing notifications).
- **CLI expansion (S)** — `tinymacro run/list/validate/convert` headless; good for
  automation and CI of macros.

### Platform & distribution
- ★ **Installer + auto-updater (L)** — see the Distribution section below (item 0).
- **macOS backend (L)** — capture/replay via Quartz `CGEvent`; docking via
  Accessibility APIs. Rounds out the cross-platform story.
- **Portable mode (S)** — keep settings/library/themes next to the executable.
- **Settings + library + theme cloud sync (L)** — part of the accounts/workshop
  plan; pull on connect.
- **Binary slimming (M)** — trim unused Qt plugins / opencv modules to cut the
  ~90–130 MB size and speed up startup.

### Reliability, safety & performance
- **Opt-in crash reporting (M)** — capture tracebacks (with consent) to fix issues
  faster.
- **Per-macro permissions (M)** — a macro declares which capabilities it needs
  (input, `run`, network); prompt on first play, especially for shared macros.
- **Signed / integrity-checked shared macros (M)** — detect tampering for
  workshop downloads; never auto-enable code execution.
- **Runaway safeguards (S)** — global kill-switch overlay, max-events / max-runtime
  guards, and an always-visible "playback is running" indicator.
- **Faster cold start (S)** — defer heavy imports; measure and trim startup.

### Content & onboarding
- **Bundled sample macros (S)** — ship a few example `.tmacc/.tmacd` so first-run
  users have something to play with (the remaining piece of the onboarding item).
- **Macro snippet library (M)** — built-in reusable blocks (login, common waits).
- **Run history & stats (S)** — per-macro run count, last run, average duration
  (extend `MacroLibrary`).

---

## Big bets: huge features (deep dives)

The transformative, multi-release features. Each is large; the value is high
enough to justify staging them carefully. They reinforce each other — self-healing
targeting makes both AI authoring and cross-device replay reliable.

### 1. Self-healing, vision-first targeting — "run-anywhere macros"

**Problem.** Coordinate and single-template macros break the moment a window
moves, resizes, is themed differently, or runs at another resolution. This is the
#1 reason automation feels brittle.

**Idea.** Every click/target carries an *ordered list of strategies*, tried in
priority order at playback until one matches with enough confidence:
1. absolute screen coords (fastest, least robust),
2. window-relative coords (survives the window moving — reuse `dock.py`),
3. image template match, multi-scale + grayscale (survives repositioning),
4. **OCR text anchor** ("the button labelled *Login*"),
5. **relative-to-anchor** ("40 px right of the *Search* icon").

At record time Tiny Macro opportunistically captures *all* of these for each
click (a small screenshot around the point, nearby OCR text, the relative offset
to the closest strong anchor). At playback the `Resolver` returns the first hit
and logs which strategy won, so users can see and trust it. Per-target confidence,
timeout, retry and on-miss policy (already exist for image steps) generalise.

**Architecture.**
- `core/targeting.py`: a `Target` (list of `Strategy` + policy) and a `Resolver`
  that, given a screen grab, evaluates strategies in order. Pure logic + the
  existing `vision.Locator`; OCR behind the optional extra.
- `MacroEvent` gains an optional `targets: list[Target]` (back-compat: absent →
  today's behaviour). Player's `_emit_click` asks the resolver first.
- Editor "target inspector": see/reorder/test each strategy with a live confidence
  read-out; re-capture a strategy from the current screen.
- Caching + a single screen grab per resolve to keep it cheap.

**Phases.** (1) data model + resolver with coords + image; (2) OCR text anchors
(Tesseract, optional dep); (3) relative-to-anchor; (4) record-time multi-strategy
capture; (5) editor inspector + run diagnostics ("clicked *Login* via OCR, 0.94").

**Risks.** Extra screen scans (mitigate: one grab, ordered short-circuit); false
matches (confidence gates + anchor cross-checks); OCR dependency size (optional
extra, lazy import).

### 2. Natural-language macro authoring (AI assist)

**Idea.** "Describe what you want and Tiny Macro builds — or edits — the macro."
Two modes: **(a) offline authoring** (generate a reviewable macro from a
description, no live control) and **(b) a guarded live agent** (observe screen →
act → observe, with a kill switch) as a stretch.

**Architecture.**
- *Screen understanding*: capture screenshot(s); build a structured description of
  the screen via OCR + lightweight UI-element detection (reusing #1's targeting).
- *Planner*: an LLM turns the natural-language goal + screen context into a
  sequence of Tiny Macro steps, **grounded** to on-screen targets from #1 (so
  "click Login" becomes a text-anchor click, not a guessed coordinate). Provider
  is configurable and **opt-in**: a **local model** (llama.cpp / Ollama) for
  privacy, or a cloud API with a **user-supplied key**. Follow the
  `docs/claude-api` guidance if wiring an Anthropic model.
- *Review-before-run*: generated steps drop into the editor to inspect/tweak
  before playback — never auto-execute.
- *Live agent (mode b)*: an act→observe loop with hard guardrails — explicit
  opt-in, per-action confirmation (or a strict action budget), the existing
  code-exec gate stays **off**, and the always-visible kill switch stops it.

**Safety & privacy (non-negotiable).** Nothing leaves the machine without
consent; screenshots are opt-in and can be redacted; a local-model path needs no
network at all; the agent cannot run shell/Python unless the user separately
enables code-exec; every agent action is logged and reversible-by-stop.

**Phases.** (1) NL → steps for explicit instructions grounded by text + coords;
(2) vision grounding via element detection ("click the X"); (3) guarded live
agent; (4) first-class local-model support + prompt/version management.

**Risks.** Reliability/hallucinated actions (mitigated by grounding +
review-before-run + budgets); privacy (opt-in + local option); dependency/size
(optional extras). This is the highest-ambition, highest-payoff bet.

### 3. Visual flow builder (node graph)

**v1 shipped (playlist-focused)**: `gui/flow_builder.py` is a node canvas that
builds an **image-gated playlist** — draggable macro cards wired into a Start→…
sequence, each with a repeat count and an optional **image gate** (snip a
load-screen; the macro waits for it before playing, via a no-click wait-for-image
step). It plays the stitched macro and exports/imports **portable bundles**
(below). Playlist gates live in `core/playlist.py` (`PlaylistItem.gate_*`);
`.tmbundle` packing in `core/bundle.py`. Next: arbitrary branching + variables.

**Original idea (fuller vision).** A node canvas for branching automations —
triggers, conditions, loops, actions, sub-macros, variables — for flows the linear
timeline can't express cleanly. Complements (not replaces) the timeline.

**Architecture.** A `Flow` (nodes + typed edges) that **lowers to the existing
linear `MacroEvent` stream** (if/else/loop already exist in the interpreter), so
the player needs no new engine — execution reuses `on_step` to highlight the live
node. Round-trip is constrained to a lowerable subset so graph↔linear stays
consistent. Canvas via `QGraphicsView`; nodes are small widgets; variables
(Backlog) feed condition nodes.

**Phases.** (1) read-only graph view of an existing macro's control flow;
(2) editable action/wait nodes; (3) branches/loops/sub-macros; (4) variables +
simple expressions; (5) live execution highlight on the canvas.

**Risks.** UI complexity; keeping the graph representable as linear events (solve
by only allowing structures the interpreter supports).

### 4. Cloud & multi-device

**Idea.** Run and control macros beyond the one desktop.
- **Remote/cloud execution**: a headless runner (reuse `export.py`'s runner) on a
  VM/agent, triggered on a schedule or via API — for always-on automation.
- **Mobile companion** (app or PWA): trigger/monitor macros, see live status and
  screenshots, start/stop — over the **local HTTP trigger API** (Backlog) on the
  LAN, or via the account/cloud (Distribution) anywhere.
- **Record-here, play-there**: Studio's resolution-independent macros + #1's
  strategy targeting make cross-machine replay actually reliable.

**Architecture.** Builds directly on the Distribution plan (accounts, sync, the
version-manifest API) and the local HTTP API; the runner already exists. Remote
input is powerful, so: strong per-device auth, scoped tokens, an audit log, and an
explicit "this device may be controlled remotely" opt-in with a visible indicator.

**Phases.** (1) local HTTP trigger API + a minimal web/PWA controller on the LAN;
(2) account-backed remote trigger + status; (3) scheduled cloud runs on a hosted
agent; (4) full mobile app.

**Risks.** Infra cost; security surface of remote input (the mitigations above are
mandatory, not optional).

---

## Distribution: install manager + website (planned)

Goal: users download Tiny Macro once, it **installs cleanly**, **auto-updates**
itself, and **syncs macros** (and macro updates) from a website whenever they're
online. Plus a public site where people browse/share macros per game.

### A. Installer (Windows first)

- Build an **Inno Setup** (or NSIS) installer that wraps `tiny-macro-windows.exe`:
  installs to `%LOCALAPPDATA%\TinyMacro` (per-user → self-update needs no admin),
  Start-Menu + desktop shortcuts, registers the `.tmacc`/`.tmacd` file
  associations and the `tinymacro://` URL protocol (see C).
- Keep publishing the raw `.exe`/`wayland` binaries on GitHub Releases too.
- Script it in `scripts/build_installer.iss` invoked after `build_windows.ps1`.
- Later: **code-sign** the exe/installer (removes SmartScreen warnings). Needs a
  cert (~$100–300/yr) — note as a cost item.

### B. Auto-updater (self-update)

- **Update source = GitHub Releases** to start (no server needed). On launch (and
  hourly), the app calls the GitHub Releases API, compares the latest tag to its
  own `__version__`, and if newer:
  1. downloads the new binary to a temp file + verifies a SHA-256 from the
     release notes/asset;
  2. writes a tiny `updater` helper that waits for the app to exit, swaps the
     binary, and relaunches (Windows can't overwrite a running exe, hence the
     helper). On Linux, replace the AppImage/binary in place.
- New module `core/updater.py` + a "Check for updates" menu item and a settings
  toggle for auto-update channel (stable / none). Show a non-blocking toast when
  an update is ready.
- Evaluate off-the-shelf first: **PyUpdater**, **tufup** (TUF-based, secure), or
  **Velopack** (great Windows delta updates) — a mature framework beats rolling
  our own signature/rollback logic. Recommendation: prototype with GitHub-based
  self-update, migrate to **tufup** (signed, resumable, rollback) if it grows.

### C. `tinymacro://` deep links + "Install from web"

- Register a URL-protocol handler at install time so a website button
  `tinymacro://install?id=<macroId>` opens the app and imports that macro
  straight into the library. Handle the URI in `cli.py`/`app.py`.
- This is the glue between the website and the desktop app.

### D. Website + macro library (workshop)

- **Frontend**: Next.js or SvelteKit — browse/search macros, per-game categories,
  tags, ratings, screenshots (reuse the webhook screenshots!), a macro's version
  history, and an "Open in Tiny Macro" button (deep link in C). A download-count
  and "verified/creator" badges.
- **Backend API**: FastAPI (Python — shares the macro models) or Node. Endpoints:
  auth, macro CRUD, search, ratings, download, and a **version manifest** the
  updater can read (so the site can also drive updates). Store macro files +
  screenshots in S3-compatible object storage; metadata in Postgres.
- **Accounts + cloud library sync**: each user's macro library lives server-side;
  the desktop app pulls updates on connect (a "Sync" that merges the local
  `MacroLibrary` with the account's) so macros update across machines — this is
  the "get any update to their macro every time they connect" ask.
- **Safety/moderation**: macros containing `run` (shell/Python) steps are flagged
  in the UI and on the site; the code-exec gate stays **off by default**; add a
  report/removal flow. Never auto-enable code execution from a downloaded macro.
- **Hosting**: start cheap — Vercel/Netlify (frontend) + Fly.io/Railway/Render
  (API) + managed Postgres + Cloudflare R2/Backblaze B2 (files). A single small
  VPS also works. Note domain + hosting as recurring costs.

### Suggested phase order

1. Inno Setup installer + `core/updater.py` self-update against GitHub Releases.
2. `tinymacro://` protocol handler + "Install from web" on a static macro page.
3. Website + API + accounts (browse/upload/download macros).
4. Cloud macro-library sync (per-account) pulled on connect; optional code-signing.

---

## Custom themes (`.tmactheme`) — shipped (phases 1–4)

**Implemented**: full reskinning — a **solid colour, a PNG/JPG, or an animated
GIF** background (fit modes + adjustable scrim), a chosen **accent/highlight**,
translucent panel/text colours (surface opacity so the background shows through
toolbars/lists/cards), and an optional UI font. Themes export as a single portable,
gzip-compressed **`.tmactheme`** with base64-embedded assets — no external paths,
cross-platform, safe to share.

- `core/theme_pack.py` — pure `Theme`/`Background` model, base64 assets, strict
  validation (hex colours, opacity ranges, fit/kind, image magic-byte sniffing,
  per-asset + total size caps, WCAG contrast warnings), gzip save/`.tmactheme`
  load (also reads plain JSON). Fully unit-tested.
- `gui/themed_background.py` — a click-through, lowered `ThemedBackground` that
  paints the still image or GIF (`QMovie`) per fit mode with a scrim; **paused
  during playback and when animations are off** (perf/reduce-motion guard).
- `gui/theme.py` — `apply_theme(Theme)` / `apply_theme_object` build the palette +
  rgba-surface stylesheet and font override; built-in presets still work.
- `gui/theme_editor.py` — live editor (colours, background, scrim/opacity sliders,
  font), **Save & Use**, **Use Default**, and **Import/Export `.tmactheme`**,
  reached from **Preferences → Appearance → Custom Themes…**. `Settings.active_theme`
  persists the choice; themes live in `~/.config/tiny-macro/themes/`.

**Still TODO** (phase 5): a theme gallery + workshop/site integration and cloud
sync (below). Original design notes retained for reference:

Goal: let users fully reskin Tiny Macro — a **solid colour, a PNG, or an animated
GIF** as the window background, a chosen **accent/highlight**, and panel/text
colours — then **export the whole look as a single portable `.tmactheme` file**
that imports on any other machine (Windows or Linux) and looks identical. Themes
are **pure data + bundled assets** (no code, no external file paths), so they are
safe to share and inherently cross-platform.

### A. What a theme controls

Extend today's `ThemeColors` (in `gui/theme.py`) into a richer, serialisable
`Theme`:

- **Background layer** — one of:
  - `solid`: a hex colour;
  - `image`: a still PNG/JPG (tiled / centred / stretched / `cover` / `fit`);
  - `animated`: a GIF/APNG played via `QMovie` (with a `fit` mode + optional
    frame-rate cap and a "freeze on first frame" fallback).
  Plus a **scrim**: an adjustable dark/light overlay alpha drawn *over* the
  background so foreground text stays legible on busy images.
- **Surfaces** — panel / elevated / border colours, each with an **opacity** so
  the background shows through cards, toolbars and list rows (the key to making an
  image background actually read as a theme rather than being hidden).
- **Accent / highlight** — the existing accent + `accent_text`; drives buttons,
  selections, the timeline playhead, progress chunks, checkboxes.
- **Text** — text + muted colours (auto-contrast helper: warn/adjust when the
  chosen text colour fails a WCAG-ish contrast ratio against the background).
- **Kind colours** — the editor/timeline per-kind palette (`key/mouse/wheel/wait`).
- **Font** — optional UI font family override (falls back to `UI_FONT_STACK`).
- **Metadata** — `name`, `author`, `version`, `created_at`, and a small preview
  thumbnail (base64 PNG) for a theme gallery.

Rendering approach: a `ThemedBackground` widget painted behind the central widget
(a custom `paintEvent` for solid/still images, a `QMovie`-driven `QLabel`/paint
for GIFs), with the existing stylesheet regenerated so panels use `rgba(...)` from
the surface opacities. Both `FramelessWindow` subclasses host it beneath their
content; the onboarding overlay already blurs whatever is behind it, so it "just
works" over a themed background.

### B. The `.tmactheme` file format

A single JSON document with **assets embedded as base64** so the file is
self-contained and portable (no broken image paths across PCs/OSes):

```jsonc
{
  "format": "tiny-macro-theme",
  "version": 1,
  "name": "Synthwave",
  "author": "…",
  "background": { "kind": "animated", "fit": "cover", "scrim": 0.35,
                  "asset": "grid.gif", "fps_cap": 24 },
  "surfaces": { "panel": "#181826", "panel_opacity": 0.82, "border": "#33334d", … },
  "accent": "#ff5cae", "accent_text": "#0c0c12",
  "text": "#f0f0ff", "muted": "#9aa0c0",
  "kind_colors": { "key": "#…", "mouse": "#…", "wheel": "#…", "wait": "#…" },
  "font_family": "",
  "assets": { "grid.gif": "<base64>", "thumbnail": "<base64-png>" }
}
```

Design decisions:
- **Embedded, not referenced** assets → true portability and one-file sharing.
- **Size discipline**: hard cap the packed file (e.g. ≤ 8–12 MB); warn on large
  GIFs; downscale/re-encode oversized images on export; store a separate small
  thumbnail so galleries don't decode full GIFs. Consider zlib-compressing the
  JSON (`.tmactheme` = gzipped JSON) to shrink base64 overhead.
- **Cross-platform correctness**: only hex colours + PNG/GIF bytes + family
  *names*; never absolute paths, never platform fonts assumed present (missing
  family → documented fallback). Pillow/Qt decode identically on Win/Linux.
- **Versioned + forward-compatible** like the macro format: unknown keys ignored,
  new optional keys only written when set.

### C. Core + GUI work

- `core/theme_pack.py` — pure, testable `Theme` dataclass with
  `to_dict`/`from_dict`/`save`/`load`, asset (de)serialisation, validation
  (colour syntax, opacity range, asset size/type sniffing, contrast check). No Qt,
  so it unit-tests cleanly like `dock.py`/`playlist.py`.
- `gui/theme.py` — `apply_theme` learns to take a `Theme` (built-in presets become
  thin `Theme` instances), regenerating palette + stylesheet with rgba surfaces
  and installing/removing the `ThemedBackground`.
- `gui/theme_store.py` + a small on-disk themes dir (`~/.config/tiny-macro/themes`)
  with an index, mirroring `MacroLibrary`.
- **Theme editor dialog** — pick background (colour / "Choose image…" / "Choose
  GIF…"), sliders for scrim + surface opacity, accent/text pickers, font, **live
  preview** on a mini mock, and **Export…/Import…** (`.tmactheme`). A gallery of
  saved themes with the thumbnails.
- `Settings` gains `active_theme` (name or path) resolved on launch; built-in
  presets stay the default so nothing changes unless a user opts in.

### D. Safety, performance, reliability

- **Untrusted input**: a `.tmactheme` is *data only*. Decode images through
  Pillow/Qt with strict type/size caps; reject anything that isn't a valid
  PNG/JPG/GIF; never execute anything; treat `name/author` as plain text in the
  UI (no rich markup). This dovetails with the workshop's moderation story — a
  future theme gallery on the site reuses the same validation.
- **Animated backgrounds**: cap FPS + resolution; pause the `QMovie` when the
  window is minimised/inactive or the macro is *playing* (so capture/replay timing
  and CPU aren't disturbed); a global "reduce motion / disable animated
  backgrounds" toggle (also honour the OS reduce-motion hint). Freeze to the first
  frame as a low-power fallback.
- **Legibility**: enforce a minimum scrim/contrast so text never becomes
  unreadable on a wild background; offer an auto-scrim that samples the image.

### E. Distribution tie-in

Themes ride the same rails as macros: shareable single files now, and later
first-class objects in the **workshop website** (browse/preview/download themes
per game or vibe, `tinymacro://install?theme=…` deep links, cloud sync of a user's
themes). The embedded-asset format means a theme downloaded on the site drops
straight into the desktop app unchanged.

### Suggested phase order

1. `core/theme_pack.py` (`Theme` + `.tmactheme` load/save/validate) with tests.
2. `apply_theme(Theme)` + `ThemedBackground` for **solid** and **still image**
   backgrounds + surface opacity; wire built-in presets through it.
3. Theme editor dialog with live preview + Import/Export.
4. **Animated (GIF)** backgrounds via `QMovie` with the motion/perf guards.
5. Theme gallery + workshop/site integration and cloud sync.

---

## Dev setup (fresh machine)

```bash
# Windows (PowerShell), from the repo root:
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"     # dev = pytest + vision extras
.venv\Scripts\python -m pytest -q                    # run the suite
.venv\Scripts\python -m tinymacro                    # launch the app
```

- Python **3.12+** (3.14 used here). GUI is PyQt6.
- Optional image features need the `vision` extra (OpenCV-headless + mss + numpy),
  already included in the `dev` extra.

## Building binaries

- **Windows**: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1`
  → `dist/tiny-macro-windows.exe` (rebuilds `.venv-windows-build`, regenerates the
  multi-res app `.ico`, bundles icons + vision).
- **Arch/Wayland** (run on Arch, or Arch WSL): `bash scripts/build_arch_wayland.sh`
  → `dist/tiny-macro-wayland`. On WSL, build from the Linux filesystem (e.g.
  `~/tiny-macro-build`), not `/mnt/c`, or PyInstaller/venv perms fail.

## Release flow

1. Bump `version` in `pyproject.toml`.
2. `pytest -q` green; rebuild both binaries.
3. Commit (no AI co-author trailer — user preference), push.
4. `git tag vX` ; `gh release create vX dist/tiny-macro-windows.exe dist/tiny-macro-wayland --title ... --notes ...`.

## Architecture map

- `core/` — `events.py` (MacroEvent), `macro.py` (Macro + formats), `recorder.py`,
  `player.py` (scheduled + control-flow execution, precise timing), `playlist.py`
  (chain macros into one run), `dock.py` (relative coords), `vision.py`,
  `scheduler.py` + `image_watcher.py`, `settings.py`, `hotkeys.py`.
- `backends/` — `base.py`, `windows.py`, `evdev_wayland.py`, `x11.py`, `fake.py`.
- `gui/` — `app.py` (bootstrap + variant switch), `main_window.py` (Classic),
  `studio_window.py` (Studio), `framed_window.py` (frameless chrome), `anim.py`,
  `icons.py`, `timeline.py`, `editor.py`, dialogs.
- `tests/` — pytest + pytest-qt.
