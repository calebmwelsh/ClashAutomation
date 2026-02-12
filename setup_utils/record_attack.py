import os
import sys
import time

import cv2
import keyboard  # To detect key presses
import numpy as np
import toml
import win32api
import win32con

# Ensure we can find util modules if needed, though we rely on standalone imports mostly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.game_window_controller import GameWindowController
from utils.settings import logger


def get_mouse_position():
    """
    Get the current position of the mouse cursor.
    :return: A tuple (x, y) representing the mouse coordinates.
    """
    x, y = win32api.GetCursorPos()
    return x, y

def record_phase(phase_name):
    logger.info(f"\n--- Recording Phase: {phase_name} ---")
    logger.info("Left Click to record a position.")
    logger.info("Press 'Enter' to finish this phase and move to the next.")
    logger.info("Press 'Esc' to cancel the entire recording.")
    
    positions = []
    
    # Debounce/State flags
    last_click_time = 0
    debounce_interval = 0.3
    
    while True:
        # Check Exit
        if keyboard.is_pressed("esc"):
            logger.info("Recording cancelled.")
            return None
        
        # Check Next Phase
        if keyboard.is_pressed("enter"):
            # Wait for key release to prevent skipping next phase immediately
            while keyboard.is_pressed("enter"):
                time.sleep(0.1)
            logger.info(f"Finished phase: {phase_name}. Recorded {len(positions)} clicks.")
            return positions

        # Check Click
        current_time = time.time()
        if (win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000):
            if (current_time - last_click_time) > debounce_interval:
                pos = get_mouse_position()
                positions.append(list(pos))
                logger.debug(f"Recorded {phase_name} position: {pos}")
                last_click_time = current_time
        
        time.sleep(0.01)

