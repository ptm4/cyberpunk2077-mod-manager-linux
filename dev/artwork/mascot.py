# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
"""The Samurai Mod Manager mascot: Tux as a cyber samurai.

Tux himself is the vector drawing in tux.svg (see README.md here for where it comes from). Everything else is
drawn below as SVG on top of him, in one shared coordinate frame: the fire rising from his head, the red headband,
the two horns, the chrome half of his head with its red optic, the chrome arm, the belt and the sword. The whole
mascot is vector art and stays sharp at any size. build.py turns it into the PNG files the program ships.

The fiery, half-machine head is a nod to the band Samurai from Cyberpunk 2077. It is drawn from scratch; nothing
here is copied from the game's artwork.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

AMBER, AMBER_HOT = "#ff9a2e", "#ffd08a"
RED, RED_HOT = "#ff3b36", "#ffd2cf"

DEFS = f'''
  <!-- metals -->
  <linearGradient id="g-chrome" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffffff"/><stop offset="0.18" stop-color="#d9dee6"/><stop offset="0.42" stop-color="#8a92a0"/>
    <stop offset="0.5" stop-color="#3f4551"/><stop offset="0.58" stop-color="#9aa2b0"/><stop offset="0.82" stop-color="#e6eaf0"/><stop offset="1" stop-color="#737b89"/>
  </linearGradient>
  <linearGradient id="g-chrome-h" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#6d7583"/><stop offset="0.2" stop-color="#f4f6f9"/><stop offset="0.45" stop-color="#aab1bd"/>
    <stop offset="0.6" stop-color="#4a505c"/><stop offset="0.78" stop-color="#c5cbd5"/><stop offset="1" stop-color="#5b626f"/>
  </linearGradient>
  <linearGradient id="g-steel" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#565966"/><stop offset="0.5" stop-color="#2c2e38"/><stop offset="1" stop-color="#14151a"/>
  </linearGradient>
  <radialGradient id="g-bowl" cx="0.66" cy="0.2" r="0.95">
    <stop offset="0" stop-color="#7b7f8f"/><stop offset="0.22" stop-color="#474a57"/><stop offset="0.6" stop-color="#22232b"/><stop offset="1" stop-color="#0b0b0e"/>
  </radialGradient>
  <linearGradient id="g-lacquer" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ff7a6c"/><stop offset="0.35" stop-color="#d23a34"/><stop offset="1" stop-color="#6e1412"/>
  </linearGradient>
  <linearGradient id="g-lame" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#5c5f6d"/><stop offset="0.18" stop-color="#34363f"/><stop offset="1" stop-color="#101116"/>
  </linearGradient>
  <linearGradient id="g-belt" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#4a4c58"/><stop offset="0.3" stop-color="#2a2b33"/><stop offset="1" stop-color="#0e0f13"/>
  </linearGradient>
  <linearGradient id="g-sides" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#000" stop-opacity="0.75"/><stop offset="0.22" stop-color="#000" stop-opacity="0"/>
    <stop offset="0.78" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.75"/>
  </linearGradient>
  <radialGradient id="g-optic" cx="0.42" cy="0.4" r="0.7">
    <stop offset="0" stop-color="#fff3f1"/><stop offset="0.2" stop-color="#ff8a80"/><stop offset="0.5" stop-color="{RED}"/><stop offset="1" stop-color="#5a0806"/>
  </radialGradient>
  <radialGradient id="g-led" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="#fff6e6"/><stop offset="0.45" stop-color="{AMBER_HOT}"/><stop offset="1" stop-color="{AMBER}"/>
  </radialGradient>
  <linearGradient id="g-wrap" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#3a3c47"/><stop offset="1" stop-color="#0e0f13"/>
  </linearGradient>
  <!-- the chrome half of his head: lit from the upper right -->
  <radialGradient id="g-skull" gradientUnits="userSpaceOnUse" cx="163" cy="24" r="92">
    <stop offset="0" stop-color="#ffffff"/><stop offset="0.16" stop-color="#e9edf2"/><stop offset="0.42" stop-color="#a4acb9"/>
    <stop offset="0.7" stop-color="#666e7b"/><stop offset="1" stop-color="#2c3038"/>
  </radialGradient>
  <linearGradient id="g-ivory" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#fffaf0"/><stop offset="0.55" stop-color="#eadbb4"/><stop offset="1" stop-color="#a8946a"/>
  </linearGradient>
  <!-- fire: the colour depends on the height, so every tongue shades the same way -->
  <linearGradient id="g-fire" gradientUnits="userSpaceOnUse" x1="0" y1="48" x2="0" y2="-58">
    <stop offset="0" stop-color="#ffb13d"/><stop offset="0.3" stop-color="#ff641f"/><stop offset="0.68" stop-color="#e42c1a"/><stop offset="1" stop-color="#9c1410"/>
  </linearGradient>
  <linearGradient id="g-fire-mid" gradientUnits="userSpaceOnUse" x1="0" y1="48" x2="0" y2="-40">
    <stop offset="0" stop-color="#ffe894"/><stop offset="0.45" stop-color="#ffa53a"/><stop offset="1" stop-color="#ff5a1f"/>
  </linearGradient>
  <linearGradient id="g-fire-core" gradientUnits="userSpaceOnUse" x1="0" y1="48" x2="0" y2="-20">
    <stop offset="0" stop-color="#fffbe6"/><stop offset="0.5" stop-color="#ffdc78"/><stop offset="1" stop-color="#ffab3d"/>
  </linearGradient>
  <!-- light and shadow -->
  <filter id="f-glow" x="-80%" y="-80%" width="260%" height="260%">
    <feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <filter id="f-glow-s" x="-80%" y="-80%" width="260%" height="260%">
    <feGaussianBlur stdDeviation="1.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <filter id="f-soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3"/></filter>
  <filter id="f-soft-s" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="1.4"/></filter>
  <filter id="f-bloom" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="7"/></filter>
  <!-- a soft light behind the whole figure, so black feathers and dark armour stand off a dark backdrop -->
  <filter id="f-rim" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur in="SourceAlpha" stdDeviation="5" result="a"/>
    <feFlood flood-color="#ff7a4a" flood-opacity="0.42"/><feComposite in2="a" operator="in" result="wide"/>
    <feGaussianBlur in="SourceAlpha" stdDeviation="1.3" result="b"/>
    <feFlood flood-color="#ffd9c2" flood-opacity="0.38"/><feComposite in2="b" operator="in" result="tight"/>
    <feMerge><feMergeNode in="wide"/><feMergeNode in="tight"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
'''


def belt_and_sword():
    leds = "".join(f'<circle cx="{x}" cy="{y}" r="1.9" fill="url(#g-led)"/>' for x, y in ((154, 209.6), (166, 207.2), (178, 204.0), (190, 200.2)))
    glow = "".join(f'<circle cx="{x}" cy="{y}" r="3.4" fill="{AMBER}"/>' for x, y in ((154, 209.6), (166, 207.2), (178, 204.0), (190, 200.2)))
    wrap = "".join(f'<path d="M{x} 192.2 l5.2 6.8 l-5.2 6.8 l-5.2 -6.8 Z" fill="#ecebe7" stroke="#07070a" stroke-width="0.5"/>' for x in (41, 52.4, 63.8, 75.2))
    return f'''
  <!-- soft shadow the belt casts on his belly -->
  <path d="M64 204 Q131 224 212 201 L212 209 Q131 234 64 212 Z" fill="#000" opacity="0.38" filter="url(#f-soft)"/>
  <!-- belt -->
  <path id="belt" d="M62 187 Q131 207 216 184 L216 201 Q131 225 62 204 Z" fill="url(#g-belt)" stroke="#07070a" stroke-width="1"/>
  <path d="M62 187 Q131 207 216 184 L216 201 Q131 225 62 204 Z" fill="url(#g-sides)"/>
  <path d="M63 188.4 Q131 208.4 215 185.4" fill="none" stroke="#9a9eae" stroke-width="0.9" opacity="0.6"/>
  <path d="M63 191.4 Q131 211.4 215 188.4" fill="none" stroke="{RED}" stroke-width="1.5"/>
  <path d="M63 200.6 Q131 221 215 197.6" fill="none" stroke="#7a1614" stroke-width="1.2"/>
  <g filter="url(#f-soft-s)" opacity="0.9">{glow}</g>
  {leds}
  <!-- buckle -->
  <g transform="translate(138 205.6)">
    <rect x="-9" y="-8" width="18" height="16" rx="2.4" fill="url(#g-chrome)" stroke="#3b404a" stroke-width="0.9"/>
    <rect x="-6.2" y="-5.4" width="12.4" height="10.8" rx="1.4" fill="#15161b" stroke="#07070a" stroke-width="0.6"/>
    <circle r="5" fill="{RED}" opacity="0.6" filter="url(#f-soft-s)"/>
    <circle r="2.6" fill="url(#g-optic)"/>
  </g>
  <!-- the sword: one straight line from pommel to scabbard tip, worn across his front and under his hand -->
  <g transform="translate(0 9) rotate(12 84 199)">
    <rect x="84" y="195" width="206" height="11" rx="5.5" fill="#000" opacity="0.4" filter="url(#f-soft-s)"/>
    <rect x="84" y="193.5" width="206" height="11" rx="5.5" fill="url(#g-steel)" stroke="#07070a" stroke-width="1"/>
    <rect x="86" y="195" width="202" height="2.2" rx="1.1" fill="#8d91a1" opacity="0.5"/>
    <rect x="262" y="193.5" width="28" height="11" rx="5.5" fill="url(#g-chrome)" stroke="#3b404a" stroke-width="0.9"/>
    <rect x="236" y="192.6" width="6" height="12.8" rx="1.5" fill="url(#g-lacquer)" stroke="#4a0d0c" stroke-width="0.7"/>
  </g>
  <g transform="translate(0 9) rotate(12 84 199)">
    <rect x="26" y="191.6" width="58" height="14.8" rx="4.4" fill="url(#g-wrap)" stroke="#07070a" stroke-width="1"/>
    {wrap}
    <rect x="27" y="192.6" width="56" height="2.2" rx="1.1" fill="#fff" opacity="0.18"/>
    <rect x="22" y="190.8" width="8" height="16.4" rx="3" fill="url(#g-chrome)" stroke="#3b404a" stroke-width="0.8"/>
    <ellipse cx="86.5" cy="199" rx="5" ry="13.5" fill="url(#g-chrome-h)" stroke="#3b404a" stroke-width="0.9"/>
    <ellipse cx="86.5" cy="199" rx="2" ry="9" fill="#15161b" opacity="0.55"/>
    <rect x="89" y="193.4" width="6.5" height="11.2" rx="1.4" fill="url(#g-lacquer)" stroke="#4a0d0c" stroke-width="0.7"/>
  </g>'''


def arm():
    return f'''
  <!-- shadow of the arm on his side -->
  <path d="M170 128 Q214 150 226 208 Q226 234 200 232 Q190 190 162 154 Z" fill="#000" opacity="0.45" filter="url(#f-soft)"/>
  <g id="arm">
    <!-- upper arm -->
    <path d="M178 122 Q212 134 224 168 L202 182 Q192 158 170 146 Z" fill="url(#g-chrome-h)" stroke="#2f343d" stroke-width="1.2" stroke-linejoin="round"/>
    <path d="M184 127 Q209 139 219 164" fill="none" stroke="#fff" stroke-width="1.6" opacity="0.75" stroke-linecap="round"/>
    <path d="M176 142 Q194 154 203 176" fill="none" stroke="#1d2027" stroke-width="1" opacity="0.6"/>
    <!-- elbow -->
    <path d="M201 180 L225 166 Q230 174 232 184 L207 194 Z" fill="#15161b" stroke="#07070a" stroke-width="0.9" stroke-linejoin="round"/>
    <path d="M205 185.5 L229 174.5" stroke="{AMBER}" stroke-width="2.4" stroke-linecap="round" filter="url(#f-glow)"/>
    <path d="M205 185.5 L229 174.5" stroke="{AMBER_HOT}" stroke-width="0.9" stroke-linecap="round"/>
    <!-- forearm -->
    <path d="M207 192 L232 182 Q239 202 237 220 L213 222 Q212 206 207 192 Z" fill="url(#g-chrome-h)" stroke="#2f343d" stroke-width="1.2" stroke-linejoin="round"/>
    <path d="M230 187 Q234.5 203 233.5 217" fill="none" stroke="#fff" stroke-width="1.5" opacity="0.7" stroke-linecap="round"/>
    <path d="M215 197 Q219 209 219 219" fill="none" stroke="#1d2027" stroke-width="1" opacity="0.55"/>
    <!-- hand -->
    <path d="M212 220 L238 218 Q241 232 232 239 Q219 244 209 236 Q208 228 212 220 Z" fill="url(#g-steel)" stroke="#07070a" stroke-width="1.1" stroke-linejoin="round"/>
    <path d="M218 226 L217 239 M225 225.4 L225 241 M232 225 L231.6 239" stroke="#07070a" stroke-width="1" fill="none"/>
    <path d="M213.4 222.2 L237 220.4" stroke="#9a9eae" stroke-width="0.9" opacity="0.7"/>
    <!-- shoulder joint and guard -->
    <circle cx="186" cy="137" r="9.6" fill="url(#g-steel)" stroke="#07070a" stroke-width="1"/>
    <circle cx="186" cy="137" r="6.2" fill="url(#g-chrome)" stroke="#3b404a" stroke-width="0.8"/>
    <circle cx="186" cy="137" r="2.2" fill="#15161b"/>
    <path d="M163 116 Q180 98 207 106 L210 116 Q186 109 168 125 Z" fill="url(#g-lame)" stroke="#07070a" stroke-width="1.1" stroke-linejoin="round"/>
    <path d="M165.4 115.4 Q181 100.6 206 107.4" fill="none" stroke="#a9adbd" stroke-width="0.9" opacity="0.65"/>
    <path d="M167.6 123.4 Q186 107.6 209.4 114.4" fill="none" stroke="{RED}" stroke-width="1.3"/>
    <path d="M168.6 126 Q187 111 211 118 L214 128.4 Q190 122 174.6 136 Z" fill="url(#g-lame)" stroke="#07070a" stroke-width="1.1" stroke-linejoin="round"/>
    <path d="M171 125.6 Q188 112.6 210.4 119.4" fill="none" stroke="#a9adbd" stroke-width="0.9" opacity="0.65"/>
    <path d="M174 134 Q190.4 120.6 213.4 126.6" fill="none" stroke="{AMBER}" stroke-width="1.7" stroke-linecap="round" filter="url(#f-glow-s)"/>
  </g>'''


# Tux's own layers sit inside a nested <svg>. To use one of them outside it (as a clip, or drawn again on top)
# the same placement has to be repeated.
TUX_LAYER = "translate(7 8) scale(1.005) translate(-16.987948 -19.575154)"
TUX_BODY, TUX_BEAK = "tux-path28712-2", "tux-g735"

# The chrome half of his head: everything right of this stepped seam and above the jaw line, cut to his outline.
SEAM = "M126 -8 L126 33 L120.5 40 L120.5 57 L125.5 63 L125.5 80"
PLATE = SEAM + " L140 100 L157 101.5 L169 95.5 L187 93 L206 93 L206 -8 Z"


def tongue(x, y, w, h, lean, bend=0.0):
    """One tongue of flame: base centred on (x, y), `w` wide, `h` tall. Its body bows sideways by `bend` and its
    tip ends `lean` to the side, so opposite signs give the S-shape of a licking flame."""
    def pt(dx, dy):
        return f"{x + dx:.1f} {y - dy * h:.1f}"
    return (f"M{pt(-w / 2, 0)} "
            f"C{pt(-w * 0.70, 0.16)} {pt(-w * 0.46 + bend, 0.38)} {pt(-w * 0.24 + bend, 0.54)} "          # left side, lower
            f"C{pt(-w * 0.06 + bend * 0.7, 0.70)} {pt(lean * 0.40 - w * 0.14, 0.88)} {pt(lean, 1.0)} "       # up to the tip
            f"C{pt(lean * 0.62 + w * 0.09, 0.80)} {pt(w * 0.20 + bend * 0.9, 0.66)} {pt(w * 0.28 + bend * 0.5, 0.50)} "   # back down
            f"C{pt(w * 0.38, 0.34)} {pt(w * 0.72, 0.18)} {pt(w / 2, 0)} "
            f"C{x + w * 0.42:.1f} {y + w * 0.30:.1f} {x - w * 0.42:.1f} {y + w * 0.30:.1f} {pt(-w / 2, 0)} Z")   # a rounded foot, never a flat cut


def fire(tongues, glow=True):
    """Tongues drawn in three nested layers (red outside, orange, a pale core), with a soft glow behind."""
    outer = "".join(f'<path d="{tongue(x, y, w, h, lean, bend)}"/>' for x, y, w, h, lean, bend in tongues)
    mid = "".join(f'<path d="{tongue(x + lean * 0.12, y, w * 0.62, h * 0.70, lean * 0.6, bend * 0.6)}"/>' for x, y, w, h, lean, bend in tongues)
    core = "".join(f'<path d="{tongue(x + lean * 0.16, y, w * 0.32, h * 0.42, lean * 0.35, bend * 0.3)}"/>' for x, y, w, h, lean, bend in tongues)
    bloom = f'<g fill="#ff6a1f" opacity="0.5" filter="url(#f-bloom)">{outer}</g>' if glow else ""
    return f"""{bloom}
  <g fill="url(#g-fire)" stroke="#7a1410" stroke-width="0.9" stroke-linejoin="round">{outer}</g>
  <g fill="url(#g-fire-mid)">{mid}</g>
  <g fill="url(#g-fire-core)">{core}</g>"""


# (x, y of the base, width, height, lean of the tip, bow). The fire leans a little to one side, as if he were moving.
FLAMES_BACK = [(95, 48, 22, 34, -4, 4), (104, 40, 26, 48, 0, 5), (114, 31, 28, 60, 3, -5), (126, 25, 30, 74, 6, -6),
               (139, 22, 30, 82, 9, -7), (152, 26, 28, 66, 11, -6), (164, 35, 26, 52, 12, -5), (175, 49, 22, 36, 12, -4)]
FLAMES_BETWEEN = [(109, 34, 14, 34, 2, -3), (133, 22, 15, 48, 6, -4), (158, 30, 14, 38, 9, -3)]
FLAMES_FRONT = [(99.5, 42, 14, 30, -3, 3), (109.5, 43, 17, 46, 0, -3), (120, 44, 15, 54, 3, -3)]
SPARKS = [(85, 6, 6, 11, 2, -1), (158, -46, 6, 12, 3, -1), (190, 10, 5, 10, 3, -1), (116, -34, 5, 9, 2, -1)]


def flames_back():
    """The mane of fire behind his head, with a few loose sparks."""
    return f"""
  <!-- fire rising from his head -->
  {fire(FLAMES_BACK)}
  {fire(FLAMES_BETWEEN, glow=False)}
  {fire(SPARKS, glow=False)}"""


def flames_front():
    """Smaller tongues that start on his brow, on the feathered half, so the fire belongs to him."""
    return f"""
  <!-- the glow of the fire on the top of his head, then the tongues that start on his brow -->
  <g clip-path="url(#c-body)"><ellipse cx="120" cy="13" rx="34" ry="13" fill="#ff7a2e" opacity="0.34" filter="url(#f-soft)"/></g>
  {fire(FLAMES_FRONT, glow=False)}"""


def cyber_half():
    bolts = "".join(f'<circle cx="{x}" cy="{y}" r="1.3" fill="url(#g-chrome)" stroke="#2f343d" stroke-width="0.5"/>'
                    for x, y in ((130.5, 13), (130.5, 29), (125.5, 49), (166, 97.5), (181, 89)))
    vents = "".join(f'<path d="M167.5 {y} L176.5 {y + 2.2}" stroke="#14161b" stroke-width="1.5" stroke-linecap="round"/>'
                    f'<path d="M167.5 {y + 1.2} L176.5 {y + 3.4}" stroke="#fff" stroke-width="0.5" stroke-linecap="round" opacity="0.6"/>'
                    for y in (74, 78.5, 83))
    return f"""
  <clipPath id="c-body"><use href="#{TUX_BODY}" transform="{TUX_LAYER}"/></clipPath>
  <clipPath id="c-plate"><path d="{PLATE}"/></clipPath>
  <!-- the chrome half of his head -->
  <g clip-path="url(#c-body)">
    <g clip-path="url(#c-plate)">
      <rect x="110" y="-10" width="100" height="120" fill="url(#g-skull)"/>
      <!-- chrome reads as chrome through its hard reflections: a dark band, then light again below it -->
      <path d="M118 60 Q150 49 186 58 L186 71 Q150 61 118 72 Z" fill="#161a20" opacity="0.62" filter="url(#f-soft-s)"/>
      <path d="M118 80 Q150 70 186 78 L186 104 L118 104 Z" fill="#dfe4ea" opacity="0.30" filter="url(#f-soft-s)"/>
      <ellipse cx="160" cy="21" rx="15" ry="5.5" fill="#fff" opacity="0.9" filter="url(#f-soft-s)" transform="rotate(34 160 21)"/>
      <!-- the fire reflected in the metal -->
      <path d="M126 -8 L126 30 Q140 12 170 4 L170 -8 Z" fill="#ff8a3a" opacity="0.30" filter="url(#f-soft)"/>
      <!-- plate seams, vents, bolts -->
      <g fill="none" stroke-linecap="round">
        <path d="M126 22 Q150 11 174.5 33" stroke="#14161b" stroke-width="1.1"/>
        <path d="M126 23.2 Q150 12.2 174 34.2" stroke="#fff" stroke-width="0.5" opacity="0.65"/>
        <path d="M120.5 46 Q150 39 178.5 48" stroke="#14161b" stroke-width="1.1"/>
        <path d="M120.5 47.2 Q150 40.2 178.5 49.2" stroke="#fff" stroke-width="0.5" opacity="0.65"/>
        <path d="M161 88 L170.5 85 L181 87" stroke="#14161b" stroke-width="1.1"/>
        <path d="M161 89.2 L170.5 86.2 L181 88.2" stroke="#fff" stroke-width="0.5" opacity="0.65"/>
      </g>
      {vents}
      {bolts}
    </g>
    <!-- the plate's edge: a dark line, a bright bevel inside it -->
    <path d="{PLATE}" fill="none" stroke="#0e1014" stroke-width="1.6" stroke-linejoin="round"/>
    <path d="{SEAM}" fill="none" stroke="#fff" stroke-width="0.7" stroke-linejoin="round" opacity="0.75" transform="translate(1.3 0)"/>
  </g>
  <!-- cyber eye: a dark housing set into the chrome, with the red optic -->
  <g id="eye">
    <circle cx="147" cy="68" r="21" fill="{RED}" opacity="0.42" filter="url(#f-bloom)"/>
    <path d="M128 53 L162 50 L171 67 L160.5 87 L130.5 84.5 Z" fill="url(#g-steel)" stroke="#0e1014" stroke-width="1.2" stroke-linejoin="round"/>
    <path d="M129.4 54.4 L161.2 51.6 L169.4 67" fill="none" stroke="#aeb4c0" stroke-width="0.8" opacity="0.8"/>
    <circle cx="133" cy="57.6" r="1.2" fill="#8a909c"/><circle cx="158" cy="82.4" r="1.2" fill="#8a909c"/><circle cx="134" cy="81" r="1.2" fill="#8a909c"/>
    <circle cx="146.6" cy="68" r="13" fill="url(#g-chrome)" stroke="#0e1014" stroke-width="0.9"/>
    <circle cx="146.6" cy="68" r="10.6" fill="#0d0e12"/>
    <circle cx="146.6" cy="68" r="10.2" fill="{RED}" opacity="0.55" filter="url(#f-soft-s)"/>
    <circle cx="146.6" cy="68" r="8.2" fill="url(#g-optic)"/>
    <circle cx="146.6" cy="68" r="8.2" fill="none" stroke="#4a0806" stroke-width="0.8"/>
    <circle cx="146.6" cy="68" r="5.4" fill="none" stroke="#7a0d0b" stroke-width="0.6" opacity="0.7"/>
    <circle cx="146.6" cy="68" r="3.1" fill="#fff6f4"/>
    <path d="M140.4 63.2 A7.6 7.6 0 0 1 148.4 60.6" fill="none" stroke="#fff" stroke-width="1.5" stroke-linecap="round" opacity="0.9"/>
    <circle cx="163.5" cy="56.5" r="1.7" fill="url(#g-led)" filter="url(#f-glow-s)"/>
  </g>
  <!-- his beak again, on top of the plate -->
  <g clip-path="url(#c-plate)"><path d="M118 96 Q140 90 160 100 L160 108 Q140 100 118 106 Z" fill="#000" opacity="0.4" filter="url(#f-soft-s)"/></g>
  <use href="#{TUX_BEAK}" transform="{TUX_LAYER}"/>
  <!-- cables from the jaw down to the shoulder -->
  <path d="M176 92 C181 100 178 108 184 116" fill="none" stroke="#0e1014" stroke-width="4.4" stroke-linecap="round"/>
  <path d="M176 92 C181 100 178 108 184 116" fill="none" stroke="#5d6470" stroke-width="2.2" stroke-linecap="round"/>
  <path d="M170 95 C173 103 170 110 175 118" fill="none" stroke="#0e1014" stroke-width="3.6" stroke-linecap="round"/>
  <path d="M170 95 C173 103 170 110 175 118" fill="none" stroke="{AMBER}" stroke-width="1.1" stroke-linecap="round" filter="url(#f-glow-s)"/>"""


def horns():
    """Two short horns: bone on the feathered side, chrome on the machine side."""
    return f"""
  <!-- horns: bone on his feathered side, chrome on the machine side -->
  <path d="M100.5 36.5 Q97 18 86.5 4 Q107.5 11 116.5 31.5 Q108 31 100.5 36.5 Z" fill="url(#g-ivory)" stroke="#4a3d22" stroke-width="1" stroke-linejoin="round"/>
  <path d="M95.5 18.5 Q102 19 107 23 M98.5 27.5 Q105 27 111.5 30" fill="none" stroke="#8a7748" stroke-width="0.8" opacity="0.8" stroke-linecap="round"/>
  <path d="M89.5 7.5 Q98.5 14.5 103.5 27" fill="none" stroke="#fff" stroke-width="1.1" opacity="0.85" stroke-linecap="round"/>
  <path d="M167.5 34.5 Q170.5 16 181.5 2 Q160 9 151.5 28.5 Q160 29 167.5 34.5 Z" fill="url(#g-chrome-h)" stroke="#0e1014" stroke-width="1" stroke-linejoin="round"/>
  <path d="M178.5 5.5 Q169.5 12.5 164.5 25" fill="none" stroke="#fff" stroke-width="1.1" opacity="0.9" stroke-linecap="round"/>
  <path d="M157.5 21.5 Q163.5 21.5 168.5 24.5" fill="none" stroke="#14161b" stroke-width="0.8" opacity="0.7" stroke-linecap="round"/>
  <path d="M154 27.2 Q160 27.6 166 31.6" fill="none" stroke="{AMBER}" stroke-width="1.2" stroke-linecap="round" filter="url(#f-glow-s)"/>"""


def headband_tails():
    """The knot's two tails, flying out behind his head."""
    return f"""
  <!-- the tails of his headband -->
  <path d="M94 36 C80 27 66 28 52 38 C47 41.5 44 45 42 49 L50 47.5 L47.5 55 C54 48 62 43.5 71 42 C79 40.5 87 42 94 45 Z"
        fill="url(#g-lacquer)" stroke="#3a0a09" stroke-width="1" stroke-linejoin="round"/>
  <path d="M90 37.5 C78 31 66 32 55 39.5" fill="none" stroke="#ffc2ba" stroke-width="0.8" opacity="0.7" stroke-linecap="round"/>
  <path d="M94 40 C83 43 73 51 67 62 C65 66 64 70 64 74 L70.5 70 L71.5 78 C74 68 79 60 86 54 C89 51.5 92 49.5 95 48 Z"
        fill="url(#g-lacquer)" stroke="#3a0a09" stroke-width="1" stroke-linejoin="round"/>
  <path d="M91 43.5 C82 47.5 74.5 55 70 64" fill="none" stroke="#ffc2ba" stroke-width="0.8" opacity="0.6" stroke-linecap="round"/>"""


