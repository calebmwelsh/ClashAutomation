import difflib
import os
import re

import cv2
import numpy as np
import pytesseract

# Setup Logging
from utils.settings import config, logger
from utils.vision_utils import VisionUtils

# from utils.logger import Logger # Removed as we use shared logger


# Keep the standalone helpers if needed, or rely on VisionUtils


""" ----------------------------- Base Functions ----------------------------- """

def is_in_rgb_range(rgb, range_key):
    # RGB is tuple (r, g, b)
    # range_key is string key in config["ObjectDetectionRanges"]
    ranges = config.get("ObjectDetectionRanges", {}).get(range_key)
    if not ranges: 
        logger.warning(f"RGB Range key '{range_key}' not found in config.")
        return False
    min_c, max_c = ranges[0], ranges[1]
    return (min_c[0] <= rgb[0] <= max_c[0]) and \
           (min_c[1] <= rgb[1] <= max_c[1]) and \
           (min_c[2] <= rgb[2] <= max_c[2])


def determine_base_location(image_path):
    img_cv = VisionUtils.load_image(image_path)
    if img_cv is None:
        logger.error(f"Failed to load image for base determination: {image_path}")
        return False, False

    h, w, _ = img_cv.shape
    # Check pixel at 1669, 149. Ensure image is large enough.
    x, y = config["ObjectDetectionCoordinates"]["base_determination_check_pos"]
    
    if y >= h or x >= w:
         logger.error(f"Image too small ({w}x{h}) for base check at ({x},{y}).")
         return False, False

    b, g, r = img_cv[y, x]
    avg_color = (b, g, r) # OpenCV uses BGR
    
    logger.debug(f"Pixel at ({x}, {y}) - RGB: {r}, {g}, {b}")
    
    # builder base bgr list
    builder_base_bgr_list = config["ObjectDetectionColors"]["builder_base_bgr_targets"]
    # home base rgb list
    home_base_bgr_list = config["ObjectDetectionColors"]["home_base_bgr_targets"]

    is_builder_base = False
    matched_builder_bgr = None
    tolerance = config["ObjectDetectionColors"].get("base_determination_tolerance", 20)
    for target in builder_base_bgr_list:
        if VisionUtils.is_color_close(avg_color, target, tolerance):
            is_builder_base = True
            matched_builder_bgr = target
            break
    
    is_home_base = False
    matched_home_bgr = None
    for target in home_base_bgr_list:
        if VisionUtils.is_color_close(avg_color, target, tolerance):
            is_home_base = True
            matched_home_bgr = target
            break

    if is_builder_base:
        logger.debug(f"Matched Builder Base Target RGB: {matched_builder_bgr[::-1]}")
    elif is_home_base:
        logger.debug(f"Matched Home Base Target RGB: {matched_home_bgr[::-1]}")
    else:
        logger.debug(f"Did not match any base target. (Builder Targets (RGB): {[c[::-1] for c in builder_base_bgr_list]}, Home Targets (RGB): {[c[::-1] for c in home_base_bgr_list]})")

    annotated_img = img_cv.copy()
    color = (0, 255, 0) if is_builder_base or is_home_base else (0, 0, 255)
    cv2.rectangle(annotated_img, (x-1, y-1), (x+1, y+1), color, 1)
    
    VisionUtils.save_annotated_image(annotated_img, image_path, f"_point_{x}_{y}_annotated.png")
    return is_builder_base, is_home_base

def annotate_coords_on_image(image_path, coords, box_size=10, color=(0, 255, 255), output_suffix='_coords_annotated.png'):
    img_cv = VisionUtils.load_image(image_path)
    annotated_img = img_cv.copy()
    half = box_size // 2
    for (x, y) in coords:
        VisionUtils.draw_region(annotated_img, (x - half, y - half, x + half, y + half), color)
    return VisionUtils.save_annotated_image(annotated_img, image_path, output_suffix)

""" ----------------------------- Home Base Functions ----------------------------- """

def extract_resources_from_image(image_path):
    img_cv = VisionUtils.load_image(image_path)
    annotated_img = img_cv.copy()
    
    regions = [
        config["ObjectDetectionCoordinates"]["resource_collection_regions_gold"],
        config["ObjectDetectionCoordinates"]["resource_collection_regions_elixir"],
        config["ObjectDetectionCoordinates"]["resource_collection_regions_dark"]
    ]
    
    results = []
    for (x1, y1, x2, y2) in regions:
        VisionUtils.draw_region(annotated_img, (x1, y1, x2, y2), (0, 0, 255))
        text = VisionUtils.extract_text_from_region(img_cv, (x1, y1, x2, y2))
        numbers = VisionUtils.extract_numbers(text)
        
        combined_val = int(''.join(numbers)) if numbers else 0
        results.append(combined_val)

    VisionUtils.save_annotated_image(annotated_img, image_path, "_annotated.png")
    return tuple(results)

