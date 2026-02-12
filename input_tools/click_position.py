import os
import sys
import time

import keyboard  # To detect the 'Esc' key press
import toml
import win32api
import win32con

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.settings import logger


def get_mouse_position():
    """
    Get the current position of the mouse cursor.
    :return: A tuple (x, y) representing the mouse coordinates.
    """
    x, y = win32api.GetCursorPos()
    return x, y

def main():
    key_name = "default_click_positions"
    logger.info(f"Recording positions for key: '{key_name}'")
    logger.info("Move your mouse to the desired position and click LEFT mouse button to record it.")
    logger.info("Press the ESC key to stop and save the positions.\n")

    positions = []

    try:
        while True:
            # Check for left mouse button click
            if win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000:  # Left mouse button
                pos = get_mouse_position()
                positions.append(list(pos))  # Store as list for TOML compatibility
                logger.debug(f"Position recorded: {pos}")
                time.sleep(0.3)  # Debounce delay to prevent duplicate inputs

            # Check for Esc key press to exit
            if keyboard.is_pressed("esc"):
                logger.info("\nRecording stopped. Saved positions:")
                for idx, position in enumerate(positions):
                    logger.info(f"{idx + 1}: {position}")
                break
    except Exception as e:
        logger.error(f"An error occurred: {e}")

    # Save the positions to config.toml in the [ClickPositions] section
    config_path = "config.toml"
    if os.path.exists(config_path):
        config = toml.load(config_path)
    else:
        config = {}
    if "ClickPositions" not in config:
        config["ClickPositions"] = {}
    config["ClickPositions"][key_name] = positions
    with open(config_path, "w") as file:
        toml.dump(config, file)
    logger.info(f"\nPositions saved to '[ClickPositions].{key_name}' in '{config_path}'.")

if __name__ == "__main__":
    main()