def headband():
    """A red headband across his brow, knotted at the side."""
    return f"""
  <!-- headband: it follows the curve of his head and crosses feathers and chrome alike -->
  <g clip-path="url(#c-body)">
    <path d="M84 44 Q134 55.5 186 42" fill="none" stroke="#000" stroke-width="3.4" opacity="0.5" filter="url(#f-soft-s)" transform="translate(0 1.8)"/>
    <path d="M84 35 Q134 46.5 186 33 L186 42 Q134 55.5 84 44 Z" fill="url(#g-lacquer)" stroke="#3a0a09" stroke-width="1"/>
    <path d="M84 36.5 Q134 48 186 34.5" fill="none" stroke="#ffc2ba" stroke-width="0.9" opacity="0.85"/>
    <path d="M84 42.2 Q134 53.7 186 40.2" fill="none" stroke="#5c0f0d" stroke-width="0.8" opacity="0.7"/>
    <path d="M118 43.2 Q121 47.5 119.5 52.6 M150 43.6 Q147.5 47.5 149.5 52.3" fill="none" stroke="#5c0f0d" stroke-width="0.7" opacity="0.6"/>
  </g>
  <!-- the knot -->
  <path d="M88.5 35.5 Q96.5 34 98 40.5 Q98.5 47 91 47.5 Q86 45.5 86.5 40.5 Z" fill="url(#g-lacquer)" stroke="#3a0a09" stroke-width="1" stroke-linejoin="round"/>
  <path d="M89.5 38 Q93.5 36.5 95.5 39.5" fill="none" stroke="#ffc2ba" stroke-width="0.8" opacity="0.8" stroke-linecap="round"/>"""


