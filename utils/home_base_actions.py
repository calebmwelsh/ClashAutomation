import copy
import glob
import os
import shutil
import sys
import time
from datetime import datetime

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
        
        # Avoid mutating the list in-place
        clicks = self.reset_camera_positions[:-1]
        end_pos = self.reset_camera_positions[-1]
        
        self.window_controller.execute_clicks(clicks)
        time.sleep(1.5)
        self.wait_for_base_load()
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
            time.sleep(0.5)
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
            army_key = list(self.attack_armies.keys())[0] if self.attack_armies else None
        army = self.attack_armies.get(army_key)
        if not army:
            raise ValueError(f"Army key '{army_key}' not found in attack_armies.")

        # --- TROOP CALCULATION ---
        total_select_count = 0
        if army_key == 'main_attack':
            try:
                positions = army.get("positions", [])
                if len(positions) >= 4:
                    counts = []
                    for i in range(4):
                        sublist = positions[i]
                        count = 0
                        for coord in sublist:
                            if isinstance(coord, (list, tuple)) and len(coord) == 2:
                                if coord[1] >= 918: # Threshold for select region (0.85)
                                    count += 1
                        counts.append(count)
                    
                    num_heroes = available_heros if isinstance(available_heros, int) else 0
                    special_count = self.special_troop_event if self.special_troop_event > 0 else 0
                    total_select_count = counts[0] + counts[1] + (counts[2] * num_heroes) + counts[3] + special_count
                    
                    self.logger.info(f"[Calculation] Breakdown: {counts[0]} (Troops) + {counts[1]} (CC) + ({counts[2]} * {num_heroes} Heroes) + {counts[3]} (Spells) + {special_count} (Special)")
                    self.logger.info(f"[Calculation] Total Troops/Clicks over 0.85: {total_select_count}")
            except Exception as e:
                self.logger.error(f"Error in troop calculation: {e}")

        # Create a copy of army positions for potential adjustments
        army_positions_copy = copy.deepcopy(army["positions"])
        needs_scroll = total_select_count > 14
        
        # --- PHASE 1: INITIAL DETECTION & TROOP DEPLOYMENT ---
        try:
            debug_screen_path = self.manage_screenshot_storage('army_placement_phase_1')
            self.window_controller.capture_minimized_window_screenshot(debug_screen_path)
            
            # 1. Detect First Tile Anchor
            first_tile_data = detect_first_army_tile(debug_screen_path)
            if not first_tile_data:
                self.logger.warning("First Tile NOT Detected in Phase 1.")
                return 

            cx, cy, ft_rect, _ = first_tile_data
            w, h = ft_rect[2], ft_rect[3]
            self.logger.debug(f"Phase 1 Anchor: {cx}, {cy} | W={w}, H={h}")

            # 2. Super Troop Injection
            num_super = int(self.special_troop_event) if self.special_troop_event else 0
            if num_super > 0 and len(army_positions_copy) > 0:
                is_special_start = detect_super_troop_at_pixel(
                    debug_screen_path, cx, cy,
                    self.config["HomeBaseGeneral"].get("special_troop_event_rgb", []),
                    self.logger
                )
                
                st_drop_pos = self.special_troop_drop[0]
                placeholders = []
                for i in range(num_super):
                    clicks = self.special_troop_counts[i] if i < len(self.special_troop_counts) else 10
                    select_dummy = self.hb_coords.get("special_troop_select_dummy", [0, 950]) 
                    placeholders.append(select_dummy)
                    for _ in range(clicks):
                        placeholders.append(st_drop_pos)

                if is_special_start:
                    army_positions_copy[0] = placeholders + army_positions_copy[0]
                else:
                    army_positions_copy[0] = army_positions_copy[0] + placeholders

            # 3. Hero Expansion
            if len(army_positions_copy) > 2:
                target_hero_count = available_heros if isinstance(available_heros, int) else 4
                if target_hero_count == 0:
                    army_positions_copy[2] = []
                elif target_hero_count > 0:
                    hero_list = army_positions_copy[2]
                    existing_hero_selects = [c for c in hero_list if isinstance(c, list) and len(c)==2 and c[1] >= 918]
                    current_count = len(existing_hero_selects)
                    if current_count < target_hero_count and current_count > 0 and len(hero_list) >= 2:
                        needed = target_hero_count - current_count
                        template_unit = hero_list[0:2]
                        for _ in range(needed):
                            hero_list.extend(copy.deepcopy(template_unit))

            # 4. Propagate Coordinates for PHASE 1
            GAP_INTRA = 8
            GAP_INTER = 24
            
            def propagate(phases, start_x, start_y):
                curr_x = start_x
                for p_idx, p_list in enumerate(phases):
                    found_select = False
                    def update_coords(obj):
                        nonlocal curr_x, found_select
                        if isinstance(obj, list) and len(obj) == 2 and all(isinstance(x, (int, float)) for x in obj):
                            if obj[1] >= 918:
                                new_c = [int(curr_x), int(start_y)]
                                curr_x += (w + GAP_INTRA)
                                found_select = True
                                return new_c
                            return [obj[0], obj[1]]
                        elif isinstance(obj, list):
                            return [update_coords(item) for item in obj]
                        return obj
                    phases[p_idx] = update_coords(p_list)
                    if found_select:
                        curr_x += (GAP_INTER - GAP_INTRA)
                return phases

            # We propagate everything initially to have a plan
            army_positions_copy = propagate(army_positions_copy, cx, cy)
            
            # --- EXECUTION PHASE 1 ---
            self.logger.info("Executing Phase 1 (Troops)...")
            self.window_controller.execute_clicks(army_positions_copy[0], delay=delay)

            if not needs_scroll:
                # Normal execution for CC, Heroes, Spells
                self.logger.info("Executing Remaining Phases (Single Pass)...")
                # CC
                self.window_controller.execute_clicks(army_positions_copy[1], delay=delay)
                # Heroes (Double Pass)
                self._deploy_and_activate_heroes(army_positions_copy[2], delay)
                # Spells
                for spell_list in army_positions_copy[3:]:
                    self.window_controller.execute_clicks(spell_list, delay=delay)
            else:
                # --- SCROLL MANEUVER ---
                self.logger.info("[Scroll] Over 14 tiles detected. Scrolling bar...")
                # Start: (0.9497, 0.9259) -> [1641, 1000] | End: (0.0347, 0.9259) -> [60, 1000]
                scroll_start = [1641, 1000]
                scroll_end = [60, 1000]
                self.window_controller.drag_in_window(scroll_start[0], scroll_start[1], scroll_end[0], scroll_end[1])
                time.sleep(1.5)

                # --- PHASE 2: RE-DETECTION & BACKWARDS ALIGNMENT ---
                debug_screen_2 = self.manage_screenshot_storage('army_placement_phase_2')
                self.window_controller.capture_minimized_window_screenshot(debug_screen_2)
                
                # Detect ALL tiles. valid_candidates[0] is leftmost, [-1] is rightmost.
                tile_results = detect_first_army_tile(debug_screen_2)
                if not tile_results:
                    self.logger.warning("No tiles detected in Phase 2! Falling back to leftmost assumption.")
                    nx, ny = cx, cy # Bad fallback but avoids crash
                else:
                    cx2, cy2, _, candidates = tile_results
                    rightmost = candidates[-1]
                    rx, ry = rightmost['x'] + rightmost['w']//2, cy2 # Use rightmost center
                    
                    self.logger.info(f"[Scroll] Phase 2 Rightmost Anchor: {rx}, {ry}")
                    
                    # --- BACKWARDS OFFSET CALCULATION ---
                    GAP_INTRA = 8
                    GAP_INTER = 24
                    
                    def get_select_count(obj):
                        cnt = 0
                        if isinstance(obj, list) and len(obj) == 2 and all(isinstance(x, (int, float)) for x in obj):
                            if obj[1] >= 918: return 1
                        elif isinstance(obj, list):
                            for item in obj: cnt += get_select_count(item)
                        return cnt

                    # Calculate tiles per phase for the remaining army
                    p1_tiles = get_select_count(army_positions_copy[1])
                    p2_tiles = get_select_count(army_positions_copy[2])
                    p3_tiles = 0
                    for sub in army_positions_copy[3:]:
                        p3_tiles += get_select_count(sub)
                    
                    # Distance from center of first tile to center of last tile
                    # Every tile adds (w + GAP_INTRA), except categories add (GAP_INTER - GAP_INTRA) extra
                    total_tiles = p1_tiles + p2_tiles + p3_tiles
                    if total_tiles <= 0:
                        nx, ny = rx, ry
                    else:
                        total_width = (total_tiles - 1) * (w + GAP_INTRA)
                        # Add INTER gap bonuses (16 pixels each)
                        if p1_tiles > 0 and (p2_tiles > 0 or p3_tiles > 0):
                            total_width += (GAP_INTER - GAP_INTRA)
                        if p2_tiles > 0 and p3_tiles > 0:
                            total_width += (GAP_INTER - GAP_INTRA)
                        
                        nx = rx - total_width
                        ny = ry
                    
                    self.logger.info(f"[Scroll] Phase 2 Tiles: CC={p1_tiles}, Heroes={p2_tiles}, Spells={p3_tiles} | Total Width: {total_width}")
                    self.logger.info(f"[Scroll] Calculated Start-X for Phase 2: {nx} (Backwards from {rx})")
                    
                    # Re-propagate remaining phases (1, 2, 3+)
                    original_remaining = copy.deepcopy(army["positions"][1:])
                    # Re-expand heroes in the original copy
                    if len(original_remaining) > 1 and num_heroes > 0:
                        h_list = original_remaining[1]
                        if len(h_list) >= 2:
                            # Use same logic to find how many template blocks to add
                            current_cfg_selects = get_select_count(h_list)
                            needed = num_heroes - current_cfg_selects
                            if needed > 0:
                                template = h_list[0:2]
                                for _ in range(needed):
                                    h_list.extend(copy.deepcopy(template))

                    army_positions_copy[1:] = propagate(original_remaining, nx, ny)

                self.logger.info("Executing Remaining Phases (Post-Scroll)...")
                # CC
                self.window_controller.execute_clicks(army_positions_copy[1], delay=delay)
                # Heroes
                self._deploy_and_activate_heroes(army_positions_copy[2], delay)
                # Spells
                for spell_list in army_positions_copy[3:]:
                    self.window_controller.execute_clicks(spell_list, delay=delay)

            self.logger.info("Attack finished")

        except Exception as e:
            self.logger.error(f"Failed in army_placement: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def _deploy_and_activate_heroes(self, heroes_pos, delay):
        """Helper to handle hero deployment and ability activation."""
        num_pairs = len(heroes_pos) // 2
        if num_pairs > 0:
            self.logger.info("Deploying Heroes...")
            for i in range(num_pairs):
                idx = i * 2
                self.window_controller.execute_clicks([heroes_pos[idx]], delay=delay)
                self.window_controller.execute_clicks([heroes_pos[idx+1]], delay=delay)
            time.sleep(3)
            self.logger.info("Activating Hero Abilities...")
            for i in range(num_pairs):
                self.window_controller.execute_clicks([heroes_pos[i * 2]], delay=delay)

        
        

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
        self.check_reload_needed()
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
                # get location of resource square (center of the region)
                x1, y1, x2, y2 = results[0]['pos']
                location = (x1 + x2) // 2, (y1 + y2) // 2
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
        # We want to ONLY click the pet building itself, not the old default button position
        if len(self.pet_building_position) > 0:
            # We take the first element (the building coordinate)
            building_pos = self.pet_building_position[-1]
            self.window_controller.execute_clicks([building_pos])
        else:
            self.logger.error("[Pet Test] No pet building position found.")
            sys.exit(1)
            
        time.sleep(2) # Wait for the menu to appear

        # Take a screenshot to find the "Pets" button in the menu
        screenshot_path = self.manage_screenshot_storage('pet_button_ocr')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        
        from utils.object_detection import detect_pet_button_with_mask
        pet_button_pos = detect_pet_button_with_mask(screenshot_path, self.logger)
        
        if pet_button_pos:
            self.window_controller.execute_clicks([pet_button_pos])
            time.sleep(2)
        else:
            self.logger.warning("[Pet] Could not find 'Pets' button via OCR. Falling back to default.")
            default_pet_button_position = self.hb_coords.get("default_pet_button_pos", [1088, 871])
            self.window_controller.execute_clicks([default_pet_button_position])
            time.sleep(2)

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



    


    

 

    
