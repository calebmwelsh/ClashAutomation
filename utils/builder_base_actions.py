import glob
import os
import time
from datetime import datetime

import cv2
import toml

from utils.base_actions import BaseActions
from utils.game_window_controller import GameWindowController
from utils.object_detection import *
from utils.object_detection import check_for_gold_warning
from utils.settings import config, logger
from utils.vision_utils import VisionUtils

# Setup Logging



class BuilderBaseActions(BaseActions):
    def __init__(self, window_controller: GameWindowController, config, logger_instance=None):
        super().__init__(window_controller, config, logger_instance if logger_instance else logger)

        # positions
        static_positions = self.config["BuilderBaseStaticClickPositions"]
        dynamic_positions = self.config["BuilderBaseDynamicClickPositions"]

        # general 
        self.thl = self.config["BuilderBaseGeneral"]["BHL"]
        
        # coords
        self.bb_coords = self.config.get("BuilderBaseCoordinates", {})
        self.coords = self.bb_coords
        self.colors = self.config.get("Colors", {})

        # reset positions
        self.reset_select_positions = static_positions["reset_select"]
        self.reset_camera_positions = static_positions["reset_camera"]

        # resource thresholds
        general_config = self.config["General"]

        # switch base positions
        self.switch_base_drag = static_positions["switch_base_drag"]
        self.switch_base_click = static_positions["switch_base_click"]
        
        # resource positions
        self.resource_positions = dynamic_positions["resource_collection"]
        self.claim_defense_reward_positions = static_positions["defense_reward"]

        # upgrade positions
        self.build_upgrade_positions = static_positions["build_upgrade"]
        self.research_upgrade_positions = static_positions["research_upgrade"]

        # attack positions
        self.train_army_button_position = static_positions["train_army_button"]
        self.start_attack_positions = static_positions["start_attack"]
        self.go_home_positions = static_positions["go_home"]

        # Attack armies dict
        attacks_config = config.get("BuilderBaseAttacks", {})
        self.attack_armies = {}
        for key, positions in attacks_config.items():
            self.attack_armies[key] = {
                "name": key.replace("_", " ").title(),
                "positions": positions
            }

               # For pet and raid loops, positions will be read dynamically as filenames are generated
        

    """ --------------------------- Reset and Click Functions --------------------------------- """


    def reset_select(self):
        """
        Executes clicks for the reset select positions (read once in __init__).
        """
        self.window_controller.execute_clicks(self.reset_select_positions)
        time.sleep(1)

    def reset_camera_position(self):
        """
        Executes a drag operation to reset the camera position.
        """
        self.window_controller.scroll_wheel_down(20)
        time.sleep(3)
        start_attack_positions = self.reset_camera_positions[:2]
        attack_positions = self.reset_camera_positions[2:4]
        leave_attack_positions = self.reset_camera_positions[4:]
        self.window_controller.execute_clicks(start_attack_positions)
        time.sleep(7)
        self.window_controller.execute_clicks(attack_positions)
        self.window_controller.scroll_wheel_down(20)
        self.window_controller.execute_clicks(leave_attack_positions)
        time.sleep(1)

    def switch_to_home_base(self):
        # reset select
        self.reset_select()
        # reset camera position
        self.reset_camera_position()
        # drag window to see home base boat
        self.window_controller.drag_in_window(*self.switch_base_drag)
        time.sleep(1)
        self.window_controller.execute_clicks(self.switch_base_click)
        time.sleep(1)



    """ --------------------------- Resource Functions --------------------------------- """
    def execute_resource_collection(self):
        # Read positions from the file (now from memory)
        positions = self.resource_positions
        # Execute clicks for each position
        self.logger.info("Executing resource collection...")
        self.window_controller.execute_clicks(positions)
        # claim defense reward
        self.window_controller.execute_clicks(self.claim_defense_reward_positions)
    
    def check_max_resources(self):
        """
        Captures a screenshot and detects if home base resources are maxed using color detection.
        Returns is_maxed True if both gold and elixir are maxed (color detected), else False.
        """
        screenshot_path = self.manage_screenshot_storage('builder_base_resource_stats')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        gold, elixir = extract_builder_resources(screenshot_path)
        self.logger.info(f"[Base Resources] Gold maxed: {gold}, Elixir maxed: {elixir}")
        is_maxed = gold == 1 and elixir == 1
        self.logger.info(f"[Base Resources] Gold or Elixir maxed: {is_maxed}")
        return is_maxed

    """ --------------------------- Attack Functions --------------------------------- """

    def check_heros(self):
        """
        Captures a screenshot and detects the number of available heroes using detect_heroes_available.
        Prints and returns the number of available heroes.
        """
        # select train army button
        self.window_controller.execute_clicks(self.train_army_button_position)
        time.sleep(1)
        
        screenshot_path = self.manage_screenshot_storage('builder_base_heros_status')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        available_heros = detect_heroes_available(screenshot_path)
        self.logger.info(f"[Builder Base Heros Status] Available heroes: {available_heros}")

        # reset select
        self.reset_select()

        return available_heros

    
    def army_placement(self, army_key=None, hero_count=1, delay=0.5):
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
        
        # scroll down
        self.window_controller.scroll_wheel_down(20)
        # execute clicks to place the army
        self.window_controller.execute_clicks(army["positions"], delay=delay)
        time.sleep(60)
        self.window_controller.execute_clicks(army["positions"], delay=delay)

    def start_attack(self, army_key=None, available_heros=0):
        """
        Starts an attack using the specified army key from self.attack_armies.
        :param army_key: String key for the army type (e.g., 'e_drag_rage_goblin').
        """
        self.reset_select()
        
        
        # Always click out just in case
        exit_click = self.bb_coords.get("gold_warning_exit_click", [1696, 395])
        self.window_controller.execute_clicks([exit_click, exit_click], delay=0.1)
        time.sleep(2)
            
        # start attack
        self.annotate_coords_on_image(self.start_attack_positions)
        self.window_controller.execute_clicks(self.start_attack_positions)
        # let the game load defenders base
        time.sleep(7)
        
        
        # Attack base
        self.logger.info("\n[Builder Base] Attacking base...")
        # Attack Type
        if army_key is None:
            army_key = self.attack_armies.keys()[0]
        army = self.attack_armies.get(army_key)
        if not army:
            raise ValueError(f"Army key '{army_key}' not found in attack_armies.")
        
        # Place the army
        self.army_placement(army_key, available_heros, delay=0.5)
        
        
        # delay for the attack to complete
        if not army_key == 'auto_lose':
            # Dynamic Wait for Battle End
            max_duration = 100
            
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

    def main_attack_loop(self, available_heros, fill_storage=False):
        while True:
            # check if resources are maxed
            if self.check_max_resources():
                break
            # start attack
            self.start_attack('main_attack', available_heros)
            # resource collection
            self.execute_resource_collection()
        
        # check for upgrades and if there are still builders available, start attack loop again to get full resources
        if self.start_builder_upgrade():
            self.main_attack_loop(available_heros)

        # get max resources again
        if fill_storage:
            while True:
                # check if resources are maxed
                if self.check_max_resources():
                    break
                # start attack
                self.start_attack('main_attack', available_heros)
                # resource collection
                self.execute_resource_collection()

    def lower_trophy_count(self):
        for i in range(20):
            # reset camera position
            self.reset_camera_position()
        

    """ --------------------------- Upgrade Functions --------------------------------- """

    def check_builder_upgrade(self):
        screenshot_path = self.manage_screenshot_storage('builder_base_builder_upgrade_character')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        # Check if a build is available
        builders_available = extract_builder_base_builders_available_from_image(screenshot_path)
        self.logger.info(f"[Builder Base Builders Available] Builders available: {builders_available}")
        if builders_available > 0:
            self.logger.info("Builder upgrade available")
            return builders_available
        else:
            self.logger.info("No builder upgrade available")
            return 0
        
    def check_builder_info_button(self):
        # get loc for upgrade button
        screenshot_path = self.manage_screenshot_storage('builder_base_info_button')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        # get info button location
        info_results = detect_info_button_color_location(screenshot_path)
        self.logger.debug(f"Info results: {info_results}")
        # if info button is found, get upgrade button location
        if info_results:
            top_right_info_button = [info_results[0]['pos'][0] + 78, info_results[0]['pos'][1] - 35, info_results[0]['pos'][2] + 74, info_results[0]['pos'][3] - 39]
            screenshot_path = self.manage_screenshot_storage('builder_base_upgrade_button')
            self.window_controller.capture_minimized_window_screenshot(screenshot_path)
            upgrade_results = detect_upgrade_button_color_location(screenshot_path, top_right_info_button)
            self.logger.debug(f"Upgrade results: {upgrade_results}")
            return upgrade_results
        else:
            self.logger.warning("No info button available")
            return None
        
    def start_builder_upgrade(self):
        # reset select
        self.reset_select()
        # check if builder upgrade is available
        num_builders = self.check_builder_upgrade()
        if num_builders > 0 and num_builders <= 2:
            self.logger.info("Starting builder upgrade...")
            # Select builder suggestions
            self.window_controller.execute_clicks(self.build_upgrade_positions[:1])
            # select building to upgrade
            for i in range(3):
                # get new y cord depending on the number of builders
                step_y = self.bb_coords.get("builder_upgrade_step_y", 42)
                new_cord = [self.build_upgrade_positions[1][0], self.build_upgrade_positions[1][1] - (step_y * i)]
                self.window_controller.execute_clicks(new_cord)
                self.annotate_coords_on_image([new_cord], name="builder_base_builder_selection_coords")

            # get loc for info button
            results = self.check_builder_info_button()
            self.logger.debug(f"Info button results: {results}")
            # if in resource square, get location of resource square
            if results:
                # get location of resource square
                location = results[0]['pos'][0], results[0]['pos'][1]
                self.logger.debug(f"Info button location: {location}")
                # selected upgrade and confirm
                self.window_controller.execute_clicks(location)
                self.window_controller.execute_clicks(self.build_upgrade_positions[-1])
                self.window_controller.execute_clicks(self.build_upgrade_positions[-2])
            else:
                self.logger.warning("No upgrade button available")
            
            # reset select
            self.reset_select()

            # check number of builders again
            num_builders = self.check_builder_upgrade()
            if num_builders > 0 and num_builders <= 2:
                self.logger.info("Another Builder upgrade available")
                return True
            else:
                self.logger.info("No builder upgrade available")
                return False
        else:
            self.logger.info("No builder upgrade available")
            return
        
    def check_laboratory_upgrade(self):
        screenshot_path = self.manage_screenshot_storage('builder_base_laboratory_upgrade')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        # Check if a build is available
        research_available = extract_builder_base_research_available_from_image(screenshot_path)
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
                step_y = self.bb_coords.get("research_upgrade_step_y", 30)
                new_cord = [self.research_upgrade_positions[1][0], self.research_upgrade_positions[1][1] - (step_y * _)]
                self.window_controller.execute_clicks(new_cord)
            # select research to upgrade
            self.window_controller.execute_clicks(self.research_upgrade_positions[2])
            # reset select
            self.reset_select()
            return True
        else:
            self.logger.info("No laboratory upgrade available")
            return False
        
   

 

    