def extract_builders_available_from_image(image_path):
    img_cv = VisionUtils.load_image(image_path)
    builders_region = config["ObjectDetectionCoordinates"]["builders_roi_region"]
    
    annotated_img = img_cv.copy()
    VisionUtils.draw_region(annotated_img, builders_region, (255, 0, 0))
    
    text = VisionUtils.extract_text_from_region(img_cv, builders_region)
    numbers = VisionUtils.extract_numbers(text)
    
    logger.info(f"[Builders OCR] Numbers: '{numbers}'")
    builders_available = int(numbers[0]) if numbers else 0
    
    # Check for goblin researcher (1/7 split)
    if len(numbers) > 1 and int(numbers[0]) == 1 and int(numbers[1]) == 7:
        builders_available = 0
        
    VisionUtils.save_annotated_image(annotated_img, image_path, "_builders_annotated.png")
    return builders_available

def is_goblin_builder_in_region(image_path):
    img_cv = VisionUtils.load_image(image_path)
    region = config["ObjectDetectionCoordinates"]["goblin_builder_region"]
    
    b, g, r = VisionUtils.get_average_color(img_cv, region)
    logger.debug(f"[Goblin Builder] Average RGB: {r:.1f}, {g:.1f}, {b:.1f}")

    goblin_bgr = tuple(config["ObjectDetectionColors"]["goblin_builder_bgr"])
    tolerance = config["ObjectDetectionColors"].get("goblin_builder_tolerance", 30)
    is_goblin = VisionUtils.is_color_close((b, g, r), goblin_bgr, tolerance)
    
    annotated_img = img_cv.copy()
    VisionUtils.draw_region(annotated_img, region, (0, 255, 0) if is_goblin else (0, 0, 255))
    VisionUtils.save_annotated_image(annotated_img, image_path, "_goblin_builder_annotated.png")
    return is_goblin

def detect_hero_upgrade(image_path):
    img_cv = VisionUtils.load_image(image_path)
    squares = config["ObjectDetectionCoordinates"]["hero_upgrade_check_regions"]
    
    annotated_img = img_cv.copy()
    results = []
    for idx, region in enumerate(squares):
        b, g, r = VisionUtils.get_average_color(img_cv, region)
        logger.info(f"[Hero Upgrade Check #{idx+1}] Region {region} | RGB: ({r}, {g}, {b})")
        # Check Upgrade (From Config)
        is_white = is_in_rgb_range((r, g, b), "hero_upgrade_valid_rgb_range")
        
        VisionUtils.draw_region(annotated_img, region, (0, 255, 0) if is_white else (255, 0, 0))
        if is_white:
            results.append({'index': idx, 'pos': region, 'avg_rgb': (r, g, b)})
            
    VisionUtils.save_annotated_image(annotated_img, image_path, "_hero_upgrade_annotated.png")
    return results

def detect_info_button_color_location(image_path):
    img_cv = VisionUtils.load_image(image_path)
    squares = config["ObjectDetectionCoordinates"]["info_button_regions"]
    
    annotated_img = img_cv.copy()
    results = []
    
    for idx, region in enumerate(squares):
        b, g, r = VisionUtils.get_average_color(img_cv, region)
        
        # Check Hero Hall
        if is_in_rgb_range((r, g, b), "info_button_hero_hall_rgb_range"):
            return "hero hall"
            
        # Check Blue (High B, Low R/G)
        is_blue = is_in_rgb_range((r, g, b), "info_button_blue_rgb_range")
        
        VisionUtils.draw_region(annotated_img, region, (255, 0, 0) if is_blue else (0, 255, 0))
        if is_blue:
            results.append({'index': idx, 'pos': region, 'avg_rgb': (r, g, b), 'type': 'building'})
            
    VisionUtils.save_annotated_image(annotated_img, image_path, "_blue_squares_annotated.png")
    return results

def extract_research_available_from_image(image_path):
    img_cv = VisionUtils.load_image(image_path)
    region = config["ObjectDetectionCoordinates"]["research_available_region"]
    
    annotated_img = img_cv.copy()
    VisionUtils.draw_region(annotated_img, region, (0, 255, 0))
    
    text = VisionUtils.extract_text_from_region(img_cv, region)
    numbers = VisionUtils.extract_numbers(text)
    
    logger.info(f"[Research OCR] Numbers: '{numbers}'")
    avail = int(numbers[0]) if numbers else 0
    # Goblin check (1/2) -> 0
    if len(numbers) > 1 and int(numbers[0]) == 1 and int(numbers[1]) == 2:
        avail = 0
    if avail == 2: avail = 0
        
    VisionUtils.save_annotated_image(annotated_img, image_path, "_research_annotated.png")
    return avail

def is_goblin_researcher_in_region(image_path):
    img_cv = VisionUtils.load_image(image_path)
    region = config["ObjectDetectionCoordinates"]["goblin_researcher_region"]
    
    b, g, r = VisionUtils.get_average_color(img_cv, region)
    logger.debug(f"[Goblin Researcher] Avg RGB: {r:.1f}, {g:.1f}, {b:.1f}")
    
    goblin_bgr = tuple(config["ObjectDetectionColors"]["goblin_researcher_bgr"])
    tolerance = config["ObjectDetectionColors"].get("goblin_researcher_tolerance", 30)
    is_goblin = VisionUtils.is_color_close((b, g, r), goblin_bgr, tolerance)
    
    annotated_img = img_cv.copy()
    VisionUtils.draw_region(annotated_img, region, (0, 255, 0) if is_goblin else (0, 0, 255))
    VisionUtils.save_annotated_image(annotated_img, image_path, "_goblin_researcher_annotated.png")
    return is_goblin

