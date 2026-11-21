# The mascot

Tux, the Linux penguin, as a cyber samurai: half machine, with horns, a red headband and fire rising from his head.
The whole thing is vector art.

| File | What it is |
| --- | --- |
| `tux.svg` | Tux as a vector drawing, unchanged from the Linux kernel sources (`Documentation/images/logo.svg`) |
| `COPYING-logo` | The terms that come with it, also from the kernel sources |
| `mascot.py` | Everything added to him, drawn as SVG: the fire, the headband, the horns, the chrome half of his head with its red optic, the chrome arm, the belt and the sword. It leaves out Tux's own right flipper, which the chrome arm replaces |
| `build.py` | Puts the two together and writes the PNG files the program and the README use |

To rebuild after a change (needs `rsvg-convert`, from librsvg):

```bash
python3 dev/artwork/build.py
```

Give it a folder name as well and it also writes the mascot as one scalable SVG, a large transparent cut-out
and a 1024-pixel icon into that folder.

## Credit and terms

Tux was created by Larry Ewing (lewing@isc.tamu.edu) with The GIMP. The vector version was re-illustrated by
Garrett LeSage and refined by IFo Hancroft. It is freely usable as long as they are acknowledged
(see `COPYING-logo`), so keep this credit wherever the mascot is shown.

Everything drawn in `mascot.py` is original to this project and covered by its license (GPL-3.0-or-later).
The fiery, half-machine head is a nod to the band Samurai from Cyberpunk 2077. It is drawn from scratch; nothing
is copied from the game's artwork, and none of it may be.
