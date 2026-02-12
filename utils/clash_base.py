import os
from datetime import datetime

import toml
from screeninfo import get_monitors

from .builder_base_actions import BuilderBaseActions
from .home_base_actions import HomeBaseActions
from .object_detection import *
from .object_detection import determine_base_location


class ClashBase:
    def __init__(self, config_path, window_controller, logger):
        self.logger = logger
        self.logger.debug(f"ClashBase initialized with config_path: {config_path}")
        self.config = self.load_config(config_path)
        self.window_controller = window_controller
        self.name = self.config.get("General", {}).get("name") or os.path.basename(config_path).split(".")[0]
        self.homebase_actions = HomeBaseActions(window_controller, self.config, self.logger) 
        self.builderbase_actions = BuilderBaseActions(window_controller, self.config, self.logger)
    
    def _deep_merge(self, base, override):
        # Recursively merge two dicts: values in override take precedence.
        if not isinstance(base, dict) or not isinstance(override, dict):
            return override if override is not None else base
        merged = dict(base)
        for key, override_value in override.items():
            base_value = base.get(key)
            if isinstance(base_value, dict) and isinstance(override_value, dict):
                merged[key] = self._deep_merge(base_value, override_value)
            else:
                # For lists and scalars, override entirely
                merged[key] = override_value
        return merged

    def load_config(self, path):
        # Load a default template and deep-merge with the specific base config so
        # static click positions only need to live in one place.
        import utils.settings as settings
        defaults = {}
        try:
            # Use the already loaded and scaled config from settings as the base
            if settings.config:
                 defaults = settings.config.copy()
            else:
                 self.logger.warning("Settings config is empty, loading from disk (unscaled)")
                 current_dir = os.path.dirname(os.path.abspath(__file__))
                 static_path = os.path.join(current_dir, 'baseconfig', 'static_config.toml')
                 if os.path.exists(static_path):
                    with open(static_path, 'r') as sf:
                        static_conf = toml.load(sf)
                        defaults = static_conf
                    
        except Exception as e:
            self.logger.error(f"Error loading defaults/static: {e}")
            defaults = {}

        # 3. Load Specific Base Config
        with open(path, 'r') as f:
            specific = toml.load(f)

        # Detect if specific config uses percentages (heuristic: found a value <= 1.0 in attacks/positions)
        uses_percentages = False
        def check_percentages(data):
            if isinstance(data, dict):
                for k, v in data.items():
                    if check_percentages(v): return True
            elif isinstance(data, list):
                for item in data:
                    if check_percentages(item): return True
            elif isinstance(data, (float)) and 0 < data <= 1.0:
                return True
            return False

        # Only check relevant sections to avoid false positives in random settings
        for section in ["HomeBaseAttacks", "BuilderBaseAttacks", "HomeBaseDynamicClickPositions", "BuilderBaseDynamicClickPositions"]:
             if section in specific:
                 if check_percentages(specific[section]):
                     uses_percentages = True
                     break
        
        if uses_percentages:
             w, h = settings.get_target_resolution(self.logger)
             self.logger.debug(f"Detected percentage-based specific config. Scaling to {w}x{h}...")
             settings.scale_config(specific, w, h)

        if defaults:
            return self._deep_merge(defaults, specific)
        return specific
        
    def current_location(self):
        self.logger.info("Determining current base location...")
        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        save_dir = os.path.join('data', 'screenshots', 'base_location_check')
        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        screenshot_path = os.path.join(save_dir, f'base_location_{timestamp}.png')
        self.window_controller.capture_minimized_window_screenshot(screenshot_path)
        is_builder_base, is_home_base = determine_base_location(screenshot_path)
        if is_builder_base:
            return 'Builder'
        elif is_home_base:
            return 'Home'
        else:
            self.logger.warning("Unknown base detected")
            return 'Unknown'

        
    