def extract_pet_upgrade_available_from_image(image_path):
    img_cv = VisionUtils.load_image(image_path)
    region = config["ObjectDetectionCoordinates"]["pet_upgrade_available_region"]
    
    b, g, r = VisionUtils.get_average_color(img_cv, region)
    logger.debug(f"[Pet Upgrade Color] Avg RGB: {r:.1f}, {g:.1f}, {b:.1f}") # Debug prints RGB often
    
    # Target RGB: 182.1, 198.2, 144.4 -> BGR: 144.4, 198.2, 182.1
    target_bgr = tuple(config["ObjectDetectionColors"]["pet_upgrade_target_bgr"])
    tolerance = config["ObjectDetectionColors"].get("pet_upgrade_available_tolerance", 20)
    
    is_avail = VisionUtils.is_color_close((b, g, r), target_bgr, tolerance)
    
    return 'available' if is_avail else 'not_available'

def is_pet_max_level_from_image(image_path):
    img_cv = VisionUtils.load_image(image_path)
    region = config["ObjectDetectionCoordinates"]["pet_max_level_region"]
    
    text = VisionUtils.extract_text_from_region(img_cv, region).lower()
    keywords = ["level", "pet", "house", "required"]
    
    is_maxed = any(k in text for k in keywords)
    
    if not is_maxed:
        b, g, r = VisionUtils.get_average_color(img_cv, region)
        target_bgr = tuple(config["ObjectDetectionColors"]["pet_max_level_target_bgr"])
        tolerance = config["ObjectDetectionColors"].get("pet_max_level_tolerance", 15)
        is_maxed = VisionUtils.is_color_close((b, g, r), target_bgr, tolerance)

    annotated_img = img_cv.copy()
    VisionUtils.draw_region(annotated_img, region, (0, 255, 0) if is_maxed else (0, 0, 255))
    VisionUtils.save_annotated_image(annotated_img, image_path, "_pet_max_annotated.png")
    return is_maxed

def is_pet_upgrade_in_progress_from_image(image_path):
    img_cv = VisionUtils.load_image(image_path)
    regions = config["ObjectDetectionCoordinates"]["pet_upgrade_in_progress_regions"]
    target_bgr = tuple(config["ObjectDetectionColors"]["pet_upgrade_in_progress_bgr"])
    
    for idx, region in enumerate(regions):
        annotated_img = img_cv.copy()
        VisionUtils.draw_region(annotated_img, region, (0, 255, 255))
        
        text = VisionUtils.extract_text_from_region(img_cv, region).lower()
        if 'finish' in text or 'upgrade' in text:
            VisionUtils.save_annotated_image(annotated_img, image_path, f"_pet_in_progress_{idx}.png")
            return True
            
        b, g, r = VisionUtils.get_average_color(img_cv, region)
        tolerance = config["ObjectDetectionColors"].get("pet_upgrade_in_progress_tolerance", 20)
        if VisionUtils.is_color_close((b, g, r), target_bgr, tolerance):
            VisionUtils.save_annotated_image(annotated_img, image_path, f"_pet_in_progress_{idx}.png")
            return True
            
    return False

def detect_attack_button_color(image_path):
    img_cv = VisionUtils.load_image(image_path)
    region = config["ObjectDetectionCoordinates"]["attack_button_region"]
    
    b, g, r = VisionUtils.get_average_color(img_cv, region)
    logger.debug(f"[Attack Button] Avg RGB: {r:.1f}, {g:.1f}, {b:.1f}")
    
    if r > 100 and r > g + 40 and r > b + 40:
        result = 'red'
    elif abs(r - g) < 30 and abs(r - b) < 30 and 80 < r < 200:
        result = 'grey'
    else:
        result = 'unknown'
        
    annotated_img = img_cv.copy()
    VisionUtils.draw_region(annotated_img, region, (255, 255, 0))
    VisionUtils.save_annotated_image(annotated_img, image_path, "_attack_button_annotated.png")
    return result

def detect_apprentices_status_from_image(image_path):
    img_cv = VisionUtils.load_image(image_path)
    regions = config["ObjectDetectionCoordinates"]["apprentice_regions_map"]
    target_rgb = tuple(config["ObjectDetectionColors"]["apprentice_target_rgb"])
    status = {}
    annotated_img = img_cv.copy()
    
    for item in regions:
        region = item['region']
        name = item['name']
        text = VisionUtils.extract_text_from_region(img_cv, region)
        numbers = VisionUtils.extract_numbers(text)
        
        b, g, r = VisionUtils.get_average_color(img_cv, region)
        tolerance = config["ObjectDetectionColors"].get("apprentice_status_tolerance", 20)
        rgb_close = VisionUtils.is_color_close((r, g, b), target_rgb, tolerance)
        
        if not numbers and rgb_close:
            status[name] = 'free'
        else:
            status[name] = 'busy'
            
        if "assistant" in text.replace("5", "s").lower():
             status[name] = 'free'
             
        VisionUtils.draw_region(annotated_img, region, (0, 255, 255))
        
    VisionUtils.save_annotated_image(annotated_img, image_path, "_apprentices_annotated.png")
    return status