def mascot(base):
    """Everything in drawing order: what is behind him, Tux, then what he wears, with the head built up last."""
    return f'''{headband_tails()}{flames_back()}
  <!-- Tux -->
  {base}
  {belt_and_sword()}
  {arm()}
  {cyber_half()}
  {flames_front()}
  {headband()}
  {horns()}'''


# The vector Tux is 249.149 x 304.188 units. The gear was first drawn over the classic 265 x 314 Tux picture;
# scaling the vector by 1.005 and moving it by (7, 8) lays it over that frame (the two outlines overlap 99%).
TUX_SCALE, TUX_DX, TUX_DY = 1.005, 7, 8
# His right flipper and hand (on the viewer's right) are left out: the chrome arm takes their place.
TUX_PARTS_REPLACED = ("path29705-5-0", "path29705-9", "g526", "g545")
NAMESPACES = (("", "http://www.w3.org/2000/svg"), ("xlink", "http://www.w3.org/1999/xlink"),
              ("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"), ("inkscape", "http://www.inkscape.org/namespaces/inkscape"),
              ("dc", "http://purl.org/dc/elements/1.1/"), ("cc", "http://creativecommons.org/ns#"),
              ("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"))


def vector_base(svg: Path, leave_out=TUX_PARTS_REPLACED):
    """The vector Tux as an SVG fragment placed in the gear's frame. Its ids get a prefix so they cannot clash with ours."""
    for prefix, uri in NAMESPACES:
        ET.register_namespace(prefix, uri)
    root = ET.parse(svg).getroot()
    for parent in list(root.iter()):
        for child in list(parent):
            if child.get("id") in leave_out or child.tag.endswith("}namedview"):
                parent.remove(child)
    xlink = "{http://www.w3.org/1999/xlink}href"
    for e in root.iter():
        if e.get("id"):
            e.set("id", "tux-" + e.get("id"))
        for key, value in list(e.attrib.items()):
            if "url(#" in value:
                e.set(key, re.sub(r"url\(#([^)]+)\)", r"url(#tux-\1)", value))
        for key in (xlink, "href"):
            if e.get(key, "").startswith("#"):
                e.set(key, "#tux-" + e.get(key)[1:])
    w, h = float(root.get("width")), float(root.get("height"))
    root.set("viewBox", f"0 0 {w} {h}")
    root.set("x", str(TUX_DX))
    root.set("y", str(TUX_DY))
    root.set("width", f"{w * TUX_SCALE:.4f}")
    root.set("height", f"{h * TUX_SCALE:.4f}")
    return ET.tostring(root, encoding="unicode")


