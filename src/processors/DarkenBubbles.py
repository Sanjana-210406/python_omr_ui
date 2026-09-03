import cv2
import numpy as np

from src.processors.interfaces.ImagePreprocessor import ImagePreprocessor
from pdf_darken import find_bubble_mask, darken, luminance


class DarkenBubbles(ImagePreprocessor):
    """Pre-processor to darken faint gray OMR bubble fills before alignment and bubble reading."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        options = self.options or {}
        self.threshold = int(options.get("threshold", 205))
        self.factor = float(options.get("factor", 0.22))
        self.min_ratio = float(options.get("min_diameter_ratio", 0.008))
        self.max_ratio = float(options.get("max_diameter_ratio", 0.034))

    def apply_filter(self, image, file_path):
        if image is None:
            return None

        if image.ndim == 2:
            gray = image
        elif image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = luminance(image)

        mask, count = find_bubble_mask(
            gray,
            threshold=self.threshold,
            min_ratio=self.min_ratio,
            max_ratio=self.max_ratio,
        )

        if count > 0:
            darkened_img = darken(image, mask, self.factor)
            return darkened_img

        return image


class Darken(DarkenBubbles):
    """Alias for DarkenBubbles preprocessor."""
    pass