def extract_home_resources(image_path):
    img_cv = VisionUtils.load_image(image_path)
    regions = config["ObjectDetectionCoordinates"]["home_resources_check_regions_map"]
    annotated_img = img_cv.copy()
    results = []
    
    for item in regions:
        region = item['region']
        type_ = item['type']
        b, g, r = VisionUtils.get_average_color(img_cv, region)
        
        logger.info(f"[Resource Check] Type: {type_} | Region: {region} | RGB: ({r}, {g}, {b})")

        maxed = 0
        maxed = 0
        if type_ == 'gold':
            # High R/G, Low B
            if is_in_rgb_range((r, g, b), "resource_gold_max_rgb_range"): maxed = 1
        elif type_ == 'elixir':
            # High R/B, Low G
            if is_in_rgb_range((r, g, b), "resource_elixir_max_rgb_range"): maxed = 1
        elif type_ == 'dark':
            # Low all
            if is_in_rgb_range((r, g, b), "resource_dark_max_rgb_range"): maxed = 1
            
        results.append(maxed)
        VisionUtils.draw_region(annotated_img, region, (0, 0, 255))
        
    VisionUtils.save_annotated_image(annotated_img, image_path, "_home_resources_annotated.png")
    return tuple(results)

def detect_heroes_available(image_path):
    img_cv = VisionUtils.load_image(image_path)
    regions = config["ObjectDetectionCoordinates"]["heroes_available_regions"]
    target_grey = config["ObjectDetectionColors"]["hero_unavailable_target_grey"]
    target_purple = config["ObjectDetectionColors"].get("hero_available_target_purple", [])
    
    # Handle single color legacy cases if necessary (though config is list of lists)
    if target_grey and isinstance(target_grey[0], int): target_grey = [target_grey]
    if target_purple and isinstance(target_purple[0], int): target_purple = [target_purple]

    annotated_img = img_cv.copy()
    available = 0
    
    # Tolerance values
    tolerance_grey = config["ObjectDetectionColors"].get("hero_unavailable_tolerance", 15)
    tolerance_purple = config["ObjectDetectionColors"].get("hero_available_tolerance", 25)

    for i, region in enumerate(regions):
        b, g, r = VisionUtils.get_average_color(img_cv, region)
        avg_rgb = (r, g, b)
        VisionUtils.draw_region(annotated_img, region, (255, 0, 255))
        
        logger.info(f"[Hero Check #{i+1}] Region {region} | RGB: ({r}, {g}, {b})")

        is_available = False
        is_unavailable = False

        # Check for Available (Purple)
        for purple_target in target_purple:
            if VisionUtils.is_color_close(avg_rgb, tuple(purple_target), tolerance_purple):
                is_available = True
                break
        
        # Check for Unavailable (Grey) if not already found to be available
        if not is_available:
            for grey_target in target_grey:
                if VisionUtils.is_color_close(avg_rgb, tuple(grey_target), tolerance_grey):
                    is_unavailable = True
                    break

        if is_available:
            available += 1
            logger.debug(f"Hero #{i+1}: Available (Match: Purple)")
        elif is_unavailable:
            logger.debug(f"Hero #{i+1}: Unavailable (Match: Grey)")
        else:
            logger.debug(f"Hero #{i+1}: Unavailable (No Match - Defaulting to unavailable)")
            
    VisionUtils.save_annotated_image(annotated_img, image_path, "_heroes_annotated.png")
    return available

def detect_word_in_region(image_path, target_word, x1, y1, x2, y2, text_color='white', fuzzy_threshold=0.6):
    # This one has complex preprocessing logic (adaptive threshold for red etc)
    # Keeping it mostly intact but cleaner loading
    img_cv = VisionUtils.load_image(image_path)
    region_img = img_cv[y1:y2, x1:x2]
    
    # Preprocessing
    scale = 2.0
    upscaled = cv2.resize(region_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    
    if text_color.lower() == 'red':
        b, g, r = cv2.split(upscaled)
        r_enhanced = cv2.addWeighted(r, 2.0, cv2.bitwise_not(r), -0.5, 0)
        gray = cv2.addWeighted(r_enhanced, 0.7, g, 0.3, 0)
        gray = cv2.addWeighted(gray, 1.0, b, -0.3, 0)
        gray = cv2.bilateralFilter(gray, 7, 50, 50)
        gray = cv2.equalizeHist(gray)
        gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    else:
        gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 7, 50, 50)

    data = pytesseract.image_to_data(gray, config='--oem 3 --psm 6', output_type=pytesseract.Output.DICT)
    
    found = []
    annotated_img = img_cv.copy()
    VisionUtils.draw_region(annotated_img, (x1, y1, x2, y2), (255, 0, 0))
    
    words = data.get('text', [])
    conf = data.get('conf', [])
    left, top, w, h = data['left'], data['top'], data['width'], data['height']
    
    target_lower = target_word.lower()
    
    for i, word in enumerate(words):
        if not word.strip(): continue
        try:
             c = int(conf[i])
             if c < 30: continue
        except: continue
        
        sim = difflib.SequenceMatcher(None, target_lower, word.lower()).ratio()
        if sim >= fuzzy_threshold:
            ox1 = x1 + int(left[i] / scale)
            oy1 = y1 + int(top[i] / scale)
            ox2 = x1 + int((left[i] + w[i]) / scale)
            oy2 = y1 + int((top[i] + h[i]) / scale)
            
            VisionUtils.draw_region(annotated_img, (ox1, oy1, ox2, oy2), (0, 255, 0))
            found.append({'word': word, 'bbox': (ox1, oy1, ox2, oy2), 'confidence': c, 'similarity': sim})
            
    VisionUtils.save_annotated_image(annotated_img, image_path, f"_word_detect_{target_word}_annotated.png")
    return found

