import os
import re

import cv2
import numpy as np
import pytesseract
from PIL import Image


class VisionUtils:
    @staticmethod
    def load_image(image_path):
        """Loads an image from path and converts to BGR (OpenCV format)."""
        img = Image.open(image_path)
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    @staticmethod
    def save_annotated_image(image, original_path, suffix, force_save=True):
        """Saves the annotated image for debugging."""
        from utils.settings import logger
        if not force_save and not logger.isEnabledFor(10):
             return
        image_path_split = original_path.split("\\")
        # Ensure we don't mess up paths if / is used
        if len(image_path_split) == 1:
             image_path_split = original_path.split("/")
             
        name_part = image_path_split[-1].split(".")[0]
        # constructing new name
        image_name = f"{name_part}{suffix}"
        
        # reconstruct directory
        base_dir = os.path.dirname(original_path)
        output_path = os.path.join(base_dir, image_name)
        
        cv2.imwrite(output_path, image)
        # print(f"Saved debug image to {output_path}")
        return output_path

    @staticmethod
    def draw_region(image, region, color=(0, 255, 0), thickness=2):
        """Draws a rectangle on the image."""
        x1, y1, x2, y2 = region
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)

    @staticmethod
    def get_average_color(image, region):
        """Returns the average (b, g, r) color tuple for a region."""
        x1, y1, x2, y2 = region
        # Ensure region is at least 1x1 (handle scaling collapse)
        if x2 <= x1: x2 = x1 + 1
        if y2 <= y1: y2 = y1 + 1
        
        region_img = image[y1:y2, x1:x2]
        avg_color_per_row = np.average(region_img, axis=0)
        avg_color = np.average(avg_color_per_row, axis=0)
        return tuple(avg_color) # (b, g, r)

    @staticmethod
    def extract_text_from_region(image, region, config='--psm 6'):
        """Extracts text from a region using Tesseract."""
        x1, y1, x2, y2 = region
        region_img = image[y1:y2, x1:x2]
        return pytesseract.image_to_string(region_img, config=config)

    @staticmethod
    def correct_ocr_text_to_numbers(text):
        """Corrects common OCR mistakes for numbers."""
        corrections = {
            'S': '5', 's': '5', 'O': '0', 'o': '0',
            'I': '1', 'l': '1', 'B': '8',
        }
        return ''.join(corrections.get(char, char) for char in text)

    @staticmethod
    def extract_numbers(text):
        """Extracts text, corrects common errors, and finds all number sequences."""
        corrected = VisionUtils.correct_ocr_text_to_numbers(text)
        return re.findall(r'\d+', corrected)

    @staticmethod
    def color_distance(c1, c2):
        """Calculates euclidean distance between two colors."""
        return np.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))

    @staticmethod
    def is_color_close(c1, c2, threshold=20):
        """Checks if two colors are within a threshold."""
        return all(abs(a - b) <= threshold for a, b in zip(c1, c2))
