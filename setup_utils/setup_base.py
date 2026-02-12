import ast
import os
import re
import sys
import time
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keyboard
import toml
import win32api
import win32con

from utils import settings
from utils.game_program_controller import GameProgramController
from utils.game_window_controller import GameWindowController
from utils.object_detection import determine_base_location
from utils.settings import logger

""" --------------------------- Constants --------------------------------- """

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT_DIR, "utils", "baseconfig")
TEMPLATE_FILE = os.path.join(CONFIG_DIR, "baseconfig_template.toml")
STATIC_CONFIG_FILE = os.path.join(CONFIG_DIR, "static_config.toml")



# Define the file paths for the programs
GP_FILEPATH = settings.config["Filesystem"]["GooglePlayGamesBetaFilepath"]
GP_PROCESS = settings.config["Filesystem"]["GooglePlayGamesBetaProcessName"]
GP_PROCESS_DIR = settings.config["Filesystem"]["GooglePlayGamesBetaProcessDirectoryName"]
COC_FILEPATH = settings.config["Filesystem"]["ClashOfClansShortcutFilepath"]

# Focus the Clash of Clans window
window_title = "Clash of Clans"  

def ensure_game_running():
    program_controller = GameProgramController()
    
    def load_game():
        # First check if window is already open
        try:
            # If this succeeds, window exists
            wc = GameWindowController(window_title)
            logger.info(f"Window found ({wc.hwnd}). Assuming game is ready.")
            return wc
        except Exception:
            pass # Not found, proceed to launch

        print("Clash of Clans not found, starting programs...")
        print("Starting Google Play Games...")
        program_controller.start_program(GP_FILEPATH)
        # Small delay to let GP start launching
        time.sleep(2)
        
        print("Starting Clash of Clans...")
        program_controller.start_program(COC_FILEPATH)

        print("Waiting for Clash of Clans window to appear...")
        # Continuously check until found
        while True:
            try:
                # Try to connect
                GameWindowController(window_title)
                # If we get here, window exists
                logger.info("Window detected!")
                break
            except Exception:
                time.sleep(1)
        
        logger.info("Window found. Waiting 20 seconds for game initialization...")
        time.sleep(20)
        
        # Re-connect to ensure we capture the now-loaded Child Window (CROSVM)
        return GameWindowController(window_title)

    return load_game()

window_controller = ensure_game_running()
if not window_controller:
    raise Exception("Failed to start or connect to Clash of Clans.")


""" --------------------------- Mouse and Position Recording --------------------------------- """

def get_mouse_position():
    x, y = win32api.GetCursorPos()
    return x, y

def record_positions_for_field(field_name):
    logger.info(f"\nRecording positions for: '{field_name}'")
    logger.info("Move your mouse to the desired position and click LEFT mouse button to record it.")
    logger.info("Press the 'd' key to stop and save the positions for this field.\n")
    positions = []
    try:
        while True:
            if win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000:
                pos = get_mouse_position()
                positions.append(list(pos))
                logger.debug(f"Position recorded: {pos}")
                time.sleep(0.3)
            if keyboard.is_pressed("d"):
                logger.info(f"\nRecording stopped for '{field_name}'. Saved positions:")
                for idx, position in enumerate(positions):
                    logger.info(f"{idx + 1}: {position}")
                break
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    # Wait for 'd' key to be released before returning
    while keyboard.is_pressed("d"):
        time.sleep(0.05)
    time.sleep(0.2)
    return positions

""" --------------------------- File and Template Utilities --------------------------------- """

def get_next_config_filename():
    files = os.listdir(CONFIG_DIR)
    used_numbers = set()
    for f in files:
        m = re.match(r"baseconfig_(\d+)\.toml", f)
        if m:
            used_numbers.add(int(m.group(1)))
    next_num = 1
    while next_num in used_numbers:
        next_num += 1
    return os.path.join(CONFIG_DIR, f"baseconfig_{next_num}.toml")

