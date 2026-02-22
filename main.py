import os
import time
from datetime import datetime
from glob import glob

import cv2
import numpy as np

from utils import settings
from utils.clash_base import ClashBase
from utils.game_program_controller import GameProgramController
from utils.game_window_controller import GameWindowController
from utils.object_detection import detect_play_store_update_screen
from utils.settings import logger

# Setup Logging

# Define the file paths for the programs
GP_FILEPATH = settings.config["Filesystem"]["GooglePlayGamesBetaFilepath"]
GP_PROCESS = settings.config["Filesystem"]["GooglePlayGamesBetaProcessName"]
GP_PROCESS_DIR = settings.config["Filesystem"]["GooglePlayGamesBetaProcessDirectoryName"]
COC_FILEPATH = settings.config["Filesystem"]["ClashOfClansShortcutFilepath"]
switch_account_positions = settings.config["General"]["switch_account"]
update_button_position = settings.config["General"].get("update_button")



def check_for_update(window_controller):
    # take screenshot of screen
    # Use subfolder 'update_checks'
    save_dir = os.path.join('data', 'screenshots', 'update_checks')
    os.makedirs(save_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    image_path = os.path.join(save_dir, f'update_screen_{timestamp}.png')
    window_controller.capture_minimized_window_screenshot(image_path)
    # check for update
    update_screen = detect_play_store_update_screen(image_path)
    logger.debug(f"Update screen: {update_screen}")
    if update_screen:
        logger.info("Update screen found")
        return True
    return False

def main():
    """ ------------------------ Start Game -------------------------- """  

    # Create instance of the program controller
    program_controller = GameProgramController(logger)
    
    # Focus the Clash of Clans window
    window_title = "Clash of Clans"  
    
    def load_game():
        # First check if window is already open
        try:
            # If this succeeds, window exists
            wc = GameWindowController(window_title, logger)
            logger.debug(f"Window found ({wc.hwnd}). Assuming game is ready.")
            if check_for_update(wc):
                wc.execute_clicks([update_button_position])
                time.sleep(180)
            return wc
        except Exception:
            pass # Not found, proceed to launch

        logger.info("Clash of Clans not found, starting programs...")
        logger.info("Starting Google Play Games...")
        program_controller.start_program(GP_FILEPATH)
        time.sleep(10)
        
        logger.info("Starting Clash of Clans...")
        program_controller.start_program(COC_FILEPATH)

        logger.info("Waiting for Clash of Clans window to appear...")
        while True:
            try:
                GameWindowController(window_title, logger)
                logger.info("Window detected!")
                break
            except Exception:
                time.sleep(1)
        
        logger.info("Window found. Waiting 20 seconds for game initialization...")
        time.sleep(20)

        wc = GameWindowController(window_title, logger)
        
        if check_for_update(wc):
             wc.execute_clicks([update_button_position])
             logger.info("Update clicked. Waiting 180s...")
             time.sleep(180)
        return wc
    # load game
    window_controller = load_game()
    
    
    
    """ ------------------------ Automate Game -------------------------- """   

    # Detect all config files in utils/baseconfig/config
    config_dir = os.path.join("utils", "baseconfig")
    config_files = [
        f for f in glob(os.path.join(config_dir, "baseconfig_*.toml"))
        if not f.endswith("baseconfig_template.toml") 
    ]
    
    # Create a ClashBase instance for each config file, passing both actions
    bases = [ClashBase(config_path, window_controller, logger) for config_path in config_files]
    logger.info(f"Loaded {len(bases)} base configs:")
    for base in bases: 
        logger.info(f"- {base.name}") 

    ranked_mode = False
    lower_trophy_count = False
    fill_storage = True

    # iterate through each base twice
    for i in range(len(bases)):
        # iterate through each base    
        for idx, base in enumerate(bases):
            if idx == 0:
                logger.info("Switching to first account...")
                base.homebase_actions.reset_select()
                base.homebase_actions.reset_select()
                # copy switch_account_positions 
                switch_account_positions_copy = switch_account_positions.copy()
                # switch to first account
                
                # Use scaled offset from config
                scaled_offset = settings.config.get("General", {}).get("account_switch_y_offset", 110)
                
                account_position = [ switch_account_positions_copy[-1][0],  switch_account_positions_copy[-1][1] - (scaled_offset) ]
                switch_account_positions_copy.pop(-1) 
                switch_account_positions_copy.append(account_position)
                window_controller.execute_clicks(switch_account_positions_copy)
                # wait for account to load
                time.sleep(10)
            
            """ ------------------------ Home Base -------------------------- """

            
            base.homebase_actions.reset_select()
            base.builderbase_actions.reset_select()
            
            
            # determine if home base or builder base
            if base.current_location() == 'Builder':
                logger.info("Current Location: Builder base")
                base.builderbase_actions.switch_to_home_base() 
            else:
                logger.info("Current Location: Home base")

            # reset camera position
            logger.info("Resetting camera position...")
            base.homebase_actions.reset_camera_position()

            # Execute the resource collection task  
            logger.info("Executing resource collection...")
            base.homebase_actions.execute_resource_collection()

            # check if builder or research upgrade is available
            logger.info("Checking for builder or research upgrade...")
            if base.homebase_actions.check_builder_upgrade() > 0 or base.homebase_actions.check_laboratory_upgrade() > 0 or fill_storage:
                # check available heros
                available_heros = 0
                # if thl >= 7, check available heros
                logger.info("Checking available heros...")
                if base.homebase_actions.thl >= 7:
                    available_heros = base.homebase_actions.check_heros()
                # upgrade walls
                logger.info("Upgrading walls...")
                # base.homebase_actions.upgrade_walls()
                # get max resources through attacking and builder upgrades
                logger.info("Starting attack loop...")
                base.homebase_actions.main_attack_loop(available_heros, ranked_mode, fill_storage)
            
            # if thl >= 3, start laboratory upgrade
            logger.info("Checking for laboratory upgrade...")
            if base.homebase_actions.thl >= 3:
                base.homebase_actions.start_laboratory_upgrade()
            # if thl >= 10, start apprentices
            logger.info("Checking for apprentices upgrade...")
            if base.homebase_actions.thl >= 9:
                base.homebase_actions.start_apprentices()
            # if thl >= 15, start pet upgrade
            logger.info("Checking for pet upgrade...")
            if base.homebase_actions.thl >= 14:
                base.homebase_actions.start_pet_upgrade()


            """ ------------------------ Builder Base -------------------------- """
            # switch to builder base
            logger.info("Switching to builder base...")
            base.homebase_actions.switch_builder_base()

            # reset select and camera position
            logger.info("Resetting camera position...")
            base.builderbase_actions.reset_select()
            base.builderbase_actions.reset_camera_position()
            # execute resource collection
            logger.info("Executing resource collection...")
            base.builderbase_actions.execute_resource_collection()

            # check available heros
            available_heros = 1
            # logger.info("Checking available heros...")
            available_heros = base.builderbase_actions.check_heros()

            # lower trophy count
            if lower_trophy_count:
                logger.info("Lowering trophy count...")
                base.builderbase_actions.lower_trophy_count()

            # check if builder or research upgrade is available
            logger.info("Checking for builder or research upgrade...")
            if base.builderbase_actions.check_builder_upgrade() > 0 or base.builderbase_actions.check_laboratory_upgrade() or fill_storage:
                # get max resources through attacking and builder upgrades
                logger.info("Starting attack loop...")
                base.builderbase_actions.main_attack_loop(available_heros, fill_storage)




            """ ------------------------ Switch Accounts -------------------------- """
            # switch account
            if len(bases) > idx + 1:
                # copy switch_account_positions 
                switch_account_positions_copy = switch_account_positions.copy()
                logger.info(f"Switching to account {idx + 2}")
                
                # Use scaled offset from config
                scaled_offset = settings.config.get("General", {}).get("account_switch_y_offset", 110)
                
                account_position = [ switch_account_positions_copy[-1][0],  switch_account_positions_copy[-1][1] + (idx * scaled_offset) ]
                switch_account_positions_copy.pop(-1)
                switch_account_positions_copy.append(account_position)
                logger.info(f"Switching to account {idx + 2} at position {account_position}")
                
                 # Draw Circle
                base.homebase_actions.annotate_coords_on_image([account_position])
                window_controller.execute_clicks(switch_account_positions_copy)
                # wait for account to load
                time.sleep(20)
            # go back to main home base
            else:
                logger.info("No more accounts to switch to")
                
                # Use scaled offset from config
                scaled_offset = settings.config.get("General", {}).get("account_switch_y_offset", 110)
                
                account_position = [ switch_account_positions[-1][0],  switch_account_positions[-1][1] - (scaled_offset) ]
                switch_account_positions.pop(-1) 
                switch_account_positions.append(account_position)
                window_controller.execute_clicks(switch_account_positions)
                # wait for account to load
                time.sleep(20)


    """ ------------------------ Stop Game -------------------------- """    
    
    # Stop the programs after actions are complete
    program_controller.stop_program(GP_PROCESS, GP_PROCESS_DIR)

    logger.info("Automation complete.")

if __name__ == "__main__":
    main()
