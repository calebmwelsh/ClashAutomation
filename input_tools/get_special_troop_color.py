import os
import sys
import time

import cv2

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.game_window_controller import GameWindowController
from utils.object_detection import detect_first_army_tile
from utils.settings import logger


def main():
    logger.info("Initializing Game Controller...")
    
    # Try to find the window
    try:
        wc = GameWindowController("Clash of Clans")
    except Exception as e:
        logger.error(f"Error: {e}")
        logger.info("Please ensure Clash of Clans is open.")
        return

    # Load Config (already loaded and scaled in utils.settings)
    from utils.settings import config
    
    start_attack_positions = config.get("HomeBaseStaticClickPositions", {}).get("start_attack", [])

    if not start_attack_positions:
        logger.error("Error: Could not find 'start_attack' positions in config")
        return

    logger.info("Starting attack sequence allow screen to load...")
    wc.execute_clicks(start_attack_positions)
    
    # Wait for the attack screen (army bar) to be visible. 
    # home_base_actions waits 8 seconds + find_enemy_base time.
    # We just need to be on an enemy base.
    logger.info("Waiting 10 seconds for game to load enemy base...")
    time.sleep(10)

    logger.info("Taking screenshot...")

    # Capture
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    # Save to standard data folder
    screenshot_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'screenshots', 'Special Troop Color Test', f'{timestamp}.png')
    
    # Ensure dir exists
    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
    
    logger.info(f"Capturing to {screenshot_path}...")
    wc.capture_minimized_window_screenshot(screenshot_path)
    
    # Read Image
    img = cv2.imread(screenshot_path)
    if img is None:
        logger.error("Failed to load image. Check if file was saved.")
        return

    # --- 1. Tile Detection ---
    # detect_first_army_tile handles ROI and adaptive scaling automatically
    tile_data = detect_first_army_tile(screenshot_path)
    
    if tile_data:
        # Unpack (cx, cy, std_rect, candidates)
        cx, cy, std_rect, candidates = tile_data
        logger.info(f"Detected First Army Tile at: ({cx}, {cy})")
        x, y = int(cx), int(cy)
        
        # Logging for sync verification
        logger.info(f"Using tile center for color sampling: ({x}, {y})")

        # Extract troop count from top right of the tile
        try:
            from utils.vision_utils import VisionUtils
            std_x, std_y, std_w, std_h = std_rect
            # Top right corner of the tile
            roi_x1 = std_x + int(std_w * 0.5)
            roi_y1 = std_y
            roi_x2 = std_x + std_w
            roi_y2 = std_y + int(std_h * 0.25)
            count_roi = (roi_x1, roi_y1, roi_x2, roi_y2)
            
            # Draw region for debugging
            cv2.rectangle(img, (roi_x1, roi_y1), (roi_x2, roi_y2), (255, 0, 0), 2)
            
            # Save a debug snippet of just the count ROI to verify the area
            count_snippet_path = screenshot_path.replace(".png", "_count_roi.png")
            roi_img = img[roi_y1:roi_y2, roi_x1:roi_x2]
            
            # Upscale the ROI by 4x for better OCR recognition
            roi_img_up = cv2.resize(roi_img, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(count_snippet_path, roi_img_up)
            logger.info(f"Saved count ROI debug image to: {count_snippet_path}")
            
            import pytesseract
            text = pytesseract.image_to_string(roi_img_up, config='--psm 7 -c tessedit_char_whitelist=x0123456789')
            numbers = VisionUtils.extract_numbers(text)
            logger.info(f"Detected Special Troop Text: {repr(text.strip())}")
            logger.info(f"Detected Special Troop Count: {numbers}")
            
            troop_count = None
            if numbers:
                troop_count = int(numbers[0])
                logger.info(f"Detected Special Troop Count: {troop_count}")
            else:
                logger.warning("Failed to detect Special Troop Count from tile.")
        except Exception as e:
            logger.error(f"Error extracting troop count: {e}")
            troop_count = None

    else:
        # Fallback: Try to use a scaled fallback based on Resolution
        h_img, w_img = img.shape[:2]
        
        # Use config-based "RecordAttackCoordinates" if available for better sync
        st_fallback = config.get("RecordAttackCoordinates", {}).get("special_troop_check_pos", [0.115, 0.916])
        x = int(st_fallback[0] * w_img)
        y = int(st_fallback[1] * h_img)
        
        logger.warning(f"First Army Tile NOT detected. Using fallback coordinates from config: ({x}, {y})")
    
    # --- 2. Color Extraction ---
    if 0 <= y < img.shape[0] and 0 <= x < img.shape[1]:
        # BGR from OpenCV
        b, g, r = img[y, x]
        new_rgb = [int(r), int(g), int(b)]
        logger.info(f"\n[RESULT] Sampled Pixel at ({x}, {y})")
        logger.info(f"RGB: {new_rgb}")
        
        # Automatic Config Update
        try:
            import toml

            from utils.settings import static_config_path
            
            if os.path.exists(static_config_path):
                config_data = toml.load(static_config_path)
                
                # Ensure the section exists
                if "HomeBaseGeneral" not in config_data:
                    config_data["HomeBaseGeneral"] = {}
                
                # Update the RGB values
                config_data["HomeBaseGeneral"]["special_troop_event_rgb"] = [new_rgb]
                
                # Update special troop counts if detected
                if 'troop_count' in locals() and troop_count is not None:
                    counts = config_data["HomeBaseGeneral"].get("special_troop_counts", [0])
                    if not isinstance(counts, list):
                        counts = [counts]
                    counts[0] = troop_count
                    config_data["HomeBaseGeneral"]["special_troop_counts"] = counts
                
                with open(static_config_path, "w") as f:
                    toml.dump(config_data, f)
                
                logger.info(f"Successfully updated 'special_troop_event_rgb' in {static_config_path} with {new_rgb}")
                if 'troop_count' in locals() and troop_count is not None:
                    logger.info(f"Successfully updated 'special_troop_counts' with {counts}")
            else:
                logger.error(f"Could not find static_config.toml at {static_config_path}")
        except Exception as e:
            logger.error(f"Failed to update config file: {e}")
        
        # Annotate
        # Use a distinctive Green circle for the exactly sampled pixel
        cv2.circle(img, (x, y), 8, (0, 255, 0), 2)
        cv2.circle(img, (x, y), 1, (0, 255, 0), -1) # Center dot
        cv2.putText(img, f"SAMPLED RGB: {new_rgb}", (x + 15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        annotated_path = screenshot_path.replace(".png", "_annotated.png")
        cv2.imwrite(annotated_path, img)
        logger.info(f"Annotated image saved to: {annotated_path}")
        logger.info("Please open the annotated image to verify the circle is on the special troop icon.")
    else:
        logger.error("Coordinates out of bounds.")

    # Exit Battle
    logger.info("\nExiting battle...")
    end_battle_positions = config.get("HomeBaseStaticClickPositions", {}).get("end_battle", [])
    if end_battle_positions:
        wc.execute_clicks(end_battle_positions)
        logger.info("Clicked End Battle.")
    else:
        logger.error("Error: 'end_battle' positions not found in config.")

if __name__ == "__main__":
    main()
