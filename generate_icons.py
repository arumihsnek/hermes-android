#!/usr/bin/env python3
"""Generate Android launcher icons from Arcticons-style SVG icon."""
import io
import os
from PIL import Image, ImageDraw

import cairosvg

# The SVG icon path
svg_path = "/home/ubuntu/.hermes/webui/attachments/36d0de67ab51/hermes-bridge.arcticons.svg"

# Output directories
base = "/home/ubuntu/code/hermes-android/hermes-android-bridge/app/src/main/res"

# Android icon densities (size in pixels for the full icon area)
DENSITIES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}

# App brand colors
BG_COLOR = (30, 30, 50)  # dark indigo background
ACCENT_COLOR = (100, 160, 255)  # light blue accent

def create_launcher_icon(size, round_icon=False):
    """Create a launcher icon with the SVG on a colored background."""
    # First render the SVG at the target size
    svg_content = open(svg_path).read()
    
    # For mdpi base, the SVG is 48x48. We scale proportionally.
    png_data = cairosvg.svg2png(bytestring=svg_content, output_width=size, output_height=size)
    
    # Load the white line art
    icon_img = Image.open(io.BytesIO(png_data)).convert("RGBA")
    
    # Create the background: rounded square or circle
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bg)
    
    # Inset for the background shape (90% of size)
    margin = int(size * 0.05)
    shape_bbox = [margin, margin, size - margin, size - margin]
    
    if round_icon:
        draw.ellipse(shape_bbox, fill=BG_COLOR)
        # Add a thin stroke
        draw.ellipse(shape_bbox, outline=ACCENT_COLOR, width=max(1, size // 48))
    else:
        # Rounded square with corner radius ~20% of size
        radius = int(size * 0.2)
        draw.rounded_rectangle(shape_bbox, radius=radius, fill=BG_COLOR)
        draw.rounded_rectangle(shape_bbox, radius=radius, outline=ACCENT_COLOR, width=max(1, size // 48))
    
    # Scale the SVG icon to fit inside the background (70% of size with padding)
    icon_size = int(size * 0.55)
    icon_resized = icon_img.resize((icon_size, icon_size), Image.LANCZOS)
    
    # Center the icon on the background
    x_offset = (size - icon_size) // 2
    y_offset = (size - icon_size) // 2
    
    # Composite: place white line art on colored background
    result = bg.copy()
    result.paste(icon_resized, (x_offset, y_offset), icon_resized)
    
    return result

print("Generating launcher icons...")

for density, dim in DENSITIES.items():
    for suffix, round_flag in [("", False), ("_round", True)]:
        img = create_launcher_icon(dim, round_icon=round_flag)
        
        out_dir = os.path.join(base, density)
        os.makedirs(out_dir, exist_ok=True)
        
        out_path = os.path.join(out_dir, f"ic_launcher{suffix}.png")
        img.save(out_path, "PNG")
        
        actual_size = os.path.getsize(out_path)
        print(f"  {density}/ic_launcher{suffix}.png  {dim}x{dim}  {actual_size} bytes")

print("Done! All icons generated.")
