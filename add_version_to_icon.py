#!/usr/bin/env python3

"""Add the version string from the overlay to the .ico file"""

from pathlib import Path

from PIL import Image, ImageDraw

from examples.overlay import VERSION_STRING


class Color:
    BLACK = (0, 0, 0, 255)
    RED = (230, 0, 0, 255)


if __name__ == "__main__":
    pyinstaller_dir = Path(__file__).parent / "pyinstaller"

    text_bg_color = Color.RED

    original_length = len(VERSION_STRING) * 10
    original_height = 11

    canvas = Image.new(
        mode="RGBA",
        size=(original_length, original_height),
        color=text_bg_color,
    )

    draw = ImageDraw.Draw(canvas)
    draw.text((1, 0), VERSION_STRING, fill=Color.BLACK)

    # Scan for first column containing text from the right
    for x in range(original_length - 1, -1, -1):
        for y in range(original_height):
            if canvas.getpixel((x, y)) != text_bg_color:
                break
        else:  # No break -> all pixels are background
            continue
        break

    # Include all the text, plus one column of padding
    cropped_length = x + 2

    cropped_canvas = canvas.crop((0, 0, cropped_length, original_height))

    text_scaling = 3

    resized_canvas = cropped_canvas.resize(
        (cropped_length * text_scaling, original_height * text_scaling),
        Image.Resampling.NEAREST,
    )

    text_x = 256 - resized_canvas.size[0] - 10
    text_y = 170

    logo_img = Image.open(pyinstaller_dir / "who.ico")

    logo_img.paste(resized_canvas, box=(text_x, text_y))
    logo_img.save(pyinstaller_dir / "who_with_version.ico")