def page(base, width, height, scale, cx, cy, background="", clip=None):
    """A whole picture: backdrop, then the figure scaled by `scale` with its own point (153, 124) placed at (cx, cy).
    The figure spans about x 20..287 (hilt to scabbard tip) and y -60..308 (flame tips to feet) in its own frame."""
    figure = f'''<g transform="translate({cx} {cy}) scale({scale}) translate(-153 -124)" filter="url(#f-rim)">{mascot(base)}
</g>'''
    if clip:
        figure = f'<g clip-path="url(#{clip})">{figure}</g>'
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
<defs>{DEFS}</defs>
{background}
{figure}
</svg>
'''


BACKDROP = '''
<defs>
  <radialGradient id="b-bg" cx="0.5" cy="0.46" r="0.75">
    <stop offset="0" stop-color="#3a1418"/><stop offset="0.45" stop-color="#1c0e11"/><stop offset="1" stop-color="#0c0c0e"/>
  </radialGradient>
  <radialGradient id="b-disc" cx="0.5" cy="0.4" r="0.62">
    <stop offset="0" stop-color="#4a4350"/><stop offset="0.6" stop-color="#2a2630"/><stop offset="1" stop-color="#17151b"/>
  </radialGradient>
  <pattern id="b-grid" width="{grid}" height="{grid}" patternUnits="userSpaceOnUse">
    <path d="M{grid} 0 L0 0 0 {grid}" fill="none" stroke="#ffffff" stroke-opacity="0.035" stroke-width="{line}"/>
  </pattern>
