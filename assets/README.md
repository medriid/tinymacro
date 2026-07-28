# Source assets

Original, unprocessed files kept for reference. They are **not** loaded at
runtime — the app ships the processed copies in
`src/tinymacro/gui/sounds/`.

| Source | Ships as | Processing |
| --- | --- | --- |
| `hover-source.wav` | `gui/sounds/hover.wav` | 24-bit stereo → 16-bit mono, trimmed, faded, gain ×0.45 |
| `click-source.wav` | `gui/sounds/click.wav` | 24-bit stereo → 16-bit mono, trimmed, faded, gain ×0.75 |

`QSoundEffect` doesn't reliably play 24-bit PCM, hence the conversion; the
trim/fade/gain also keeps the UI feedback subtle. Playback volume is set
separately in `gui/sounds.py` (hover 0.22, click 0.45).

Sounds courtesy of tunetank.com.