def check_region_color(image_path, region, target_color_1='red', target_color_1_rgb=None, target_color_2='white', target_color_2_rgb=None):
    if target_color_1_rgb is None:
        target_color_1_rgb = tuple(config["ObjectDetectionColors"]["check_color_target_1_rgb"])
    if target_color_2_rgb is None:
        target_color_2_rgb = tuple(config["ObjectDetectionColors"]["check_color_target_2_rgb"])
    
    img_cv = VisionUtils.load_image(image_path)
    b, g, r = VisionUtils.get_average_color(img_cv, region)
    avg_rgb = (r, g, b)
    
    tol1 = config["ObjectDetectionColors"].get("check_color_tolerance_primary", 30)
    tol2 = config["ObjectDetectionColors"].get("check_color_tolerance_secondary", 20)
    
    is_c1 = VisionUtils.is_color_close(avg_rgb, target_color_1_rgb, tol1)
    is_c2 = VisionUtils.is_color_close(avg_rgb, target_color_2_rgb, tol2)
    
    dominant = 'other'
    if is_c1: dominant = target_color_1
    elif is_c2: dominant = target_color_2
    
    return {
        'avg_rgb': avg_rgb,
        f'is_{target_color_1}': is_c1,
        f'is_{target_color_2}': is_c2,
        'dominant_color': dominant
    }

def detect_red_or_white(image_path, region, threshold=100):
    """
    Determines if a region is predominantly 'red' or 'white' using HSV pixel counting.
    More robust than average RGB when text is present.
    """
    img_cv = VisionUtils.load_image(image_path)
    if img_cv is None: 
        return 'unknown'

    x1, y1, x2, y2 = region
    roi = img_cv[y1:y2, x1:x2]
    
    # Convert to HSV
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    
    # --- Red Masks (wraps around 0/180) ---
    # Lower Red: Hue 0-10
    lower_red1 = np.array([0, 70, 50])
    upper_red1 = np.array([10, 255, 255])
    # Upper Red: Hue 170-180
    lower_red2 = np.array([170, 70, 50])
    upper_red2 = np.array([180, 255, 255])
    
    mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask_red = cv2.bitwise_or(mask_red1, mask_red2)
    
    # --- White Mask ---
    # Low Saturation, High Value
    # S < 40 (very low color), V > 200 (very bright) - adjusted for slight off-white
    lower_white = np.array([0, 0, 180])
    upper_white = np.array([180, 50, 255])
    mask_white = cv2.inRange(hsv, lower_white, upper_white)
    
    # Count pixels
    red_count = cv2.countNonZero(mask_red)
    white_count = cv2.countNonZero(mask_white)
    total_pixels = roi.shape[0] * roi.shape[1]
    
    logger.debug(f"[Detect Red/White] Region {region} | Total Pixels: {total_pixels}")
    logger.debug(f"[Detect Red/White] Red Pixels: {red_count} | White Pixels: {white_count}")

    # Decision Logic
    result = 'unknown'
    # Red text often has white outlines/anti-aliasing, so it's not purely red pixels vs white pixels.
    # We check if Red is "significant" relative to White.
    # Pure White text (Available) has very low Red count.
    # Red text (Insufficient) has High Red AND High White.
    if red_count > (white_count * 0.5) and red_count > threshold:
        result = 'red'
    elif white_count > red_count and white_count > threshold:
        result = 'white'
    
    # Debug Image Generation
    # Create a side-by-side view: Original ROI | Red Mask | White Mask
    if logger.isEnabledFor(10): # 10 is logging.DEBUG
        try:
           roi_debug = roi.copy()
           
           # Convert masks to BGR for concatenation
           mask_red_bgr = cv2.cvtColor(mask_red, cv2.COLOR_GRAY2BGR)
           mask_white_bgr = cv2.cvtColor(mask_white, cv2.COLOR_GRAY2BGR)
           
           # Tint them for clarity
           # Red mask -> Red tint
           mask_red_bgr[:, :, 0] = 0 # B
           mask_red_bgr[:, :, 1] = 0 # G
           # White mask -> Grey/White tint (keep as is or just grey) - let's leave grey
           
           combined = np.hstack((roi_debug, mask_red_bgr, mask_white_bgr))
           
           debug_path = image_path.replace('.png', f'_red_white_debug_{x1}_{y1}.png')
           cv2.imwrite(debug_path, combined)
        except Exception as e:
            logger.error(f"Failed to save red/white debug image: {e}")

    return result

