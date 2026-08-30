"""Generate the Gasmeter Downloader application icon.

Renders a simple, plain-color gas-meter glyph (rounded blue tile, white meter
dial with tick marks + red needle, black-on-white odometer display) into
``app/resources/Icon.png`` (256 px) and a multi-resolution ``Icon.ico``
(16/24/32/48/64/128/256) for the Windows taskbar, title bar and the
PyInstaller ``--icon`` option.

Run from the repository root:

    python scripts/generate_icon.py

Requires Pillow (installed implicitly via matplotlib in this project).
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / "app" / "resources"
OUT_PNG = RESOURCES / "Icon.png"
OUT_ICO = RESOURCES / "Icon.ico"

#: Render at 4x and downsample for crisp edges at small sizes.
SIZE = 1024
ICON_SIZES = [256, 128, 64, 48, 32, 24, 16]


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = [
        Path(r"C:\Windows\Fonts\arialbd.ttf") if bold else Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeuib.ttf") if bold else Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\DejaVuSans-Bold.ttf") if bold else Path(r"C:\Windows\Fonts\DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _vertical_gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    """Vertical gradient image ``(top, bottom)`` used as the tile fill."""
    gradient = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(size - 1, 1)
        gradient.putpixel(
            (0, y),
            (
                round(top[0] + (bottom[0] - top[0]) * t),
                round(top[1] + (bottom[1] - top[1]) * t),
                round(top[2] + (bottom[2] - top[2]) * t),
            ),
        )
    return gradient.resize((size, size))


def _draw_ticks(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    """Gas-meter dial ticks: major every 30 deg, minor every 10 deg."""
    for angle in range(0, 360, 10):
        major = angle % 30 == 0
        r_inner = 172 if major else 190
        r_outer = 218 if major else 204
        width = 12 if major else 6
        color = (30, 30, 30) if major else (120, 120, 120)
        a = math.radians(angle)
        draw.line(
            [
                (cx + r_inner * math.sin(a), cy - r_inner * math.cos(a)),
                (cx + r_outer * math.sin(a), cy - r_outer * math.cos(a)),
            ],
            fill=color,
            width=width,
        )


def _draw_needle(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    """Red needle pointing up-right (~35 deg) plus a dark hub."""
    angle = math.radians(35)
    length = 196
    tip = (cx + length * math.sin(angle), cy - length * math.cos(angle))
    # thin triangle: tip + two base corners perpendicular to the direction
    perp = (math.cos(angle), math.sin(angle))
    base_half = 16
    top = (cx - base_half * perp[0], cy - base_half * perp[1])
    bottom = (cx + base_half * perp[0], cy + base_half * perp[1])
    draw.polygon([tip, top, bottom], fill=(198, 40, 40))
    # hub
    draw.ellipse((cx - 28, cy - 28, cx + 28, cy + 28), fill=(30, 30, 30))
    draw.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), fill=(198, 40, 40))


def _draw_display(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    """Black-on-white odometer strip showing a four-digit meter reading."""
    width, height = 480, 150
    left, top = cx - width // 2, cy - height // 2
    draw.rounded_rectangle(
        (left, top, left + width, top + height),
        radius=30,
        fill=(255, 255, 255),
        outline=(40, 40, 40),
        width=8,
    )
    font = _font(120)
    digits = "1 8 3 6"
    step = width / len(digits)
    for i, char in enumerate(digits.split(" ")):
        x = left + step * i + step / 2
        draw.text((x, cy), char, font=font, fill=(25, 25, 25), anchor="mm")
        if i > 0:
            sep_x = left + step * i
            draw.line((sep_x, top + 14, sep_x, top + height - 14), fill=(150, 150, 150), width=6)


def build_icon() -> Image.Image:
    """Render the 1024 px master icon."""
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # rounded blue tile with a vertical gradient
    tile = _vertical_gradient(SIZE, (25, 118, 210), (13, 71, 161))
    tile_mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(tile_mask).rounded_rectangle((0, 0, SIZE, SIZE), radius=190, fill=255)
    image.paste(tile, (0, 0), tile_mask)

    # subtle tile border
    draw.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=190, outline=(10, 45, 100), width=16)

    # meter dial
    cx, cy = SIZE // 2, 470
    draw.ellipse((cx - 260, cy - 260, cx + 260, cy + 260), fill=(236, 239, 241))
    draw.ellipse((cx - 205, cy - 205, cx + 205, cy + 205), fill=(255, 255, 255))
    _draw_ticks(draw, cx, cy)
    _draw_needle(draw, cx, cy)

    # odometer display
    _draw_display(draw, SIZE // 2, 895)

    return image


def main() -> None:
    RESOURCES.mkdir(parents=True, exist_ok=True)
    master = build_icon()

    png = master.resize((256, 256), Image.Resampling.LANCZOS)
    png.save(OUT_PNG, "PNG")
    print(f"wrote {OUT_PNG}")

    # multi-resolution ICO (Pillow writes 16/24/32/48/64/128/256 for Windows)
    master.save(
        OUT_ICO,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)],
    )
    print(f"wrote {OUT_ICO}")


if __name__ == "__main__":
    main()
