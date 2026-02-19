import copy
import glob
import os
import shutil
import time
from datetime import datetime

import cv2
import toml

from utils.base_actions import BaseActions
from utils.game_window_controller import GameWindowController
from utils.object_detection import *
from utils.settings import config, logger
from utils.vision_utils import VisionUtils

# Setup Logging



class HomeBaseActions(BaseActions):
    def __init__(self, window_controller: GameWindowController, config, logger_instance=None):
        super().__init__(window_controller, config, logger_instance if logger_instance else logger)

        # positions
        static_positions = self.config["HomeBaseStaticClickPositions"]
        dynamic_positions = self.config["HomeBaseDynamicClickPositions"]

        # coords and colors
        self.hb_coords = self.config.get("HomeBaseCoordinates", {})
        self.coords = self.hb_coords
        self.colors = self.config.get("Colors", {})

        # reset positions
        self.reset_select_positions = static_positions["reset_select"]
        self.reset_camera_positions = static_positions["reset_camera"]
        self.return_home_refocus_positions = static_positions.get("return_home_refocus", [])

        # switch builder base positions
        self.switch_builder_base_positions = static_positions["switch_builder_base"]

        # general config
        general_config = self.config["HomeBaseGeneral"]
        self.thl = general_config["THL"]
        self.special_troop_event = general_config["special_troop_event"]
        self.enemy_gold_threshold = general_config.get("ENEMY_GOLD_THRESHOLD", 300000)
        self.enemy_elixir_threshold = general_config.get("ENEMY_ELIXIR_THRESHOLD", 300000)
        self.enemy_dark_elixir_threshold = general_config.get("ENEMY_DARK_ELIXIR_THRESHOLD", 3000)
        self.special_troop_drop = general_config.get("special_troop_drop", [[382, 298]])
        self.special_troop_counts = general_config.get("special_troop_counts", [10, 10])

        # resource positions
        self.resource_positions = dynamic_positions["resource_collection"]

        # attack positions
        self.train_army_button_position = static_positions["train_army_button"]
        self.start_attack_positions = static_positions["start_attack"]
        self.find_next_positions = static_positions["find_next"]
        self.go_home_positions = static_positions["go_home"]

        # upgrade positions
        self.research_upgrade_positions = static_positions["research_upgrade"]
        self.build_upgrade_positions = static_positions["build_upgrade"]
        self.pet_positions = []
        pet_start = static_positions.get("pet_start_pos", [0.202546, 0.764815])
        pet_step_x = static_positions.get("pet_step_x", 0.184028)
        
        for i in range(4):
            self.pet_positions.append([pet_start[0] + (i * pet_step_x), pet_start[1]])
        self.pet_building_position = dynamic_positions["pet_building"]
        self.pet_drag_coords = static_positions.get("pet_drag_coords")
        self.pet_confirm_upgrade_positions = static_positions["confirm_pet_upgrade"]
        self.exit_pet_upgrade_positions = static_positions["exit_pet_upgrade"]

        # raid positions
        self.launch_raid_start_positions = static_positions["launch_raid_start"]

        # apprentice positions
        self.apprentice_building_position = dynamic_positions["apprentice_building"]
        self.apprentice_research_positions = static_positions["apprentice_research"]
        self.apprentice_builder_positions = static_positions["apprentice_builder"]
        self.apprentice_alchemist_positions = static_positions["apprentice_alchemist"]
        
        
        # ranked mode 
        self.ranked_game_count = 0

        # super troop positions
        self.activate_super_troop_positions = static_positions["activate_super_troop"]

        # Attack armies dict
        attacks_config = config.get("HomeBaseAttacks", {})
        self.attack_armies = {}
        for key, positions in attacks_config.items():
            self.attack_armies[key] = {
                "name": key.replace("_", " ").title(),
                "positions": positions
            }

        # For pet and raid loops, positions will be read dynamically as filenames are generated


    """ --------------------------- Reset and Click Functions --------------------------------- """
    def reset_select(self, delay=0.5, num_clicks=2):
        """
        Executes clicks for the reset select positions (read once in __init__).
        """
        # Only execute the repeating 'clearing' clicks if we have more than one position
        if len(self.reset_select_positions) > 1:
            for _ in range(num_clicks):
                self.window_controller.execute_clicks(self.reset_select_positions[:-1], delay=delay)
        
        # Execute the final reset click
        if self.reset_select_positions:
            self.window_controller.execute_clicks(self.reset_select_positions[-1], delay=delay)
        time.sleep(1)

    def return_home_refocus(self):
        """
        Executes clicks for the return home refocus positions.
        """
        if self.return_home_refocus_positions:
            self.logger.info("Return Home Refocus...")
            for _ in range(7):
                self.window_controller.execute_clicks(self.return_home_refocus_positions)
        else:
            self.logger.warning("No return home refocus positions found in config.")

    def reset_camera_position(self):
        """
        Executes a drag operation to reset the camera position.
        """
        self.reset_select()
        self.window_controller.scroll_wheel_down(20)
        time.sleep(3)
        end_pos = self.reset_camera_positions[-1]
        self.reset_camera_positions.pop(-1)
        
        self.window_controller.execute_clicks(self.reset_camera_positions)
        time.sleep(7)
        self.window_controller.execute_clicks(end_pos)
        time.sleep(4)

    def switch_builder_base(self):
        """
        Switches to the builder base.
        """
        self.logger.info("Switching to builder base...")
        self.reset_select()
        self.window_controller.execute_clicks(self.switch_builder_base_positions)
        self.window_controller.execute_clicks(self.switch_builder_base_positions)
        time.sleep(2)

    """ --------------------------- Resource Functions --------------------------------- """
    def execute_resource_collection(self):
        # Read positions from the file (now from memory)
        positions = self.resource_positions
        # Execute clicks for each position
        self.window_controller.execute_clicks(positions)
        
    
    def check_max_resources(self):
        """
        Captures a screenshot and detects if home base resources are maxed using color detection.
        Returns is_maxed True if both gold and elixir are maxed (color detected), else False.
        """
        screenshot_path = self.manage_screenshot_storage('home_base_resource_stats')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        gold, elixir, dark_elixir = extract_home_resources(screenshot_path)
        self.logger.info(f"[Base Resources] Gold maxed: {gold}, Elixir maxed: {elixir}, Dark Elixir maxed: {dark_elixir}")
        is_maxed = gold == 1 and elixir == 1 and dark_elixir == 1
        self.logger.info(f"[Base Resources] Both gold and elixirs maxed: {is_maxed}")
        return is_maxed

    def wait_for_base_load(self, timeout=30):
        """
        Waits for the base to load by checking if the pixel is NOT white (clouds).
        Target: Pixel (1669, 149) should NOT be (254, 254, 254).
        """
        self.logger.info("Waiting for base to load...")
        start_time = time.time()
        
        # Avoid RGB (White/Clouds)
        avoid_rgb = self.colors.get("white_clouds_rgb", [254, 254, 254])
        check_pos = self.hb_coords.get("check_base_load_pos", [1669, 149])
        
        while (time.time() - start_time) < timeout:
            screenshot_path = self.manage_screenshot_storage('base_load_check')
            # Using capture_minimized_window_screenshot returns PIL Image, also saves file
            img = self.window_controller.capture_minimized_window_screenshot(screenshot_path)
            
            # Annotate the check position
            try:
                # self.annotate_coords_on_image([check_pos]) # Avoid recursion or using heavy func here
                annotate_coords_on_image(screenshot_path, [check_pos], output_suffix='.png')
            except Exception as e:
                self.logger.error(f"Failed to annotate base load check: {e}")
            
            if img:
                try:
                    r, g, b = img.getpixel(check_pos)
                    
                    # Euclidean distance to the "Avoid" color (White)
                    dist = ((r - avoid_rgb[0])**2 + (g - avoid_rgb[1])**2 + (b - avoid_rgb[2])**2) ** 0.5
                    
                    # If distance is LARGE (> 10), then we are NOT white, so base is loaded
                    if dist > 10:
                        self.logger.debug(f"Base loaded! Pixel is NOT {avoid_rgb} | Found RGB: ({r},{g},{b}) | Diff from White: {dist:.2f}")
                        time.sleep(1)
                        return True
                    
                    # Still white/clouds
                    self.logger.debug(f"Waiting for base: Found RGB ({r}, {g}, {b}) is close to {avoid_rgb} (Diff: {dist:.2f})")
                        
                except Exception as e:
                    pass # Ignore out of bounds or read errors
            
            time.sleep(1)
            
        self.logger.warning("Warning: Timed out waiting for base load.")
        return False



    """ --------------------------- Attack Functions --------------------------------- """

    def check_heros(self):
        """
        Captures a screenshot and detects the number of available heroes using detect_heroes_available.
        Prints and returns the number of available heroes.
        """
        # select train army button
        self.window_controller.execute_clicks(self.train_army_button_position)
        time.sleep(1)
        
        screenshot_path = self.manage_screenshot_storage('heros_status')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        available_heros = detect_heroes_available(screenshot_path)
        self.logger.info(f"[Heros Status] Available heroes: {available_heros}")

        # reset select
        self.reset_select()

        return available_heros
    
    def army_placement(self, army_key=None, available_heros=None, delay=0.5):
        """
        Places the army in the correct position.
        :param army_key: String key for the army type (e.g., 'e_drag_rage_goblin').
        """
        # get army positions
        if army_key is None:
            army_key = self.attack_armies.keys()[0]
        army = self.attack_armies.get(army_key)
        if not army:
            raise ValueError(f"Army key '{army_key}' not found in attack_armies.")
        
        # Create a copy of army positions for potential adjustments
        self.logger.debug(f"Original Army Positions: {army['positions']}")
        army_positions_copy = copy.deepcopy(army["positions"])

        # --- DEBUG: Snapshot positions BEFORE adjustments ---
        try:
            # Unified screenshot management for pre-adjust tiles
            # This creates 'data/screenshots/army_placement_debug_pre_adjust_tiles/'
            debug_screen_path = self.manage_screenshot_storage('army_placement_debug_pre_adjust_tiles')
            self.window_controller.capture_minimized_window_screenshot(debug_screen_path)
            
            # Extract distinct select coords (Y > 900) from the UNADJUSTED copy
            debug_coords = []
            def extract_select_coords(obj):
                found = []
                if isinstance(obj, (list, tuple)):
                    if len(obj) == 2 and all(isinstance(x, (int, float)) for x in obj):
                        if obj[1] > 900:
                            found.append(tuple(obj))
                    else:
                        for item in obj:
                            found.extend(extract_select_coords(item))
                return found

            debug_coords = extract_select_coords(army_positions_copy)
            # Annotate
            if debug_coords:
                annotate_coords_on_image(debug_screen_path, debug_coords, output_suffix='_annotated.png')
                self.logger.debug(f"Saved pre-adjustment army debug image to {debug_screen_path}")
                
            # --- Tile Count & First Tile Detection ---
            # 1. Detect First Tile
            first_tile_data = detect_first_army_tile(debug_screen_path)
            
            if first_tile_data:
                # Unpack (cx, cy, rect, candidates)
                cx, cy, ft_rect, candidates = first_tile_data
                w, h = ft_rect[2], ft_rect[3]
                
                self.logger.debug(f"First Tile Detected at: {cx}, {cy} | W={w}, H={h}")

                # --- PROPAGATION LOGIC ---
                # We will now traverse the army_positions_copy structure (Phases)
                # and assign calculated coordinates based on the First Tile Anchor.
                
                # Anchor Position (Center of First Tile)
                current_x = cx 
                current_y = cy


                # --- SUPER TROOP INJECTION ---
                
                num_super = int(self.special_troop_event) if self.special_troop_event else 0
                is_special_start = False # Default to End if logic checked
                
                if num_super > 0 and len(army_positions_copy) > 0:
                    self.logger.debug(f"Super Troop Config: {num_super} active. determining position (Start vs End).")
                    
                    # DETERMINING POSITION:
                    try:
                        temp_img = cv2.imread(debug_screen_path)
                        if temp_img is not None:
                            check_x = int(cx)
                            check_y = int(cy)
                            
                            self.logger.debug(f"Checking for Super Troop at First Tile: ({check_x}, {check_y})")

                            if 0 <= check_y < temp_img.shape[0] and 0 <= check_x < temp_img.shape[1]:
                                b, g, r = temp_img[check_y, check_x]
                                # Match against special_troop_event_rgb from Config
                                st_rgb_list = self.config["HomeBaseGeneral"].get("special_troop_event_rgb", [])

                                matched = False
                                for ref_rgb in st_rgb_list:
                                    if abs(r - ref_rgb[0]) < 40 and abs(g - ref_rgb[1]) < 40 and abs(b - ref_rgb[2]) < 40:
                                        matched = True
                                        break
                                if matched:
                                    
                                    # Save debug image of the check
                                    try:
                                        if self.logger.isEnabledFor(10):
                                            cv2.circle(temp_img, (check_x, check_y), 5, (0, 0, 255), 2)
                                            debug_st_path = debug_screen_path.replace('.png', '_debug_st_check.png')
                                            cv2.imwrite(debug_st_path, temp_img)
                                            self.logger.debug(f"Saved Super Troop Check debug image to {debug_st_path}")
                                    except Exception as e:
                                        self.logger.error(f"Failed to save ST debug img: {e}")

                                    is_special_start = True
                                    self.logger.debug(f"Super Troop detected at Start (Pixel Match at {check_x},{check_y}). Detected RGB: {r}, {g}, {b}")
                                else:
                                    # Save debug image even on failure
                                    try:
                                        if self.logger.isEnabledFor(10):
                                            cv2.circle(temp_img, (check_x, check_y), 5, (255, 0, 0), 2) # Blue for fail
                                            debug_st_path = debug_screen_path.replace('.png', '_debug_st_check.png')
                                            cv2.imwrite(debug_st_path, temp_img)
                                            self.logger.debug(f"Saved Super Troop Check debug image to {debug_st_path}")
                                    except: pass

                                    self.logger.debug(f"Super Troop NOT detected at Start (Pixel {r},{g},{b}). Did not match any of {st_rgb_list}.")
                            else:
                                self.logger.warning("Super Troop check out of bounds.")
                    except Exception as e:
                        self.logger.error(f"Super Troop detection error: {e}")


                    # INJECTION LOGIC
                    # PREPARE INJECTION DATA
                    # Check if we have a valid Reference Placement (Y < 900) to copy
                    ref_place = self.hb_coords.get("reference_place_pos", [150, 517]) # Default
                    
                    # Scan for valid placement in Troops list just in case
                    def find_place(obj):
                        if isinstance(obj, (list, tuple)) and len(obj) == 2 and all(isinstance(x, (int, float)) for x in obj):
                            if obj[1] < 900: return obj
                        elif isinstance(obj, list):
                            for item in obj:
                                res = find_place(item)
                                if res: return res
                        return None

                    
                    found_place = find_place(army_positions_copy[0])
                    if found_place: ref_place = found_place
                    
                    # NEW LOGIC: Use special_troop_drop for placement
                    # "click that coordinate [ 382, 298] 10 times for each special troop tile"
                    st_drop_pos = self.special_troop_drop[0] # Expecting [[382, 298]]
                    
                    placeholders = []
                    for i in range(num_super):
                        # Get count for this special troop index, default to 10 if missing
                        clicks = self.special_troop_counts[i] if i < len(self.special_troop_counts) else 10
                        
                        select_dummy = self.hb_coords.get("special_troop_select_dummy", [0, 950]) 
                        
                        seq = [select_dummy]
                        for _ in range(clicks):
                            seq.append(st_drop_pos)
                            
                        # Add this sequence to the master placeholders list
                        placeholders.extend(seq)

                    # DETERMINE INJECTION POINT
                    if is_special_start:
                        # Case A: Start -> Inject into Troops (List 0)
                        # Shifts Everything (Troops, CC, Heroes, Spells)
                        army_positions_copy[0] = placeholders + army_positions_copy[0]
                        self.logger.debug(f"Injected {num_super} Special Troop sequences (Select + 10 Drops) into Troops (Start).")
                    else:
                        # Case B: End of Troops category
                        # This places them AFTER other troops but BEFORE CC/Heroes/Spells
                        army_positions_copy[0] = army_positions_copy[0] + placeholders
                        self.logger.debug(f"Injected {num_super} Special Troop sequences (Select + 10 Drops) into End of Troops phase.")

                # -----------------------------
                # --- HERO EXPANSION LOGIC ---
                # User Request: "make sure there are the number of heroes based on the counter... not necessarily the coordinate itself."
                # We need to ensure army_positions_copy[2] (Heroes) has enough slots for 'available_heros'.
                
                if len(army_positions_copy) > 2:
                    # Determine target count
                    target_hero_count = 4 # Default
                    if isinstance(available_heros, int):
                        target_hero_count = available_heros
                    elif isinstance(available_heros, list):
                        target_hero_count = len(available_heros)
                    
                    if target_hero_count == 0:
                        self.logger.debug(f"Target hero count is 0. Clearing hero slots.")
                        army_positions_copy[2] = []
                    
                    elif target_hero_count > 0:
                        hero_list = army_positions_copy[2]
                        # Count existing selection slots (Y > 900)
                        existing_hero_selects = []
                        def scan_hero_selects(obj):
                            if isinstance(obj, (list, tuple)):
                                if len(obj) == 2 and all(isinstance(x, (int, float)) for x in obj):
                                    if obj[1] > 900: existing_hero_selects.append(obj)
                                else:
                                    for item in obj: scan_hero_selects(item)
                        scan_hero_selects(hero_list)
                        
                        current_count = len(existing_hero_selects)
                        
                        if current_count < target_hero_count and current_count > 0:
                            self.logger.debug(f"Expanding Hero slots from {current_count} to {target_hero_count}.")
                            # We need to add (target - current) more slots.
                            # We will replicate the FIRST slot structure we can find.
                            # Assuming standard structure: [[Select, Place], [Select, Place]...] OR [[Select, Place]]
                            
                            needed = target_hero_count - current_count
                            
                            # Simple assumption: The hero_list itself is a list of [Select, Place] pairs.
                            # Or it's a list containing them.
                            # If we just duplicate the content of the list, we might duplicate placement logic too.
                            
                            # Strategy: Verify structure and replicate the [Select, Place] unit.
                            # We assume the hero_list is a flat list of coordinates [S, P, S, P...] or a list of pairs [[S,P], [S,P]].
                            # Vision propagation flattens things sometimes, but let's check structure.
                            
                            # Check if the first two items form a valid [Select, Place] pair
                            # Select: y > 900, Place: y < 900 (usually)
                            # Or just assume stride of 2.
                            
                            if len(hero_list) >= 2:
                                # We assume a stride of 2 for (Select, Place)
                                template_unit = hero_list[0:2] # Copy first two items
                                # Deep copy the template
                                
                                for _ in range(needed):
                                    hero_list.extend(copy.deepcopy(template_unit))
                                    
                                self.logger.debug(f"Expanded hero list. New length: {len(hero_list)} (Expected {target_hero_count * 2})")
                                    
                # -----------------------------
                
                # Configurable Gaps
                GAP_INTRA_CATEGORY = 8   # Pixels between same category tiles
                # User requested "barrier of 20" after category is done.
                GAP_INTER_CATEGORY = 24 
                
                last_used_category_idx = -1
                
                # Iterate phases: [0: Troops, 1: CC, 2: Heroes, 3+: Spells]
                for phase_idx, phase_list in enumerate(army_positions_copy):
                    
                    found_select_in_phase = False
                    
                    # We need to update nested coordinates. 
                    # Helper function to traverse and update SELECT coords (Y > 900)
                    def update_phase_coords(obj, phase_active_idx):
                        nonlocal current_x
                        nonlocal found_select_in_phase
                        
                        if isinstance(obj, (list, tuple)):
                            # Check if it's a coordinate pair [x, y]
                            if len(obj) == 2 and all(isinstance(x, (int, float)) for x in obj):
                                if obj[1] > 900:
                                    # This is a Select Coordinate (Slot)
                                    # Assign the Current Calculated X
                                    
                                    # If this is the VERY FIRST tile (Phase 0, First Item),
                                    # it should match 'cx'. 
                                    # logic: The loop state 'current_x' *is* the next slot's center.
                                    # For the very first one, we initialize current_x = cx.
                                    
                                    new_coord = [int(current_x), int(current_y)]
                                    found_select_in_phase = True
                                    
                                    # Advance X for the NEXT tile
                                    current_x += (w + GAP_INTRA_CATEGORY)
                                    return new_coord
                                else:
                                    # Non-select coord (Placement), keep as is
                                    return [obj[0], obj[1]]
                            else:
                                # Recursively update
                                return [update_phase_coords(item, phase_active_idx) for item in obj]
                        return obj

                    # Update the phase in place
                    army_positions_copy[phase_idx] = update_phase_coords(phase_list, phase_idx)
                    
                    # After finishing a Phase, if it contained tiles, we apply the INTER-CATEGORY gap
                    # Note: We already added INTRA_CATEGORY gap after the last tile.
                    # So we need to adjustments:
                    if found_select_in_phase:
                        # We stepped forward by (W+8) after the last item.
                        # We want that last step to have been (W+GAP_INTER).
                        # So add difference.
                        current_x += (GAP_INTER_CATEGORY - GAP_INTRA_CATEGORY)
                

                self.logger.debug("Coordinates propagated successfully based on First Tile detection.")
                
            else:
                self.logger.warning("First Tile NOT Detected. Using Config Coordinates with Normalization.")

            # -----------------------------------------------
            
            
            # --- VISUALIZATION of the Final Plan ---
            try:
                if os.path.exists(debug_screen_path):
                    debug_img = cv2.imread(debug_screen_path)
                    
                    # Colors for phases: 0=Troops(Blue), 1=CC(Yellow), 2=Heroes(Green), 3=Spells(Red)
                    # BGR Format
                    phase_colors = [
                        (255, 0, 0),    # Blue
                        (0, 255, 255),  # Yellow
                        (0, 255, 0),    # Green
                        (0, 0, 255),    # Red
                        (255, 0, 255)   # Magenta (Extra)
                    ]
                    
                    global_counter = 1
                    
                    # Iterate explicitly by phase to assign colors
                    for p_idx, p_list in enumerate(army_positions_copy):
                        # Extract selects for this specific phase
                        phase_selects = []
                        def extract_phase_selects(obj):
                            if isinstance(obj, (list, tuple)):
                                if len(obj) == 2 and all(isinstance(x, (int, float)) for x in obj):
                                    if obj[1] > 900: phase_selects.append(obj)
                                else:
                                    for item in obj: extract_phase_selects(item)
                            elif isinstance(obj, list):
                                for item in obj: extract_phase_selects(item)
                        extract_phase_selects(p_list)
                        
                        self.logger.debug(f"Phase {p_idx} detected count: {len(phase_selects)}")

                        # Pick color
                        color = phase_colors[min(p_idx, len(phase_colors)-1)]
                        
                        for (fx, fy) in phase_selects:
                            # Draw box using detected W/H
                            bx = int(fx - w/2)
                            by = int(fy - h/2)
                             
                            cv2.rectangle(debug_img, (bx, by), (bx+w, by+h), color, 2)
                            cv2.putText(debug_img, str(global_counter), (bx, by+20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
                            global_counter += 1
                    
                    if self.logger.isEnabledFor(10):
                        debug_inferred_path = debug_screen_path.replace('.png', '_inferred_army_plan.png')
                        cv2.imwrite(debug_inferred_path, debug_img)
                        self.logger.debug(f"Saved Inferred Army Plan to {debug_inferred_path}")
            except Exception as e:
                self.logger.error(f"Debug viz failed: {e}")
            # -----------------------------------------------
            
        except Exception as e:
            self.logger.error(f"Failed to create pre-adjustment debug screenshot: {e}")
            
            
        if len(army_positions_copy) >= 4 and not army_key == 'auto_lose':


            troops_pos = army_positions_copy[0]
            cc_pos = army_positions_copy[1]
            heroes_pos = army_positions_copy[2]
            spells_pos = army_positions_copy[3]
            
            self.logger.debug(f"Troops Positions: {troops_pos}")
            self.logger.debug(f"CC Positions: {cc_pos}")
            self.logger.debug(f"Heroes Positions: {heroes_pos}")
            self.logger.debug(f"Spells Positions: {spells_pos}")
            # 1. Troops
            self.window_controller.execute_clicks(troops_pos, delay=delay)
            
            # 2. Clan Castle
            self.window_controller.execute_clicks(cc_pos, delay=delay)

            # 3. Heroes
            if not army_key == 'auto_lose':
                # Determine how many heroes we actually have positions for
                # Assuming stride of 2 [Select, Place]
                num_pairs = len(heroes_pos) // 2
                
                if num_pairs > 0:
                    # 2 passes: 1st for deployment, 2nd for ability activation
                    # Pass 1: Deployment
                    self.logger.info("Deploying Heroes...")
                    for i in range(num_pairs):
                        idx = i * 2
                        select_pos = heroes_pos[idx]
                        place_pos = heroes_pos[idx+1]
                        
                        self.window_controller.execute_clicks([select_pos], delay=delay)
                        self.window_controller.execute_clicks([place_pos], delay=delay)
                        
                    time.sleep(3) # Wait before activation
                    
                    # Pass 2: Ability Activation
                    self.logger.info("Activating Hero Abilities...")
                    for i in range(num_pairs):
                        idx = i * 2
                        select_pos = heroes_pos[idx]
                        # Click select again to activate
                        self.window_controller.execute_clicks([select_pos], delay=delay)
                        # No need to place again
                else:
                    self.logger.warning("No hero positions available to execute.")

            # 4. Spells (and any extra phases)
            for idx, spells_list in enumerate(spells_pos):
                
                # Annotate spell positions for debugging

                self.window_controller.execute_clicks(spells_list, delay=delay)
                time.sleep(1)

            self.logger.info("Attack finished")

        
        

    def get_enemy_base_resources(self):
        screenshot_path = self.manage_screenshot_storage('enemy_base_resource_stats')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        gold, elixir, dark_elixir = extract_resources_from_image(screenshot_path)
        return gold, elixir, dark_elixir


    def find_enemy_base(self):
        """
        Loops through enemy bases until one is found that meets the gold and elixir thresholds.
        Returns the gold, elixir, and dark_elixir values of the found base.
        """
        gold, elixir, dark_elixir = self.get_enemy_base_resources()
        self.logger.info(f"\nGold: {gold}, Elixir: {elixir}, Dark Elixir: {dark_elixir}")
        
        # Initialize safeguard counter
        same_resource_counter = 0
        last_resources = (gold, elixir, dark_elixir)

        time.sleep(2)
        while gold + elixir < self.enemy_gold_threshold + self.enemy_elixir_threshold:
            # Find next base
            self.window_controller.execute_clicks(self.find_next_positions, delay=0)
            self.window_controller.execute_clicks(self.find_next_positions, delay=0)
            
            # reduced sleep
            self.wait_for_base_load()
            time.sleep(1) # Reduced from 5s to 1s

            # Check resources of new base
            gold, elixir, dark_elixir = self.get_enemy_base_resources()
            self.logger.info(f"\nGold: {gold}, Elixir: {elixir}, Dark Elixir: {dark_elixir}")

            # Safeguard: Check for identical consecutive readings
            current_resources = (gold, elixir, dark_elixir)
            if current_resources == last_resources:
                same_resource_counter += 1
                if same_resource_counter >= 20:
                    self.logger.warning("Safeguard triggered: 20 consecutive identical resource readings. Restarting detection.")
                    return None
            else:
                same_resource_counter = 0
                last_resources = current_resources
        
        return gold, elixir, dark_elixir


    def start_attack(self, army_key=None, available_heros=0, ranked_mode=False):
        """
        Starts an attack using the specified army key from self.attack_armies.
        :param army_key: String key for the army type (e.g., 'e_drag_rage_goblin').
        """
        self.reset_select()
        # if ranked mode, increment ranked game count
        if ranked_mode and self.ranked_game_count < 10:
            self.ranked_game_count += 1
            # start attack
            self.window_controller.execute_clicks(self.start_attack_positions[0])
            offset = self.hb_coords.get("ranked_mode_offset", [300, 0])
            ranked_mode_position = [self.start_attack_positions[1][0] + offset[0] , self.start_attack_positions[1][1] + offset[1] ]
            self.logger.debug(f"Ranked mode position: {ranked_mode_position}")
            self.window_controller.execute_clicks(ranked_mode_position)
        else:
            # start attack
            self.window_controller.execute_clicks(self.start_attack_positions)
        # let the game load defenders base
        # let the game load defenders base
        self.wait_for_base_load()
        
        # if not auto_lose, find enemy base
        if not army_key == 'auto_lose':
            # Find a suitable enemy base
            result = self.find_enemy_base()
            if result is None:
                self.logger.warning("Restarting attack process from start_attack due to safeguard.")
                return self.start_attack(army_key, available_heros, ranked_mode)
        # Attack base
        self.logger.info("\n[Home Base] Attacking base...")
        # Attack Type
        if army_key is None:
            army_key = self.attack_armies.keys()[0]
        army = self.attack_armies.get(army_key)
        if not army:
            raise ValueError(f"Army key '{army_key}' not found in attack_armies.")
        
        # Place the army
        self.army_placement(army_key, available_heros, delay=0.25)
        
        # delay for the attack to complete
        if not army_key == 'auto_lose':
            # Dynamic Wait for Battle End
            max_duration = 170
            
            self.logger.info(f"Waiting for battle to end (Max {max_duration}s)...")
            start_wait = time.time()
            check_interval = 5
            
            while (time.time() - start_wait) < max_duration:
                 if self.check_return_home_visible():
                     self.logger.info("Return Home detected! Battle ended early.")
                     break
                 time.sleep(check_interval)
            self.window_controller.scroll_wheel_down(20)
        else:
            time.sleep(1)

        # Go Home
        self.window_controller.execute_clicks(self.go_home_positions)
        time.sleep(2)
        self.return_home_refocus()
        self.reset_select(delay=0.2, num_clicks=10)

    def main_attack_loop(self, available_heros, ranked_mode, fill_storage=False):
        while True:
            # check if resources are maxed
            if self.check_max_resources():
                break
            # start attack
            self.start_attack('main_attack', available_heros, ranked_mode)
        
        # check for upgrades and if there are still builders available, start attack loop again to get full resources
        if self.start_builder_upgrade():
            self.logger.info("Builders upgraded. Checking heros again...")
            available_heros = self.check_heros()
            self.main_attack_loop(available_heros, ranked_mode)
        
        # get max resources again
        if fill_storage:
            while True:
                # check if resources are maxed
                if self.check_max_resources():
                    break
                # start attack
                self.start_attack('main_attack', available_heros, ranked_mode)
        
    def lower_trophy_count(self):
        for _ in range(10):
            self.start_attack('auto_lose')
            time.sleep(1)
        

    """ --------------------------- Upgrade Functions --------------------------------- """

    def upgrade_walls(self):
        if not self.check_builder_upgrade():
            self.logger.info("No builders available, skipping wall upgrade.")
            return
        
        # reset select
        self.reset_select()
        
        # check if goblin 
        if self.check_goblin_builder():
            self.logger.info("Goblin builder in region, skipping wall upgrade.")
            return
        
        # once for gold once for elixir
        gold_region = self.hb_coords.get("wall_gold_region", [958, 808, 1065, 830])
        elixir_region = self.hb_coords.get("wall_elixir_region", [1118, 808, 1220, 830])
        # buttons pos
        add_wall_button_position = self.hb_coords.get("add_wall_button_pos", [863, 854])
        remove_wall_button_position = self.hb_coords.get("remove_wall_button_pos", [554, 858])
        confirm_button_pos = self.hb_coords.get("wall_confirm_button_pos", [1019, 665])
        for i, check_region_pos  in enumerate([gold_region, elixir_region]):
            # Execute click to open build options and move mouse to the opened area
            self.window_controller.execute_clicks(self.build_upgrade_positions[0], verbose=True)
            time.sleep(1)
            # scroll down 5 times
            for _ in range(6):
                # drag page down
                drag_coords = self.hb_coords.get("wall_scroll_drag_coords", [889, 578, 885, 234])
                self.window_controller.drag_in_window(*drag_coords)
                time.sleep(.75)
                # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                screenshot_path = self.manage_screenshot_storage('wall_upgrade_test')
                self.window_controller.capture_minimized_window_screenshot(screenshot_path)
                search_region = self.hb_coords.get("wall_upgrade_search_region", [600, 113, 1160, 684])
                upgrade_detected = detect_word_in_region(screenshot_path, 'wall', *search_region)
                # check if wall upgrade is in list
                if upgrade_detected:
                    self.logger.info("Wall word detected.")
                    break
            # check if wall upgrade is in list
            if not upgrade_detected and i == 0:
                self.logger.info("No walls found in suggested upgrades (Gold). Breaking wall upgrade loop.")
                break

            if upgrade_detected:
                detected_wall_element = max(upgrade_detected, key=lambda x: (x['similarity'], x['confidence']))
                self.logger.debug(f"Detected wall element: {detected_wall_element}")
                # click the middle of the box 
                wall_upgrade_position = int((detected_wall_element['bbox'][0] + detected_wall_element['bbox'][2]) / 2) , int((detected_wall_element['bbox'][1] + detected_wall_element['bbox'][3]) / 2)
                self.logger.debug(f"Wall upgrade position: {wall_upgrade_position}")
                # self.logger.info(f"Wall upgrade position: {wall_upgrade_position}")
                self.window_controller.execute_clicks(wall_upgrade_position, verbose=True)
                time.sleep(1)
                start_dt = datetime.now()
                # print(f"check region: {check_region_pos}")
                for j in range(10):
                    
                    # 1. Capture for Resource Check
                    # Use cleanup=False to speed up capture (avoid file listing delay)
                    screenshot_path = self.manage_screenshot_storage('wall_resource_check', cleanup=False)
                    end_dt = datetime.now()
                    self.window_controller.capture_minimized_window_screenshot(screenshot_path, read_back=False)
                    self.logger.debug(f"\nTime elapsed: {(end_dt - start_dt).total_seconds()} seconds\n")
                    self.logger.debug(f"Screenshot has been taken")
                    
                    # check both wall upgrades gold and elixir
                    self.logger.debug(f"Checking resource region upgrade color: {screenshot_path}")
                    resource_region_color = detect_red_or_white(screenshot_path, check_region_pos)
                    
                    # 2. Copy/Capture for Max Wall Check (User requested separate folders)
                    # We reuse the image but save it to the other folder for separation
                    # Cleanup=False for speed here too
                    max_wall_path = self.manage_screenshot_storage('wall_max_check', cleanup=False)
                    shutil.copy(screenshot_path, max_wall_path)
                    
                    # check for over max capacity
                    self.logger.debug(f"Checking max wall message region upgrade color: {max_wall_path}")
                    max_wall_region = self.hb_coords.get("max_wall_message_region", [423, 286, 625, 330])
                    max_wall_msg_color = detect_is_red(max_wall_path, max_wall_region)
                    
                    # Debug Annotation
                    if self.logger.isEnabledFor(10):
                        try:
                            # Load image
                            debug_img = cv2.imread(screenshot_path)
                            if debug_img is not None:
                                # Resource Region
                                # check_region_pos is [x1, y1, x2, y2]
                                cv2.rectangle(debug_img, (int(check_region_pos[0]), int(check_region_pos[1])), (int(check_region_pos[2]), int(check_region_pos[3])), (0, 0, 255), 2)
                                resource_debug_path = screenshot_path.replace('.png', '_resource_region.png')
                                cv2.imwrite(resource_debug_path, debug_img)

                                # Max Wall Region
                                debug_img_2 = cv2.imread(max_wall_path)
                                cv2.rectangle(debug_img_2, (int(max_wall_region[0]), int(max_wall_region[1])), (int(max_wall_region[2]), int(max_wall_region[3])), (255, 0, 0), 2)
                                max_wall_debug_path = max_wall_path.replace('.png', '_max_wall_msg.png')
                                cv2.imwrite(max_wall_debug_path, debug_img_2)
                        except Exception as e:
                            self.logger.error(f"Failed to save debug images: {e}")
                            
                    self.logger.debug(f"detect max wall count message color: {max_wall_msg_color}")
                    self.logger.debug(f"resource_region color: {resource_region_color}")
                    
                    if max_wall_msg_color == 'red':
                        self.logger.info("Max wall count message detected (red)")
                         # resouce button press
                        res_pos_1 = self.hb_coords.get("resource_upgrade_pos_1", [1018, 853])
                        res_pos_2 = self.hb_coords.get("resource_upgrade_pos_2", [1179, 866])
                        resouce_upgrade_button_pos = res_pos_1 if i == 0 else res_pos_2
                        self.window_controller.execute_clicks(resouce_upgrade_button_pos, verbose=True)
                        time.sleep(.5)
                        # confirm button
                        self.window_controller.execute_clicks(confirm_button_pos, verbose=True)
                        time.sleep(.5)
                        break
                    elif resource_region_color == 'red':
                        self.logger.debug('red')
                        # if first iteration
                        if j == 0:
                            self.reset_select()
                            break
                        # remove a wall
                        self.logger.debug(f"Removing wall: {remove_wall_button_position}")
                        self.window_controller.execute_clicks(remove_wall_button_position, verbose=True)
                        time.sleep(.5)
                        # resouce button press
                        res_pos_1 = self.hb_coords.get("resource_upgrade_pos_1", [1018, 853])
                        res_pos_2 = self.hb_coords.get("resource_upgrade_pos_2", [1179, 866])
                        resouce_upgrade_button_pos = res_pos_1 if i == 0 else res_pos_2
                        self.window_controller.execute_clicks(resouce_upgrade_button_pos, verbose=True)
                        time.sleep(.5)
                        # confirm button
                        self.window_controller.execute_clicks(confirm_button_pos, verbose=True)
                        time.sleep(.5)
                        break
                    elif resource_region_color == 'white':
                        self.logger.debug('white')
                        self.logger.debug(f"Adding wall: {add_wall_button_position}")
                        self.window_controller.execute_clicks(add_wall_button_position, verbose=True)
                        if j == 0:
                            self.window_controller.execute_clicks(add_wall_button_position, verbose=True)
                        start_dt = datetime.now()
                        self.logger.debug(f"Take a screenshot")
                        
                # Deferred cleanup (safe to do here at end of inner loop iteration)
                self.cleanup_screenshot_storage('wall_resource_check')
                self.cleanup_screenshot_storage('wall_max_check')
                
            else:
                self.logger.info("No wall upgrade available")
        
            
            
        
    def check_goblin_builder(self):
        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = self.manage_screenshot_storage('goblin_builder')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        is_goblin = is_goblin_builder_in_region(screenshot_path)
        return is_goblin

    def check_goblin_researcher(self):
        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = self.manage_screenshot_storage('goblin_researcher')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        is_goblin = is_goblin_researcher_in_region(screenshot_path)
        return is_goblin

    def check_builder_upgrade(self):
        # check if goblin builder is in region
        is_goblin = self.check_goblin_builder()
        if is_goblin:
            self.logger.info("Goblin builder in region, skipping builder upgrade.")
            return 0
        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = self.manage_screenshot_storage('builder_upgrade')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        # Check if a build is available
        builders_available = extract_builders_available_from_image(screenshot_path)
        if builders_available > 0:
            self.logger.info("Builder upgrade available")
            return builders_available
        else:
            self.logger.info("No builder upgrade available")
            return 0
        
    def check_builder_upgrade_button(self):
        # get loc for upgrade button
        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = self.manage_screenshot_storage('builder_upgrade_button_loc')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        # get resource square location or hero hall bool
        results = detect_info_button_color_location(screenshot_path)
        # if in hero hall, get location of hero upgrade
        if results == 'hero hall':
            screenshot_path = self.manage_screenshot_storage('hero_upgrade_loc')
            self.window_controller.capture_minimized_window_screenshot(screenshot_path)
            results = detect_hero_upgrade(screenshot_path)
            # Filter for only Hero 1 (index 0)
            results = [r for r in results if r['index'] == 0]
        return results
        
    def start_builder_upgrade(self):
        # reset select
        self.reset_select()
        # check if builder upgrade is available
        num_builders = self.check_builder_upgrade()
        if num_builders > 0:
            self.logger.info("Starting builder upgrade...")
            # Select builder suggestions
            self.window_controller.execute_clicks(self.build_upgrade_positions[:1])
            # select building to upgrade
            for i in range(3):
                # get new y cord depending on the number of builders
                step_y = self.hb_coords.get("builder_upgrade_step_y_small", 20)
                new_cord = [self.build_upgrade_positions[1][0], self.build_upgrade_positions[1][1] + (step_y * i)]
                self.window_controller.execute_clicks(new_cord)

            # get loc for upgrade button
            results = self.check_builder_upgrade_button()
            self.logger.debug(f"Upgrade button results: {results}")
            # if in resource square, get location of resource square
            if results:
                # get location of resource square
                location = results[0]['pos'][0], results[0]['pos'][1]
                self.logger.debug(f"Upgrade button location: {location}")
                # selected upgrade and confirm
                self.window_controller.execute_clicks(location)
                self.window_controller.execute_clicks(self.build_upgrade_positions[-1])
                self.window_controller.execute_clicks(self.build_upgrade_positions[-1])
            else:
                self.logger.warning("No upgrade button available")
                self.window_controller.execute_clicks(self.build_upgrade_positions[2:])
            
            # reset select
            self.reset_select()

            # check number of builders again
            num_builders = self.check_builder_upgrade()
            if num_builders > 0 and num_builders <= 6:
                self.logger.info("Builder upgrade available")
                return True
            else:
                self.logger.info("No builder upgrade available")
                return False
        else:
            self.logger.info("No builder upgrade available")
            return False
        
    def check_laboratory_upgrade(self):
        # check if goblin researcher is in region
        is_goblin = self.check_goblin_researcher()
        if is_goblin:
            self.logger.info("Goblin researcher in region, skipping researcher upgrade.")
            return 0
        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = self.manage_screenshot_storage('laboratory_upgrade')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        # Check if a build is available
        research_available = extract_research_available_from_image(screenshot_path)
        if research_available:
            self.logger.info("Research upgrade available")
            return True
        else:
            self.logger.info("No research upgrade available")
            return False
        
    def start_laboratory_upgrade(self):
        # reset select
        self.reset_select()
        # check if research upgrade is available
        research_available = self.check_laboratory_upgrade()
        if research_available:
            self.logger.info("Starting laboratory upgrade...")
            # execute clicks to upgrade research
            self.logger.info(f"Research upgrade positions: {self.research_upgrade_positions}")
            # select research suggestions
            self.window_controller.execute_clicks(self.research_upgrade_positions[0])
            # select research to upgrade
            for _ in range(3):
                res_step_y = self.hb_coords.get("research_upgrade_step_y", 30)
                new_cord = [self.research_upgrade_positions[1][0], self.research_upgrade_positions[1][1] - (res_step_y * _)]
                self.window_controller.execute_clicks(new_cord)
            # select research to upgrade
            self.window_controller.execute_clicks(self.research_upgrade_positions[2])
            # reset select
            self.reset_select()
        else:
            self.logger.info("No laboratory upgrade available")
            return False
        
    def check_pet_upgrade(self):
        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = self.manage_screenshot_storage('pet_upgrade')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        # Check if a build is available
        pet_upgrade_available = extract_pet_upgrade_available_from_image(screenshot_path) 
        return pet_upgrade_available
        
    def check_pet_max_level(self):
        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = self.manage_screenshot_storage('pet_max_level')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        is_maxed = is_pet_max_level_from_image(screenshot_path)
        return is_maxed
    
    def check_pet_upgrade_in_progress(self):
        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = self.manage_screenshot_storage('pet_upgrade_in_progress')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        time.sleep(10)
        pet_upgrade_in_progress = is_pet_upgrade_in_progress_from_image(screenshot_path)
        return pet_upgrade_in_progress

    def start_pet_upgrade(self):
        self.reset_select()
        time.sleep(1)
        # Execute clicks to get to the pet building
        default_pet_button_position = self.hb_coords.get("default_pet_button_pos", [1088, 871])
        self.pet_building_position.append(default_pet_button_position)
        self.window_controller.execute_clicks(self.pet_building_position)
        # get exit pet upgrade positions
        exit_pet_upgrade_positions = self.exit_pet_upgrade_positions
        # check if pet upgrade in progress
        self.logger.debug("[Pet] Checking if pet upgrade in progress...")
        pet_upgrade_in_progress = self.check_pet_upgrade_in_progress()
        if pet_upgrade_in_progress:
            self.logger.info("[Pet] Pet upgrade in progress, skipping.")
            # exit pet upgrade
            self.window_controller.execute_clicks(exit_pet_upgrade_positions)
            return
        else:
            self.logger.debug("[Pet] Pet upgrade not in progress, continuing.") 
        
        
        # Outer loop for pages (Drags)
        # "If there is no result through all four, then we drag, and then repeat."
        # Assuming 2 pages (0-3, 4-7)
        for page_idx in range(2):
            self.logger.debug(f"[Pet] Checking Page {page_idx + 1}")
            
            # Loop through up to 4 pets
            for i, pos in enumerate(self.pet_positions):
                self.logger.debug(f"current pet pos: {pos}")
                if i == 2:
                    time.sleep(20)
                
                current_pet_index = (page_idx * 4) + i + 1
                
                # click specific pet to upgrade 
                self.window_controller.execute_clicks(pos)
                time.sleep(1)
                # see if max level text pops up
                is_maxed = self.check_pet_max_level()
                self.logger.debug(f"[Pet] Pet {current_pet_index} max level: {is_maxed}")
                time.sleep(6)
                if is_maxed:
                    continue
                pet_upgrade_available =  self.check_pet_upgrade()
                self.logger.info(f"[Pet] Pet {current_pet_index} upgrade available: {pet_upgrade_available}")
                if pet_upgrade_available == 'available':
                    # Execute clicks to confirm upgrade
                    self.window_controller.execute_clicks(self.pet_confirm_upgrade_positions)
                    # exit pet upgrade
                    self.window_controller.execute_clicks(exit_pet_upgrade_positions)
                    # reset select
                    self.reset_select()
                    return True
                else:
                    self.window_controller.execute_clicks(exit_pet_upgrade_positions)
                    self.logger.info(f"[Pet] Pet {current_pet_index} upgrade not available.")
            
            # If we are here, we finished the loop for this page without returning.
            # Perform Drag if this is the first page
            if page_idx == 0:
                 self.logger.info("[Pet] No upgrade found on Page 1. Dragging to Page 2.")
                 if self.pet_drag_coords:
                     self.window_controller.drag_in_window(*self.pet_drag_coords)
                     time.sleep(1)
            
        self.logger.info("[Pet] No pet upgrade available after checking all pets.")
        # exit pet upgrade
        self.window_controller.execute_clicks(exit_pet_upgrade_positions)
        # reset select
        self.reset_select()
        return False

    """ --------------------------- Raid Functions --------------------------------- """

    def check_raid(self):
        """
        Initiates a raid by clicking through the raid screen and checking up to 9 houses if any is raidable.
        Returns True if a raidable base is found, otherwise False.
        """
        # Step 1: Click to open the raid screen
        start_raid_positions = self.launch_raid_start_positions
        self.window_controller.execute_clicks(start_raid_positions)
        time.sleep(2)

        # Step 2: Loop through up to 9 houses
        for i in range(1, 10):
            raid_positions_file = f'data/click_pos/launch_raid/raid_loc/raid_{i}.txt'
            if not os.path.exists(raid_positions_file):
                self.logger.warning(f"[Raid] {raid_positions_file} does not exist, skipping.")
                continue
            raid_positions = self.raid_positions
            self.window_controller.execute_clicks(raid_positions)
            time.sleep(2)
            screenshot_path = self.manage_screenshot_storage(f'raid_check_house_{i}')
            self.window_controller.capture_minimized_window_screenshot(screenshot_path)
            color = detect_attack_button_color(screenshot_path)
            self.logger.info(f"[Raid] House {i} attack button color: {color}")
            if color == 'red':
                self.logger.info(f"[Raid] House {i} is raidable!")
                return True
            else:
                self.logger.info(f"[Raid] House {i} is not raidable.")
        self.logger.info("[Raid] No raidable base found after checking all houses.")
        return False

    def start_raid(self):
        raid_available = self.check_raid()
        if raid_available:
            self.logger.info("Raid available")
        else:
            self.logger.info("No raid available")
            return

    """ --------------------------- Apprentices Functions --------------------------------- """

    def check_apprentices_status(self):
        """
        Captures a screenshot and detects the status (busy/free) of apprentices using detect_apprentices_status_from_image.
        Prints and returns the status dict.
        """
        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = self.manage_screenshot_storage('apprentices_status')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        status = detect_apprentices_status_from_image(screenshot_path)
        self.logger.debug(f"[{'Apprentices Status'}] {status}")
        return status

    def start_apprentices(self):
        """
        Resets select, then checks and prints the apprentices status.
        Returns the status dict.
        """
        # reset select
        self.reset_select()

        # select apprentice building 
        self.window_controller.execute_clicks(self.apprentice_building_position)

        # check apprentices status
        status = self.check_apprentices_status()
        
        # if research is free, start research
        if status['research'] == 'free':
            # start research
            self.window_controller.execute_clicks(self.apprentice_research_positions)
        # if builder is free, start builder
        if status['builder'] == 'free':
            # start builder
            self.window_controller.execute_clicks(self.apprentice_builder_positions)
        # if alchemist is free, start alchemist
        if status['alchemist'] == 'free':
            # Pass blocks removed
            pass # Placeholder if logic is added later
        # reset select
        self.reset_select()



    


    

 

    
