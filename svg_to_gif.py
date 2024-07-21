import xml.etree.ElementTree as ET
from svgpathtools import parse_path
from PIL import Image, ImageDraw
import numpy as np
import colorsys


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


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def get_variable_width(t, base_width, max_width):
    # Define the length of the tapering effect (e.g., first and last 15% of the stroke)
    taper_length = 0.05

    if t < taper_length:
        # Start thin and increase to max_width
        return base_width + (max_width - base_width) * (t / taper_length)
    elif t > (1 - taper_length):
        # Start at max_width and decrease to base_width
        return base_width + (max_width - base_width) * ((1 - t) / taper_length)
    else:
        # Middle section maintains max_width
        return max_width


def get_rainbow_color(progress):
    hue = progress % 1.0
    rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return tuple(int(x * 255) for x in rgb)


def create_frame(
    paths,
    progress,
    width,
    height,
    color,
    base_stroke_width,
    use_variable_width,
    padding,
    is_loopback,
    use_rainbow_mode,
):
    img = Image.new("RGBA", (width, height), color=(255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    xmin = min(path.bbox()[0] for path in paths)
    xmax = max(path.bbox()[1] for path in paths)
    ymin = min(path.bbox()[2] for path in paths)
    ymax = max(path.bbox()[3] for path in paths)

    content_width = xmax - xmin
    content_height = ymax - ymin

    scale_x = (width - 2 * padding) / content_width
    scale_y = (height - 2 * padding) / content_height
    scale = min(scale_x, scale_y)

    offset_x = (
        padding + (width - 2 * padding - content_width * scale) / 2 - xmin * scale
    )
    offset_y = (
        padding + (height - 2 * padding - content_height * scale) / 2 - ymin * scale
    )

    total_length = sum(path.length() for path in paths)
    current_length = 0

    for path in paths:
        path_length = path.length()
        path_start_progress = current_length / total_length
        path_end_progress = (current_length + path_length) / total_length

        if progress <= path_start_progress:
            continue
        elif progress >= path_end_progress:
            # Draw the entire path
            if use_rainbow_mode:
                path_color = get_rainbow_color(path_start_progress)
            else:
                path_color = color
            draw_path(
                draw,
                path,
                scale,
                offset_x,
                offset_y,
                path_color,
                base_stroke_width,
                use_variable_width,
                0,
                1,
                is_loopback,
                use_rainbow_mode,
                path_start_progress,
                path_end_progress,
            )
        else:
            # Draw partial path
            path_progress = (progress - path_start_progress) / (
                path_end_progress - path_start_progress
            )
            if use_rainbow_mode:
                path_color = get_rainbow_color(
                    path_start_progress
                    + path_progress * (path_end_progress - path_start_progress)
                )
            else:
                path_color = color
            draw_path(
                draw,
                path,
                scale,
                offset_x,
                offset_y,
                path_color,
                base_stroke_width,
                use_variable_width,
                0,
                path_progress,
                is_loopback,
                use_rainbow_mode,
                path_start_progress,
                path_end_progress,
            )
            break

        current_length += path_length

    return img


def draw_path(
    draw,
    path,
    scale,
    offset_x,
    offset_y,
    color,
    base_stroke_width,
    use_variable_width,
    start,
    end,
    is_loopback,
    use_rainbow_mode,
    path_start_progress,
    path_end_progress,
):
    cumulative_length = np.cumsum([seg.length() for seg in path])
    total_path_length = cumulative_length[-1]

    points = []
    widths = []
    colors = []

    for i, segment in enumerate(path):
        seg_start = cumulative_length[i - 1] / total_path_length if i > 0 else 0
        seg_end = cumulative_length[i] / total_path_length

        if end <= seg_start:
            break
        if start >= seg_end:
            continue

        t_start = max(0, (start - seg_start) / (seg_end - seg_start))
        t_end = min(1, (end - seg_start) / (seg_end - seg_start))

        if is_loopback:
            t_end = min(t_end, 0.4)

        num_points = max(50, int(500 * segment.length() / total_path_length))
        t_values = np.linspace(t_start, t_end, num_points)
        seg_points = [segment.point(t) for t in t_values]
        points.extend(seg_points)

        if use_variable_width:
            global_t_values = np.linspace(
                seg_start + t_start * (seg_end - seg_start),
                seg_start + t_end * (seg_end - seg_start),
                num_points,
            )
            seg_widths = [
                get_variable_width(t, base_stroke_width, base_stroke_width * 2)
                for t in global_t_values
            ]
            widths.extend(seg_widths)
        else:
            widths.extend([base_stroke_width] * num_points)

        if use_rainbow_mode:
            seg_colors = [
                get_rainbow_color(
                    path_start_progress
                    + (path_end_progress - path_start_progress)
                    * (seg_start + t * (seg_end - seg_start))
                )
                for t in t_values
            ]
            colors.extend(seg_colors)

    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        w = (widths[i] + widths[i + 1]) / 2
        if use_rainbow_mode:
            line_color = colors[i]
        else:
            line_color = color
        draw.line(
            [
                (p1.real * scale + offset_x, p1.imag * scale + offset_y),
                (p2.real * scale + offset_x, p2.imag * scale + offset_y),
            ],
            fill=line_color,
            width=int(w),
            joint="curve",
        )


def create_animation(
    paths,
    width,
    height,
    duration,
    fps,
    color,
    base_stroke_width,
    use_variable_width,
    linger_time,
    padding,
    is_loopback,
    use_rainbow_mode,
):
    total_frames = int((duration + linger_time) * fps)
    animation_frames = int(duration * fps)
    linger_frames = total_frames - animation_frames

    frames = []

    for i in range(animation_frames):
        progress = (i + 1) / animation_frames
        frame = create_frame(
            paths,
            progress,
            width,
            height,
            color,
            base_stroke_width,
            use_variable_width,
            padding,
            is_loopback,
            use_rainbow_mode,
        )
        frames.append(frame)

    last_frame = frames[-1]
    frames.extend([last_frame] * linger_frames)

    return frames


def get_user_input(prompt, default):
    user_input = input(f"{prompt} (default: {default}): ").strip()
    return user_input if user_input else default


def main():
    print("--- Handwriting Animator 2024 ---")

    svg_file = get_user_input("Enter the name of your SVG file", "input.svg")
    output_file = os.path.splitext(svg_file)[0] + ".gif"
    is_loopback = (
        get_user_input(
            "Is this file an unedited file from Calligrapher.ai? (y/n)", "y"
        ).lower()
        == "y"
    )
    duration = float(
        get_user_input("Enter the duration of the animation in seconds", "4")
    )
    fps = int(get_user_input("Enter the frames per second", "30"))
    rainbow_mode = get_user_input("Rainbow mode? (y/n)", "n").lower() == "y"
    color_hex = (
        get_user_input("Enter the color for the animation (hex code)", "#000000")
        if not rainbow_mode
        else "#000000"
    )

    base_stroke_width = int(get_user_input("Enter the base stroke width", "2"))
    use_variable_width = (
        get_user_input("Use variable width for tapering strokes? (y/n)", "y").lower()
        == "y"
    )
    linger_time = float(get_user_input("Enter the linger time in seconds", "1"))

    padding = 0.05

    paths_data, width, height = extract_paths_data(svg_file)
    paths = parse_svg_paths(paths_data)

    if width is None or height is None:
        print("Could not extract dimensions from SVG. Using default values.")
        width, height = 800, 600
    else:
        print(f"Extracted dimensions from SVG: {width}x{height}")

    print("Now Cooking")

    color_rgb = hex_to_rgb(color_hex)
    color = color_rgb + (255,)  # Add alpha channel for full opacity

    frames = create_animation(
        paths,
        width,
        height,
        duration,
        fps,
        color,
        base_stroke_width,
        use_variable_width,
        linger_time,
        padding,
        is_loopback,
        rainbow_mode,
    )

    frames[0].save(
        output_file,
        save_all=True,
        append_images=frames[1:],
        optimize=False,
        duration=int(1000 / fps),
        loop=0,
        disposal=2,
        transparency=0,
    )
    print(f"Animation saved as {output_file}")


if __name__ == "__main__":
    main()
