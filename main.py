#!/usr/bin/env python3
"""Main entry point for OMRChecker and OMR Bubble Darkener.

Supports both:
1. Bubble Darkener mode:
   python3 main.py input.jpg -o output_darkened.png
   python3 main.py input.pdf -o output_darkened.pdf

2. OMR Evaluation mode:
   python3 main.py --inputDir ./inputs --outputDir ./outputs
"""

import sys
import argparse
from pathlib import Path

from src.entry import entry_point


def entry_point_for_args(args: dict) -> None:
    input_paths = args.get("input_paths", [])
    if not input_paths and "inputDir" in args:
        input_paths = [args["inputDir"]]

    for root_path in input_paths:
        entry_point(Path(root_path), args)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="OMR Processing and Bubble Darkener Engine",
        add_help=False,
    )
    
    # Check if user is invoking OMR evaluation mode or Darken mode
    # OMR options
    parser.add_argument("--inputDir", "--input-dir", dest="inputDir", help="Path to input directory containing OMR sheets")
    parser.add_argument("--outputDir", "--output-dir", dest="outputDir", default="outputs", help="Path to output directory")
    parser.add_argument("--autoAlign", action="store_true", help="Enable auto alignment")
    parser.add_argument("--setLayout", action="store_true", help="Show template layouts")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    # Darken options (matching pdf-darken.py)
    parser.add_argument("input", nargs="?", default=None, help="Input image or PDF file path for darkening")
    parser.add_argument("-o", "--output", default=None, help="Output file path for darkened image/PDF")
    parser.add_argument("--pdf-dpi", type=int, default=200, help="PDF rasterization DPI")
    parser.add_argument("--pdftoppm", default=None, help="Path to pdftoppm executable")
    parser.add_argument("--threshold", type=int, default=205, help="Mark threshold (default: 205)")
    parser.add_argument("--factor", type=float, default=0.22, help="Brightness multiplier (default: 0.22)")
    parser.add_argument("--min-diameter-ratio", type=float, default=0.008, help="Min bubble diameter ratio")
    parser.add_argument("--max-diameter-ratio", type=float, default=0.034, help="Max bubble diameter ratio")
    parser.add_argument("--debug-mask", default=None, help="Output debug mask path/dir")
    parser.add_argument("-h", "--help", action="store_true", help="Show help message")

    return parser, parser.parse_known_args()


def main():
    parser, (args, unknown) = parse_arguments()

    if args.help:
        parser.print_help()
        sys.exit(0)

    # Determine execution mode:
    # 1. Darken mode: if positional input file is provided or output/factor/threshold specific args are passed
    if args.input and (Path(args.input).is_file() or args.input.endswith((".pdf", ".png", ".jpg", ".jpeg"))):
        from pdf_darken import process_pdf, process_raster_image
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: Input file '{input_path}' does not exist.")
            sys.exit(1)

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

    # 2. OMR Evaluation mode:
    elif args.inputDir or args.setLayout or unknown:
        if not args.inputDir:
            print("Error: --inputDir is required for OMR evaluation mode.")
            sys.exit(1)

        omr_args = {
            "input_paths": [args.inputDir],
            "output_dir": args.outputDir,
            "autoAlign": args.autoAlign,
            "setLayout": args.setLayout,
            "debug": args.debug,
            "silent": False,
        }
        entry_point_for_args(omr_args)

    else:
        parser.print_help()


if __name__ == "__main__":
    # Import pdf_darken dynamically if needed
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    main()
