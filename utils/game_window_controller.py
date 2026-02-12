import ctypes
import os
import time
from ctypes import wintypes
from datetime import datetime

import cv2
import win32con
import win32gui
import win32ui
from PIL import Image, ImageGrab

from utils.settings import logger

# Setup Logging
# logger = Logger(level="DEBUG").get_logger()


class GameWindowController:
    def __init__(self, window_title, logger_instance=None):
        self.logger = logger_instance if logger_instance else logger
        self.window_title = window_title
        self.hwnd = self.find_window(window_title)
        self.child_hwnd = self.find_input_child(self.hwnd)
        
        if self.child_hwnd:
            self.logger.debug(f"GameWindowController: Found Input Child Window (Handle: {self.child_hwnd})")
        else:
            self.logger.warning("GameWindowController: WARNING - Input Child Window (CROSVM) not found. Background inputs may fail.")
            self.child_hwnd = self.hwnd # Fallback

    def find_input_child(self, parent_hwnd):
        """
        Finds the child window responsible for receiving input (e.g. CROSVM class for Google Play Games).
        """
        found_child = []
        def enum_child_cb(hwnd, _):
            cls_name = win32gui.GetClassName(hwnd)
            if "CROSVM" in cls_name.upper():
                found_child.append(hwnd)
        
        try:
            win32gui.EnumChildWindows(parent_hwnd, enum_child_cb, None)
        except Exception as e:
            self.logger.error(f"Error enumerating children: {e}")
            
        return found_child[0] if found_child else None

    def find_window(self, window_title):
        """
        Finds and returns the window handle (hwnd) for the given window title (partial, case-insensitive).
        :param window_title: The title (or part of it) of the window to focus.
        :return: Window handle (hwnd).
        """
        def enum_windows_callback(hwnd, result):
            if win32gui.IsWindowVisible(hwnd): # Check visibility
                title = win32gui.GetWindowText(hwnd)
                if window_title.lower() in title.lower():
                    result.append(hwnd)
        result = []
        win32gui.EnumWindows(enum_windows_callback, result)
        if not result:
            raise Exception(f"Window with title containing '{window_title}' not found.")
        return result[0]

    def is_window_open(self, window_title):
        """
        Checks if a window with the given title is currently open.
        :param window_title: The title (or part of it) of the window to check.
        :return: True if window is open, False otherwise.
        """
        def enum_windows_callback(hwnd, result):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if window_title.lower() in title.lower():
                    result.append(hwnd)
        result = []
        win32gui.EnumWindows(enum_windows_callback, result)
        return len(result) > 0

    def wait_for_window(self, window_title, timeout=30, poll_interval=1):
        """
        Waits for a window with the given title (partial, case-insensitive) to appear, up to a timeout.
        :param window_title: The title (or part of it) of the window to wait for.
        :param timeout: Maximum time to wait in seconds.
        :param poll_interval: Time between checks in seconds.
        :return: Window handle (hwnd) if found, else raises Exception.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                hwnd = self.find_window(window_title)
                return hwnd
            except Exception:
                time.sleep(poll_interval)
        raise Exception(f"Window with title containing '{window_title}' not found after {timeout} seconds.")

    def click_in_window(self, x, y):
        """
        Sends a mouse click event to a specific window at the given coordinates (x, y).
        Targets the Child Input Window (CROSVM) if available.
        """
        # Calculate lparam: pack x and y coordinates into a single value
        lparam = (y << 16) | x  # Packs y into the high word and x into the low word
        target_hwnd = self.child_hwnd if self.child_hwnd else self.hwnd

        # Send mouse down event
        win32gui.PostMessage(target_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
        # Send mouse up event
        win32gui.PostMessage(target_hwnd, win32con.WM_LBUTTONUP, 0, lparam)
        # print(f"Clicked {target_hwnd} at position ({x}, {y})")

    def move_mouse_in_window(self, x, y):
        """
        Moves the mouse cursor to the specified (x, y) position within the window without clicking.
        """
        lparam = (y << 16) | x
        target_hwnd = self.child_hwnd if self.child_hwnd else self.hwnd
        win32gui.PostMessage(target_hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
        # print(f"Moved mouse in {target_hwnd} to ({x}, {y})")

    def read_positions(self, file_path):
        """
        Reads positions from a text file.
        :param file_path: Path to the text file containing positions.
        :return: A list of tuples with (x, y) coordinates.
        """
        positions = []
        try:
            with open(file_path, "r") as file:
                for line in file:
                    x, y = map(int, line.strip().split(","))
                    positions.append((x, y))
        except Exception as e:
            self.logger.error(f"Error reading positions: {e}")
        return positions

    def execute_clicks(self, positions, delay=1, verbose=False):
        """
        Executes mouse clicks at the given positions.
        :param positions: List of (x, y) coordinates.
        :param delay: Delay in seconds between each click.
        :param verbose: If True, prints the coordinates being clicked.
        """
        from utils.object_detection import gold_pass_trigger

        # print(f"clicked positions: {positions}")
        if len(positions) == 0:
            self.logger.warning("No positions to execute clicks for")
            return

        def check_gold_pass():
            # Capture screenshot to check for gold pass
            # Use a specific name to avoid spamming the main screenshot folder too much or use temp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            save_dir = os.path.join('data', 'screenshots', 'temp_images')
            os.makedirs(save_dir, exist_ok=True)
            check_path = os.path.join(save_dir, f'gp_check_{timestamp}.png')
            
            self.capture_minimized_window_screenshot(check_path)
            if os.path.exists(check_path):
                if gold_pass_trigger(check_path):
                    self.logger.critical("GOLD PASS TRIGGERED. EXITING NOW.")
                    import sys
                    sys.exit(0)
                # Cleanup temp image to save space? Optional.
                # os.remove(check_path) 

        if len(positions) == 2 and isinstance(positions[0], (int, float)):
            if verbose:
                self.logger.debug(f"Clicking at: {positions}")
            self.click_in_window(positions[0], positions[1])
            time.sleep(delay)
            # Check after click
            # check_gold_pass()
            return
        else:   
            for idx, (x, y) in enumerate(positions):
                if verbose:
                    self.logger.debug(f"Clicking at: ({x}, {y})")
                self.click_in_window(x, y)  # Use window controller for clicking
                time.sleep(delay)
                # Check after click
                # check_gold_pass()


    def scroll_wheel_up(self, times=10):
        """
        Scrolls the mouse wheel up in the window a specified number of times.
        """
        target_hwnd = self.child_hwnd if self.child_hwnd else self.hwnd
        for _ in range(times):
            win32gui.PostMessage(target_hwnd, win32con.WM_MOUSEWHEEL, 0x00780000, 0)
            time.sleep(0.05)

    def scroll_wheel_down(self, times=10):
        """
        Scrolls the mouse wheel down in the window a specified number of times.
        """
        target_hwnd = self.child_hwnd if self.child_hwnd else self.hwnd
        for _ in range(times):
            win32gui.PostMessage(target_hwnd, win32con.WM_MOUSEWHEEL, 0xff880000, 0)
            time.sleep(0.05)

    def capture_window_screenshot(self):
        """
        Captures a screenshot of the window and returns a PIL Image object.
        Uses ctypes and PrintWindow with flag 0 for better compatibility with visible windows.
        """
        import ctypes

        import win32ui
        from PIL import Image
        
        target_hwnd = self.child_hwnd if self.child_hwnd else self.hwnd
        
        left, top, right, bottom = win32gui.GetWindowRect(target_hwnd)
        width = right - left
        height = bottom - top

        # Restore and bring to the foreground (Only if targeting main window? Or specific logic needed?)
        # If we target child, do we need to restore parent? Yes probably.
        if win32gui.IsIconic(self.hwnd): # If minimized
             win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
        
        # win32gui.SetForegroundWindow(self.hwnd) # Optional, might steal focus

        hwnd_dc = win32gui.GetWindowDC(target_hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bitmap)

        # Use ctypes to access the PrintWindow function from user32.dll
        user32 = ctypes.windll.user32
        result = user32.PrintWindow(target_hwnd, save_dc.GetSafeHdc(), 0)

        img = None
        if result:
            # Convert the bitmap to a PIL Image
            bmpinfo = bitmap.GetInfo()
            bmpstr = bitmap.GetBitmapBits(True)
            img = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1)
        else:
            self.logger.error("Failed to capture the window. Ensure it's visible and accessible.")

        # Release resources
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(target_hwnd, hwnd_dc)
        win32gui.DeleteObject(bitmap.GetHandle())

        return img

    def capture_minimized_window_screenshot(self, output_file=None, read_back=True):
        """
        Captures a screenshot of the window even if it is minimized, using PrintWindow with flag 2.
        Saves the screenshot to output_file (default: data/screenshots/screenshot_TIMESTAMP.png) and returns a PIL Image object.
        If read_back is False, returns None instead of loading the image from disk (faster).
        """
        import os
        from datetime import datetime

        import win32con
        import win32gui
        import win32ui

        # Set default directory
        # Use a 'misc_captures' subfolder for unclassified screenshots
        save_dir = os.path.join('data', 'screenshots', 'misc_captures')
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        # Set default filename if not provided
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(save_dir, f'screenshot_{timestamp}.png')
        elif not os.path.isabs(output_file):
            output_file = os.path.join(output_file)
            
        target_hwnd = self.child_hwnd if self.child_hwnd else self.hwnd
        
        left, top, right, bottom = win32gui.GetWindowRect(target_hwnd)
        width = right - left
        height = bottom - top
        hwnd_dc = win32gui.GetWindowDC(target_hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bitmap)
        user32 = ctypes.windll.user32
        result = user32.PrintWindow(target_hwnd, save_dc.GetSafeHdc(), 2)
        if result:
            bitmap.SaveBitmapFile(save_dc, output_file)
        else:
            # Try restoring and capturing if minimized capture fails
            # Note: We must restore the PARENT hwnd (self.hwnd), not the child
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(1)
            result2 = user32.PrintWindow(target_hwnd, save_dc.GetSafeHdc(), 0)
            if result2:
                bitmap.SaveBitmapFile(save_dc, output_file)
            else:
                self.logger.error("Failed to capture screenshot even after restoring window.")
            win32gui.ShowWindow(self.hwnd, win32con.SW_MINIMIZE)
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(target_hwnd, hwnd_dc)
        win32gui.DeleteObject(bitmap.GetHandle())
        if not read_back:
            # Skip reading back, re-saving as PNG, and sleeping
            return None

        try:
            img = Image.open(output_file)
            # Validate size
            if img.width < 200 or img.height < 200:
                self.logger.warning(f"captured screenshot is suspiciously small ({img.width}x{img.height}). Window might be minimized to tray or invalid.")
                # Maybe return None or try again?
                # For now let's just warn, but saving it back might be useless.
            img.save(output_file, "PNG")
            time.sleep(.25)
            return img
        except Exception as e:
            self.logger.error(f"Could not convert screenshot to PNG: {e}")
            return None

    def drag_in_window(self, x1, y1, x2, y2, delay=0.5, steps=200):
        """
        Simulates a mouse click-and-drag from (x1, y1) to (x2, y2) in the window using multiple midpoints.
        Targets the Child Input Window (CROSVM) if available.
        """
        lparam_start = (y1 << 16) | x1
        lparam_end = (y2 << 16) | x2
        target_hwnd = self.child_hwnd if self.child_hwnd else self.hwnd

        # Mouse down at start
        win32gui.PostMessage(target_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam_start)
        time.sleep(delay / (steps * 2))

        # Gradually move mouse through midpoints
        for i in range(1, steps):
            mid_x = int(x1 + (x2 - x1) * i / steps)
            mid_y = int(y1 + (y2 - y1) * i / steps)
            lparam_mid = (mid_y << 16) | mid_x
            win32gui.PostMessage(target_hwnd, win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, lparam_mid)
            time.sleep(delay / steps)

        # Mouse move to end
        win32gui.PostMessage(target_hwnd, win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, lparam_end)
        time.sleep(delay / (steps * 2))
        # Mouse up at end
        win32gui.PostMessage(target_hwnd, win32con.WM_LBUTTONUP, None, lparam_end)
        # print(f"Dragged from ({x1}, {y1}) to ({x2}, {y2}) in {target_hwnd}.")

    def valid_coordinate_debug(self, coordinate, folder_name="temp_images", label="Check Click"):
        """
        Creates a debug screenshot with the specified coordinate annotated.
        Useful for verifying if a coordinate is within bounds and targeting the correct UI element.
        
        :param coordinate: [x, y] or (x, y) coordinate to annotate.
        :param folder_name: Subfolder in data/screenshots/ to save the image (default: "temp_images").
        :param label: Text label to draw near the point.
        """
        try:
            debug_dir = os.path.join("data", "screenshots", folder_name)
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            screenshot_path = os.path.join(debug_dir, f"{folder_name}_{timestamp}.png")
            
            # Capture
            self.capture_minimized_window_screenshot(screenshot_path)
            
            # Annotate
            if os.path.exists(screenshot_path):
                 img = cv2.imread(screenshot_path)
                 if img is not None:
                     pt = (int(coordinate[0]), int(coordinate[1]))
                     
                     self.logger.debug(f"Annotating screenshot at {pt}. Image size: {img.shape}")
                     
                     # Draw Circle
                     cv2.circle(img, pt, 15, (0, 0, 255), 3) # Red circle
                     cv2.putText(img, label, (pt[0], pt[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
                     
                     cv2.imwrite(screenshot_path, img)
                     self.logger.debug(f"Saved debug screenshot to {screenshot_path}")
        except Exception as e:
            self.logger.error(f"Failed to save debug screenshot: {e}")