def detect_is_red(image_path, region):
    """
    Determines if a region has significant red pixels, regardless of other colors.
    Used for cases where we just need to detect red text vs background.
    """
    img_cv = VisionUtils.load_image(image_path)
    if img_cv is None: 
        return 'unknown'

    x1, y1, x2, y2 = region
    roi = img_cv[y1:y2, x1:x2]
    
    # Convert to HSV
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    
    # --- Red Masks (wraps around 0/180) ---
    # Same ranges as detect_red_or_white
    lower_red1 = np.array([0, 70, 50])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 70, 50])
    upper_red2 = np.array([180, 255, 255])
    
    mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask_red = cv2.bitwise_or(mask_red1, mask_red2)
    
    # Count pixels
    red_count = cv2.countNonZero(mask_red)
    total_pixels = roi.shape[0] * roi.shape[1]
    threshold = int(total_pixels / 7)
    
    logger.debug(f"[Detect Is Red] Region {region} | Red Pixels: {red_count} | Total Pixels: {total_pixels} | Threshold: {threshold}")

    result = 'unknown'
    if red_count > threshold:
        result = 'red'
    
    # Debug Image Generation
    if logger.isEnabledFor(10): # 10 is logging.DEBUG
        try:
           roi_debug = roi.copy()
           mask_red_bgr = cv2.cvtColor(mask_red, cv2.COLOR_GRAY2BGR)
           mask_red_bgr[:, :, 0] = 0 # B
           mask_red_bgr[:, :, 1] = 0 # G
           
           combined = np.hstack((roi_debug, mask_red_bgr))
           
           debug_path = image_path.replace('.png', f'_is_red_debug_{x1}_{y1}.png')
           cv2.imwrite(debug_path, combined)
        except Exception as e:
            logger.error(f"Failed to save is_red debug image: {e}")

    return result

""" ----------------------------- Builder Base Functions ----------------------------- """

def extract_builder_resources(image_path):
    img_cv = VisionUtils.load_image(image_path)
    regions = config["ObjectDetectionCoordinates"]["builder_resources_regions_map"]
    
    annotated_img = img_cv.copy()
    results = []
    for item in regions:
        region = item['region']
        type_ = item['type']
        b, g, r = VisionUtils.get_average_color(img_cv, region)
        maxed = 0
        if type_ == 'gold':
            if is_in_rgb_range((r, g, b), "resource_gold_max_rgb_range"): maxed = 1
        elif type_ == 'elixir':
             if is_in_rgb_range((r, g, b), "builder_resource_elixir_max_rgb_range"): maxed = 1
        results.append(maxed)
        
        # Annotation
        VisionUtils.draw_region(annotated_img, region, (0, 0, 255) if maxed else (0, 255, 0))
        
    VisionUtils.save_annotated_image(annotated_img, image_path, "_builder_resources_annotated.png")
    return tuple(results)

def extract_builder_base_builders_available_from_image(image_path):
    img_cv = VisionUtils.load_image(image_path)
    region = config["ObjectDetectionCoordinates"]["builder_base_builders_region"]
    annotated_img = img_cv.copy()
    VisionUtils.draw_region(annotated_img, region, (0, 255, 0))
    VisionUtils.save_annotated_image(annotated_img, image_path, ".png")

    text = VisionUtils.extract_text_from_region(img_cv, region)
    nums = VisionUtils.extract_numbers(text)
    # logger.debug(text)
    # logger.debug(nums)
    
    if 've' in text.lower() or 'we' in text.lower():
        return 1
    return int(nums[0]) if nums else 0

def extract_builder_base_research_available_from_image(image_path):
    img_cv = VisionUtils.load_image(image_path)
    region = config["ObjectDetectionCoordinates"]["builder_base_research_region"]
    text = VisionUtils.extract_text_from_region(img_cv, region)
    nums = VisionUtils.extract_numbers(text)
    return int(nums[0]) if nums else 0

def detect_builder_base_heroes_available(image_path):
    img_cv = VisionUtils.load_image(image_path)
    region = config["ObjectDetectionCoordinates"]["builder_base_hero_region"]
    target_grey = tuple(config["ObjectDetectionColors"]["hero_unavailable_target_grey"])
    target_unavail = tuple(config["ObjectDetectionColors"]["hero_unavailable_target_blue"])
    
    b, g, r = VisionUtils.get_average_color(img_cv, region)
    logger.info(f"[Builder Hero Check] Region {region} | RGB: ({r}, {g}, {b})")
    tolerance = config["ObjectDetectionColors"].get("hero_unavailable_tolerance", 10)
    if VisionUtils.is_color_close((b,g,r), target_grey, tolerance):
        # upgrading
        pass
    elif VisionUtils.is_color_close((b,g,r), target_unavail, tolerance):
        # unavail
        pass
    else:
        return 1
    return 0

