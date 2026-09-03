import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import cv2
from pdf_darken import find_bubble_mask, darken, process_image, luminance
from src.processors.DarkenBubbles import DarkenBubbles


def test_luminance():
    # 3D RGB array
    rgb = np.zeros((100, 100, 3), dtype=np.uint8) + 200
    gray = luminance(rgb)
    assert gray.shape == (100, 100)
    assert np.allclose(gray[0, 0], 200, atol=2)


def test_faint_bubble_darkening():
    # Create a synthetic white page with a faint gray bubble
    height, width = 500, 500
    img = np.zeros((height, width), dtype=np.uint8) + 250  # White paper

    # Draw a faint gray filled bubble (gray level 180, diameter ~12px)
    cv2.circle(img, (250, 250), 6, 180, -1)

    # Before darkening: circle center is 180
    assert img[250, 250] == 180

    darkened_img, mask, candidates = process_image(img, threshold=205, factor=0.22, min_ratio=0.008, max_ratio=0.034)

    assert candidates > 0
    assert mask[250, 250] == True
    # After darkening: value should be significantly lower (darker)
    assert darkened_img[250, 250] < 100


def test_darken_bubbles_preprocessor():
    class DummyImageInstanceOps:
        tuning_config = None

    ops = DummyImageInstanceOps()
    preprocessor = DarkenBubbles(options={"threshold": 205, "factor": 0.22}, image_instance_ops=ops)

    img = np.zeros((500, 500), dtype=np.uint8) + 250
    cv2.circle(img, (100, 100), 6, 175, -1)

    res = preprocessor.apply_filter(img, "test.png")
    assert res is not None
    assert res[100, 100] < 100


if __name__ == "__main__":
    test_luminance()
    test_faint_bubble_darkening()
    test_darken_bubbles_preprocessor()
    print("All darken tests passed successfully!")