</defs>
<rect width="{w}" height="{h}" fill="url(#b-bg)"/>
<rect width="{w}" height="{h}" fill="url(#b-grid)"/>
<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#b-disc)"/>
<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#e2504c" stroke-width="{sw}"/>
<circle cx="{cx}" cy="{cy}" r="{r2}" fill="none" stroke="#ff9a2e" stroke-width="{sw2}" stroke-opacity="0.55" stroke-dasharray="{dash}"/>
<ellipse cx="{cx}" cy="{gy}" rx="{grx}" ry="{gry}" fill="#000" opacity="0.55" filter="url(#f-soft)"/>
'''


def banner(base, w=640, h=720):
    """The whole figure on a dark backdrop with a ring: the side picture in the window (w : h is 8 : 9)."""
    k = w / 640
    bg = BACKDROP.format(w=w, h=h, cx=w / 2, cy=h * 0.5, r=w * 0.43, r2=w * 0.405, sw=4 * k, sw2=1.5 * k,
                         dash=f"{10 * k} {16 * k}", gy=h * 0.865, grx=w * 0.27, gry=h * 0.018, grid=40 * k, line=k)
    # his body's middle is at x = 137 in the figure's frame, left of the frame's own centre (the sword sticks out
    # to one side), so shift him to put the body, not the sword, on the middle of the ring
    scale = 1.36 * k
    return page(base, w, h, scale, w / 2 + (153 - 137) * scale, h * 0.5, bg)


def icon(base, size=512):
    """Head and shoulders on a rounded dark tile: it stays readable at app-menu size."""
    k = size / 512
    bg = f'''
<defs>
  <radialGradient id="i-disc" cx="0.5" cy="0.38" r="0.7">
    <stop offset="0" stop-color="#4c4452"/><stop offset="0.6" stop-color="#2a2630"/><stop offset="1" stop-color="#141217"/>
  </radialGradient>
  <clipPath id="i-clip"><rect width="{size}" height="{size}" rx="{96 * k}"/></clipPath>
</defs>
<rect width="{size}" height="{size}" rx="{96 * k}" fill="url(#i-disc)"/>
<rect x="{6 * k}" y="{6 * k}" width="{size - 12 * k}" height="{size - 12 * k}" rx="{90 * k}" fill="none" stroke="#e2504c" stroke-width="{8 * k}"/>'''
    return page(base, size, size, 1.95 * k, 284 * k, 400 * k, bg, clip="i-clip")


def cutout(base, scale=4):
    """The figure alone on a transparent background, for banners and thumbnails."""
    w, h = round(300 * scale), round(396 * scale)
    return page(base, w, h, scale, w / 2, 198 * scale)
