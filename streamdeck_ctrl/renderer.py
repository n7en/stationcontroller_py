"""
Button image renderer for Stream Deck keys.

Requires Pillow (pip install Pillow).  The streamdeck library is also needed
but is imported only in manager.py so this module can be unit-tested standalone.
"""
from __future__ import annotations

from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# ── Colour palette ────────────────────────────────────────────────────────────
_BG_OFF      = (30,  30,  38)
_BG_ON       = (30, 140,  60)
_BG_SELECTED = (30,  90, 200)
_BG_TUNE     = (80,  40, 160)
_BG_BLANK    = (20,  20,  26)
_FG_BRIGHT   = (240, 240, 240)
_FG_DIM      = (130, 130, 140)
_FG_ON       = (200, 255, 200)
_FG_SELECTED = (180, 210, 255)


def _load_font(size: int) -> "ImageFont.ImageFont":
    candidates = [
        "DejaVuSans-Bold.ttf",
        "Arial Bold.ttf",
        "arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (IOError, OSError):
            pass
    return ImageFont.load_default()


def render_button(
    width: int,
    height: int,
    *,
    btn_type: str = "blank",
    label: str = "",
    state_text: str = "",
    active: bool = False,
    margin: int = 6,
) -> "Image.Image":
    """
    Return a PIL Image sized *width* × *height* for a Stream Deck key.

    btn_type  : 'relay_toggle' | 'coax_select' | 'radio_tune' | 'blank'
    label     : top line (small, muted)
    state_text: bottom line (large, bright) — e.g. "ON", "Port 2", "14.225"
    active    : whether this button is in its active/on state
    """
    if not _PIL_AVAILABLE:
        raise RuntimeError("Pillow is required for Stream Deck rendering: pip install Pillow")

    if btn_type == "blank":
        img = Image.new("RGB", (width, height), _BG_BLANK)
        return img

    if btn_type == "relay_toggle":
        bg = _BG_ON if active else _BG_OFF
        fg_state = _FG_ON if active else _FG_DIM
    elif btn_type == "coax_select":
        bg = _BG_SELECTED if active else _BG_OFF
        fg_state = _FG_SELECTED if active else _FG_DIM
    elif btn_type == "radio_tune":
        bg = _BG_TUNE
        fg_state = _FG_BRIGHT
    else:
        bg = _BG_OFF
        fg_state = _FG_DIM

    img  = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    label_font = _load_font(max(10, width // 8))
    state_font = _load_font(max(14, width // 5))

    # Label (top, small, dimmed)
    if label:
        lbl = label[:14]
        try:
            lw = draw.textlength(lbl, font=label_font)
        except AttributeError:
            lw = label_font.getlength(lbl)
        draw.text(
            ((width - lw) / 2, margin),
            lbl,
            font=label_font,
            fill=_FG_DIM,
        )

    # State text (centre, large, bright)
    if state_text:
        st = state_text[:10]
        try:
            sw = draw.textlength(st, font=state_font)
        except AttributeError:
            sw = state_font.getlength(st)
        draw.text(
            ((width - sw) / 2, height // 2 - state_font.size // 2),
            st,
            font=state_font,
            fill=fg_state,
        )

    # Bottom accent bar for active state
    if active and btn_type != "radio_tune":
        bar_h = max(3, height // 18)
        draw.rectangle(
            [margin, height - margin - bar_h, width - margin, height - margin],
            fill=_FG_BRIGHT,
        )

    return img
