#!/usr/bin/env python3
"""Darken lightly filled OMR bubbles in a scanned sheet.

The script detects compact, round-ish gray/dark components (filled bubbles),
filters out thin unfilled outlines and text, then darkens only those candidate
regions. It intentionally avoids template coordinates so it can be reused on
similar OMR scans.
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path
import shutil
import subprocess
import tempfile
import numpy as np
from PIL import Image

try:
    import cv2
    HAVE_CV2 = True
except ImportError:
    HAVE_CV2 = False

try:
    import fitz  # PyMuPDF
    HAVE_FITZ = True
except ImportError:
    HAVE_FITZ = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Darken faintly shaded OMR bubbles in an input image or PDF."
    )
    parser.add_argument("input", help="Input image or PDF path")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output path (default: <input_stem>_darkened.png/pdf)",
    )
    parser.add_argument(
        "--pdf-dpi",
        type=int,
        default=200,
        help="DPI used when rasterizing PDF input pages (default: 200).",
    )
    parser.add_argument(
        "--pdftoppm",
        default=None,
        help="Path to pdftoppm. By default, the script searches PATH.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=205,
        help="Pixels darker than this are considered possible marks (default: 205).",
    )
    parser.add_argument(
        "--factor",
        type=float,
        default=0.22,
        help="Brightness multiplier applied to detected bubble fills (default: 0.22).",
    )
    parser.add_argument(
        "--min-diameter-ratio",
        type=float,
        default=0.008,
        help="Minimum candidate diameter as a ratio of the shorter image side.",
    )
    parser.add_argument(
        "--max-diameter-ratio",
        type=float,
        default=0.034,
        help="Maximum candidate diameter as a ratio of the shorter image side.",
    )
    parser.add_argument(
        "--debug-mask",
        default=None,
        help=(
            "Optional mask output path. For PDF input, this is used as a directory "
            "for per-page masks."
        ),
    )
    return parser.parse_args()


def luminance(rgb: np.ndarray) -> np.ndarray:
    if rgb.ndim == 2:
        return rgb.astype(np.uint8)
    rgb_float = rgb.astype(np.float32)
    return (
        0.299 * rgb_float[:, :, 0]
        + 0.587 * rgb_float[:, :, 1]
        + 0.114 * rgb_float[:, :, 2]
    ).astype(np.uint8)


def dilate(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    result = mask.copy()
    for _ in range(iterations):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        result = (
            padded[:-2, :-2]
            | padded[:-2, 1:-1]
            | padded[:-2, 2:]
            | padded[1:-1, :-2]
            | padded[1:-1, 1:-1]
            | padded[1:-1, 2:]
            | padded[2:, :-2]
            | padded[2:, 1:-1]
            | padded[2:, 2:]
        )
    return result


def connected_components(mask: np.ndarray):
    if HAVE_CV2:
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            mask.astype(np.uint8), connectivity=8
        )
        for label in range(1, num_labels):
            min_x = stats[label, cv2.CC_STAT_LEFT]
            min_y = stats[label, cv2.CC_STAT_TOP]
            box_w = stats[label, cv2.CC_STAT_WIDTH]
            box_h = stats[label, cv2.CC_STAT_HEIGHT]
            area = stats[label, cv2.CC_STAT_AREA]
            max_x = min_x + box_w - 1
            max_y = min_y + box_h - 1

            local_mask = (labels[min_y : max_y + 1, min_x : max_x + 1] == label)
            ys, xs = np.nonzero(local_mask)
            ys = ys + min_y
            xs = xs + min_x
            pixels = list(zip(ys, xs))
            yield {
                "pixels": pixels,
                "area": area,
                "bbox": (min_x, min_y, max_x, max_y),
            }
    else:
        height, width = mask.shape
        visited = np.zeros(mask.shape, dtype=bool)

        for start_y in range(height):
            xs = np.flatnonzero(mask[start_y] & ~visited[start_y])
            for start_x in xs:
                if visited[start_y, start_x]:
                    continue

                queue = deque([(start_y, int(start_x))])
                visited[start_y, start_x] = True
                pixels = []
                min_x = max_x = int(start_x)
                min_y = max_y = start_y

                while queue:
                    y, x = queue.popleft()
                    pixels.append((y, x))
                    if x < min_x:
                        min_x = x
                    elif x > max_x:
                        max_x = x
                    if y < min_y:
                        min_y = y
                    elif y > max_y:
                        max_y = y

                    for ny in (y - 1, y, y + 1):
                        if ny < 0 or ny >= height:
                            continue
                        for nx in (x - 1, x, x + 1):
                            if nx < 0 or nx >= width or visited[ny, nx] or not mask[ny, nx]:
                                continue
                            visited[ny, nx] = True
                            queue.append((ny, nx))

                yield {
                    "pixels": pixels,
                    "area": len(pixels),
                    "bbox": (min_x, min_y, max_x, max_y),
                }


def find_bubble_mask(gray: np.ndarray, threshold: int, min_ratio: float, max_ratio: float):
    height, width = gray.shape
    short_side = min(height, width)
    min_diameter = max(8, int(short_side * min_ratio))
    max_diameter = max(min_diameter + 1, int(short_side * max_ratio))

    possible_marks = gray < threshold
    bubble_mask = np.zeros(gray.shape, dtype=bool)
    candidates = 0

    for component in connected_components(possible_marks):
        min_x, min_y, max_x, max_y = component["bbox"]
        box_w = max_x - min_x + 1
        box_h = max_y - min_y + 1
        area = component["area"]

        if not (min_diameter <= box_w <= max_diameter):
            continue
        if not (min_diameter <= box_h <= max_diameter):
            continue

        aspect = box_w / box_h
        if not (0.68 <= aspect <= 1.47):
            continue

        box_area = box_w * box_h
        density = area / box_area
        if density < 0.26:
            continue

        ys = np.array([p[0] for p in component["pixels"]], dtype=np.float32)
        xs = np.array([p[1] for p in component["pixels"]], dtype=np.float32)
        center_x = xs.mean()
        center_y = ys.mean()
        radius = max(box_w, box_h) / 2.0
        distances = np.sqrt((xs - center_x) ** 2 + (ys - center_y) ** 2)
        round_fill = np.count_nonzero(distances <= radius) / max(area, 1)
        if round_fill < 0.82:
            continue

        yy, xx = np.ogrid[min_y : max_y + 1, min_x : max_x + 1]
        local_dist = np.sqrt((xx - center_x) ** 2 + (yy - center_y) ** 2)
        disk = local_dist <= radius * 0.92
        inner_disk = local_dist <= radius * 0.52
        component_view = possible_marks[min_y : max_y + 1, min_x : max_x + 1]
        disk_density = np.count_nonzero(component_view & disk) / max(
            np.count_nonzero(disk), 1
        )
        inner_density = np.count_nonzero(component_view & inner_disk) / max(
            np.count_nonzero(inner_disk), 1
        )
        if disk_density < 0.34 or inner_density < 0.46:
            continue

        region = np.zeros(gray.shape, dtype=bool)
        region[ys.astype(np.int32), xs.astype(np.int32)] = True
        region = dilate(region, iterations=2)

        # Keep the expansion close to the component and away from white paper.
        x0 = max(0, min_x - 4)
        x1 = min(width, max_x + 5)
        y0 = max(0, min_y - 4)
        y1 = min(height, max_y + 5)
        local = np.zeros(gray.shape, dtype=bool)
        local[y0:y1, x0:x1] = (
            region[y0:y1, x0:x1]
            & (gray[y0:y1, x0:x1] < threshold + 35)
            & (gray[y0:y1, x0:x1] > 45)
        )

        bubble_mask |= local
        candidates += 1

    return bubble_mask, candidates


def darken(image_arr: np.ndarray, mask: np.ndarray, factor: float) -> np.ndarray:
    factor = min(max(factor, 0.0), 1.0)
    output = image_arr.copy().astype(np.float32)
    output[mask] *= factor
    return np.clip(output, 0, 255).astype(np.uint8)


def process_image(image: Image.Image | np.ndarray, threshold=205, factor=0.22, min_ratio=0.008, max_ratio=0.034):
    if isinstance(image, np.ndarray):
        img_arr = image
        gray = luminance(img_arr)
    else:
        img_arr = np.asarray(image.convert("RGB"))
        gray = luminance(img_arr)

    mask, candidates = find_bubble_mask(
        gray,
        threshold=threshold,
        min_ratio=min_ratio,
        max_ratio=max_ratio,
    )
    result = darken(img_arr, mask, factor)
    if isinstance(image, Image.Image):
        return Image.fromarray(result), mask, candidates
    return result, mask, candidates


def find_pdftoppm(custom_path: str | None) -> str | None:
    if custom_path:
        path = Path(custom_path)
        if not path.exists():
            raise FileNotFoundError(f"pdftoppm not found: {custom_path}")
        return str(path)
    return shutil.which("pdftoppm")


def render_pdf_pages(input_path: Path, dpi: int, pdftoppm_path: str | None, temp_dir: Path):
    if HAVE_FITZ:
        doc = fitz.open(str(input_path))
        page_paths = []
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        for index, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)
            page_path = temp_dir / f"page-{index:03d}.png"
            pix.save(str(page_path))
            page_paths.append(page_path)
        doc.close()
        return page_paths

    pdftoppm = find_pdftoppm(pdftoppm_path)
    if not pdftoppm:
        raise FileNotFoundError(
            "Neither PyMuPDF nor pdftoppm was found. Please install PyMuPDF (fitz) or Poppler."
        )

    prefix = temp_dir / "page"
    subprocess.run(
        [pdftoppm, "-r", str(dpi), "-png", str(input_path), str(prefix)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    page_paths = sorted(temp_dir.glob("page-*.png"))
    if not page_paths:
        raise RuntimeError(f"No pages were rendered from PDF: {input_path}")
    return page_paths


def save_pdf(images: list[Image.Image], output_path: Path, dpi: int) -> None:
    rgb_images = [image.convert("RGB") for image in images]
    first, rest = rgb_images[0], rgb_images[1:]
    first.save(output_path, save_all=True, append_images=rest, resolution=dpi)


def process_pdf(input_path: Path, output_path: Path, args: argparse.Namespace) -> int:
    total_candidates = 0
    processed_pages = []
    debug_dir = Path(args.debug_mask) if getattr(args, "debug_mask", None) else None
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="omr_pdf_") as temp_name:
        temp_dir = Path(temp_name)
        page_paths = render_pdf_pages(input_path, getattr(args, "pdf_dpi", 200), getattr(args, "pdftoppm", None), temp_dir)

        for index, page_path in enumerate(page_paths, start=1):
            page = Image.open(page_path)
            result, mask, candidates = process_image(
                page,
                threshold=getattr(args, "threshold", 205),
                factor=getattr(args, "factor", 0.22),
                min_ratio=getattr(args, "min_diameter_ratio", 0.008),
                max_ratio=getattr(args, "max_diameter_ratio", 0.034),
            )
            processed_pages.append(result)
            total_candidates += candidates

            if debug_dir:
                mask_path = debug_dir / f"{input_path.stem}_page_{index:03d}_mask.png"
                Image.fromarray((mask * 255).astype(np.uint8)).save(mask_path)

    save_pdf(processed_pages, output_path, getattr(args, "pdf_dpi", 200))
    return total_candidates


def process_raster_image(input_path: Path, output_path: Path, args: argparse.Namespace) -> int:
    image = Image.open(input_path)
    result, mask, candidates = process_image(
        image,
        threshold=getattr(args, "threshold", 205),
        factor=getattr(args, "factor", 0.22),
        min_ratio=getattr(args, "min_diameter_ratio", 0.008),
        max_ratio=getattr(args, "max_diameter_ratio", 0.034),
    )

    result.save(output_path)
    if getattr(args, "debug_mask", None):
        Image.fromarray((mask * 255).astype(np.uint8)).save(args.debug_mask)
    return candidates


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: '{input_path}'")

    is_pdf = input_path.suffix.lower() == ".pdf"
    default_extension = "pdf" if is_pdf else "png"
    output_path = (
        Path(args.output)
        if args.output
        else input_path.with_name(f"{input_path.stem}_darkened.{default_extension}")
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if is_pdf:
        candidates = process_pdf(input_path, output_path, args)
    else:
        candidates = process_raster_image(input_path, output_path, args)

    print(f"Detected and darkened {candidates} bubble-like marks.")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