def main(logger_instance=None):
    global logger
    if logger_instance:
        logger = logger_instance
        
    logger.info("=== Custom Attack Recorder ===")
    attack_name = input("Enter a name for this attack (default: 'E-Dragon'): ").strip()
    if not attack_name:
        attack_name = "E-Dragon"
        logger.info(f"Using default name: {attack_name}")

    # Load Static Config for start_attack
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'utils', 'baseconfig', 'static_config.toml')
        with open(config_path, 'r') as f:
            static_config = toml.load(f)
        start_attack_positions = static_config.get("HomeBaseStaticClickPositions", {}).get("start_attack", [])
        reset_select_positions = static_config.get("HomeBaseStaticClickPositions", {}).get("reset_select", [])
        reset_camera_positions = static_config.get("HomeBaseStaticClickPositions", {}).get("reset_camera", [])
        
        # New Configs
        record_coords = static_config.get("RecordAttackCoordinates", {})
        colors = static_config.get("Colors", {})

        if start_attack_positions:
            logger.info("\nInitializing Game Controller to start attack...")
            try:
                wc = GameWindowController("Clash of Clans")

                # --- Camera Reset Logic ---
                logger.info("Resetting Camera...")
                # 1. Reset Select (Deselct)
                if reset_select_positions:
                     # Click first parts a few times
                    wc.execute_clicks(reset_select_positions[:-1], delay=0.5)
                    wc.execute_clicks(reset_select_positions[:-1], delay=0.5)
                    # Click last part
                    wc.execute_clicks(reset_select_positions[-1], delay=0.5)
                    time.sleep(1)

                # 2. Scroll Down
                wc.scroll_wheel_down(20)
                time.sleep(3)

                # 3. Reset Camera Sequence
                if reset_camera_positions:
                    # Copied logic from home_base_actions: 
                    # end_pos is the last one. 
                    # pop last one, execute rest, wait 7s, execute end_pos.
                    # We shouldn't pop in place if we want to reuse config but here we just read it.
                    # Safe to just slice.
                    if len(reset_camera_positions) > 1:
                        end_pos = reset_camera_positions[-1]
                        main_reset_clicks = reset_camera_positions[:-1]
                        
                        wc.execute_clicks(main_reset_clicks)
                        time.sleep(7)
                        wc.execute_clicks(end_pos)
                    else:
                        wc.execute_clicks(reset_camera_positions)
                    time.sleep(2)
                # --------------------------

                logger.info("Starting attack sequence...")
                wc.execute_clicks(start_attack_positions)
                logger.info("Attack started. Waiting for base to load (checking pixel 1669, 149)...")
                
                # Dynamic wait logic
                timeout = 30
                start_wait = time.time()
                base_loaded = False
                
                target_rgb = colors.get("base_load_target_rgb", [184, 34, 235])
                check_pos = record_coords.get("base_load_check_pos", [1676, 103])
                
                while (time.time() - start_wait) < timeout:
                    # Capture screenshot
                    temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug_base_check.png')
                    img = wc.capture_minimized_window_screenshot(temp_path)
                    
                    if img:
                        try:
                            r, g, b = img.getpixel(check_pos)
                            dist = ((r - target_rgb[0])**2 + (g - target_rgb[1])**2 + (b - target_rgb[2])**2) ** 0.5
                            
                            logger.debug(f"Checking base load: Found RGB({r},{g},{b}) at {check_pos}. Dist: {dist:.2f}")

                            if dist < 30: # Tolerance
                                logger.debug(f"Base loaded! Color matched: {r},{g},{b}")
                                base_loaded = True
                                break
                            
                            # Save annotated for debug
                            # Convert to CV2 for annotation (RGB -> BGR)
                            # img_np = np.array(img)
                            # img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                            # cv2.circle(img_cv, check_pos, 10, (0, 0, 255), 2) # Red circle
                            # cv2.putText(img_cv, f"RGB:{r},{g},{b}", (check_pos[0]+15, check_pos[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                            
                            # debug_ann_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug_base_check_annotated.png')
                            # cv2.imwrite(debug_ann_path, img_cv)
                            
                        except Exception as inner_e:
                            logger.error(f"Error checking pixel: {inner_e}")
                            pass 
                            
                    time.sleep(1)
                
                if not base_loaded:
                    logger.warning("Warning: Timed out waiting for base load color match. Proceeding anyway...")
                else:
                    # Slight buffer after visual match
                    time.sleep(2) 

            except Exception as e:
                logger.error(f"Failed to start attack automatically: {e}")
                logger.info("Please ensure Clash of Clans is open.")
                return
        else:
            logger.warning("Warning: 'start_attack' positions not found in static_config.toml.")
            
    except Exception as e:
        logger.error(f"Error loading config or controller: {e}")

    # --- Special Troop Detection (Normalization Prep) ---
    special_troop_event_count = static_config.get("HomeBaseGeneral", {}).get("SpecialTroopEvent", 0)
    special_troop_rgb = static_config.get("HomeBaseGeneral", {}).get("SpecialTroopEventRGB", [0, 0, 0])
    is_special_at_start = False
    
    if special_troop_event_count > 0:
        logger.info(f"\nChecking for Special Troop Event (Count: {special_troop_event_count})...")
        # Check pixel at (200, 990)
        check_special_pos = record_coords.get("special_troop_check_pos", [200, 990])
        try:
             # Capture for check
            temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'special_check.png')
            wc = GameWindowController("Clash of Clans") # Ensure we have controller
            img = wc.capture_minimized_window_screenshot(temp_path)
            if img:
                r, g, b = img.getpixel(check_special_pos)
                # Compare with ID
                # Simple distance
                # Config RGB is likely in list [r, g, b]
                target = special_troop_rgb
                dist = ((r - target[0])**2 + (g - target[1])**2 + (b - target[2])**2) ** 0.5
                logger.debug(f"Special Troop Check at {check_special_pos}: Found RGB({r},{g},{b}). Target: {target}. Dist: {dist:.2f}")
                
                if dist < 30 and sum(target) > 0:
                    is_special_at_start = True
                    logger.info("-> Special Troops detected at START.")
                else:
                    logger.info("-> Special Troops NOT detected at start (Assuming END).")
        except Exception as e:
            logger.error(f"Failed to check special troop status: {e}")

    # Define phases
    phases = [
        "Troops",
        "Clan Castle",
        "Heroes",
        "Spells"
    ]
    
    attack_data = []
    
    logger.info("\nStarting recording... Switch to your game window.")
    
    for phase in phases:
        recorded_positions = record_phase(phase)
        if recorded_positions is None:
            return # Cancelled
        attack_data.append(recorded_positions)
        time.sleep(0.5)

    # --- Normalize Data (Reverse Shifts) ---
    if special_troop_event_count > 0:
        logger.info("\nNormalizing coordinates (removing special troop shifts)...")
        shift_amount = 115 * special_troop_event_count
        
        normalized_data = []
        for idx, phase_clicks in enumerate(attack_data):
            # phase indices: 0=Troops, 1=CC, 2=Heroes, 3=Spells
            
            should_shift = False
            if is_special_at_start:
                # If at start, EVERYTHING shifts
                should_shift = True
            else:
                # If at end, only Heroes(2) and Spells(3) shift
                if idx in [2, 3]: 
                    should_shift = True
            
            new_phase_clicks = []
            for pos in phase_clicks:
                x, y = pos[0], pos[1]
                if should_shift and y > 900:
                    # Subtract the shift to normalize
                    new_x = x - shift_amount
                    logger.debug(f"  Adjusting {phases[idx]} click at ({x}, {y}) -> ({new_x}, {y})")
                    new_phase_clicks.append([new_x, y])
                else:
                    new_phase_clicks.append([x, y])
            normalized_data.append(new_phase_clicks)
        
        attack_data = normalized_data

    # Save to file
    base_config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'utils', 'baseconfig')
    output_file = os.path.join(base_config_dir, 'recorded_attacks.toml')
    
    # Load existing or create new
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r') as f:
                config = toml.load(f)
        except Exception as e:
            logger.error(f"Error loading existing file: {e}. Starting fresh.")
            config = {}
    else:
        config = {}

    if "HomeBaseAttacks" not in config:
        config["HomeBaseAttacks"] = {}
        
    config["HomeBaseAttacks"][attack_name] = attack_data
    

    try:
        with open(output_file, 'w') as f:
            toml.dump(config, f)
        logger.info(f"\nAttack '{attack_name}' saved successfully to:")
        logger.info(f"{output_file}")
        logger.info("\nStructure:")
        logger.info(f"  Phase 1 (Troops): {len(attack_data[0])} clicks")
        logger.info(f"  Phase 2 (Clan Castle): {len(attack_data[1])} clicks")
        logger.info(f"  Phase 3 (Heroes): {len(attack_data[2])} clicks")
        logger.info(f"  Phase 4 (Spells): {len(attack_data[3])} clicks")
        
    except Exception as e:
        logger.error(f"Failed to save file: {e}")

if __name__ == "__main__":
    main()