def load_static_config():
    static_positions = {}
    builderbase_static_positions = {}
    
    if os.path.exists(STATIC_CONFIG_FILE):
        try:
            with open(STATIC_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = toml.load(f)
                static_positions = data.get('HomeBaseStaticClickPositions', {})
                builderbase_static_positions = data.get('BuilderBaseStaticClickPositions', {})
        except Exception as e:
            logger.error(f"Error loading static config: {e}")
            
    return static_positions, builderbase_static_positions

def parse_toml_template(template_path):
    sections = {}
    current_section = None
    with open(template_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line
                sections[current_section] = []
            elif current_section:
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    sections[current_section].append((key, value))
                    
    # Load static positions from separate file
    static_positions, builderbase_static_positions = load_static_config()
    
    return sections, static_positions, builderbase_static_positions

""" --------------------------- Camera Centering --------------------------------- """

def center_camera(static_positions):
    logger.info("Centering camera...")
    reset_select_positions = static_positions.get('reset_select', [])
    reset_camera_positions = static_positions.get('reset_camera', [])
    if reset_select_positions:
        window_controller.execute_clicks(reset_select_positions)
        window_controller.execute_clicks(reset_select_positions)
        time.sleep(1)
    if reset_camera_positions:
        window_controller.scroll_wheel_down(20)
        time.sleep(3)
        end_pos = reset_camera_positions[-1]
        window_controller.execute_clicks(reset_camera_positions[:-1])
        time.sleep(7)
        window_controller.execute_clicks([end_pos])

def center_camera_builder_base(static_positions):
    logger.info("Centering builder base camera...")
    reset_select_positions = static_positions.get('reset_select', [])
    reset_camera_positions = static_positions.get('reset_camera', [])
    if reset_select_positions:
        window_controller.execute_clicks(reset_select_positions)
        window_controller.execute_clicks(reset_select_positions)
        time.sleep(1)
    if reset_camera_positions:
        window_controller.scroll_wheel_down(20)
        time.sleep(3)
        start_attack_positions = reset_camera_positions[:2]
        attack_positions = reset_camera_positions[2:4]
        leave_attack_positions = reset_camera_positions[4:]
        window_controller.execute_clicks(start_attack_positions)
        time.sleep(7)
        window_controller.execute_clicks(attack_positions)
        window_controller.scroll_wheel_down(20)
        window_controller.execute_clicks(leave_attack_positions)

""" --------------------------- Example Attacks Loader --------------------------------- """

def load_example_attacks():
    example_path = os.path.join(CONFIG_DIR, "example_attacks_by_th.toml")
    attacks_by_th = {}
    attacks_by_bh = {}
    current_th = None
    current_bh = None
    with open(example_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[TH") and line.endswith("]"):
                current_th = int(line[3:-1])
                current_bh = None
            elif line.startswith("[BH") and line.endswith("]"):
                current_bh = int(line[3:-1])
                current_th = None
            elif line.startswith("attacks"):
                eq = line.find("=")
                if eq != -1:
                    value = line[eq+1:].strip()
                    # Read multiline attacks
                    if value.startswith("[") and not value.endswith("]"):
                        multiline = value
                        while not multiline.endswith("]"):
                            next_line = next(f).strip()
                            multiline += " " + next_line
                        value = multiline
                    try:
                        parsed_value = ast.literal_eval(value)
                    except Exception as e:
                        logger.error(f"Error parsing attacks for TH/BH {current_th or current_bh}: {e}\nValue: {value}")
                        parsed_value = []
                    if current_th is not None:
                        attacks_by_th[current_th] = parsed_value
                    elif current_bh is not None:
                        attacks_by_bh[current_bh] = parsed_value
    return attacks_by_th, attacks_by_bh


""" --------------------------- Switch Builder Base --------------------------------- """

def check_current_base(window_controller):
    timestamp = str(int(time.time()))
    screenshot_path = os.path.join('data', 'screenshots', f'setup_check_base_{timestamp}.png')
    window_controller.capture_minimized_window_screenshot(screenshot_path)
    is_builder, is_home = determine_base_location(screenshot_path)
    
    # Construct expected path of the debug image created by determine_base_location
    annotated_path = screenshot_path.replace(".png", "_point_1669_149_annotated.png")
    logger.debug(f"DEBUG: Visual check saved to: {annotated_path}")
    
    logger.debug(f"DEBUG: determine_base_location returned: Builder={is_builder}, Home={is_home}")
    return is_builder, is_home

def switch_to_builder_base(static_positions):
    logger.info("Checking current base location...")
    is_builder, is_home = check_current_base(window_controller)
    
    if is_builder:
        logger.info("Already at Builder Base.")
        return

    logger.info("Switching to builder base...")
    switch_positions = static_positions.get('switch_builder_base', [])
    if switch_positions:
        window_controller.execute_clicks(switch_positions)
        time.sleep(4) # Wait for boat travel

""" --------------------------- User Prompt and Config Generation --------------------------------- """


def switch_to_home_base(static_positions):
    # This was a placeholder in previous steps, now unused? 
    # prompt_for_values calls ensure_home_base_state mostly.
    pass

def switch_from_builder_to_home(window_controller, builder_static):
    # Replicates BuilderBaseActions.switch_to_home_base
    logger.info("Switching from Builder to Home...")
    reset_pos = builder_static.get('reset_select', [])
    if reset_pos: window_controller.execute_clicks(reset_pos)
    
    # We can't easily call reset_camera_position without knowing if we are there, 
    # but we can try generic scroll down
    window_controller.scroll_wheel_down(20)
    time.sleep(1)
    
    # Drag
    drag = builder_static.get('switch_base_drag')
    click = builder_static.get('switch_base_click')
    
    if drag and click:
        window_controller.drag_in_window(*drag)
        time.sleep(1)
        window_controller.execute_clicks(click)
        time.sleep(4) # Wait for travel
    else:
        logger.warning("Warning: Missing switch_base_drag/click in static config for builder base.")

def ensure_home_base_state(window_controller, home_static, builder_static):
    logger.info("Checking current base location...")
    is_builder, is_home = check_current_base(window_controller)
    logger.debug(f"DEBUG: Base State -> Builder: {is_builder}, Home: {is_home}")
    
    if is_builder:
        if builder_static:
            switch_from_builder_to_home(window_controller, builder_static)
        else:
            logger.warning("Warning: Cannot switch to Home Base (missing Builder Static Config).")
            
    elif not is_home:
        logger.warning("WARNING: Could not identify base (Unknown). Assuming we might need to switch or check manually.")
        # Optional: Try to switch anyway if we suspect we are in Builder?
        # But for now just warn.
    
    else:
        logger.info("Confirmed at Home Base.")
            
    # If we are effectively at home (or switched to it), center camera
    center_camera(home_static)


def prompt_for_values(sections, static_positions, builderbase_static_positions=None):
    user_sections = {}
    th_level = None
    bh_level = None
    attacks_by_th, attacks_by_bh = load_example_attacks()

    # Create a tempoary window controller for executing switch/center commands
    # We rely on the global window_controller initialized at startup.
    
    # 1. Process General/HomeBaseGeneral/BuilderBaseGeneral first to get Levels
    for section_name in ['[General]', '[HomeBaseGeneral]', '[BuilderBaseGeneral]']:
        if section_name in sections:
            items = sections[section_name]
            temp_items = []
            logger.info(f"\nScanning section: {section_name}")
            for key, value in items:
                default = value.strip('"')
                
                # Special prompt for Levels
                if key == 'THL':
                    user_input = input(f"  {key} (default: {default}): ")
                    if user_input == "":
                        th_level = int(default) if default.isdigit() else None
                        temp_items.append((key, default))
                    else:
                        th_level = int(user_input)
                        temp_items.append((key, user_input))
                elif key == 'BHL':
                    user_input = input(f"  {key} (default: {default}): ")
                    if user_input == "":
                        bh_level = int(default) if default.isdigit() else None
                        temp_items.append((key, default))
                    else:
                        bh_level = int(user_input)
                        temp_items.append((key, user_input))
                else:
                    user_input = input(f"  {key} (default: {default}): ")
                    if user_input == "":
                        temp_items.append((key, default))
                    else:
                        temp_items.append((key, user_input))
            user_sections[section_name] = temp_items

    # 2. Process remaining sections (Attacks, Dynamic Positions)
    for section, items in sections.items():
        if section in ['[General]', '[HomeBaseGeneral]', '[BuilderBaseGeneral]']:
            continue
            
        print(f"\nProcessing section: {section}")
        user_sections[section] = []

        # -- Skip Builder Base sections if TH < 6 --
        if section.startswith('[BuilderBase') and (th_level is not None and th_level < 6):
            logger.info(f"Skipping {section} (TH Level {th_level} < 6)")
            for key, value in items:
                 user_sections[section].append((key, value if value else ""))
            continue
            
        # -- Dynamic Positions (Click Recording) --
        if 'DynamicClickPositions' in section:
            # Handle Camera Centering and Base Switching
            if section == '[HomeBaseDynamicClickPositions]':
                logger.info("Ensuring Home Base and resetting camera...")
                # If we have builder static positions, we can try to switch back from builder if needed.
                # But mostly we assume we start at Home. 
                # If the user was previously at Builder Base (from previous section), we MUST switch back.
                ensure_home_base_state(window_controller, static_positions, builderbase_static_positions)
                
            elif section == '[BuilderBaseDynamicClickPositions]': 
                 if builderbase_static_positions:
                     logger.info("Switching to Builder Base and resetting camera...")
                     switch_to_builder_base(static_positions) # Switch actions from Home static
                     center_camera_builder_base(builderbase_static_positions)

            for key, value in items:
                # Skip advanced buildings for low levels
                if key == 'pet_building' and (th_level is None or th_level < 14):
                    user_sections[section].append((key, ""))
                    continue
                if key == 'apprentice_building' and (th_level is None or th_level < 10):
                     user_sections[section].append((key, ""))
                     continue

                # Record Positions
                logger.info(f"preparing to record {key}")
                if key == "resource_collection":
                     logger.info("Please click on each resource building. Press 'd' to stop.")
                
                # Reset camera before EACH field coordinate recording?
                # User asked: "make sure we do a camera reset before recording these coordinates"
                # If we do it once per section, is it enough?
                # "coordinates might be variable... need to make sure we do a camera reset before recording"
                # If the user moves the camera to find the building, the next building's coords will be wrong if we don't reset.
                # BUT if we reset, the user loses their view of the building they just found?
                # No, the flow is: 
                # 1. Reset Camera (Standard View)
                # 2. User sees building
                # 3. User clicks building
                # If the building is off-screen (zoomed out max), then the user CANNOT click it without panning.
                # If CoC zoomed out view shows everything, then no need to pan.
                # Assuming Reset Camera gives a view of the whole base.
                # So we SHOULD reset before each recording session if there are multiple.
                
                # But 'record_positions_for_field' records a list of clicks.
                # If we reset before calling it, that's good.
                # We are inside the loop over keys. So for each key (building type), we reset.


                positions = record_positions_for_field(f"{key} ({section})")
                if positions:
                    user_sections[section].append((key, str(positions)))
                else:
                    user_sections[section].append((key, value if value else ""))
            continue


        # -- Attacks --
        if 'Attacks' in section:
             for key, value in items:
                default = value
                # Auto-fill main_attack from examples
                if key == 'main_attack':
                     if section.startswith('[BuilderBase') and bh_level in attacks_by_bh:
                         default = attacks_by_bh[bh_level]
                     elif not section.startswith('[BuilderBase') and th_level in attacks_by_th:
                         default = attacks_by_th[th_level]
                
                # Convert list to string for display if needed, but we keep it raw for writing?
                # The writer expects python objects or strings.
                
                user_input = input(f"  {key} (default: {default}): ")
                if user_input == "":
                    user_sections[section].append((key, default))
                else:
                    user_sections[section].append((key, user_input))
             continue

        # -- Fallback for any other fields --
        for key, value in items:
            default = value.strip('"')
            user_input = input(f"  {key} (default: {default}): ")
            user_sections[section].append((key, user_input if user_input else default))
            
    return user_sections

""" --------------------------- TOML Writing --------------------------------- """

def write_toml_file(filename, user_sections):
    with open(filename, "w", encoding="utf-8") as f:
        for section, items in user_sections.items():
            f.write(f"{section}\n")
            for key, value in items:
                if value == "" or value is None:
                    f.write(f"{key} = \n")
                elif isinstance(value, list):
                    f.write(f"{key} = {repr(value)}\n")
                elif isinstance(value, str) and value.startswith("[") and value.endswith("]"):
                    f.write(f"{key} = {value}\n")
                elif isinstance(value, str) and value.isdigit():
                    f.write(f"{key} = {value}\n")
                else:
                    f.write(f'{key} = "{value}"\n')
            f.write("\n")

""" --------------------------- Main Entrypoint --------------------------------- """

def main(logger_instance=None):
    global logger
    if logger_instance:
        logger = logger_instance
        
    logger.info("--- Clash Automation Base Config Setup ---")
    sections, static_positions, builderbase_static_positions = parse_toml_template(TEMPLATE_FILE)
    user_sections = prompt_for_values(sections, static_positions, builderbase_static_positions)
    filename = get_next_config_filename()
    logger.info(f"New config will be saved as: {filename}")
    write_toml_file(filename, user_sections)
    logger.info(f"Config saved to {filename}")

if __name__ == "__main__":
    main() 