def detect_upgrade_button_color_location(image_path, starting_region):
    img_cv = VisionUtils.load_image(image_path)
    x1_base, y1, x2_base, y2 = starting_region
    offsets = config["ObjectDetectionCoordinates"]["upgrade_button_offsets"]
    squares = [ (x1_base+o, y1, x2_base+o, y2) for o in offsets]
    
    gold_rgb_list = config["ObjectDetectionColors"].get("upgrade_button_gold_rgb_targets", [])
    purple_rgb_list = config["ObjectDetectionColors"].get("upgrade_button_purple_rgb_targets", [])
    
    # Handle legacy single-value case just in case config wasn't updated correctly or during transition
    if gold_rgb_list and isinstance(gold_rgb_list[0], int): gold_rgb_list = [gold_rgb_list]
    if purple_rgb_list and isinstance(purple_rgb_list[0], int): purple_rgb_list = [purple_rgb_list]

    results = []
    annotated_img = img_cv.copy()
    
    for idx, region in enumerate(squares):
        # Draw region being checked (Blue)
        VisionUtils.draw_region(annotated_img, region, (255, 0, 0))
        
        b, g, r = VisionUtils.get_average_color(img_cv, region)
        rgb = (r, g, b)
        
        logger.debug(f"[Upgrade Button Check] Region: {region} | Detected RGB: {rgb} | Targets Gold: {gold_rgb_list} | Targets Purple: {purple_rgb_list}")

        is_gold = False
        tolerance = config["ObjectDetectionColors"].get("upgrade_button_tolerance", 30)
        for target in gold_rgb_list:
             if VisionUtils.is_color_close(rgb, tuple(target), tolerance):
                 is_gold = True
                 break

        is_purple = False
        if not is_gold: # Optimization
            for target in purple_rgb_list:
                # Target is RGB, our rgb variable is RGB.
                if VisionUtils.is_color_close(rgb, tuple(target), tolerance):
                    is_purple = True
                    break
        
        color_name = 'gold' if is_gold else 'purple' if is_purple else None
        
        if color_name:
            VisionUtils.draw_region(annotated_img, region, (0, 255, 255))
            results.append({'index': idx, 'pos': region, 'color': color_name, 'avg_rgb': (r,g,b)})
            
    VisionUtils.save_annotated_image(annotated_img, image_path, ".png")
    return results

