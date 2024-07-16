import xml.etree.ElementTree as ET
from svgpathtools import parse_path
from PIL import Image, ImageDraw
import numpy as np
import json
import os


def extract_paths_data(svg_file):
    tree = ET.parse(svg_file)
    root = tree.getroot()
    paths = root.findall(".//{http://www.w3.org/2000/svg}path")

    width = height = None
    if "width" in root.attrib and "height" in root.attrib:
        width = int(float(root.attrib["width"]))
        height = int(float(root.attrib["height"]))
    else:
        viewbox = root.attrib.get("viewBox")
        if viewbox:
            _, _, width, height = map(float, viewbox.split())
            width, height = int(width), int(height)

    return [path.get("d") for path in paths], width, height


def parse_svg_paths(path_data_list):
    return [parse_path(d) for d in path_data_list]


def create_frame(paths, progress, width, height, color, stroke_width):
    img = Image.new("RGBA", (width, height), color=(255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    xmin = min(path.bbox()[0] for path in paths)
    xmax = max(path.bbox()[1] for path in paths)
    ymin = min(path.bbox()[2] for path in paths)
    ymax = max(path.bbox()[3] for path in paths)

    scale_x = width / (xmax - xmin)
    scale_y = height / (ymax - ymin)
    scale = min(scale_x, scale_y)

    offset_x = (width - (xmax - xmin) * scale) / 2 - xmin * scale
    offset_y = (height - (ymax - ymin) * scale) / 2 - ymin * scale

    total_paths = len(paths)
    current_path_index = int(progress * total_paths)

    for i, path in enumerate(paths):
        if i < current_path_index:
            for segment in path:
                points = [segment.point(t) for t in np.linspace(0, 1, 100)]
                draw.line(
                    [
                        (p.real * scale + offset_x, p.imag * scale + offset_y)
                        for p in points
                    ],
                    fill=color,
                    width=stroke_width,
                )
        elif i == current_path_index:
            path_progress = (progress * total_paths) % 1
            current_length = 0
            path_length = path.length()

            for segment in path:
                seg_length = segment.length()
                seg_progress = min(
                    (path_progress * path_length - current_length) / seg_length, 1
                )

                if seg_progress > 0:
                    points = [
                        segment.point(t) for t in np.linspace(0, seg_progress, 100)
                    ]
                    draw.line(
                        [
                            (p.real * scale + offset_x, p.imag * scale + offset_y)
                            for p in points
                        ],
                        fill=color,
                        width=stroke_width,
                    )

                current_length += seg_length
                if current_length >= path_progress * path_length:
                    break

    return img


def create_animation(paths, width, height, duration, fps, color, stroke_width):
    frames = []
    n_frames = duration * fps

    for i in range(n_frames):
        progress = (i + 1) / n_frames
        frame = create_frame(paths, progress, width, height, color, stroke_width)
        frames.append(frame)

    return frames


def load_config():
    config_file = "config.json"
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            return json.load(f)
    else:
        return {
            "svg_file": "input.svg",
            "output_file": "output.gif",
            "duration": 5,
            "fps": 30,
            "use_white": False,
            "stroke_width": 2,
        }


def save_config(config):
    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)


def get_user_input(prompt, default):
    user_input = input(f"{prompt} (default: {default}): ").strip()
    return user_input if user_input else default


def main():
    print("Welcome to the SVG to GIF Animator!")
    config = load_config()

    config["svg_file"] = get_user_input(
        "Enter the name of your SVG file", config["svg_file"]
    )
    config["output_file"] = get_user_input(
        "Enter the name for the output GIF", config["output_file"]
    )
    config["duration"] = int(
        get_user_input(
            "Enter the duration of the animation in seconds", config["duration"]
        )
    )
    config["fps"] = int(get_user_input("Enter the frames per second", config["fps"]))
    config["use_white"] = (
        get_user_input(
            "Use white color for writing? (yes/no)",
            "yes" if config["use_white"] else "no",
        ).lower()
        == "yes"
    )
    config["stroke_width"] = int(
        get_user_input("Enter the stroke width", config["stroke_width"])
    )

    save_config(config)

    paths_data, width, height = extract_paths_data(config["svg_file"])
    paths = parse_svg_paths(paths_data)

    if width is None or height is None:
        print("Could not extract dimensions from SVG. Using default values.")
        width, height = 800, 600
    else:
        print(f"Extracted dimensions from SVG: {width}x{height}")

    color = (255, 255, 255, 255) if config["use_white"] else (0, 0, 0, 255)
    frames = create_animation(
        paths,
        width,
        height,
        config["duration"],
        config["fps"],
        color,
        config["stroke_width"],
    )

    frames[0].save(
        config["output_file"],
        save_all=True,
        append_images=frames[1:],
        optimize=False,
        duration=int(1000 / config["fps"]),
        loop=0,
        disposal=2,
        transparency=0,
    )
    print(f"Animation saved as {config['output_file']}")


if __name__ == "__main__":
    main()
