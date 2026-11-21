# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
"""Colours and shapes of the window, in one place."""

CSS = """
window.cp, window.cp .view, window.cp scrolledwindow, window.cp viewport, window.cp list {
  background-color: #0c0c0e; color: #e9e6e2;
}
window.cp headerbar { background: #0c0c0e; background-image: none; color: #e9e6e2;
  border-bottom: 1px solid #2b1617; box-shadow: none; min-height: 40px; }
window.cp .sidebar { background-color: #111114; border-right: 1px solid #2b1617; }
window.cp .sidebar scrolledwindow, window.cp .sidebar viewport { background-color: #111114; }
window.cp .brand { font-weight: 800; font-size: 19px; letter-spacing: 3px; color: #e2504c; }
window.cp .brand-sub { font-size: 11px; letter-spacing: 3px; color: #9a9792; }
window.cp .section { font-size: 11px; font-weight: 700; letter-spacing: 2px; color: #e2504c; margin-top: 6px; }
window.cp .dim { color: #9a9792; }
window.cp .small { font-size: 12px; }
window.cp .strong { font-weight: 700; }
window.cp .state-ok { color: #7fc98a; font-weight: 700; }
window.cp .state-bad { color: #f0b04a; font-weight: 700; }
window.cp button.cpbtn { background-image: none; background-color: #1b1b20; color: #e9e6e2;
  border: 1px solid #3a3a41; border-radius: 4px; box-shadow: none; text-shadow: none;
  padding: 5px 12px; min-height: 22px; }
window.cp button.cpbtn:hover { border-color: #e2504c; background-color: #24191b; }
window.cp button.cpbtn:disabled { opacity: 0.4; }
window.cp button.cpbtn.primary { background-color: #c8403d; border-color: #e2504c; color: #ffffff; font-weight: 700; }
window.cp button.cpbtn.primary:hover { background-color: #e2504c; }
window.cp button.cpbtn.danger { border-color: #7d2b2a; color: #f08a86; }
window.cp button.cpbtn.danger:hover { background-color: #3a1516; border-color: #e2504c; }
window.cp button.cpbtn.tiny { padding: 1px 8px; min-height: 18px; font-size: 12px; }
window.cp entry, window.cp dropdown > button { background-image: none; background-color: #16161a; color: #e9e6e2;
  border: 1px solid #3a3a41; border-radius: 4px; box-shadow: none; min-height: 30px; }
window.cp entry:focus-within { border-color: #e2504c; outline: none; }
window.cp list.modlist { background-color: #101013; border: 1px solid #2a2a30; border-radius: 4px; }
window.cp list.modlist row { padding: 6px 10px; border-bottom: 1px solid #1c1c21; color: #e9e6e2; background-image: none; }
window.cp list.modlist row:hover { background-color: #18181c; }
window.cp list.modlist row:selected { background-color: #3a1516; color: #ffffff; }
window.cp .badge { font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 3px;
  background-color: #23232a; color: #b9b6b1; }
window.cp .badge.good { background-color: #17301c; color: #7fc98a; }
window.cp .badge.warn { background-color: #3a2c12; color: #f0b04a; }
window.cp .badge.bad { background-color: #3d1617; color: #ff8a84; }
window.cp .path { font-family: monospace; font-size: 12px; color: #d9d6d1; }
window.cp textview.output, window.cp textview.output text { background-color: #070708; color: #d6d3cf;
  font-family: monospace; font-size: 12px; }
window.cp .outframe { border-top: 1px solid #2b1617; }
window.cp stackswitcher button { background-image: none; background-color: #16161a; color: #b9b6b1;
  border: 1px solid #3a3a41; box-shadow: none; text-shadow: none; padding: 4px 16px; }
window.cp stackswitcher button:checked { background-color: #3a1516; color: #ffffff; border-color: #e2504c; }
window.cp checkbutton, window.cp label { color: inherit; }
window.cp checkbutton check, window.cp checkbutton radio { background-image: none; background-color: #16161a;
  border: 1px solid #55555e; box-shadow: none; color: transparent; }
window.cp checkbutton check:checked, window.cp checkbutton radio:checked { background-color: #c8403d;
  border-color: #e2504c; color: #ffffff; }
window.cp checkbutton:disabled { opacity: 0.6; }
window.cp switch { background-image: none; background-color: #2a2a30; border: 1px solid #44444c; box-shadow: none; }
window.cp switch:checked { background-color: #c8403d; border-color: #e2504c; }
window.cp switch:disabled { opacity: 0.5; }
window.cp switch slider { background-image: none; background-color: #e9e6e2; box-shadow: none; border: none; }
window.cp .picker-title { font-weight: 800; font-size: 16px; color: #e9e6e2; }
window.cp separator { background-color: #232329; min-height: 1px; }
window.cp .banner { background-color: #3a2c12; color: #f6d9a0; padding: 6px 12px; font-weight: 700; }
window.cp .card { background-color: #101013; border: 1px solid #2a2a30; border-radius: 4px; padding: 10px 12px; }
"""