def detect_play_store_update_screen(image_path):
    # This function had specific upscaling/OCR logic similar to generic but full image.
    img_cv = VisionUtils.load_image(image_path)
    scale = 1.5
    up = cv2.resize(img_cv, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
    
    data = pytesseract.image_to_data(gray, config='--oem 3 --psm 6', output_type=pytesseract.Output.DICT)
    words = [w.lower() for w in data.get('text', [])]
    
    has_update_avail = 'update available' in ' '.join(words)
    has_update_btn = 'update' in words
    has_play = 'google' in words and 'play' in words
    
    return (has_update_avail and has_update_btn) or (has_play and has_update_btn)

def check_for_gold_warning(image_path):
    """
    Checks if the average color of the region [568, 141, 1182, 235] is close to gold.
    Target Gold (RGB): (255, 215, 0) approximately, or similar to coin icon gold.
    The user specified "close to gold".
    Using a standard Gold RGB: (255, 215, 0) -> BGR: (0, 215, 255)
    Or the one used in upgrade checks: (255, 234, 61) -> BGR: (61, 234, 255)
    """
    img_cv = VisionUtils.load_image(image_path)
    # Region: x1, y1, x2, y2
    region = config["ObjectDetectionCoordinates"]["gold_warning_check_region"]
    
    b, g, r = VisionUtils.get_average_color(img_cv, region)
    
    # Using the upgrade gold color as reference: RGB (255, 234, 61)
    target_bgr = tuple(config["ObjectDetectionColors"]["gold_warning_target_bgr"])
    target_rgb_disp = (255, 234, 61)
    
    logger.debug(f"[Gold Warning Check] Target RGB: {target_rgb_disp} | Current RGB: ({r:.1f}, {g:.1f}, {b:.1f})")
    
    # Check if close to gold (using a slightly looser threshold as "close to gold" implies variance)
    tolerance = config["ObjectDetectionColors"].get("gold_warning_tolerance", 40)
    is_gold = VisionUtils.is_color_close((b, g, r), target_bgr, tolerance)
    
    annotated_img = img_cv.copy()
    VisionUtils.draw_region(annotated_img, region, (0, 0, 255) if is_gold else (0, 255, 0))
    VisionUtils.save_annotated_image(annotated_img, image_path, "_gold_warning_check.png")
    
    return is_gold

def detect_first_army_tile(image_path):
    """
    Detects the FIRST (leftmost) army tile in the bottom section using Black Outline detection.
    Returns the (center_x, center_y, std_rect) of the tile.
    """
    try:
        img_cv = VisionUtils.load_image(image_path)
        if img_cv is None:
            return None

        h_img, w_img = img_cv.shape[:2]
        
        # --- ROI SELECTION ---
        # If the image is already small in height (e.g. crop from bot), use it as is.
        if h_img < 400:
            roi = img_cv
            roi_top = 0
        else:
            # Full screenshot: Select bottom 25% (Bottom Bar Area)
            roi_top = int(h_img * 0.75)
            roi = img_cv[roi_top:h_img, 0:w_img]
        
        # --- 1. Edge Detection (Canny method) ---
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        
        # Debug: Save edges
        cv2.imwrite(image_path.replace('.png', '_debug_canny_edges.png'), edges)
        
        # --- 2. Find Contours ---
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # --- SCALING LOGIC ---
        # Constants from Config are relative to a 1080p width/height (1728x1080 usually)
        tile_cfg = config["TileDetection"]
        
        # Horizontal scale is usually literal if full-width (1728)
        scale_x = w_img / 1728.0
        
        # Reference height for ratios (Logic assumes 'h' is the full game height)
        # If the image is a crop, we simulate the full height that would have existed.
        simulated_h = h_img if h_img >= 400 else (1080.0 * scale_x)
        
        target_w = int(w_img * tile_cfg["target_w"])
        target_h = int(simulated_h * tile_cfg["target_h"])
        
        min_w = int(w_img * tile_cfg["min_w"])
        max_w = int(w_img * tile_cfg["max_w"])
        
        min_h = int(simulated_h * tile_cfg["min_h"])
        max_h = int(simulated_h * tile_cfg["max_h"])
        
        min_y_pos = int(simulated_h * tile_cfg["min_y_pos"])
        
        logger.debug(f"[Object Detection] Detection Params Scaled: W[{min_w}-{max_w}], H[{min_h}-{max_h}], Y_min={min_y_pos}")
        
        valid_candidates = []
        annotated_img = roi.copy()

        
        # VISUALIZATION: Candidates will be drawn on original image

        
        for i, cnt in enumerate(contours):
            x, y, rw, rh = cv2.boundingRect(cnt)
            
            # Check dimensions using SCALED thresholds
            size_ok = (min_w <= rw <= max_w) and (min_h <= rh <= max_h)
            
            # Check Position (Y coordinate)
            # If the image is already a crop (e.g. bottom bar only), skip position check but still calculate global_y for debugging
            global_y_check = roi_top + y
            if h_img < 400:
                pos_ok = True
            else:
                pos_ok = global_y_check > (min_y_pos - 50) # Slight tolerance


            
            if size_ok and pos_ok:
                # Valid Tile Candidate
                # logger.debug(f"Contour {i} VALID: x={x}, y={y}, global_y={global_y_check}, w={rw}, h={rh}")
                valid_candidates.append({
                    'index': i,
                    'cnt': cnt,
                    'x': x, 'y': y, 'w': rw, 'h': rh,
                    'roi_y': y
                })
                # VISUALIZATION
                cv2.rectangle(annotated_img, (x, y), (x + rw, y + rh), (0, 255, 0), 2)
                cv2.putText(annotated_img, f"OK {rw}x{rh}", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

            else:
                # Log rejection for debugging if it's somewhat close in size
                if rw > (min_w * 0.5) and rh > (min_h * 0.5):
                    #  logger.debug(f"Contour {i} REJECTED: x={x}, y={y}, w={rw}, h={rh}")
                    pass

        # --- 3. Determine Leftmost ---
        if valid_candidates:
            # Sort by X coordinate
            valid_candidates.sort(key=lambda c: c['x'])
            
            leftmost = valid_candidates[0]
            
            # Convert back to Global Coordinates
            global_x = leftmost['x']
            global_y = roi_top + leftmost['y']
            global_w = leftmost['w']
            global_h = leftmost['h']
            
            cx = global_x + global_w // 2
            cy = global_y + global_h // 2
            
            # Standard Size Output
            std_w = target_w
            std_h = target_h
            
            std_x = cx - (std_w // 2)
            std_y = cy - (std_h // 2)
            std_rect = (std_x, std_y, std_w, std_h)

            logger.info(f"[Object Detection] LEFTMOST TILE DETECTED. Center: ({cx}, {cy}). Dimension: {global_w}x{global_h}")

            # Highlight winner in Magenta
            lx, ly, lw, lh = leftmost['x'], leftmost['y'], leftmost['w'], leftmost['h']
            cv2.rectangle(annotated_img, (lx, ly), (lx + lw, ly + lh), (255, 0, 255), 3)
            cv2.putText(annotated_img, f"WIN {lw}x{lh}", (lx, ly - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
            
            # Save Debug
            debug_path = image_path.replace('.png', '_detected_first_tile.png')
            cv2.imwrite(debug_path, annotated_img)
            
            return (cx, cy, std_rect, valid_candidates)
            
        return None

    except Exception as e:
        logger.error(f"Error in detect_first_army_tile: {e}")
        return None



def gold_pass_trigger(image_path):
    # Reference image path - construct absolute path relative to this file
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ref_path = os.path.join(base_dir, 'data', 'templates', 'gold_pass_reference.png')
    
    if not os.path.exists(ref_path):
        logger.warning(f"Gold Pass reference image not found at {ref_path}")
        return False
        
    img_cv = VisionUtils.load_image(image_path)
    if img_cv is None: return False
    
    ref_cv = VisionUtils.load_image(ref_path)
    if ref_cv is None: return False
    
    # Ensure reference is not larger than image
    rh, rw = ref_cv.shape[:2]
    ih, iw = img_cv.shape[:2]
    
    # Check if reference is larger than image in any dimension
    if rh > ih or rw > iw:
        logger.debug(f"[Gold Pass] Resizing reference ({rw}x{rh}) to fit image ({iw}x{ih})")
        # Resize maintaining aspect ratio based on width
        scale = iw / rw
        new_w = int(rw * scale)
        new_h = int(rh * scale)
        # If height is still too big, scale by height instead
        if new_h > ih:
             scale = ih / rh
             new_w = int(rw * scale)
             new_h = int(rh * scale)
        ref_cv = cv2.resize(ref_cv, (new_w, new_h))
        
    res = cv2.matchTemplate(img_cv, ref_cv, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    
    logger.debug(f"[Gold Pass Trigger] Max Similarity: {max_val}")
    
    if max_val > 0.8:
        logger.info(f"GOLD PASS SCREEN DETECTED (Score: {max_val:.2f}). TRIGGERING EXIT.")
        return True
        
    return False
