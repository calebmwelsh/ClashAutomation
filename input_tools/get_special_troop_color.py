import os
import re
import sys
import time

import cv2
import numpy as np

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytesseract
import toml

from utils.game_window_controller import GameWindowController
from utils.object_detection import detect_first_army_tile
from utils.settings import config, logger, static_config_path


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
    start_attack_positions = config.get("HomeBaseStaticClickPositions", {}).get("start_attack", [])

    if not start_attack_positions:
        logger.error("Error: Could not find 'start_attack' positions in config")
        return

    logger.info("Starting attack sequence allow screen to load...")
    wc.execute_clicks(start_attack_positions)
    
    # Wait for the attack screen (army bar) to be visible. 
    logger.info("Waiting 10 seconds for game to load enemy base...")
    time.sleep(10)

    logger.info("Taking screenshot...")

    # Capture
    timestamp = time.strftime("%Y%m%d_%H%M%S")
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
    tile_data = detect_first_army_tile(screenshot_path)
    
    if tile_data:
        cx, cy, std_rect, candidates_info = tile_data
        logger.info(f"Detected First Army Tile at: ({cx}, {cy})")
        x, y = int(cx), int(cy)
        
        # --- 2. Phase 2 OCR Preprocessing ---
        try:
            std_x, std_y, std_w, std_h = std_rect
            # Widened ROI: Start 40% from the left instead of 50%
            roi_x1 = std_x + int(std_w * 0.4)
            roi_y1 = std_y
            roi_x2 = std_x + std_w
            roi_y2 = std_y + int(std_h * 0.26)
            
            roi_img = img[roi_y1:roi_y2, roi_x1:roi_x2]
            if roi_img.size == 0:
                raise ValueError("Extracted ROI is empty")

            # Create variants of the image for OCR
            proc_variants = [] # List of (name, image)
            
            # Scales: 3x and 4x
            for scale in [3, 4]:
                upscaled = cv2.resize(roi_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
                
                # Variant 1: Global Threshold (200) - Cleanest for high contrast
                _, t200 = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
                proc_variants.append((f"{scale}x_Thresh200", cv2.copyMakeBorder(t200, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)))
                
                # Variant 2: Global Threshold (150) - Lower for thinner characters
                _, t150 = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
                proc_variants.append((f"{scale}x_Thresh150", cv2.copyMakeBorder(t150, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)))
                
                # Variant 3: Adaptive Thresholding
                adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
                proc_variants.append((f"{scale}x_Adaptive", cv2.copyMakeBorder(adaptive, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)))

            # Save diagnostic images for the 4x variant
            count_snippet_path = screenshot_path.replace(".png", "_count_roi.png")
            cv2.imwrite(count_snippet_path, roi_img)
            # Find the 4x Thresh200 for debug visualization
            for name, pimg in proc_variants:
                if name == "4x_Thresh200":
                    cv2.imwrite(count_snippet_path.replace(".png", "_thresh.png"), pimg)
                    break
            
            # --- 3. Phase 2 Robust Candidate Selection ---
            psm_modes = ['7', '6', '11', '8', '3']
            found_candidates = [] # List of (priority, count, psm, variant)
            
            for psm in psm_modes:
                ocr_config = f'--psm {psm}'
                for name, pimg in proc_variants:
                    try:
                        raw_text = pytesseract.image_to_string(pimg, config=ocr_config).strip()
                        if not raw_text: continue
                        
                        logger.debug(f"OCR Try (PSM {psm}, {name}): {repr(raw_text)}")
                        
                        # Normalize text
                        text_clean = raw_text.lower().replace(" ", "")
                        
                        # 1. Match 'x' followed by digits (Priority 2)
                        match = re.search(r'x(\d+)', text_clean)
                        if match:
                            count = int(match.group(1))
                            found_candidates.append((2, count, psm, name))
                            continue
                        
                        # Handle common '1' misreadings
                        text_mapped = text_clean.replace('|', '1').replace('i', '1').replace('l', '1').replace('!', '1').replace('[', '1').replace(']', '1')
                        
                        # 2. Match digits only (Priority 1)
                        digits = "".join(re.findall(r'\d+', text_mapped))
                        if digits and len(digits) <= 3:
                            count = int(digits)
                            found_candidates.append((1, count, psm, name))
                    except Exception:
                        pass
            
            if found_candidates:
                # ELECTION:
                # 1. Sort by Priority (x-prefix is better)
                # 2. Sort by Count (11 is better than 1 if both found)
                found_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
                best = found_candidates[0]
                troop_count = best[1]
                logger.info(f"Selected Count '{troop_count}' (Priority {best[0]}, Count {best[1]}) from PSM {best[2]} on {best[3]}")
                logger.debug(f"All OCR Candidates: {found_candidates}")
            else:
                troop_count = None
                logger.warning("No troop count candidates found across all OCR modes.")

        except Exception as e:
            logger.error(f"Error in OCR Processing: {e}")
            troop_count = None

    else:
        # Fallback Logic
        h_img, w_img = img.shape[:2]
        st_fallback = config.get("RecordAttackCoordinates", {}).get("special_troop_check_pos", [0.115, 0.916])
        if st_fallback[0] > 1.0:
            x, y = int(st_fallback[0]), int(st_fallback[1])
        else:
            x = int(st_fallback[0] * w_img)
            y = int(st_fallback[1] * h_img)
        logger.warning(f"Tile NOT detected. Using fallback: ({x}, {y})")
        troop_count = None
    
    # --- 4. Config and Annotation ---
    if 0 <= y < img.shape[0] and 0 <= x < img.shape[1]:
        b, g, r = img[y, x]
        new_rgb = [int(r), int(g), int(b)]
        logger.info(f"\n[RESULT] Sampled Pixel at ({x}, {y}) RGB: {new_rgb}")
        
        try:
            if os.path.exists(static_config_path):
                config_data = toml.load(static_config_path)
                if "HomeBaseGeneral" not in config_data: config_data["HomeBaseGeneral"] = {}
                
                config_data["HomeBaseGeneral"]["special_troop_event_rgb"] = [new_rgb]
                
                if troop_count is not None:
                    counts = config_data["HomeBaseGeneral"].get("special_troop_counts", [0])
                    if not isinstance(counts, list): counts = [counts]
                    counts[0] = troop_count
                    config_data["HomeBaseGeneral"]["special_troop_counts"] = counts
                
                with open(static_config_path, "w") as f:
                    toml.dump(config_data, f)
                logger.info(f"Updated {static_config_path}")
        except Exception as e:
            logger.error(f"Config Update Failed: {e}")
        
        # Annotation
        cv2.circle(img, (x, y), 8, (0, 255, 0), 2)
        cv2.putText(img, f"RGB: {new_rgb} Count: {troop_count}", (x + 15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        annotated_path = screenshot_path.replace(".png", "_annotated.png")
        cv2.imwrite(annotated_path, img)
        logger.info(f"Annotated: {annotated_path}")
    else:
        logger.error("Out of bounds.")

    # Exit Battle
    logger.info("Exiting battle...")
    end_battle_positions = config.get("HomeBaseStaticClickPositions", {}).get("end_battle", [])
    if end_battle_positions: wc.execute_clicks(end_battle_positions)

if __name__ == "__main__":
    main()
