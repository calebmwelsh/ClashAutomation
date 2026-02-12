import glob
import os
import time
from datetime import datetime

import cv2

from utils.object_detection import annotate_coords_on_image, detect_word_in_region
from utils.vision_utils import VisionUtils


class BaseActions:
    def __init__(self, window_controller, config, logger):
        self.window_controller = window_controller
        self.config = config
        self.logger = logger
        # To be overridden by subclasses if needed
        self.colors = self.config.get("Colors", {})
        # Coords to be set by subclasses
        self.coords = {} 

    def cleanup_screenshot_storage(self, base_name, limit=10):
        """
        Cleans up old screenshots for the given base_name.
        """
        dir_path = os.path.join('data', 'screenshots', base_name)
        if not os.path.exists(dir_path):
            return

        # Pattern to find existing files for this type in the subfolder
        search_pattern = os.path.join(dir_path, f'{base_name}_*.png')
        existing_files = glob.glob(search_pattern)
        
        # Sort by modification time
        existing_files.sort(key=os.path.getmtime)
        
        # If we have more than (limit - 1), delete the oldest ones
        while len(existing_files) >= limit:
            oldest_file = existing_files.pop(0)
            try:
                os.remove(oldest_file)
                self.logger.debug(f"Removed old screenshot: {oldest_file}")
            except OSError as e:
                self.logger.warning(f"Error removing file {oldest_file}: {e}")

    def manage_screenshot_storage(self, base_name, limit=10, cleanup=True):
        """
        Manages screenshot storage by keeping only the most recent 'limit' files 
        in 'data/screenshots/{base_name}/'.
        Returns the new screenshot path.
        """
        start_dt = datetime.now()
        timestamp = start_dt.strftime('%Y%m%d_%H%M%S')
        
        # Create subfolder path: data/screenshots/{base_name}
        dir_path = os.path.join('data', 'screenshots', base_name)
        os.makedirs(dir_path, exist_ok=True)
        
        new_filename = f'{base_name}_{timestamp}.png'
        new_path = os.path.join(dir_path, new_filename)
        
        if cleanup:
            self.cleanup_screenshot_storage(base_name, limit)
                
        return new_path

    def annotate_coords_on_image(self, coords, name="annotate_coords"):
        screenshot_path = self.manage_screenshot_storage(name)
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        annotate_coords_on_image(screenshot_path, coords, output_suffix='.png')

    def check_return_home_visible(self, region_key="return_home_region", default_region=[788, 888, 945, 974]):
        """
        Checks if 'Return Home' button is visible using OCR in the bottom area.
        """
        # Get region from coords if available, otherwise default
        region = self.coords.get(region_key, default_region)
        
        # We'll use a temp file for this check to avoid clutter
        temp_path = self.manage_screenshot_storage('return_home_check')
        self.window_controller.capture_minimized_window_screenshot(temp_path)
        
        # Debug: Annotate bounding box and log raw text
        if self.logger.isEnabledFor(10):
            # Draw Region Box
            try:
                img_cv = cv2.imread(temp_path)
                if img_cv is not None:
                    cv2.rectangle(img_cv, (region[0], region[1]), (region[2], region[3]), (0, 0, 255), 2)
                    debug_box_path = temp_path.replace('.png', '_debug_bbox.png')
                    cv2.imwrite(debug_box_path, img_cv)
                    self.logger.debug(f"Saved Return Home Bbox Debug to: {debug_box_path}")
            except Exception as e:
                self.logger.error(f"Failed to save debug bbox: {e}")

        # --- Color Detection ---
        color_match = False
        try:
            # Load image for color check
            temp_img = cv2.imread(temp_path)
            if temp_img is None:
                self.logger.warning(f"Failed to load image for color check: {temp_path}")
            else:
                # Crop region from temp_img
                # Check dimensions
                h, w, _ = temp_img.shape
            x1, y1, x2, y2 = region
            if x1 < 0 or y1 < 0 or x2 > w or y2 > h:
                self.logger.warning(f"Return Home region {region} out of bounds for image {w}x{h}")
            else:
                roi = temp_img[y1:y2, x1:x2]
                if roi.size > 0:
                    # Calculate avg RGB (OpenCV is BGR)
                    avg_bgr = cv2.mean(roi)[:3]
                    avg_rgb = (avg_bgr[2], avg_bgr[1], avg_bgr[0]) # Convert to RGB
                    
                    self.logger.debug(f"Return Home Region Avg RGB: {avg_rgb}")

                    target_rgb = self.colors.get("return_home_avg_rgb", [255, 255, 255])
                    
                    # Tolerance (can be moved to config later)
                    tol = 30
                    if (abs(avg_rgb[0] - target_rgb[0]) < tol and 
                        abs(avg_rgb[1] - target_rgb[1]) < tol and 
                        abs(avg_rgb[2] - target_rgb[2]) < tol):
                        
                        self.logger.debug(f"Return Home Color Matched: {avg_rgb} ~ {target_rgb}")
                        color_match = True
                    else:
                        self.logger.debug(f"Return Home Color MISMATCH: {avg_rgb} vs Target {target_rgb}")
        except Exception as e:
             self.logger.error(f"Color detection failed: {e}")
        
        if not color_match:
            self.logger.debug("Return Home: Color Check Failed. Skipping OCR.")
            return False
        
        self.logger.debug("Return Home: Color Matched. Proceeding to OCR...")
        # -----------------------

        # Perform Detection
        try:
             raw_text = VisionUtils.extract_text_from_region(VisionUtils.load_image(temp_path), region)
             # Aggressive cleaning: remove smart quotes, symbols, and extra whitespace
             clean_text = raw_text.replace('“', '"').replace('”', '"').replace('™', '').replace('"', '').replace("'", '').strip()
             self.logger.debug(f"OCR Raw Text in Return Home Region {region}: '{raw_text}' (Cleaned: '{clean_text}')")
 
             # Case-Insensitive Matching
             lower_clean = clean_text.lower()
             lower_raw = raw_text.lower()
             if "home" in lower_clean or "return" in lower_clean or "home" in lower_raw:
                 self.logger.info(f"Return Home detected via Raw Text: '{clean_text}'")
                 return True

        except Exception as e:
             self.logger.warning(f"Could not extract raw text for debug: {e}")

        found_return = detect_word_in_region(temp_path, "Return", region[0], region[1], region[2], region[3])
        if found_return: 
            self.logger.debug(f"Found 'Return': {found_return}")
            return True
            
        found_home = detect_word_in_region(temp_path, "Home", region[0], region[1], region[2], region[3])
        if found_home: 
            self.logger.debug(f"Found 'Home': {found_home}")
            return True
        
        return False
