#!/usr/bin/env python3
"""Generate Android launcher icons from Arcticons-style SVG icon.

Faithful to Arcticons: white 1px strokes on solid dark background.
No accent borders, no extra colors — just the icon.
"""
import io
import os
from PIL import Image, ImageDraw

import cairosvg

SVG_PATH = "/home/ubuntu/.hermes/webui/attachments/36d0de67ab51/hermes-bridge.arcticons.svg"
BASE = "/home/ubuntu/code/hermes-android/hermes-android-bridge/app/src/main/res"

DENSITIES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}

BG_COLOR = (27, 27, 40)  # near-black dark indigo (Arcticons style)

def create_launcher_icon(size, round_icon=False):
    """Create clean Arcticons-style launcher icon."""
    svg = open(SVG_PATH).read()

    # Render SVG at full size — cairosvg handles 1px stroke correctly
    png_data = cairosvg.svg2png(
        bytestring=svg,
        output_width=size,
        output_height=size,
    )
    icon = Image.open(io.BytesIO(png_data)).convert("RGBA")

    # Background: rounded square or circle, no border
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bg)

    inset = int(size * 0.04)  # 4% margin
    bbox = [inset, inset, size - inset, size - inset]

    if round_icon:
        draw.ellipse(bbox, fill=BG_COLOR)
    else:
        radius = int(size * 0.22)
        draw.rounded_rectangle(bbox, radius=radius, fill=BG_COLOR)

    # Scale icon to fill background with slight padding
    # The SVG is 48x48 with 1px strokes; at target size we scale
    # so the icon fills ~82% of the background area
    icon_target = int(size * 0.72)
    icon_resized = icon.resize((icon_target, icon_target), Image.LANCZOS)

    x_off = (size - icon_target) // 2
    y_off = (size - icon_target) // 2

    result = bg.copy()
    result.paste(icon_resized, (x_off, y_off), icon_resized)
    return result


print("Generating Arcticons-style launcher icons...")
for density, dim in DENSITIES.items():
    for suffix, round_flag in [("", False), ("_round", True)]:
        img = create_launcher_icon(dim, round_icon=round_flag)
        out_dir = os.path.join(BASE, density)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"ic_launcher{suffix}.png")
        img.save(out_path, "PNG")
        sz = os.path.getsize(out_path)
        print(f"  {density}/ic_launcher{suffix}.png  {dim}x{dim}  {sz} bytes")
print("Done!")
